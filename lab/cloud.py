"""Explicit AWS experiment CLI. No automatic provisioning or background spend."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import time
import uuid
import boto3
from .data import root, load_dataset

def worker():
    from .benchmark import measured
    s3=boto3.client("s3")
    bucket=os.environ["LAB_BUCKET"];prefix=os.environ["LAB_PREFIX"]
    index=int(os.environ["LAB_GROUP"])
    manifest=json.loads(s3.get_object(Bucket=bucket,Key=prefix+"/manifest.json")["Body"].read())
    configs=manifest["groups"][index]
    for version in set(c["dataset_id"] for c in configs):
        folder=root()/"datasets"/version;folder.mkdir(parents=True,exist_ok=True)
        for name in ["prices.parquet","metadata.json"]:
            s3.download_file(bucket,prefix+"/datasets/"+version+"/"+name,str(folder/name))
    results=[]
    for config in configs:
        value=measured(config)
        value["config"]=config
        results.append(value)
    s3.put_object(Bucket=bucket,Key=prefix+f"/results/{index}.json",Body=json.dumps(results).encode())

def experiment(args):
    from .api import RunConfig
    configs=[RunConfig.model_validate(c).model_dump(mode="json") for c in json.loads(Path(args.manifest).read_text(encoding="utf-8"))]
    if not 1<=len(configs)<=1000: raise ValueError("작업 수는 1~1000")
    groups=[configs[i::args.workers] for i in range(args.workers)]
    groups=[g for g in groups if g]
    identifier=uuid.uuid4().hex;prefix="experiments/"+identifier
    s3=boto3.client("s3",region_name=args.region)
    batch=boto3.client("batch",region_name=args.region)
    for version in set(c["dataset_id"] for c in configs):
        load_dataset(version)
        for name in ["prices.parquet","metadata.json"]:
            s3.upload_file(str(root()/"datasets"/version/name),args.bucket,prefix+"/datasets/"+version+"/"+name)
    s3.put_object(Bucket=args.bucket,Key=prefix+"/manifest.json",Body=json.dumps(dict(groups=groups)).encode())
    ids=[]; began=time.time();success=False
    try:
        for i in range(len(groups)):
            response=batch.submit_job(jobName=f"research-{identifier[:8]}-{i}",jobQueue=args.queue,jobDefinition=args.definition,
                timeout={"attemptDurationSeconds":args.timeout},
                containerOverrides={"environment":[{"name":"LAB_BUCKET","value":args.bucket},{"name":"LAB_PREFIX","value":prefix},{"name":"LAB_GROUP","value":str(i)}]})
            ids.append(response["jobId"])
        while True:
            jobs=batch.describe_jobs(jobs=ids)["jobs"]
            if any(j["status"]=="FAILED" for j in jobs): raise RuntimeError("AWS 작업 실패. CloudWatch 로그를 확인하세요.")
            if len(jobs)==len(ids) and all(j["status"]=="SUCCEEDED" for j in jobs): break
            if time.time()-began>args.timeout+300: raise TimeoutError("제출 이후 대기·실행 제한 초과")
            time.sleep(10)
        records=[]
        for i in range(len(groups)):
            records.extend(json.loads(s3.get_object(Bucket=args.bucket,Key=prefix+f"/results/{i}.json")["Body"].read()))
        from .benchmark import concurrency
        duration=time.time()-began
        report=dict(id=identifier,environment="aws-fargate",created_at=datetime.now(timezone.utc).isoformat(),
            dataset_ids=sorted(set(c["dataset_id"] for c in configs)),
            runs=[dict(workers=args.workers,total_seconds=duration,throughput=len(configs)/duration,completed=len(records),
                failed=0,observed_concurrency=concurrency(records),equal_results=None,estimated_compute_cost=None)],
            jobs=[{k:j.get(k) for k in ["jobId","status","createdAt","startedAt","stoppedAt"]} for j in jobs],
            records=records,cost_note="비용은 미산정. 리전별 단가와 청구 내역을 대조해야 합니다.",
            prefix=prefix,bucket=args.bucket)
        folder=root()/"benchmarks";folder.mkdir(exist_ok=True)
        (folder/(identifier+".json")).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
        success=True
        return report
    finally:
        if not success:
            for job_id in ids:
                # terminate_job also cancels jobs that have not started.
                batch.terminate_job(jobId=job_id,reason="Research experiment aborted")

def main():
    p=argparse.ArgumentParser();p.add_argument("command",choices=["worker","experiment"])
    p.add_argument("--manifest");p.add_argument("--bucket");p.add_argument("--queue");p.add_argument("--definition")
    p.add_argument("--region",default="ap-northeast-2");p.add_argument("--workers",type=int,choices=[1,2,4],default=1)
    p.add_argument("--timeout",type=int,default=600)
    a=p.parse_args()
    if a.command=="worker": worker();return
    if not all([a.manifest,a.bucket,a.queue,a.definition]) or not 60<=a.timeout<=1800:
        p.error("manifest/bucket/queue/definition 필요, timeout 60~1800초")
    print(json.dumps(experiment(a),ensure_ascii=False,indent=2))

if __name__=="__main__":main()
