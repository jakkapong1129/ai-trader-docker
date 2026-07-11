"""
🧠 AI Trader — Trade Model
Represents a single trade record
"""
from datetime import datetime
from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class Trade:
    """Single trade record"""
    id: Optional[int] = None
    timestamp: str = ""
    asset_name: str = ""
    asset_id: int = 0
    strategy: str = ""          # e.g. "rsi_reversal", "ema_cross"
    direction: str = ""         # "call" or "put"
    amount: float = 0.0
    confidence: float = 0.0     # AI confidence score 0-100
    
    # Market conditions at entry
    rsi_value: float = 0.0
    ema_fast: float = 0.0
    ema_slow: float = 0.0
    bb_upper: float = 0.0
    bb_lower: float = 0.0
    bb_mid: float = 0.0
    atr_value: float = 0.0
    candle_pattern: str = ""    # e.g. "bullish_engulfing"
    trend_direction: str = ""   # "up", "down", "sideways"
    
    # Result
    result: str = ""            # "win", "loss", "equal", "pending"
    profit: float = 0.0
    close_price: float = 0.0
    close_time: str = ""
    broker_order_id: str = ""     # ID returned immediately by place_trade
    broker_position_id: str = ""  # Stable ID returned by the broker for reconciliation
    
    # ML context
    mg_level: int = 0           # Martingale level (0 = first bet)
    session_hour: int = 0       # Hour of trade (UTC+7)
    session_type: str = ""      # "morning", "afternoon", "evening", "night"
    account_type: str = "demo"  # "demo" or "real"

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()
        if not self.session_hour:
            self.session_hour = datetime.now().hour
        self.session_type = self._get_session_type()

    def _get_session_type(self) -> str:
        h = self.session_hour
        if 6 <= h < 12:
            return "morning"
        elif 12 <= h < 18:
            return "afternoon"
        elif 18 <= h < 24:
            return "evening"
        else:
            return "night"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class StrategyPerformance:
    """Aggregated performance of a strategy"""
    strategy_name: str
    asset_name: str = "ALL"
    total_trades: int = 0
    wins: int = 0
    losses: int = 0
    equals: int = 0
    win_rate: float = 0.0
    total_profit: float = 0.0
    avg_confidence: float = 0.0
    best_session: str = ""
    last_updated: str = ""

    def update_from_trades(self, trades: list[Trade]):
        self.total_trades = len(trades)
        self.wins = sum(1 for t in trades if t.result == "win")
        self.losses = sum(1 for t in trades if t.result == "loss")
        self.equals = sum(1 for t in trades if t.result == "equal")
        self.win_rate = self.wins / max(1, self.total_trades)
        self.total_profit = sum(t.profit for t in trades)
        self.avg_confidence = sum(t.confidence for t in trades) / max(1, self.total_trades)
        
        # Find best session
        sessions = {}
        for t in trades:
            s = t.session_type
            if s not in sessions:
                sessions[s] = {"w": 0, "t": 0}
            sessions[s]["t"] += 1
            if t.result == "win":
                sessions[s]["w"] += 1
        
        best = ""
        best_wr = 0
        for s, d in sessions.items():
            wr = d["w"] / max(1, d["t"])
            if wr > best_wr and d["t"] >= 10:
                best_wr = wr
                best = s
        self.best_session = best
        self.last_updated = datetime.now().isoformat()
