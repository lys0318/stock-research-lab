import argparse
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
from functools import cache
import json
import platform
import time
import uuid
from pathlib import Path
from .data import root
from .engine import run

def single_thread():
    """Pin numeric libraries to one thread for the whole process. Per-backtest limits cost ~0.15s each at 16 workers."""
    from threadpoolctl import threadpool_limits
    threadpool_limits(limits=1)

@cache
def cpu_model():
    """CPU name for reports: /proc/cpuinfo on Linux (Fargate assigns it), platform string elsewhere."""
    try:
        with open("/proc/cpuinfo",encoding="utf-8") as f:
            for line in f:
                if line.startswith("model name"): return line.split(":",1)[1].strip()
    except OSError: pass
    return platform.processor()

def measured(config):
    start=time.time()
    result=run(config)
    return dict(started_at=start,finished_at=time.time(),metrics=result["metrics"],curve=result["curve"],code_version=result["code_version"],cpu=cpu_model())

def concurrency(records):
    events=[]
    for r in records: events.extend([(r["started_at"],1),(r["finished_at"],-1)])
    active=peak=0
    for _,delta in sorted(events):
        active+=delta; peak=max(peak,active)
    return peak

def benchmark(configs,workers,repeats=3):
    reference=None
    reports=[]
    for w in workers:
        for repeat in range(repeats):
            began=time.time()
            with ProcessPoolExecutor(max_workers=w,initializer=single_thread) as pool:
                records=list(pool.map(measured,configs))
            elapsed=time.time()-began
            signature=[dict(metrics=r["metrics"],curve=r["curve"]) for r in records]
            if reference is None: reference=signature
            if signature!=reference: raise ValueError("순차·병렬 결과 불일치")
            reports.append(dict(workers=w,repeat=repeat+1,total_seconds=elapsed,
                throughput=len(configs)/elapsed,completed=len(records),failed=0,
                observed_concurrency=concurrency(records),equal_results=True,
                estimated_compute_cost=None,records=[{k:r[k] for k in ["started_at","finished_at"]} for r in records]))
    output=dict(id=uuid.uuid4().hex,environment="local",cpu=cpu_model(),created_at=datetime.now(timezone.utc).isoformat(),
        dataset_ids=sorted(set(c["dataset_id"] for c in configs)),runs=reports,
        cost_note="로컬 측정입니다. AWS 비용 또는 성능으로 해석할 수 없습니다.")
    folder=root()/"benchmarks";folder.mkdir(exist_ok=True)
    (folder/(output["id"]+".json")).write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding="utf-8")
    return output

def main():
    p=argparse.ArgumentParser()
    p.add_argument("manifest");p.add_argument("--workers",type=int,nargs="+",default=[1,2,4])
    p.add_argument("--repeats",type=int,default=3)
    a=p.parse_args()
    configs=json.loads(Path(a.manifest).read_text(encoding="utf-8"))
    if not isinstance(configs,list) or not 1<=len(configs)<=10000 or any(not 1<=w<=64 for w in a.workers) or not 1<=a.repeats<=3:
        p.error("작업 1~10000개, 작업자 1~64, 반복 1~3회")
    from .api import RunConfig
    configs=[RunConfig.model_validate(c).model_dump(mode="json") for c in configs]
    print(json.dumps(benchmark(configs,a.workers,a.repeats),ensure_ascii=False,indent=2))

if __name__=="__main__":main()
