import ast
import re
from pathlib import Path

# Extract the pure predicate without opening the production journal database.
source = ast.parse((Path(__file__).parents[1] / 'app.py').read_text())
predicate = next(node for node in source.body if isinstance(node, ast.FunctionDef) and node.name == 'focused')
namespace = {'re': re}
exec(compile(ast.Module(body=[predicate], type_ignores=[]), 'focused', 'exec'), namespace)
focused = namespace['focused']


def order(symbol, **changes):
    return dict(symbol=symbol, product='INTRADAY', segment='NSE_FNO', option='PUT', **changes)


def test_dhan_hyphenated_symbols():
    assert focused(order('NIFTY-Oct2026-22800-PE'))
    assert focused(order('SENSEX-Oct2026-80000-CE'))


def test_other_indices_and_products_excluded():
    assert not focused(order('NIFTYNXT50-Oct2026-22800-PE'))
    assert not focused(order('BANKNIFTY-Oct2026-22800-PE'))
    o = order('NIFTY-Oct2026-22800-PE')
    o['product'] = 'MARGIN'
    assert not focused(o)


def test_supported_symbol_formats():
    assert focused(order('NIFTY 22800 PE'))
    assert focused(order('NIFTY26OCT22800PE'))
