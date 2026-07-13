import ast
from pathlib import Path

SOURCE = Path("auto_loop.py")


def _assignment(name):
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            return ast.literal_eval(node.value)
    raise AssertionError(f"missing assignment: {name}")


def test_gbpjpy_is_replaced_by_gbpnzd():
    assets = _assignment("TRADE_ASSETS")
    params = _assignment("ASSET_PARAMS")
    assert "GBPJPY" not in assets
    assert 84 not in params
    assert assets["GBPNZD"] == 2132
    assert params[2132] == {"rsi_ob": 70, "rsi_os": 28}
