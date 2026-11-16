import json
import os
import subprocess
import sys
import tempfile
import uuid
import threading
from contextlib import asynccontextmanager
from functools import lru_cache
from datetime import date
from pathlib import Path
from typing import Annotated
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel, Field, model_validator
from . import store
from .data import datasets, load_dataset

processes = {}
submit_lock = threading.Lock()
@asynccontextmanager
async def lifespan(app):
    store.recover()
    yield
    for identifier, process in processes.items():
        if process.poll() is None:
            store.update(identifier,"cancelled")
            process.terminate()
            process.wait(timeout=10)

app = FastAPI(title="주식 전략 연구실 · Local API", lifespan=lifespan)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1","localhost","testserver"])

@app.middleware("http")
async def local_only(request: Request, call_next):
    from fastapi.responses import JSONResponse
    origin = request.headers.get("origin")
    allowed = ["http://127.0.0.1:5173","http://localhost:5173","http://127.0.0.1:8000","http://localhost:8000"]
    if origin and origin not in allowed:
        return JSONResponse({"detail":"허용되지 않은 Origin"},status_code=403)
    if request.method in ("POST","DELETE") and request.headers.get("x-research-local") != "1":
        return JSONResponse({"detail":"로컬 실행 헤더가 필요합니다."},status_code=403)
    return await call_next(request)

class Period(BaseModel):
    dataset_id: str = Field(pattern=r"^[a-f0-9]{20}$")
    start: date
    end: date
    capital: float = Field(default=1000000,ge=1000,le=1e10)
    fee: float = Field(default=.00015,ge=0,le=.05)
    tax: float = Field(default=0,ge=0,le=.05)
    slippage: float = Field(default=.0005,ge=0,le=.05)
    @model_validator(mode="after")
    def check_dates(self):
        if self.start >= self.end: raise ValueError("시작일은 종료일보다 빨라야 합니다.")
        return self

class RunConfig(Period):
    strategy: str
    seed: int = Field(default=42,ge=0,le=2147483647)
    ma_window: int = Field(default=20,ge=2,le=250)
    params: dict[str, float] = Field(default_factory=dict)
    @model_validator(mode="after")
    def check_strategy(self):
        from .strategies import resolve
        resolve(self.strategy,self.params,self.ma_window)  # unknown strategy/params, ranges, short<long...
        return self

def check_range(period: Period):
    """422 unless the period lies inside the saved data and spans at least 10 trading days."""
    try:
        frame, meta = load_dataset(period.dataset_id)
        if str(period.start)<meta["start"] or str(period.end)>meta["end"]:
            raise ValueError(f"확보 기간 {meta['start']} ~ {meta['end']} 안에서 선택하세요.")
        if ((frame.date >= str(period.start)) & (frame.date <= str(period.end))).sum() < 10:
            raise ValueError("평가 기간에는 최소 10개의 거래일이 필요합니다.")
    except ValueError as e: raise HTTPException(422,str(e))

@app.get("/api/datasets")
def dataset_list(): return datasets()

@lru_cache(maxsize=1024)
def run_metrics(identifier):
    # Completed result files are replaced atomically before the status flips, then never change.
    try: return json.loads(store.result_path(identifier).read_text(encoding="utf-8")).get("metrics")
    except (OSError, ValueError): return None

@app.get("/api/runs")
def runs():
    jobs = store.listing()
    for job in jobs:
        if job["status"] == "completed": job["metrics"] = run_metrics(job["id"])
    return jobs

@app.post("/api/runs", status_code=202)
def submit(config: RunConfig):
    with submit_lock:
        return _submit(config)

def _submit(config: RunConfig):
    active = sum(p.poll() is None for p in processes.values())
    if active >= 2: raise HTTPException(429,"동시 작업은 최대 2개입니다.")
    check_range(config)
    identifier = uuid.uuid4().hex
    store.create(identifier,config.model_dump(mode="json"))
    try:
        processes[identifier] = subprocess.Popen([sys.executable,"-m","lab.worker",identifier])
    except Exception:
        store.update(identifier,"failed","작업자 시작 실패")
        raise HTTPException(500,"작업자 시작 실패")
    def monitor():
        process = processes[identifier]
        try:
            process.wait(timeout=600)
            if process.returncode and store.get(identifier)["status"] in ["queued","running"]:
                store.update(identifier,"failed","작업자가 비정상 종료되었습니다.")
        except subprocess.TimeoutExpired:
            store.update(identifier,"failed","로컬 작업 시간 제한 600초 초과")
            process.terminate()
            process.wait(timeout=10)
    threading.Thread(target=monitor,daemon=True).start()
    return store.get(identifier)

@app.get("/api/strategies")
def strategy_catalog():
    from .strategies import catalog
    return catalog()

def summarize(config):
    """Metrics, round-trip count and win rate of one backtest, or why it could not run."""
    from .engine import round_trips, run
    try:
        pnl = round_trips((result := run(config))["trades"])
        return dict(metrics=result["metrics"], trips=len(pnl), win_rate=sum(p > 0 for p in pnl)/len(pnl) if pnl else None, error=None)
    except ValueError as e:
        return dict(metrics=None, trips=0, win_rate=None, error=str(e))

@app.post("/api/compare")
def compare(period: Period):
    """Every strategy with default settings on one period. In-process: ~11 short backtests."""
    from .strategies import STRATEGIES
    check_range(period)
    return [dict(strategy=key, label=spec["label"], group=spec["group"], **summarize(dict(period.model_dump(mode="json"), strategy=key)))
            for key, spec in STRATEGIES.items()]

GRID_LIMIT, MANIFEST_LIMIT = 200, 50000  # in-process vs. a manifest for lab.benchmark / lab.cloud

class Grid(Period):
    strategy: str
    grid: dict[str, list[float]] = Field(min_length=1, max_length=6)
    @model_validator(mode="after")
    def check_grid(self):
        from .strategies import STRATEGIES
        if self.strategy not in STRATEGIES: raise ValueError(f"알 수 없는 전략입니다: {self.strategy}")
        unknown = set(self.grid) - set(STRATEGIES[self.strategy]["params"])
        if unknown: raise ValueError(f"이 전략에 없는 설정입니다: {', '.join(sorted(unknown))}")
        if not all(self.grid.values()): raise ValueError("설정값마다 후보를 하나 이상 넣으세요.")
        if self.count() > MANIFEST_LIMIT: raise ValueError(f"조합 {self.count()}개는 한도 {MANIFEST_LIMIT}개를 넘습니다.")
        return self
    def count(self):
        from math import prod
        return prod(len(set(v)) for v in self.grid.values())
    def combinations(self):
        """(run configs, skipped): every candidate combination the strategy accepts (e.g. not short ≥ long)."""
        from itertools import product
        from .strategies import resolve
        base, keys, configs, skipped = self.model_dump(mode="json", exclude={"grid"}), list(self.grid), [], 0
        for values in product(*(sorted(set(v)) for v in self.grid.values())):
            params = dict(zip(keys, values))
            try: resolve(self.strategy, params)
            except ValueError:
                skipped += 1
                continue
            configs.append(dict(base, params=params))
        return configs, skipped

@app.post("/api/grid")
def grid(spec: Grid):
    """Run every valid combination in-process (up to GRID_LIMIT short backtests)."""
    if spec.count() > GRID_LIMIT:
        raise HTTPException(422, f"조합 {spec.count()}개는 화면 실행 한도 {GRID_LIMIT}개를 넘습니다. 작업 목록을 받아 벤치마크나 클라우드로 실행하세요.")
    check_range(spec)
    configs, skipped = spec.combinations()
    return dict(rows=[dict(params=c["params"], **summarize(c)) for c in configs], skipped=skipped)

@app.post("/api/grid/manifest")
def grid_manifest(spec: Grid):
    """The same combinations as run configs for `lab.benchmark` / `lab.cloud experiment --manifest`."""
    check_range(spec)
    configs, skipped = spec.combinations()
    return dict(configs=configs, skipped=skipped)

class LocalBenchmark(Grid):
    workers: list[Annotated[int, Field(ge=1, le=64)]] = Field(min_length=1, max_length=8)
    repeats: int = Field(default=3, ge=1, le=3)

benchmark_lock = threading.Lock()

@app.post("/api/benchmarks")
def local_benchmark(spec: LocalBenchmark):
    """The grid's combinations through the same `lab.benchmark` CLI, in its own process so the server does not skew timings."""
    check_range(spec)
    configs, _ = spec.combinations()
    if not configs: raise HTTPException(422, "규칙에 맞는 조합이 없습니다.")
    if not benchmark_lock.acquire(blocking=False): raise HTTPException(409, "이미 로컬 벤치마크가 실행 중입니다.")
    try:
        with tempfile.TemporaryDirectory() as folder:
            manifest = Path(folder)/"manifest.json"
            manifest.write_text(json.dumps(configs), encoding="utf-8")
            done = subprocess.run([sys.executable, "-m", "lab.benchmark", str(manifest), "--workers", *map(str, spec.workers), "--repeats", str(spec.repeats)],
                                  capture_output=True, text=True, encoding="utf-8", timeout=3600,
                                  env={**os.environ, "PYTHONIOENCODING": "utf-8"})  # Korean messages through Windows pipes
    except subprocess.TimeoutExpired: raise HTTPException(504, "로컬 벤치마크가 1시간 안에 끝나지 않았습니다.")
    finally: benchmark_lock.release()
    if done.returncode: raise HTTPException(500, (done.stderr.strip().splitlines() or ["로컬 벤치마크 실패"])[-1])
    return dict(id=json.loads(done.stdout)["id"], jobs=len(configs))

@app.get("/api/stocks")
def stock_search(q: str = ""):
    from .stocks import search
    return search(q)

@app.post("/api/stocks/{symbol}/prepare")
def stock_prepare(symbol: str):
    from .stocks import prepare
    try: return prepare(symbol)
    except ValueError as e: raise HTTPException(422,str(e))

@app.get("/api/forecast")
def forecast_view(dataset_id: str, horizon: int = 20):
    from .forecast import run_forecast
    try: return run_forecast(dataset_id,horizon)
    except ValueError as e: raise HTTPException(422,str(e))

@app.get("/api/benchmarks")
def benchmarks():
    from .data import root
    output=[]
    for path in sorted((root()/"benchmarks").glob("*.json")):
        report=json.loads(path.read_text(encoding="utf-8"))
        report.pop("records",None)
        for record in report.get("runs",[]): record.pop("records",None)
        output.append(report)
    return sorted(output, key=lambda r: r.get("created_at", ""), reverse=True)  # newest first on the cloud page

def job_or_404(identifier):
    job = store.get(identifier)
    if not job: raise HTTPException(404,"작업을 찾을 수 없습니다.")
    return job

@app.get("/api/runs/{identifier}")
def status(identifier: str): return job_or_404(identifier)

@app.post("/api/runs/{identifier}/cancel")
def cancel(identifier: str):
    job = job_or_404(identifier)
    if job["status"] in ["queued","running"]:
        store.update(identifier,"cancelled")
        process = processes.get(identifier)
        if process and process.poll() is None:
            process.terminate()
            process.wait(timeout=10)
    return store.get(identifier)

@app.delete("/api/runs/{identifier}", status_code=204)
def delete_run(identifier: str):
    job_or_404(identifier)
    cancel(identifier)  # stops a queued/running worker first; no-op otherwise
    processes.pop(identifier, None)
    store.delete(identifier)

@app.get("/api/runs/{identifier}/results")
def results(identifier: str):
    if job_or_404(identifier)["status"] != "completed":
        raise HTTPException(409,"완료된 결과만 조회할 수 있습니다.")
    result = json.loads(store.result_path(identifier).read_text(encoding="utf-8"))
    if "prices" not in result:
        frame, _ = load_dataset(result["config"]["dataset_id"])
        config = result["config"]
        result["prices"] = frame.loc[(frame.date >= config["start"]) & (frame.date <= config["end"])].to_dict(orient="records")
    return result
