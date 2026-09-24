import json
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from lab.api import app
from lab.data import demo, load_dataset
from lab.engine import run
from lab.toss import import_raw
from lab.cli import export
from lab import store

@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv('LAB_DATA_DIR', str(tmp_path / 'data'))

def candle(day, close='110'):
    return dict(timestamp=f'2024-01-{day:02}T00:00:00+09:00', openPrice='100',
                highPrice='120', lowPrice='90', closePrice=close, volume='10', currency='KRW')

def write_page(folder, page, rows):
    (folder/f'005930-{page:04}.json').write_text(json.dumps({'result':{'candles':rows}}),encoding='utf-8')

def test_raw_cursor_overlap_and_private_export(tmp_path):
    write_page(tmp_path,0,[candle(3),candle(2)])
    write_page(tmp_path,1,[candle(2),candle(1)])
    meta=import_raw(tmp_path,'005930','Samsung')
    f,_=load_dataset(meta['id'])
    assert f.date.tolist()==['2024-01-01','2024-01-02','2024-01-03']
    assert f.close.tolist()==[110]*3
    assert meta['synthetic'] is False and meta['publication_allowed'] is False
    store.create('private',{})
    store.result_path('private').write_text(json.dumps({'dataset':meta}),encoding='utf-8')
    store.update('private','completed')
    assert export(tmp_path/'public')['exported']==0

def test_raw_conflicting_duplicate_rejected(tmp_path):
    write_page(tmp_path,0,[candle(2),candle(1)])
    write_page(tmp_path,1,[candle(2,'111')])
    with pytest.raises(ValueError,match='같은 거래일'):
        import_raw(tmp_path,'005930','Samsung')

def test_raw_rejects_wrong_currency(tmp_path):
    c=candle(1);c['currency']='USD'
    write_page(tmp_path,0,[c,candle(2)])
    with pytest.raises(ValueError,match='KRW'):
        import_raw(tmp_path,'005930','Samsung')

def test_short_period_rejected_before_job_creation():
    meta=demo()
    with TestClient(app) as client:
        r=client.post('/api/runs',headers={'X-Research-Local':'1'},json={
            'dataset_id':meta['id'],'start':'2024-01-01','end':'2024-01-03','strategy':'ma'})
    assert r.status_code==422
    assert not store.listing()

def test_result_chart_prices_and_execution_phase():
    meta=demo();f,_=load_dataset(meta['id'])
    result=run(dict(dataset_id=meta['id'],start='2024-01-01',end='2024-12-31',strategy='hold',slippage=0,fee=0))
    assert [p['date'] for p in result['prices']]==[p['date'] for p in result['curve']]
    assert result['trades'][0]['price']==result['prices'][0]['open']
    assert result['trades'][0]['phase']=='open'
    assert result['trades'][-1]['price']==result['prices'][-1]['close']
    assert result['trades'][-1]['phase']=='close'
