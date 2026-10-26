from engine import group_fills


def fill(id, side, qty, price, security='1'):
    return dict(id=str(id),order=str(id),time=f'2026-10-22 09:{id:02}:00',
                day='2026-10-22',segment='NSE_FNO',security=security,
                symbol='NIFTY 25000 CE',side=side,qty=qty,price=price)


def test_scale_and_partial_exit_fifo():
    t = group_fills([fill(1,'BUY',100,10), fill(2,'BUY',50,20), fill(3,'SELL',120,30)])[0]
    assert t['pnl'] == 2200
    assert t['net'] == 30


def test_reversal_splits_execution():
    trades = group_fills([fill(1,'BUY',50,10),fill(2,'SELL',100,20),fill(3,'BUY',50,15)])
    assert [t['pnl'] for t in trades] == [500,250]
    assert all(t['status']=='CLOSED' for t in trades)
    assert sum(l['qty'] for t in trades for l in t['legs'] if l['order']=='2') == 100


def test_reentry_and_contracts_are_separate():
    assert len(group_fills([fill(1,'BUY',1,10),fill(2,'SELL',1,12),fill(3,'BUY',1,11),fill(4,'BUY',1,5,'2')])) == 3


def test_input_unchanged_and_repeatable():
    fs=[fill(1,'SELL',5,12),fill(2,'BUY',3,10)]
    assert group_fills(fs) == group_fills(fs)
    assert fs[0]['qty']==5
    assert group_fills(fs)[0]['pnl']==6
