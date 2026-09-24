import json
import sys
from . import store

def execute(identifier):
    job = store.get(identifier)
    if not job or job["status"] != "queued": return
    try:
        store.update(identifier, "running")
        from .engine import run
        result = run(job["config"])
        result.update(id=identifier, attempt=job["attempt"])
        if store.get(identifier)["status"] == "cancelled": return
        path = store.result_path(identifier)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(result, ensure_ascii=False, allow_nan=False), encoding="utf-8")
        temporary.replace(path)
        store.update(identifier, "completed")
    except Exception as error:
        store.update(identifier, "failed", str(error))

if __name__ == "__main__":
    execute(sys.argv[1])
