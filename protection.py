"""Journal protection levels, with conservative broker-order linking."""
from classification import exit_purpose
def protection_history(trades, orders, edits, events, plans):
    edits = {e['order']: e for e in edits}
    observed_stops = set()
    for e in events:
        raw = e['payload']
        if raw.get('orderType', raw.get('OrderType')) in ('SL', 'SLM', 'STOP_LOSS', 'STOP_LOSS_MARKET'):
            observed_stops.add(str(raw.get('orderId') or raw.get('OrderNo') or ''))
    linked = {}
    for o in orders:
        edit = edits.get(o['id'])
        if edit:
            purpose = exit_purpose(edit)
            if purpose in ('stop', 'target') and edit['trade']:
                linked[o['id']] = (edit['trade'], purpose, 'confirmed')
            continue
        leg = str(o.get('leg', ''))
        role = ('target' if leg in ('3', 'TARGET_LEG') else
                'stop' if leg in ('2', 'STOP_LOSS_LEG') or o.get('type') in
                ('SL', 'SLM', 'STOP_LOSS', 'STOP_LOSS_MARKET') or o['id'] in observed_stops else None)
        if not role:
            continue
        candidates = []
        for t in trades:
            if str(o.get('security')) != str(t['security']) or o.get('segment') != t['segment'] or o['day'] != t['day']:
                continue
            if o.get('side') != ('SELL' if t['direction'] == 1 else 'BUY'):
                continue
            start, end = t['legs'][0]['time'], t['legs'][-1]['time']
            created = o.get('created') or o.get('time', '')
            parent = str(o.get('parent') or '')
            if parent and parent in {l['order'] for l in t['legs'] if l['role'] == 'entry'}:
                candidates = [t]
                break
            if start <= created and (t['status'] == 'OPEN' or created <= end):
                candidates.append(t)
        if len(candidates) == 1:
            linked[o['id']] = (candidates[0]['id'], role, 'suggested')
    result = {t['id']: {'planned': {}, 'plan_history': [], 'orders': []} for t in trades}
    for p in plans:
        if p['trade'] in result:
            r = result[p['trade']]
            r['planned'][p['role']] = p['price']
            r['plan_history'].append(p)
    for oid, (tid, role, confidence) in linked.items():
        if tid not in result:
            continue
        history, last, last_time = [], None, ''
        for e in events:
            raw = e['payload']
            if str(raw.get('orderId') or raw.get('OrderNo') or '') != oid:
                continue
            time = raw.get('updateTime') or raw.get('LastUpdatedTime') or e['received']
            if time < last_time:
                continue
            price = raw.get('price', raw.get('Price', 0)) or 0
            trigger = raw.get('triggerPrice', raw.get('TriggerPrice', 0)) or 0
            status = str(raw.get('orderStatus') or raw.get('Status') or '').upper()
            current = (float(price), float(trigger), status)
            if current != last:
                history.append(dict(time=time, received=e['received'], source=e['source'],
                                    price=current[0], trigger=current[1], status=status))
                last = current
            last_time = time
        result[tid]['orders'].append(dict(order=oid, role=role, confidence=confidence, history=history))
    return result
