from pathlib import Path


DASHBOARD = Path(__file__).resolve().parents[1] / "dashboard-command-deck.html"


def test_asset_scanner_ignores_partial_updates():
    source = DASHBOARD.read_text()

    assert "if (assets.length < scannerAssetCache.size) return;" in source


def test_asset_scanner_updates_cards_by_asset_name_not_array_position():
    source = DASHBOARD.read_text()

    assert "scannerAssetCache.set(asset.name, asset);" in source
    assert "scannerGrid.querySelector(`[data-asset-name=\"${asset.name}\"]`)" in source
