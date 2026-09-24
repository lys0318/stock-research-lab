import json
import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from lab.data import demo,load_dataset,validate
from lab.engine import simulate,model_signals,run
from lab.api import app
from lab import store
from lab.cli import export

@pytest.fixture(autouse=True)
def isolated(tmp_path,monkeypatch):
    monkeypatch.setenv("LAB_DATA_DIR",str(tmp_path))

def frame():
    return pd.DataFrame(dict(date=["2024-01-01","2024-01-02"],open=[100.,110.],high=[100.,110.],low=[100.,110.],close=[100.,110.],volume=[10,10]))

def test_hand_calculated():
    result=simulate(frame(),[True,True],"hold",capital=1000,fee=0,tax=0,slippage=0)
    assert result["metrics"]["final_equity"]==1100
    assert result["trades"][0]["shares"]==10
    assert result["metrics"]["total_return"]==pytest.approx(.1)

def test_costs():
    r=simulate(frame(),[True,True],"hold",capital=1000,fee=.01,tax=.02,slippage=0)
    # Buy 9 shares for 909; sell for 990 minus 29.7.
    assert r["metrics"]["final_equity"]==pytest.approx(1051.3)

def test_next_open_not_same_close():
    r=simulate(frame(),[True,False],"ma",capital=1000,fee=0,tax=0,slippage=0)
    assert r["trades"][0]["date"]=="2024-01-02"
    assert r["trades"][0]["price"]==110

def test_validation():
    f=frame();f.loc[1,"date"]=f.loc[0,"date"]
    with pytest.raises(ValueError):validate(f)
    f=frame();f.loc[0,"high"]=90
    with pytest.raises(ValueError):validate(f)

def test_model_boundary_and_future_independence():
    meta=demo();f,_=load_dataset(meta["id"])
    signals,score=model_signals(f,"2024-01-01","2025-12-31",42)
    assert score["train_label_end"]<"2023-01-01"
    assert score["validation_label_end"]<"2024-01-01"
    changed=f.copy()
    late=changed.date>"2025-01-01"
    for c in ["open","high","low","close"]: changed.loc[late,c]*=3
    modified,_=model_signals(changed,"2024-01-01","2025-12-31",42)
    assert np.array_equal(signals[f.date<"2025-01-01"],modified[f.date<"2025-01-01"])

def test_export_rejects_synthetic(tmp_path):
    meta=demo();config=dict(dataset_id=meta["id"],start="2024-01-01",end="2025-12-31",strategy="hold")
    store.create("abc",config)
    result=run(config);result["id"]="abc"
    store.result_path("abc").write_text(json.dumps(result),encoding="utf-8")
    store.update("abc","completed")
    assert export(tmp_path/"published")["exported"]==0

def test_cancel_terminal_state():
    store.create("x",{})
    store.update("x","cancelled")
    store.update("x","completed")
    assert store.get("x")["status"]=="cancelled"

def test_local_api_protection():
    with TestClient(app) as c:
        assert c.post("/api/runs",json={}).status_code==403
        assert c.get("/api/datasets",headers={"Origin":"https://evil.example"}).status_code==403
        assert c.get("/api/datasets").status_code==200
        assert c.get("/api/runs/unknown/results").status_code==404

def test_parallel_matches():
    from lab.benchmark import benchmark
    meta=demo()
    configs=[dict(dataset_id=meta["id"],start="2024-01-01",end="2025-12-31",strategy=s) for s in ["hold","ma"]]
    result=benchmark(configs,[1,2],1)
    assert all(r["equal_results"] for r in result["runs"])
