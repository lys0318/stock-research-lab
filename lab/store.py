import json
import sqlite3
from datetime import datetime, timezone
from .data import root

def db():
    connection = sqlite3.connect(root() / "jobs.sqlite", timeout=15)
    connection.row_factory = sqlite3.Row
    connection.execute("CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, status TEXT, config TEXT, created_at TEXT, error TEXT, attempt INTEGER DEFAULT 1)")
    return connection

def create(identifier, config):
    with db() as c:
        c.execute("INSERT INTO runs (id,status,config,created_at) VALUES (?,?,?,?)",
                  (identifier,"queued",json.dumps(config),datetime.now(timezone.utc).isoformat()))

def update(identifier, status, error=None):
    with db() as c:
        c.execute("UPDATE runs SET status=?,error=? WHERE id=? AND status NOT IN ('cancelled','completed','failed')",
                  (status,error,identifier))

def get(identifier):
    with db() as c: row = c.execute("SELECT * FROM runs WHERE id=?",(identifier,)).fetchone()
    if not row: return None
    result = dict(row)
    result["config"] = json.loads(result["config"])
    return result

def listing():
    with db() as c: rows = c.execute("SELECT id FROM runs ORDER BY created_at DESC LIMIT 100").fetchall()
    return [get(row["id"]) for row in rows]

def result_path(identifier):
    folder = root() / "runs"
    folder.mkdir(exist_ok=True)
    return folder / (identifier+".json")

def recover():
    with db() as c:
        c.execute("UPDATE runs SET status='failed',error='서버가 재시작되었습니다. 새 작업으로 다시 실행하세요.' WHERE status IN ('queued','running')")
