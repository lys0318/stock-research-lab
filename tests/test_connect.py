import os
import pytest
from lab import connect as module

@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.setenv("LAB_DATA_DIR", str(tmp_path))
    for name in ("TOSS_CLIENT_ID", "TOSS_CLIENT_SECRET"):
        monkeypatch.delenv(name, raising=False)

def test_hidden_input_restored(monkeypatch):
    inputs = iter(["fake-client", "fake-secret"])
    monkeypatch.setattr(module, "getpass", lambda _: next(inputs))
    def fake_collect(symbol, output, max_pages):
        assert os.environ["TOSS_CLIENT_SECRET"] == "fake-secret"
        assert symbol == "005930" and max_pages == 20
        return {"output": output}
    monkeypatch.setattr(module, "collect", fake_collect)
    assert "toss-" in module.connect()["output"]
    assert "TOSS_CLIENT_ID" not in os.environ
    assert "TOSS_CLIENT_SECRET" not in os.environ

def test_failure_clears_credentials(monkeypatch):
    monkeypatch.setattr(module, "getpass", lambda _: "fake-value")
    def fail(*args, **kwargs):
        raise ValueError("HTTP 403")
    monkeypatch.setattr(module, "collect", fail)
    with pytest.raises(ValueError, match="403"):
        module.connect()
    assert "TOSS_CLIENT_ID" not in os.environ
    assert "TOSS_CLIENT_SECRET" not in os.environ

def test_existing_environment_preserved(monkeypatch):
    monkeypatch.setenv("TOSS_CLIENT_ID", "existing-client")
    monkeypatch.setenv("TOSS_CLIENT_SECRET", "existing-secret")
    monkeypatch.setattr(module, "getpass", lambda _: pytest.fail("unexpected prompt"))
    monkeypatch.setattr(module, "collect", lambda *args, **kwargs: {})
    module.connect()
    assert os.environ["TOSS_CLIENT_SECRET"] == "existing-secret"
