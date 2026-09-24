import argparse
import json
import os
import sys
from pathlib import Path
from .data import demo, import_csv, datasets
from . import store

def export(destination):
    target = Path(destination)
    target.mkdir(parents=True,exist_ok=True)
    entries=[]
    for job in store.listing():
        if job["status"]!="completed": continue
        result=json.loads(store.result_path(job["id"]).read_text(encoding="utf-8"))
        meta=next((d for d in datasets() if d["id"]==result["dataset"]["id"]),None)
        if not meta: continue
        if meta["synthetic"] or not meta["publication_allowed"]: continue
        public={k:result[k] for k in ["id","dataset","config","metrics","curve","trades","prediction","created_at","code_version","compute_seconds","assumptions"]}
        public["dataset"]={k:meta[k] for k in ["id","symbol","name","source","start","end","synthetic","adjustment"]}
        entries.append(public)
    (target/"index.json").write_text(json.dumps(entries,ensure_ascii=False,allow_nan=False),encoding="utf-8")
    allowed={d["id"] for d in datasets() if not d["synthetic"] and d["publication_allowed"]}
    reports=[]
    from .data import root
    for path in sorted((root()/"benchmarks").glob("*.json")):
        report=json.loads(path.read_text(encoding="utf-8"))
        if not report.get("dataset_ids") or not set(report["dataset_ids"]).issubset(allowed): continue
        reports.append({k:report[k] for k in ["id","environment","created_at","runs","cost_note"]})
        for item in reports[-1]["runs"]: item.pop("records",None)
    (target/"benchmarks.json").write_text(json.dumps(reports,ensure_ascii=False),encoding="utf-8")
    return dict(exported=len(entries),benchmarks=len(reports),destination=str(target))

def main():
    parser=argparse.ArgumentParser()
    sub=parser.add_subparsers(dest="command",required=True)
    sub.add_parser("demo")
    sub.add_parser("serve")
    sub.add_parser("connect-toss")
    imp=sub.add_parser("import-csv"); imp.add_argument("csv"); imp.add_argument("metadata")
    raw=sub.add_parser("import-toss"); raw.add_argument("folder"); raw.add_argument("symbol"); raw.add_argument("name")
    exp=sub.add_parser("export"); exp.add_argument("destination",nargs="?",default="web/public/results")
    toss=sub.add_parser("collect-toss"); toss.add_argument("symbol"); toss.add_argument("--output",default="data/raw"); toss.add_argument("--pages",type=int,default=1)
    args=parser.parse_args()
    if args.command=="demo": result=demo()
    elif args.command=="connect-toss":
        from .connect import connect
        try: result=connect()
        except (ValueError, EOFError, KeyboardInterrupt) as error:
            parser.exit(1, str(error) or "연결 확인을 중단했습니다.")
    elif args.command=="import-csv": result=import_csv(args.csv,args.metadata)
    elif args.command=="import-toss":
        from .toss import import_raw
        result=import_raw(args.folder,args.symbol,args.name)
    elif args.command=="export": result=export(args.destination)
    elif args.command=="collect-toss":
        from .toss import collect
        if not 1<=args.pages<=100: parser.error("pages는 1~100")
        result=collect(args.symbol,args.output,args.pages)
    else:
        from .stocks import has_key
        env=Path(".env")
        if env.exists():  # local-only secrets file, git/docker-ignored; real env vars win
            for line in env.read_text(encoding="utf-8-sig").splitlines():
                key,sep,value=line.partition("=")
                if sep and key.strip() and not key.lstrip().startswith("#"): os.environ.setdefault(key.strip(),value.strip())
        if not has_key() and sys.stdin.isatty():
            from getpass import getpass
            print("토스 키를 입력하면 검색한 새 종목을 자동으로 받습니다. 건너뛰려면 Enter. 키는 저장하지 않습니다.")
            for name in ("TOSS_CLIENT_ID","TOSS_CLIENT_SECRET"):
                value=getpass(f"{name} (hidden input): ").strip()
                if not value: break
                os.environ[name]=value
        import uvicorn
        uvicorn.run("lab.api:app",host="127.0.0.1",port=8000)
        return
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=="__main__": main()
