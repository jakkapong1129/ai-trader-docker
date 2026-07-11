"""
🧠 AI Trader — Settings
Configuration values loaded from environment variables.
"""
import os
from pathlib import Path

# === Paths ===
PROJECT_ROOT = Path(__file__).parent.parent
LOGS_DIR = PROJECT_ROOT / "logs"
REPORTS_DIR = PROJECT_ROOT / "reports"

# Ensure dirs exist
for d in [LOGS_DIR, REPORTS_DIR]:
    d.mkdir(exist_ok=True)

# === IQ Option Connection ===
IQ_EMAIL = os.getenv("IQ_EMAIL", "")
IQ_PASSWORD = os.getenv("IQ_PASSWORD", "")
IQ_BALANCE_TYPE = os.getenv("IQ_BALANCE_TYPE", "PRACTICE")  # PRACTICE or REAL

# === Trading Parameters ===
BASE_AMOUNT = float(os.getenv("BASE_AMOUNT", "30"))  # THB
MAX_MARTINGALE_LEVEL = int(os.getenv("MAX_MG_LEVEL", "4"))
MARTINGALE_MULTIPLIER = float(os.getenv("MG_MULTIPLIER", "2.0"))

# === AI Learning Parameters ===
MIN_TRADES_FOR_LEARNING = 50       # Min trades before AI adjusts
CONFIDENCE_THRESHOLD = 60          # Min confidence to trade (0-100)
WIN_RATE_DROP_THRESHOLD = 0.50     # Switch strategy if WR drops below
LOOKBACK_WINDOW = 200              # Trades to look back for learning
RE_OPTIMIZE_INTERVAL = 100         # Re-optimize every N trades

# === Candle Settings ===
CANDLE_SIZE = 60                   # 1 minute candles
CANDLE_COUNT = 200                 # History to fetch

# === Logging ===
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
