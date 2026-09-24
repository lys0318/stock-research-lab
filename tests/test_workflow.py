import json
import time
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from lab.api import app
from lab.data import demo
from lab.engine import simulate
from lab.cli import export
from lab import store

@pytest.fixture(autouse=True)
def isolated(tmp_path,monkeypatch):
    monkeypatch.setenv("LAB_DATA_DIR",str(tmp_path))

def test_worker_roundtrip():
    meta=demo()
    with TestClient(app) as client:
        response=client.post("/api/runs",headers={"X-Research-Local":"1"},json={
            "dataset_id":meta["id"],"start":"2024-01-01","end":"2025-12-31","strategy":"model"})
        assert response.status_code==202
        identifier=response.json()["id"]
        for _ in range(120):
            status=client.get("/api/runs/"+identifier).json()
            if status["status"] not in ["queued","running"]:break
            time.sleep(.25)
        assert status["status"]=="completed",status
        result=client.get("/api/runs/"+identifier+"/results").json()
        assert result["prediction"]["test_rows"]>10
        assert result["dataset"]["synthetic"] is True
        assert export(Path(store.root())/"public")["exported"]==0

def test_five_day_holding():
    import pandas as pd
    f=pd.DataFrame(dict(date=pd.date_range("2024-01-01",periods=8).strftime("%Y-%m-%d"),
        open=[100]*8,close=[100]*8))
    result=simulate(f,[True]*8,"model",1000,0,0,0)
    assert [t["date"] for t in result["trades"]]==["2024-01-02","2024-01-06"]

def test_server_restart_recovers():
    store.create("pending",{})
    store.update("pending","running")
    store.recover()
    assert store.get("pending")["status"]=="failed"

def test_invalid_date_request():
    meta=demo()
    with TestClient(app) as c:
        r=c.post("/api/runs",headers={"X-Research-Local":"1"},json={
          "dataset_id":meta["id"],"start":"2025-01-01","end":"2024-01-01","strategy":"hold"})
        assert r.status_code==422
