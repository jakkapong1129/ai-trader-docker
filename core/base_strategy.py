"""
🧠 AI Trader — Base Strategy
Abstract class for all trading strategies
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class Signal:
    """Trading signal from a strategy"""
    direction: str = ""        # "call" or "put"
    confidence: float = 0.0    # 0-100
    strategy_name: str = ""
    reason: str = ""
    indicators: dict = None    # Current indicator values

    def __post_init__(self):
        if self.indicators is None:
            self.indicators = {}

    @property
    def is_valid(self) -> bool:
        return self.direction in ("call", "put") and self.confidence > 0


class BaseStrategy(ABC):
    """Abstract base for all strategies"""

    name: str = "base"

    @abstractmethod
    def analyze(self, candles: list[dict], params: dict = None) -> Optional[Signal]:
        """
        Analyze candles and return a Signal or None.
        
        candles: list of {open, close, min, max, from, to}
        params: optimized parameters from StrategyState
        
        Returns: Signal if conditions met, None otherwise
        """
        pass

    @abstractmethod
    def get_default_params(self) -> dict:
        """Return default parameters for this strategy"""
        pass

    def get_param_ranges(self) -> dict:
        """Return parameter ranges for optimization"""
        return {}
