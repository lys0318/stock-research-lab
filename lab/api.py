import json
import subprocess
import sys
import uuid
import threading
from contextlib import asynccontextmanager
from functools import lru_cache
from datetime import date
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel, Field, model_validator
from typing import Literal
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
    if request.method == "POST" and request.headers.get("x-research-local") != "1":
        return JSONResponse({"detail":"로컬 실행 헤더가 필요합니다."},status_code=403)
    return await call_next(request)

class RunConfig(BaseModel):
    dataset_id: str = Field(pattern=r"^[a-f0-9]{20}$")
    start: date
    end: date
    strategy: Literal["hold","ma","model"]
    capital: float = Field(default=1000000,ge=1000,le=1e10)
    fee: float = Field(default=.00015,ge=0,le=.05)
    tax: float = Field(default=0,ge=0,le=.05)
    slippage: float = Field(default=.0005,ge=0,le=.05)
    seed: int = Field(default=42,ge=0,le=2147483647)
    ma_window: int = Field(default=20,ge=2,le=250)
    @model_validator(mode="after")
    def check_dates(self):
        if self.start >= self.end: raise ValueError("시작일은 종료일보다 빨라야 합니다.")
        return self

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
    try:
        frame, meta = load_dataset(config.dataset_id)
        if str(config.start)<meta["start"] or str(config.end)>meta["end"]:
            raise ValueError(f"확보 기간 {meta['start']} ~ {meta['end']} 안에서 선택하세요.")
        if ((frame.date >= str(config.start)) & (frame.date <= str(config.end))).sum() < 10:
            raise ValueError("평가 기간에는 최소 10개의 거래일이 필요합니다.")
    except ValueError as e: raise HTTPException(422,str(e))
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
    return output

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
