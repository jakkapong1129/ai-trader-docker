#!/usr/bin/env python3
"""
🧠 AI Trader — LLM Test
Test the mimo-text @ 9router decision maker
"""
import sys
import json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from modules.llm_decision import LLMDecisionMaker, parse_llm_response
from modules.rsi_strategy import calc_rsi, calc_ema, calc_atr, detect_trend, detect_candle_pattern
import random


def generate_candles(n=200, base=1.1000, trend_bias=0.0001):
    """Generate realistic candle data"""
    candles = []
    price = base
    for i in range(n):
        change = random.gauss(trend_bias, 0.0008)
        open_p = price
        close_p = price + change
        high = max(open_p, close_p) + abs(random.gauss(0, 0.0003))
        low = min(open_p, close_p) - abs(random.gauss(0, 0.0003))
        candles.append({
            "open": open_p, "close": close_p,
            "min": low, "max": high,
            "from": i * 60, "to": (i + 1) * 60,
        })
        price = close_p
    return candles


def make_oversold_scenario():
    """Generate candles where RSI drops below 30 (CALL signal)"""
    candles = generate_candles(180, 1.1000, 0.0001)
    # Add a sharp drop at the end
    price = candles[-1]["close"]
    for i in range(20):
        drop = random.uniform(-0.0015, -0.0005)
        open_p = price
        close_p = price + drop
        candles.append({
            "open": open_p, "close": close_p,
            "min": min(open_p, close_p) - 0.0002,
            "max": max(open_p, close_p) + 0.0001,
            "from": (180 + i) * 60, "to": (181 + i) * 60,
        })
        price = close_p
    return candles


def make_overbought_scenario():
    """Generate candles where RSI rises above 70 (PUT signal)"""
    candles = generate_candles(180, 1.1000, -0.0001)
    # Add a sharp rise at the end
    price = candles[-1]["close"]
    for i in range(20):
        rise = random.uniform(0.0005, 0.0015)
        open_p = price
        close_p = price + rise
        candles.append({
            "open": open_p, "close": close_p,
            "min": min(open_p, close_p) - 0.0001,
            "max": max(open_p, close_p) + 0.0002,
            "from": (180 + i) * 60, "to": (181 + i) * 60,
        })
        price = close_p
    return candles


def calc_indicators(candles):
    """Calculate all indicators for a set of candles"""
    closes = [c["close"] for c in candles]
    
    rsi_vals = calc_rsi(closes, 14)
    ema_fast = calc_ema(closes, 9)
    ema_slow = calc_ema(closes, 21)
    atr_vals = calc_atr(candles, 14)
    trend = detect_trend(closes)
    pattern = detect_candle_pattern(candles)
    
    # Bollinger Bands
    bb_period = 20
    if len(closes) >= bb_period:
        import statistics
        recent = closes[-bb_period:]
        mid = statistics.mean(recent)
        std = statistics.stdev(recent)
        bb_upper = mid + 2 * std
        bb_lower = mid - 2 * std
    else:
        mid = bb_upper = bb_lower = 0

    return {
        "rsi": rsi_vals[-1] if rsi_vals else 0,
        "ema_fast": ema_fast[-1] if ema_fast else 0,
        "ema_slow": ema_slow[-1] if ema_slow else 0,
        "atr": atr_vals[-1] if atr_vals else 0,
        "trend": trend,
        "pattern": pattern,
        "bb_upper": bb_upper,
        "bb_lower": bb_lower,
        "bb_mid": mid,
        "recent_candles": candles[-10:],
    }


def main():
    print("""
╔═══════════════════════════════════════════╗
║   🧠 AI Trader — LLM Decision Test      ║
║   Model: mimo-text @ 9router             ║
╚═══════════════════════════════════════════╝
""")

    maker = LLMDecisionMaker()

    # === Test 1: Oversold Scenario (should CALL) ===
    print("=" * 50)
    print("🧪 TEST 1: RSI Oversold Scenario (EURCAD)")
    print("=" * 50)
    
    candles = make_oversold_scenario()
    indicators = calc_indicators(candles)
    
    print(f"  RSI: {indicators['rsi']:.1f}")
    print(f"  Trend: {indicators['trend']}")
    print(f"  Pattern: {indicators['pattern']}")
    print(f"  EMA Fast: {indicators['ema_fast']:.5f}")
    print(f"  EMA Slow: {indicators['ema_slow']:.5f}")
    print()

    trade_history = {
        "win_rate": "63.2%",
        "win_rate_30d": "67.1%",
        "total_trades": 245,
        "best_session": "morning",
        "confidence": 72,
        "strategy": "rsi_reversal",
    }

    result = maker.analyze("EURCAD", indicators, trade_history)
    
    print(f"\n  🤖 LLM Decision:")
    print(f"  Action: {result['action']}")
    print(f"  Confidence: {result['confidence']}")
    print(f"  Reason: {result['reason']}")
    print(f"  Risk: {result['risk_factors']}")
    print()

    # === Test 2: Overbought Scenario (should PUT) ===
    print("=" * 50)
    print("🧪 TEST 2: RSI Overbought Scenario (GBPCAD)")
    print("=" * 50)
    
    candles = make_overbought_scenario()
    indicators = calc_indicators(candles)
    
    print(f"  RSI: {indicators['rsi']:.1f}")
    print(f"  Trend: {indicators['trend']}")
    print(f"  Pattern: {indicators['pattern']}")
    print()

    result = maker.analyze("GBPCAD", indicators, trade_history)
    
    print(f"\n  🤖 LLM Decision:")
    print(f"  Action: {result['action']}")
    print(f"  Confidence: {result['confidence']}")
    print(f"  Reason: {result['reason']}")
    print(f"  Risk: {result['risk_factors']}")
    print()

    # === Test 3: Neutral Scenario (should NO_TRADE) ===
    print("=" * 50)
    print("🧪 TEST 3: Neutral Scenario (EURGBP)")
    print("=" * 50)
    
    candles = generate_candles(200, 1.1000, 0.0)
    indicators = calc_indicators(candles)
    
    print(f"  RSI: {indicators['rsi']:.1f}")
    print(f"  Trend: {indicators['trend']}")
    print(f"  Pattern: {indicators['pattern']}")
    print()

    result = maker.analyze("EURGBP", indicators)
    
    print(f"\n  🤖 LLM Decision:")
    print(f"  Action: {result['action']}")
    print(f"  Confidence: {result['confidence']}")
    print(f"  Reason: {result['reason']}")
    print(f"  Risk: {result['risk_factors']}")

    print(f"\n✅ LLM Test complete! Total API calls: {maker.call_count}")


if __name__ == "__main__":
    main()
