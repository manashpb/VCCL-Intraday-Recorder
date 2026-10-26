from classification import classify
from engine import group_fills


def fill(id,side,qty,price):
    return dict(id=id,order=id,time='2026-10-22 10:00:0'+id,day='2026-10-22',
                segment='NSE_FNO',security='1',symbol='NIFTY',side=side,qty=qty,price=price)


def test_partial_exit_purpose_and_remaining_quantity():
    trades=group_fills([fill('1','BUY',65,100),fill('2','SELL',25,120)])
    orders=[dict(id='1'),dict(id='2'),dict(id='pending')]
    classify(trades,orders,[dict(order='2',purpose='target')],[])
    leg=trades[0]['legs'][-1]
    assert leg['purpose']=='target' and leg['partial_exit']
    assert leg['qty']==25 and leg['remaining_qty']==40
    assert orders[1]['effect']=='Exit'
    assert orders[2]['effect']=='Unfilled'


def test_reversal_exit_override_never_labels_new_entry():
    trades=group_fills([fill('1','BUY',65,100),fill('2','SELL',100,110)])
    orders=[dict(id='2')]
    override=dict(trade=trades[0]['id'],fill='2',purpose='stop',breakeven=True)
    classify(trades,orders,[dict(order='2',purpose='target')],[override])
    closing=trades[0]['legs'][-1]
    opening=trades[1]['legs'][0]
    assert closing['qty']==65 and closing['purpose']=='stop' and closing['breakeven']
    assert opening['qty']==35 and opening['purpose'] is None and not opening['breakeven']
    assert orders[0]['effect']=='Reversal'
    assert (orders[0]['entry_qty'],orders[0]['exit_qty'])==(35,65)


def test_inherit_and_legacy_edits():
    trades=group_fills([fill('1','SELL',10,100),fill('2','BUY',10,90)])
    edits=[dict(order='2',role='stop')]
    classify(trades,[],edits,[dict(trade=trades[0]['id'],fill='2',purpose='inherit')])
    assert trades[0]['legs'][-1]['purpose']=='stop'
    assert trades[0]['legs'][-1]['purpose_source']=='order default'


def test_distinct_closing_fills_can_have_different_purposes():
    first=fill('2','SELL',25,120)
    second={**fill('3','SELL',40,100),'order':'2'}
    trades=group_fills([fill('1','BUY',65,100),first,second])
    classify(trades,[],[dict(order='2',purpose='target')],
             [dict(trade=trades[0]['id'],fill='3',purpose='discretionary')])
    assert [l['purpose'] for l in trades[0]['legs']]==[None,'target','discretionary']
    assert trades[0]['pnl']==500
