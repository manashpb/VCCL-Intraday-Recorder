import importlib.util
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def hosted(tmp_path, monkeypatch):
    monkeypatch.setenv('RECORDER_DATA_DIR', str(tmp_path))
    monkeypatch.setenv('PORTAL_ORIGIN', 'https://workspace.example')
    spec = importlib.util.spec_from_file_location('recorder_test_app', Path(__file__).parents[1] / 'app.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    original = httpx.AsyncClient
    def verify(request):
        assert str(request.url) == 'http://127.0.0.1:5001/verify'
        return httpx.Response(204 if request.headers.get('cookie') == 'trading_session=valid' else 401)
    monkeypatch.setattr(module.httpx, 'AsyncClient', lambda **kwargs: original(transport=httpx.MockTransport(verify), **kwargs))
    with TestClient(module.service) as client:
        yield client, module


def test_all_resources_require_workspace_session(hosted):
    client, _ = hosted
    for path in ('/', '/static/app.js', '/api/journal', '/api/events/123'):
        assert client.get('/recorder' + path).status_code == 401
        assert client.get('/recorder' + path, headers={'Cookie': 'trading_session=expired'}).status_code == 401


def test_prefix_assets_and_authenticated_journal(hosted):
    client, _ = hosted
    headers = {'Cookie': 'trading_session=valid'}
    page = client.get('/recorder/', headers=headers)
    assert page.status_code == 200
    assert '/recorder/static/app.js' in page.text
    assert client.get('/recorder/static/app.js', headers=headers).status_code == 200
    result = client.get('/recorder/api/journal?day=2026-10-26', headers=headers)
    assert result.status_code == 200
    assert result.json()['trades'] == []
    assert result.headers['cache-control'] == 'no-store'


def test_mutations_need_exact_origin_and_session(hosted):
    client, _ = hosted
    for origin in ('https://evil.example', ''):
        assert client.post('/recorder/api/disconnect', headers={'Cookie': 'trading_session=valid', 'Origin': origin}).status_code == 403
    assert client.post('/recorder/api/disconnect', headers={'Origin': 'https://workspace.example'}).status_code == 401
    assert client.post('/recorder/api/disconnect', headers={'Cookie': 'trading_session=valid', 'Origin': 'https://workspace.example'}).status_code == 200
    assert client.get('/recorder/api/journal', headers={'Cookie': 'trading_session=valid', 'Host': 'evil.example'}).status_code == 403


def test_verifier_failure_denies_access(hosted, monkeypatch):
    client, module = hosted
    class Offline:
        async def __aenter__(self):
            raise httpx.ConnectError('offline')
        async def __aexit__(self, *args):
            pass
    monkeypatch.setattr(module.httpx, 'AsyncClient', lambda **kwargs: Offline())
    assert client.get('/recorder/api/journal', headers={'Cookie': 'trading_session=valid'}).status_code == 401


def test_recorded_fills_plans_and_annotations(hosted):
    client, module = hosted
    headers = {'Cookie': 'trading_session=valid', 'Origin': 'https://workspace.example'}
    for oid, side, price in [('buy', 'BUY', 100), ('sell', 'SELL', 110)]:
        module.ingest(dict(orderId=oid, tradingSymbol='NIFTY-Oct2026-25000-CE', securityId='123',
            exchangeSegment='NSE_FNO', productType='INTRADAY', transactionType=side,
            quantity=50, filledQty=50, orderStatus='TRADED', drvOptionType='CE',
            createTime='2026-10-26 09:20:00'), 'test')
        module.save('fills', oid, dict(id=oid, order=oid, time='2026-10-26 09:20:00' if oid == 'buy' else '2026-10-26 09:21:00',
            day='2026-10-26', security='123', segment='NSE_FNO', symbol='NIFTY-Oct2026-25000-CE', side=side, qty=50, price=price))
    result = client.get('/recorder/api/journal?day=2026-10-26', headers=headers).json()
    trade = result['trades'][0]
    assert trade['pnl'] == 500
    assert trade['status'] == 'CLOSED'
    assert client.post('/recorder/api/plans', headers=headers, json={'trade': trade['id'], 'role': 'stop', 'price': 95}).status_code == 200
    assert client.put('/recorder/api/assign/sell', headers=headers, json={'trade': trade['id'], 'purpose': 'target', 'notes': 'Reviewed exit'}).status_code == 200
    saved = client.get('/recorder/api/journal?day=2026-10-26', headers=headers).json()
    assert saved['trades'][0]['protection']['planned']['stop'] == 95
    assert saved['edits'][0]['notes'] == 'Reviewed exit'
    assert saved['trades'][0]['pnl'] == 500
    assert client.post('/recorder/api/plans', headers=headers, json={'trade': 'missing', 'role': 'stop', 'price': 95}).status_code == 404
    assert len(client.get('/recorder/api/events/buy', headers=headers).json()) == 1


def test_account_binding_and_memory_only_token(hosted, monkeypatch):
    import asyncio
    client, module = hosted
    headers = {'Cookie': 'trading_session=valid', 'Origin': 'https://workspace.example'}
    async def reconcile():
        pass
    async def background():
        await asyncio.Event().wait()
    monkeypatch.setattr(module, 'reconcile', reconcile)
    monkeypatch.setattr(module, 'stream', background)
    monkeypatch.setattr(module, 'poll', background)
    secret = 'example-not-a-real-token'
    assert client.post('/recorder/api/connect', headers=headers, json={'client': ' 123 ', 'token': secret}).status_code == 200
    assert module.token == secret
    assert secret not in client.get('/recorder/api/journal', headers=headers).text
    assert client.post('/recorder/api/disconnect', headers=headers).status_code == 200
    assert module.token is None
    assert client.post('/recorder/api/connect', headers=headers, json={'client': '456', 'token': secret}).status_code == 400
