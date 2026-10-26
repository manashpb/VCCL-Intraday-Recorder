"""Execution effects are calculated; purposes are journal annotations."""
def exit_purpose(edit):
    return edit.get('purpose', edit.get('role') if edit.get('role') in ('stop', 'target') else 'unknown')


def classify(trades, orders, edits, overrides):
    edits = {e['order']: e for e in edits}
    overrides = {(e['trade'], e['fill']): e for e in overrides}
    effects = {}
    for t in trades:
        links = {o['order']: o for o in t.get('protection', {}).get('orders', [])}
        remaining = 0
        for leg in t['legs']:
            remaining += leg['qty'] if leg['role'] == 'entry' else -leg['qty']
            leg['remaining_qty'] = remaining
            leg['partial_exit'] = leg['role'] == 'exit' and remaining > 0
            effects.setdefault(leg['order'], []).append(leg)
            if leg['role'] == 'entry':
                leg.update(purpose=None, breakeven=False, purpose_source='not applicable')
                continue
            override = overrides.get((t['id'], leg['id']))
            edit = edits.get(leg['order'])
            link = links.get(leg['order'])
            if override and override['purpose'] != 'inherit':
                purpose, source, be = override['purpose'], 'allocation override', override.get('breakeven', False)
            elif edit:
                purpose, source, be = exit_purpose(edit), 'order default', edit.get('breakeven', False)
            elif link:
                purpose, source, be = link['role'], link['confidence'], False
            else:
                purpose, source, be = 'unknown', 'unclassified', False
            leg.update(purpose=purpose, purpose_source=source, breakeven=bool(be and purpose == 'stop'))
    for o in orders:
        legs = effects.get(o['id'], [])
        kinds = {l['role'] for l in legs}
        o['effect'] = 'Reversal' if len(kinds) > 1 else ('Entry' if 'entry' in kinds else 'Exit' if 'exit' in kinds else 'Unfilled')
        o['entry_qty'] = sum(l['qty'] for l in legs if l['role'] == 'entry')
        o['exit_qty'] = sum(l['qty'] for l in legs if l['role'] == 'exit')
