"""Deterministic, quantity-level flat-to-flat grouping and FIFO gross P&L."""
from decimal import Decimal


def group_fills(fills):
    active, result = {}, []
    for f in sorted(fills, key=lambda x: (x['time'], x['id'])):
        key = (f['day'], f['segment'], f['security'])
        remaining = int(f['qty'])
        direction = 1 if f['side'] == 'BUY' else -1
        while remaining:
            t = active.get(key)
            if t is None:
                t = dict(id='auto:' + f['id'] + ':' + str(remaining), symbol=f['symbol'],
                         security=f['security'], segment=f['segment'], day=f['day'],
                         direction=direction, net=0, pnl=Decimal(0), lots=[], legs=[])
                active[key] = t
                result.append(t)
            qty = remaining if not t['net'] or t['net'] * direction > 0 else min(remaining, abs(t['net']))
            price = Decimal(str(f['price']))
            role = 'entry' if t['net'] * direction >= 0 else 'exit'
            t['legs'].append({**f, 'qty': qty, 'role': role})
            if role == 'entry':
                t['lots'].append([qty, price])
            else:
                rest = qty
                while rest:
                    lot = t['lots'][0]
                    matched = min(rest, lot[0])
                    t['pnl'] += (price - lot[1]) * matched * t['direction']
                    lot[0] -= matched
                    rest -= matched
                    if not lot[0]:
                        t['lots'].pop(0)
            t['net'] += direction * qty
            remaining -= qty
            if not t['net']:
                del active[key]
    for t in result:
        t['pnl'] = float(t['pnl'])
        t['status'] = 'OPEN' if t['net'] else 'CLOSED'
        del t['lots']
    return result
