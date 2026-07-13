"""
🧠 AI Trader — RSI Reversal Strategy
The proven profitable strategy from backtesting
"""
from typing import Optional
from core.base_strategy import BaseStrategy, Signal


def calc_rsi(closes: list[float], period: int = 14) -> list[float]:
    """Calculate RSI values"""
    if len(closes) < period + 1:
        return []

    rsi_values = []
    gains = []
    losses = []

    for i in range(1, len(closes)):
        change = closes[i] - closes[i-1]
        gains.append(max(0, change))
        losses.append(max(0, -change))

    # Initial average
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    def current_rsi() -> float:
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))

    rsi_values.append(current_rsi())
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        rsi_values.append(current_rsi())

    return rsi_values


def calc_ema(values: list[float], period: int) -> list[float]:
    """Calculate EMA"""
    if len(values) < period:
        return []

    ema = [sum(values[:period]) / period]
    multiplier = 2 / (period + 1)

    for i in range(period, len(values)):
        ema.append((values[i] - ema[-1]) * multiplier + ema[-1])

    return ema


def calc_atr(candles: list[dict], period: int = 14) -> list[float]:
    """Calculate ATR"""
    if len(candles) < period + 1:
        return []

    true_ranges = []
    for i in range(1, len(candles)):
        high = candles[i]["max"]
        low = candles[i]["min"]
        prev_close = candles[i-1]["close"]
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        true_ranges.append(tr)

    atr = [sum(true_ranges[:period]) / period]
    for i in range(period, len(true_ranges)):
        atr.append((atr[-1] * (period - 1) + true_ranges[i]) / period)

    return atr


def detect_trend(closes: list[float], fast_period: int = 9, 
                 slow_period: int = 21) -> str:
    """Detect trend direction"""
    if len(closes) < slow_period:
        return "sideways"

    fast_ema = calc_ema(closes, fast_period)
    slow_ema = calc_ema(closes, slow_period)

    if not fast_ema or not slow_ema:
        return "sideways"

    if fast_ema[-1] > slow_ema[-1]:
        return "up"
    elif fast_ema[-1] < slow_ema[-1]:
        return "down"
    return "sideways"


def detect_candle_pattern(candles: list[dict]) -> str:
    """Detect recent candle patterns"""
    if len(candles) < 3:
        return "none"

    c = candles[-1]
    prev = candles[-2]

    body = c["close"] - c["open"]
    prev_body = prev["close"] - prev["open"]

    # Bullish engulfing
    if prev_body < 0 and body > 0 and abs(body) > abs(prev_body):
        return "bullish_engulfing"

    # Bearish engulfing
    if prev_body > 0 and body < 0 and abs(body) > abs(prev_body):
        return "bearish_engulfing"

    # Doji (small body)
    if abs(body) < (c["max"] - c["min"]) * 0.1:
        return "doji"

    # Hammer (long lower wick)
    lower_wick = min(c["open"], c["close"]) - c["min"]
    upper_wick = c["max"] - max(c["open"], c["close"])
    if lower_wick > abs(body) * 2 and upper_wick < abs(body) * 0.5:
        return "hammer"

    # Shooting star (long upper wick)
    if upper_wick > abs(body) * 2 and lower_wick < abs(body) * 0.5:
        return "shooting_star"

    return "none"


class RSIReversalStrategy(BaseStrategy):
    """
    RSI Reversal Strategy
    
    Logic:
    - RSI crosses below oversold → BUY CALL (expect reversal up)
    - RSI crosses above overbought → BUY PUT (expect reversal down)
    - Enhanced with EMA trend filter + candle pattern
    """

    name = "rsi_reversal"

    def get_default_params(self) -> dict:
        return {
            "rsi_period": 14,
            "rsi_ob": 70,       # Overbought
            "rsi_os": 30,        # Oversold
            "ema_fast": 9,
            "ema_slow": 21,
            "atr_period": 14,
            "rsi_reentry_margin": 5,
            "rsi_rebound_min": 1.5,
        }

    def get_param_ranges(self) -> dict:
        return {
            "rsi_period": (5, 21),
            "rsi_ob": (60, 85),
            "rsi_os": (15, 40),
            "ema_fast": (5, 15),
            "ema_slow": (15, 30),
        }

    def analyze(self, candles: list[dict], params: dict = None) -> Optional[Signal]:
        p = params or self.get_default_params()
        
        if len(candles) < max(p["rsi_period"], p.get("ema_slow", 21)) + 5:
            return None

        closes = [c["close"] for c in candles]
        
        # Calculate RSI
        rsi_vals = calc_rsi(closes, p["rsi_period"])
        if not rsi_vals or len(rsi_vals) < 3:
            return None

        current_rsi = rsi_vals[-1]
        prev_rsi = rsi_vals[-2]

        # Calculate trend
        trend = detect_trend(closes, p.get("ema_fast", 9), p.get("ema_slow", 21))
        
        # Calculate ATR for volatility
        atr_vals = calc_atr(candles, p.get("atr_period", 14))
        current_atr = atr_vals[-1] if atr_vals else 0
        avg_atr = sum(atr_vals[-20:]) / min(20, len(atr_vals)) if atr_vals else 1
        volatility = current_atr / avg_atr if avg_atr > 0 else 1

        # Candle pattern
        pattern = detect_candle_pattern(candles)

        # === SIGNAL LOGIC ===
        signal = None

        setup_type = ""

        if prev_rsi < p["rsi_os"] and current_rsi >= p["rsi_os"]:
            setup_type = "primary_cross"
            confidence = self._calc_confidence(
                rsi=current_rsi, previous_rsi=prev_rsi, threshold=p["rsi_os"],
                trend=trend, favorable_trend="up",
                pattern=pattern, favorable_patterns=["bullish_engulfing", "hammer"],
                volatility=volatility,
                direction="call", setup_type=setup_type,
            )
            if confidence > 0:
                signal = Signal(
                    direction="call",
                    confidence=confidence,
                    strategy_name=self.name,
                    reason=f"RSI {current_rsi:.1f} crossing above OS {p['rsi_os']}, trend={trend}, pattern={pattern}",
                    indicators={
                        "rsi": current_rsi, "prev_rsi": prev_rsi, "trend": trend,
                        "atr": current_atr, "pattern": pattern,
                        "volatility": volatility, "setup_type": setup_type,
                    }
                )

        elif prev_rsi > p["rsi_ob"] and current_rsi <= p["rsi_ob"]:
            setup_type = "primary_cross"
            confidence = self._calc_confidence(
                rsi=current_rsi, previous_rsi=prev_rsi, threshold=p["rsi_ob"],
                trend=trend, favorable_trend="down",
                pattern=pattern, favorable_patterns=["bearish_engulfing", "shooting_star"],
                volatility=volatility,
                direction="put", setup_type=setup_type,
            )
            if confidence > 0:
                signal = Signal(
                    direction="put",
                    confidence=confidence,
                    strategy_name=self.name,
                    reason=f"RSI {current_rsi:.1f} crossing below OB {p['rsi_ob']}, trend={trend}, pattern={pattern}",
                    indicators={
                        "rsi": current_rsi, "prev_rsi": prev_rsi, "trend": trend,
                        "atr": current_atr, "pattern": pattern,
                        "volatility": volatility, "setup_type": setup_type,
                    }
                )

        else:
            margin = p.get("rsi_reentry_margin", 5)
            rebound_min = p.get("rsi_rebound_min", 1.5)
            current_candle = candles[-1]
            bullish_candle = current_candle["close"] > current_candle["open"]
            bearish_candle = current_candle["close"] < current_candle["open"]
            candle_range = current_candle["max"] - current_candle["min"]
            body_ratio = abs(current_candle["close"] - current_candle["open"]) / candle_range if candle_range > 0 else 0
            bullish_reversal = pattern in ("bullish_engulfing", "hammer")
            bearish_reversal = pattern in ("bearish_engulfing", "shooting_star")
            call_confirmation = bullish_reversal or (trend != "down" and body_ratio >= 0.25)
            put_confirmation = bearish_reversal or (trend != "up" and body_ratio >= 0.25)
            rsi_change = current_rsi - prev_rsi

            if (
                current_rsi <= p["rsi_os"] + margin
                and rsi_change >= rebound_min
                and bullish_candle
                and pattern != "doji"
                and call_confirmation
            ):
                setup_type = "secondary_reversal"
                confidence = self._calc_confidence(
                    rsi=current_rsi, previous_rsi=prev_rsi, threshold=p["rsi_os"],
                    trend=trend, favorable_trend="up",
                    pattern=pattern, favorable_patterns=["bullish_engulfing", "hammer"],
                    volatility=volatility,
                    direction="call", setup_type=setup_type,
                )
                signal = Signal(
                    direction="call",
                    confidence=confidence,
                    strategy_name=self.name,
                    reason=f"RSI rebound +{rsi_change:.1f} near OS {p['rsi_os']}, bullish confirmation, trend={trend}, pattern={pattern}",
                    indicators={
                        "rsi": current_rsi, "prev_rsi": prev_rsi, "trend": trend,
                        "atr": current_atr, "pattern": pattern,
                        "volatility": volatility, "setup_type": setup_type,
                    },
                )
            elif (
                current_rsi >= p["rsi_ob"] - margin
                and rsi_change <= -rebound_min
                and bearish_candle
                and pattern != "doji"
                and put_confirmation
            ):
                setup_type = "secondary_reversal"
                confidence = self._calc_confidence(
                    rsi=current_rsi, previous_rsi=prev_rsi, threshold=p["rsi_ob"],
                    trend=trend, favorable_trend="down",
                    pattern=pattern, favorable_patterns=["bearish_engulfing", "shooting_star"],
                    volatility=volatility,
                    direction="put", setup_type=setup_type,
                )
                signal = Signal(
                    direction="put",
                    confidence=confidence,
                    strategy_name=self.name,
                    reason=f"RSI rebound {rsi_change:.1f} near OB {p['rsi_ob']}, bearish confirmation, trend={trend}, pattern={pattern}",
                    indicators={
                        "rsi": current_rsi, "prev_rsi": prev_rsi, "trend": trend,
                        "atr": current_atr, "pattern": pattern,
                        "volatility": volatility, "setup_type": setup_type,
                    },
                )

        return signal

    def _calc_confidence(self, rsi: float, previous_rsi: float, threshold: float,
                         trend: str, favorable_trend: str,
                         pattern: str, favorable_patterns: list,
                         volatility: float, direction: str,
                         setup_type: str = "primary_cross") -> float:
        """Calculate confidence score 0-100"""
        score = 55.0 if setup_type == "primary_cross" else 48.0

        if direction == "call":
            score += min(15, max(0, (threshold - min(previous_rsi, rsi)) * 1.5))
        else:
            score += min(15, max(0, (max(previous_rsi, rsi) - threshold) * 1.5))

        score += min(10, abs(rsi - previous_rsi) * 1.5)

        if trend == favorable_trend:
            score += 3
        elif trend == "sideways":
            score += 8
        else:
            score -= 3

        # Candle pattern bonus
        if pattern in favorable_patterns:
            score += 10

        # Volatility adjustment
        if 0.8 < volatility < 1.5:
            score += 5  # Normal volatility = good
        elif volatility > 2.0:
            score -= 10  # Too volatile = risky

        return max(0, min(100, score))
