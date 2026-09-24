"""Compare immutable AWS result files and export measured summary CSV."""
import argparse
import csv
import json
from pathlib import Path
import numpy as np

def compare(paths):
    reports=[json.loads(Path(p).read_text(encoding="utf-8")) for p in paths]
    if len(reports)<2: raise ValueError("최소 두 실험 파일이 필요합니다.")
    def ordered(report):
        records=report.get("records")
        if not records: raise ValueError("AWS 작업별 결과가 없는 파일입니다.")
        return sorted(records,key=lambda r:json.dumps(r["config"],sort_keys=True))
    base=ordered(reports[0])
    for report in reports[1:]:
        other=ordered(report)
        if len(base)!=len(other): raise ValueError("작업 수 불일치")
        for a,b in zip(base,other):
            if a["config"]!=b["config"] or a["code_version"]!=b["code_version"]:
                raise ValueError("입력 또는 코드 버전 불일치")
            if [r["date"] for r in a["curve"]]!=[r["date"] for r in b["curve"]]:
                raise ValueError("거래일 불일치")
            if not all(np.isclose(a["metrics"][k],b["metrics"][k],rtol=1e-10,atol=1e-8) for k in a["metrics"]):
                raise ValueError("성과 지표 불일치")
            if not np.allclose([[r["equity"],r["drawdown"]] for r in a["curve"]],
                               [[r["equity"],r["drawdown"]] for r in b["curve"]],rtol=1e-10,atol=1e-8):
                raise ValueError("자산 경로 불일치")
    # Only change verification fields after every comparison has passed.
    for path,report in zip(paths,reports):
        for row in report["runs"]: row["equal_results"]=True
        Path(path).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    return {"verified_reports":len(reports)}

def summary(paths,output):
    with Path(output).open("w",newline="",encoding="utf-8-sig") as file:
        writer=csv.DictWriter(file,fieldnames=["id","environment","workers","total_seconds","throughput","observed_concurrency","equal_results","estimated_compute_cost"])
        writer.writeheader()
        for path in paths:
            report=json.loads(Path(path).read_text(encoding="utf-8"))
            for row in report["runs"]:
                writer.writerow({key:report.get(key,row.get(key)) for key in writer.fieldnames})

def main():
    p=argparse.ArgumentParser()
    p.add_argument("command",choices=["compare","csv"])
    p.add_argument("files",nargs="+")
    p.add_argument("--output",default="benchmark-summary.csv")
    a=p.parse_args()
    if a.command=="compare": print(json.dumps(compare(a.files)))
    else: summary(a.files,a.output)

if __name__=="__main__":main()
