import pandas as pd
import pytest
from fastapi.testclient import TestClient
from lab import stocks
from lab.api import app
from lab.data import save_dataset, demo

@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("LAB_DATA_DIR", str(tmp_path))
    for name in ("TOSS_CLIENT_ID", "TOSS_CLIENT_SECRET"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(stocks, "_failed_at", 0.)

def prices(end, n=30):
    d = pd.bdate_range(end=end, periods=n)
    return pd.DataFrame(dict(date=d, open=100., high=101., low=99., close=100., volume=10))

def saved(symbol="005930", name="삼성전자", end="2026-09-24"):
    return save_dataset(prices(end), symbol, name, "test", False, "test")

def test_search_without_key_uses_saved_only():
    demo(); meta = saved()
    r = stocks.search("삼성")
    assert r["connected"] is False
    assert [i["symbol"] for i in r["items"]] == ["005930"]
    assert r["items"][0]["dataset_id"] == meta["id"]
    assert stocks.search("0059")["items"][0]["name"] == "삼성전자"
    assert all(i["symbol"] != "000000" for i in stocks.search("")["items"])

def test_prepare_without_key():
    meta = saved(end="2020-01-03")
    assert stocks.prepare("005930")["id"] == meta["id"]
    with pytest.raises(ValueError, match="토스 키"):
        stocks.prepare("000660")

def test_rejected_key_is_not_reported_as_connected(monkeypatch):
    monkeypatch.setenv("TOSS_CLIENT_ID", "x"); monkeypatch.setenv("TOSS_CLIENT_SECRET", "y")
    calls = []
    def rejected():
        calls.append(1)
        raise ValueError("토스 인증 실패 HTTP 401")
    monkeypatch.setattr(stocks, "listed_stocks", rejected)
    saved()
    r = stocks.search("삼성")
    assert r["connected"] is False and [i["symbol"] for i in r["items"]] == ["005930"]
    stocks.search("삼성전")
    assert len(calls) == 1

def test_prepare_collects_new_symbol(monkeypatch):
    monkeypatch.setenv("TOSS_CLIENT_ID", "x"); monkeypatch.setenv("TOSS_CLIENT_SECRET", "y")
    monkeypatch.setattr(stocks, "listed_stocks", lambda: [dict(symbol="000660", name="SK하이닉스", market="KOSPI")])
    calls = []
    monkeypatch.setattr(stocks, "collect", lambda symbol, output, max_pages: calls.append((symbol, max_pages)))
    monkeypatch.setattr(stocks, "import_raw", lambda folder, symbol, name: saved(symbol, name, str(pd.Timestamp.today().date())))
    assert stocks.search("하이닉스")["items"][0]["market"] == "KOSPI"
    meta = stocks.prepare("000660")
    assert meta["name"] == "SK하이닉스" and calls == [("000660", 15)]
    assert stocks.prepare("000660")["id"] == meta["id"] and len(calls) == 1

def test_toss_client_session_is_usable(monkeypatch):
    # Real httpx client over a mock transport: catches session lifecycle bugs the mocks above skip.
    import httpx
    from lab import toss
    limited = []
    def handler(request):
        if request.url.path == "/oauth2/token": return httpx.Response(200, json={"access_token": "t"})
        assert request.headers["Authorization"] == "Bearer t"
        if request.url.params["market"] == "KOSDAQ" and not limited:  # stocks/all: 1 request per second
            limited.append(1)
            return httpx.Response(429, headers={"Retry-After": "1"})
        return httpx.Response(200, json={"result": [{"symbol": "005930", "name": "삼성전자"}]})
    real = httpx.Client
    monkeypatch.setattr(toss.httpx, "Client", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    monkeypatch.setenv("TOSS_CLIENT_ID", "x"); monkeypatch.setenv("TOSS_CLIENT_SECRET", "y")
    listing = toss.listed_stocks()
    assert listing[0] == dict(symbol="005930", name="삼성전자", market="KOSPI")
    assert listing[1]["market"] == "KOSDAQ" and limited

def test_api_routes():
    meta = demo(); saved()
    with TestClient(app) as c:
        assert c.get("/api/stocks", params={"q": "삼성"}).json()["items"][0]["symbol"] == "005930"
        assert c.post("/api/stocks/005930/prepare").status_code == 403
        assert c.post("/api/stocks/000660/prepare", headers={"X-Research-Local": "1"}).status_code == 422
        r = c.get("/api/forecast", params={"dataset_id": meta["id"], "horizon": 5})
        assert r.status_code == 200 and len(r.json()["path"]) == 5
        assert c.get("/api/forecast", params={"dataset_id": meta["id"], "horizon": 7}).status_code == 422
