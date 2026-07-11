"""
🧠 AI Trader — Asset Configuration
Assets optimized from backtest results
"""

# Top assets from RSI Reversal backtest
# Format: asset_id -> {name, best_ob, best_os, notes}
TOP_ASSETS = {
    # asset_id: {name, ob, os, priority}
    "EURCAD":  {"ob": 75, "os": 28, "priority": 1, "note": "Top performer"},
    "GBPCAD":  {"ob": 75, "os": 22, "priority": 2, "note": "Consistent"},
    "GBPNZD":  {"ob": 70, "os": 28, "priority": 3, "note": "High WR"},
    "EURGBP":  {"ob": 75, "os": 30, "priority": 4, "note": "Stable"},
    "EURCHF":  {"ob": 70, "os": 30, "priority": 5, "note": "Good signals"},
}

# Blacklisted assets (bad backtest results)
BLACKLISTED_ASSETS = ["GBPCHF", "EURNZD", "AUDCHF", "AUDNZD", "AUDUSD", "GBPAUD"]

# Asset name to IQ Option asset_id mapping
# Will be populated at runtime from MCP list_assets
ASSET_ID_MAP = {}
