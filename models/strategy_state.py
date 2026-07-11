"""
🧠 AI Trader — Strategy State Model
Tracks optimized parameters per strategy per asset
"""
from dataclasses import dataclass, asdict
from typing import Optional
from datetime import datetime


@dataclass
class StrategyState:
    """
    Stores the AI-optimized parameters for a strategy on a specific asset.
    Updated by the Strategy Learner after enough data.
    """
    id: Optional[int] = None
    strategy_name: str = ""       # e.g. "rsi_reversal"
    asset_name: str = ""          # e.g. "EURCAD"
    
    # Optimized parameters (RSI Reversal)
    rsi_period: int = 14
    rsi_ob: float = 70.0          # Overbought threshold
    rsi_os: float = 30.0          # Oversold threshold
    
    # Optimized parameters (EMA Cross)
    ema_fast_period: int = 9
    ema_slow_period: int = 21
    
    # Optimized parameters (Bollinger Bands)
    bb_period: int = 20
    bb_std: float = 2.0
    
    # ATR
    atr_period: int = 14
    
    # Performance tracking
    win_rate: float = 0.0
    total_trades: int = 0
    confidence_score: float = 50.0   # How much AI trusts this config
    last_30d_wr: float = 0.0         # Recent win rate
    
    # Metadata
    last_optimized: str = ""
    optimization_count: int = 0

    def __post_init__(self):
        if not self.last_optimized:
            self.last_optimized = datetime.now().isoformat()

    def to_dict(self) -> dict:
        return asdict(self)

    def is_stale(self, min_trades: int = 100) -> bool:
        """Check if parameters need re-optimization"""
        return self.total_trades - (self.optimization_count * min_trades) >= min_trades
