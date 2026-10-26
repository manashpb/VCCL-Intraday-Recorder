import os
import asyncio
import contextlib
import hashlib
import json
import re
import sqlite3
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import websockets
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from engine import group_fills
from protection import protection_history
from classification import classify, exit_purpose

ROOT = Path(__file__).parent
IST = ZoneInfo('Asia/Kolkata')
DATA = Path(os.environ.get('RECORDER_DATA_DIR', str(ROOT / 'data')))
DATA.mkdir(parents=True, exist_ok=True)
# All database work is synchronous and runs in one worker; allow ASGI lifespan
# and test-client threads to own the same connection.
db = sqlite3.connect(DATA / 'journal.sqlite3', check_same_thread=False)
db.execute('PRAGMA journal_mode=WAL')
db.executescript('''
CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, received TEXT, source TEXT, hash TEXT UNIQUE, payload TEXT);
CREATE TABLE IF NOT EXISTS orders(id TEXT PRIMARY KEY, payload TEXT);
CREATE TABLE IF NOT EXISTS fills(id TEXT PRIMARY KEY, payload TEXT);
CREATE TABLE IF NOT EXISTS edits(id TEXT PRIMARY KEY, payload TEXT);
CREATE TABLE IF NOT EXISTS plans(id INTEGER PRIMARY KEY, payload TEXT);
CREATE TABLE IF NOT EXISTS allocation_edits(id TEXT PRIMARY KEY, payload TEXT);
''')
state = dict(connected=False, stream='Disconnected', error=None, last_sync=None, client=None)
token = None
tasks = []


def now():
    return datetime.now(IST).isoformat()


def today():
    return datetime.now(IST).date().isoformat()


def rows(table):
    return [json.loads(r[0]) for r in db.execute(f'SELECT payload FROM {table}')]


def save(table, id, payload):
    db.execute(f'INSERT OR REPLACE INTO {table} VALUES (?,?)', (id, json.dumps(payload)))
    db.commit()


def ingest(raw, source):
    raw = raw.get('Data', raw)
    oid = str(raw.get('orderId') or raw.get('OrderNo') or '')
    if not oid:
        return
    encoded = json.dumps(raw, sort_keys=True)
    db.execute('INSERT OR IGNORE INTO events(received,source,hash,payload) VALUES (?,?,?,?)',
               (now(), source, hashlib.sha256(encoded.encode()).hexdigest(), encoded))
    old = db.execute('SELECT payload FROM orders WHERE id=?', (oid,)).fetchone()
    o = json.loads(old[0]) if old else {}
    incoming_time = raw.get('updateTime') or raw.get('LastUpdatedTime')
    if incoming_time and o.get('time') and str(incoming_time) < str(o['time']):
        db.commit()
        return
    mappings = dict(symbol=('tradingSymbol','Symbol'), security=('securityId','SecurityId'),
        status=('orderStatus','Status'), side=('transactionType','TxnType'),
        product=('productType','Product'), type=('orderType','OrderType'), qty=('quantity','Quantity'),
        filled=('filledQty','TradedQty'), price=('price','Price'), trigger=('triggerPrice','TriggerPrice'),
        average=('averageTradedPrice','AvgTradedPrice'), time=('updateTime','LastUpdatedTime'),
        created=('createTime','OrderDateTime'), option=('drvOptionType','OptType'),
        parent=('parentOrderId','AlgoOrdNo'), leg=('legName','LegNo'))
    for name, keys in mappings.items():
        for k in keys:
            if raw.get(k) is not None:
                o[name] = raw[k]
                break
    o['id'] = oid
    o['segment'] = raw.get('exchangeSegment') or o.get('segment') or (('BSE' if raw.get('Exchange') == 'BSE' else 'NSE') + '_FNO')
    o['side'] = {'B':'BUY','S':'SELL'}.get(o.get('side'), o.get('side'))
    o['product'] = {'I':'INTRADAY'}.get(o.get('product'), o.get('product'))
    o['status'] = str(o.get('status','UNKNOWN')).upper()
    o['day'] = str(o.get('created') or o.get('time') or today())[:10]
    save('orders', oid, o)


def focused(o):
    return (o.get('product') == 'INTRADAY' and o.get('segment') in ('NSE_FNO','BSE_FNO')
            and re.match(r'^(NIFTY|SENSEX)(?:\d|[\s_-]|$)', o.get('symbol','').upper()) is not None
            and (o.get('option') in ('CE','PE','CALL','PUT') or re.search(r'(CE|PE|CALL|PUT)$', o.get('symbol','').upper()) is not None))


async def reconcile():
    async with httpx.AsyncClient(timeout=20) as client:
        headers = {'access-token': token}
        responses = []
        for endpoint in ('orders','trades'):
            r = await client.get('https://api.dhan.co/v2/' + endpoint, headers=headers)
            if r.status_code != 200:
                raise ValueError(f'Dhan {endpoint} returned HTTP {r.status_code}. Check token validity and permissions.')
            body = r.json()
            if not isinstance(body, list):
                raise ValueError(f'Dhan {endpoint} returned an unexpected response.')
            responses.append(body)
        for o in responses[0]:
            ingest(o, 'rest_snapshot')
        for f in responses[1]:
            oid = str(f['orderId'])
            exchange_id = f.get('exchangeTradeId')
            if not exchange_id:
                state['error'] = 'A fill lacks exchangeTradeId; skipped to avoid duplicate execution.'
                continue
            id = oid + ':' + str(exchange_id)
            time = f.get('exchangeTime') or f.get('createTime') or today()
            save('fills', id, dict(id=id, order=oid, time=time, day=time[:10],
                 security=str(f['securityId']), segment=f['exchangeSegment'],
                 symbol=f.get('tradingSymbol',''), side=f['transactionType'],
                 qty=int(f['tradedQuantity']), price=f['tradedPrice']))
        state['last_sync'] = now()


async def poll():
    while True:
        try:
            await reconcile()
        except Exception as e:
            state['error'] = str(e) if isinstance(e, ValueError) else 'Reconciliation failed; retrying.'
        await asyncio.sleep(5)


async def stream():
    delay = 1
    while True:
        try:
            state['stream'] = 'Connecting'
            async with websockets.connect('wss://api-order-update.dhan.co', ping_interval=20) as ws:
                await ws.send(json.dumps({'LoginReq': {'MsgCode':42, 'ClientId':state['client'], 'Token':token}, 'UserType':'SELF'}))
                state['stream'] = 'Socket open · awaiting updates'
                delay = 1
                await reconcile()
                async for message in ws:
                    body = json.loads(message)
                    if isinstance(body, dict) and isinstance(body.get('Data'), dict) and body['Data'].get('OrderNo'):
                        ingest(body, 'websocket')
                        state['stream'] = 'Receiving updates'
                    elif isinstance(body, dict) and ('error' in str(body.get('Type','')).lower()):
                        state['error'] = 'Dhan rejected the order stream. Check credentials.'
        except asyncio.CancelledError:
            raise
        except Exception:
            state['stream'] = 'Reconnecting'
        await asyncio.sleep(delay)
        delay = min(delay * 2, 30)


async def stop():
    global token
    for task in tasks:
        task.cancel()
    for task in tasks:
        with contextlib.suppress(asyncio.CancelledError):
            await task
    tasks.clear()
    token = None
    state.update(connected=False, stream='Disconnected', client=None)


@asynccontextmanager
async def lifespan(app):
    yield
    await stop()
    db.close()


app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


@app.middleware('http')
async def workspace_access(request: Request, call_next):
    from fastapi.responses import JSONResponse
    origin = os.environ.get('PORTAL_ORIGIN', 'http://127.0.0.1:5001')
    if request.headers.get('host', '').split(':')[0] not in ('127.0.0.1', 'localhost', 'testserver'):
        return JSONResponse({'detail': 'Loopback access only'}, status_code=403)
    if request.method not in ('GET', 'HEAD', 'OPTIONS') and request.headers.get('origin') != origin:
        return JSONResponse({'detail': 'Invalid request origin'}, status_code=403)
    try:
        async with httpx.AsyncClient(timeout=5) as verifier:
            verified = await verifier.get('http://127.0.0.1:5001/verify',
                headers={'Cookie': request.headers.get('cookie', '')})
        authenticated = verified.status_code == 204
    except httpx.HTTPError:
        authenticated = False
    if not authenticated:
        return JSONResponse({'detail': 'Workspace session expired. Sign in again.'}, status_code=401)
    response = await call_next(request)
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Content-Security-Policy'] = "default-src 'self'; style-src 'self' 'unsafe-inline'; frame-ancestors 'none'; form-action 'self'"
    return response


class Credentials(BaseModel):
    client: str = Field(min_length=1, max_length=100)
    token: str = Field(min_length=10, max_length=10000)


@app.post('/api/connect')
async def connect(c: Credentials):
    global token
    c.client = c.client.strip()
    if state['client'] and state['client'] != c.client:
        raise HTTPException(400, 'Disconnect before changing accounts. Use a separate project/data folder for another account.')
    account = DATA / 'account.txt'
    fingerprint = hashlib.sha256(c.client.encode()).hexdigest()
    if account.exists() and account.read_text() != fingerprint:
        raise HTTPException(400, 'This journal belongs to another account. Use a separate data folder.')
    await stop()
    token = c.token.strip()
    state.update(client=c.client.strip(), error=None)
    try:
        await reconcile()
    except Exception as e:
        await stop()
        raise HTTPException(400, str(e) if isinstance(e, ValueError) else 'Cannot reach Dhan. Check your connection.')
    account.write_text(fingerprint)
    state['connected'] = True
    tasks.extend([asyncio.create_task(stream()), asyncio.create_task(poll())])
    return state


@app.post('/api/disconnect')
async def disconnect():
    await stop()
    return state


@app.get('/api/journal')
async def journal(day: str | None = None):
    day = day or today()
    orders = [o for o in rows('orders') if o['day'] == day and focused(o)]
    ids = {o['id'] for o in orders}
    fills = [f for f in rows('fills') if f['order'] in ids and f['day'] == day]
    trades = group_fills(fills)
    captured = [dict(received=r[0], source=r[1], payload=json.loads(r[2])) for r in db.execute(
        'SELECT received,source,payload FROM events ORDER BY id')]
    protections = protection_history(trades, orders, rows('edits'), captured, rows('plans'))
    for t in trades:
        t['protection'] = protections[t['id']]
    classify(trades, orders, rows('edits'), rows('allocation_edits'))
    return dict(state=state, day=day, orders=orders, trades=trades, edits=rows('edits'),
                allocation_edits=rows('allocation_edits'),
                events=db.execute('SELECT count(*) FROM events').fetchone()[0])


class AllocationEdit(BaseModel):
    trade: str = Field(max_length=200)
    fill: str = Field(max_length=200)
    purpose: str = Field(pattern='^(inherit|stop|target|discretionary|unknown)$')
    breakeven: bool = False


class Edit(BaseModel):
    trade: str = Field(max_length=200)
    purpose: str = Field(pattern='^(stop|target|discretionary|unknown)$')
    breakeven: bool = False
    notes: str = Field(default='', max_length=5000)
    allocations: list[AllocationEdit] = Field(default_factory=list, max_length=500)


class Plan(BaseModel):
    trade: str = Field(min_length=1, max_length=200)
    role: str = Field(pattern='^(stop|target)$')
    price: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    notes: str = Field(default='', max_length=2000)


@app.post('/api/plans')
async def plan(p: Plan):
    fills = rows('fills')
    if p.trade not in {t['id'] for t in group_fills(fills)}:
        raise HTTPException(404, 'Trade not found')
    payload = dict(**p.model_dump(), time=now())
    db.execute('INSERT INTO plans(payload) VALUES (?)', (json.dumps(payload),))
    db.commit()
    return {'ok': True}


@app.put('/api/assign/{order_id}')
async def assign(order_id: str, edit: Edit):
    if not db.execute('SELECT 1 FROM orders WHERE id=?',(order_id,)).fetchone():
        raise HTTPException(404, 'Order not found')
    valid = {(t['id'], l['id']) for t in group_fills(rows('fills')) for l in t['legs']
             if l['order'] == order_id and l['role'] == 'exit'}
    for a in edit.allocations:
        if (a.trade, a.fill) not in valid:
            raise HTTPException(400, 'Exit allocation no longer exists. Refresh and try again.')
        if a.breakeven and a.purpose != 'stop':
            raise HTTPException(400, 'Breakeven adjustment requires stop-loss purpose.')
    if edit.breakeven and edit.purpose != 'stop':
        raise HTTPException(400, 'Breakeven adjustment requires stop-loss purpose.')
    payload = dict(order=order_id, **edit.model_dump(exclude={'allocations'}), updated=now())
    db.execute('INSERT OR REPLACE INTO edits VALUES (?,?)', (order_id, json.dumps(payload)))
    for a in edit.allocations:
        key = json.dumps([a.trade, a.fill])
        db.execute('INSERT OR REPLACE INTO allocation_edits VALUES (?,?)',
                   (key, json.dumps(dict(**a.model_dump(), order=order_id, updated=now()))))
    db.commit()
    return {'ok':True}


@app.get('/api/events/{order_id}')
async def events(order_id: str):
    return [dict(received=r[0],source=r[1],payload=json.loads(r[2])) for r in db.execute(
        "SELECT received,source,payload FROM events WHERE json_extract(payload,'$.orderId')=? OR json_extract(payload,'$.OrderNo')=? ORDER BY id DESC", (order_id,order_id))]


@app.get('/')
def index():
    return FileResponse(ROOT / 'static/index.html')


app.mount('/static', StaticFiles(directory=ROOT / 'static'), name='static')

service = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
service.mount('/recorder', app)
