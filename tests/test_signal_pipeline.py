import unittest

from auto_loop import remember_processed_result
from modules.llm_decision import build_analysis_prompt, constrain_confirmation
from modules.rsi_strategy import RSIReversalStrategy, calc_rsi


def candles_from_closes(closes):
    candles = []
    previous_close = closes[0]
    for index, close in enumerate(closes):
        open_price = previous_close if index else close
        candles.append({
            "open": open_price,
            "close": close,
            "min": min(open_price, close) - 0.1,
            "max": max(open_price, close) + 0.1,
            "from": index * 300,
            "to": (index + 1) * 300,
        })
        previous_close = close
    return candles


class SignalPipelineTests(unittest.TestCase):
    def test_rsi_includes_latest_close(self):
        closes = [100, 101, 99, 102, 98, 103, 97, 104, 96, 105, 95, 106, 94, 107, 93, 108, 92, 109, 91, 110, 90]

        values = calc_rsi(closes, 14)

        self.assertEqual(len(values), len(closes) - 14)
        self.assertAlmostEqual(values[-1], 46.707790815620605)

    def test_secondary_reversal_creates_call_signal(self):
        closes = [100 + index * 0.1 for index in range(10)]
        price = closes[-1]
        for _ in range(20):
            price -= 1
            closes.append(price)
        closes.append(price + 0.7)

        candles = candles_from_closes(closes)
        candles[-1]["min"] = candles[-1]["open"] - 2
        candles[-1]["max"] = candles[-1]["close"] + 0.1

        signal = RSIReversalStrategy().analyze(candles)

        self.assertIsNotNone(signal)
        self.assertEqual(signal.direction, "call")
        self.assertEqual(signal.indicators["setup_type"], "secondary_reversal")
        self.assertGreater(signal.indicators["rsi"], signal.indicators["prev_rsi"])

    def test_secondary_reversal_rejects_doji(self):
        closes = [100 + index * 0.1 for index in range(10)]
        price = closes[-1]
        for _ in range(20):
            price -= 1
            closes.append(price)
        closes.append(price + 0.7)
        candles = candles_from_closes(closes)
        candles[-1]["min"] = candles[-1]["open"] - 4
        candles[-1]["max"] = candles[-1]["close"] + 4

        signal = RSIReversalStrategy().analyze(candles)

        self.assertIsNone(signal)

    def test_llm_cannot_reverse_math_direction(self):
        result = constrain_confirmation({
            "action": "PUT",
            "confidence": 90,
            "reason": "reverse",
            "risk_factors": "",
        }, "call")

        self.assertEqual(result["action"], "NO_TRADE")
        self.assertEqual(result["confidence"], 0)

    def test_unmatched_broker_result_is_remembered_once(self):
        processed = set()

        self.assertTrue(remember_processed_result(processed, "position-123"))
        self.assertFalse(remember_processed_result(processed, "position-123"))
        self.assertEqual(processed, {"position-123"})

    def test_prompt_contains_locked_direction_and_real_account(self):
        prompt = build_analysis_prompt("EURUSD", {
            "signal_direction": "call",
            "signal_setup": "primary_cross",
            "signal_reason": "RSI crossed",
            "math_confidence": 65,
            "account_type": "real",
            "prev_rsi": 27,
            "rsi": 31,
            "ema_fast": 1.0,
            "ema_slow": 1.1,
            "trend": "down",
            "atr": 0.1,
            "bb_upper": 1.2,
            "bb_lower": 0.8,
            "bb_mid": 1.0,
            "pattern": "hammer",
            "recent_candles": [],
        })

        self.assertIn("Account: REAL", prompt)
        self.assertIn("Required direction: CALL", prompt)
        self.assertIn("Previous RSI(14): 27.0", prompt)


if __name__ == "__main__":
    unittest.main()
