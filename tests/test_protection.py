from protection import protection_history


def fixtures():
    trade = dict(id='t',security='1',segment='NSE_FNO',day='2026-10-22',direction=1,
                 status='CLOSED',legs=[dict(order='entry',role='entry',time='2026-10-22 10:00:00'),
                                           dict(order='exit',role='exit',time='2026-10-22 11:00:00')])
    order = dict(id='sl',security='1',segment='NSE_FNO',day='2026-10-22',side='SELL',
                 type='STOP_LOSS',created='2026-10-22 10:01:00')
    return trade, order


def event(price, trigger, time, status='PENDING', websocket=False):
    raw = dict(orderId='sl',price=price,triggerPrice=trigger,updateTime=time,orderStatus=status)
    if websocket:
        raw = dict(OrderNo='sl',Price=price,TriggerPrice=trigger,LastUpdatedTime=time,Status=status)
    return dict(payload=raw,received=time,source='websocket' if websocket else 'rest_snapshot')


def test_breakeven_modification_and_cancel_are_preserved_without_duplicate_snapshot():
    t,o = fixtures()
    events=[event(79,80,'2026-10-22 10:01:00'),event(79,80,'2026-10-22 10:01:00',websocket=True),
            event(99,100,'2026-10-22 10:30:00',websocket=True),
            event(79,80,'2026-10-22 10:01:00'),
            event(99,100,'2026-10-22 10:31:00','CANCELLED')]
    p=protection_history([t],[o],[],events,[])['t']['orders'][0]
    assert p['confidence']=='suggested'
    assert [x['trigger'] for x in p['history']]==[80,100,100]
    assert p['history'][-1]['status']=='CANCELLED'


def test_planned_only_levels_and_clear_keep_audit_trail():
    t,_=fixtures()
    plans=[dict(trade='t',role='stop',price=80),dict(trade='t',role='stop',price=100),
           dict(trade='t',role='target',price=140),dict(trade='t',role='target',price=None)]
    p=protection_history([t],[],[],[],plans)['t']
    assert p['planned']=={'stop':100,'target':None}
    assert len(p['plan_history'])==4
    assert p['orders']==[]


def test_manual_assignment_overrides_inference_and_ambiguous_trade_not_linked():
    t,o=fixtures()
    t2={**t,'id':'other'}
    assert not protection_history([t,t2],[o],[],[],[])['t']['orders']
    edits=[dict(order='sl',trade='other',role='target')]
    result=protection_history([t,t2],[o],edits,[],[])
    assert not result['t']['orders']
    assert result['other']['orders'][0]['role']=='target'
    assert result['other']['orders'][0]['confidence']=='confirmed'
