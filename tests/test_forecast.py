import numpy as np
import pandas as pd
import pytest
from lab.data import demo, load_dataset
from lab.forecast import forecast

@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("LAB_DATA_DIR", str(tmp_path))

def test_path_shape_and_dates():
    f, _ = load_dataset(demo()["id"])
    r = forecast(f, 20)
    assert len(r["path"]) == 20
    dates = pd.to_datetime([p["date"] for p in r["path"]])
    assert dates[0] > pd.Timestamp(r["last_date"]) and (dates.dayofweek < 5).all()
    assert all(np.isfinite(p["price"]) and p["price"] > 0 for p in r["path"])
    assert r["last_close"] == f.close.iloc[-1]
    assert r["prices"][-1]["date"] == r["last_date"] and len(r["prices"]) == 500

def test_path_skips_krx_holidays():
    f, _ = load_dataset(demo()["id"])
    f["date"] = [str(d.date()) for d in pd.bdate_range(end="2026-09-23", periods=len(f))]
    dates = [p["date"] for p in forecast(f, 20)["path"]]
    assert dates[:3] == ["2026-09-28", "2026-09-29", "2026-09-30"]  # 09-24·25 추석
    assert "2026-10-05" not in dates and "2026-10-09" not in dates  # 개천절 대체·한글날

def test_evaluation_has_no_leakage():
    f, _ = load_dataset(demo()["id"])
    e = forecast(f, 60)["evaluation"]
    assert e["train_label_end"] < e["test_start"]
    assert 0 <= e["hit_rate"] <= 1 and 0 <= e["up_rate"] <= 1
    assert e["mape"] >= 0 and e["naive_mape"] >= 0

def test_rejects_bad_horizon_and_short_data():
    f, _ = load_dataset(demo()["id"])
    with pytest.raises(ValueError):
        forecast(f, 7)
    with pytest.raises(ValueError, match="부족"):
        forecast(f.tail(150).reset_index(drop=True), 5)
