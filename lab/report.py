"""Compare immutable AWS result files and export measured summary CSV.

A report is X.json (timings, metrics, config per job) plus X.curves.parquet (curve_id, date, equity):
equity curves are ~95% of the bytes, so they live in compressed columns instead of JSON.
"""
import argparse
import csv
import json
from pathlib import Path
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

def curves_path(report_path): return Path(report_path).with_suffix(".curves.parquet")

def pack(index, values):
    """Measured results (an iterable, so a worker never holds every curve as Python objects) -> (records, curves table)."""
    records, batches = [], []
    for n, value in enumerate(values):
        curve = value.pop("curve")
        value["curve_id"] = f"{index}:{n}"
        records.append(value)
        batches.append(pa.RecordBatch.from_pydict({"curve_id": [value["curve_id"]]*len(curve),
            "date": [p["date"] for p in curve], "equity": [p["equity"] for p in curve]}))
    return records, pa.Table.from_batches(batches)

def save_report(path, report, table):
    path = Path(path)
    pq.write_table(table, curves_path(path), compression="zstd")
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return path

def curves_of(path):
    """curve_id -> (dates, equity). Reports written before the Parquet split keep curves inline instead."""
    file = curves_path(path)
    if not file.exists(): return {}
    frame = pq.read_table(file).to_pandas()
    return {key: (group.date.tolist(), group.equity.to_numpy()) for key, group in frame.groupby("curve_id", sort=False)}

def curve(record, lookup):
    if "curve" in record: return [r["date"] for r in record["curve"]], np.array([r["equity"] for r in record["curve"]])
    return lookup[record["curve_id"]]

def compare(paths):
    reports=[json.loads(Path(p).read_text(encoding="utf-8")) for p in paths]
    if len(reports)<2: raise ValueError("최소 두 실험 파일이 필요합니다.")
    def ordered(report):
        records=report.get("records")
        if not records: raise ValueError("AWS 작업별 결과가 없는 파일입니다.")
        return sorted(records,key=lambda r:json.dumps(r["config"],sort_keys=True))
    base,base_curves=ordered(reports[0]),curves_of(paths[0])
    for path,report in zip(paths[1:],reports[1:]):
        other,other_curves=ordered(report),curves_of(path)
        if len(base)!=len(other): raise ValueError("작업 수 불일치")
        for a,b in zip(base,other):
            if a["config"]!=b["config"] or a["code_version"]!=b["code_version"]:
                raise ValueError("입력 또는 코드 버전 불일치")
            (dates_a,equity_a),(dates_b,equity_b)=curve(a,base_curves),curve(b,other_curves)
            if dates_a!=dates_b: raise ValueError("거래일 불일치")
            if not all(k in b["metrics"] and np.isclose(a["metrics"][k],b["metrics"][k],rtol=1e-10,atol=1e-8) for k in a["metrics"]):
                raise ValueError("성과 지표 불일치")
            # Drawdown is derived from equity, so matching equity covers it.
            if not np.allclose(equity_a,equity_b,rtol=1e-10,atol=1e-8): raise ValueError("자산 경로 불일치")
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
