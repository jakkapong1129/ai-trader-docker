"""
🧠 AI Trader — LLM Decision Maker
Uses mimo-text @ 9router to analyze and make trading decisions
"""
import json
import logging
import os
from typing import Optional
from datetime import datetime

log = logging.getLogger("ai_trader")

# 9router endpoint
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://9router.irobotsonline.com/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "mimo-text")
LLM_API_KEY = os.getenv("LLM_API_KEY", "YOUR_LLM_API_KEY_HERE")
LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "16000"))


async def call_llm(prompt: str, system: str = "") -> str:
    """Call mimo-text via 9router"""
    import httpx

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            f"{LLM_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {LLM_API_KEY}"},
            json={
                "model": LLM_MODEL,
                "messages": messages,
                "temperature": 0.3,
                "max_tokens": LLM_MAX_TOKENS,
                "stream": False,
            }
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]


def call_llm_sync(prompt: str, system: str = "") -> str:
    """Sync version of LLM call"""
    import httpx

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    with httpx.Client(timeout=60) as client:
        resp = client.post(
            f"{LLM_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {LLM_API_KEY}"},
            json={
                "model": LLM_MODEL,
                "messages": messages,
                "temperature": 0.3,
                "max_tokens": LLM_MAX_TOKENS,
                "stream": False,
            }
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]


SYSTEM_PROMPT = """You are an aggressive digital options trader for IQ Option OTC Forex.

CONTEXT: The Math AI (RSI/EMA/Bollinger) already confirmed this signal. Your job is to CONFIRM or REJECT it. Lean towards CONFIRM unless there's a clear reason not to.

Rules:
- Math AI already detected RSI crossing OB/OS — this is a REVERSAL signal, trust it
- OTC markets trade 24/7 — ignore session timing (Asian/London/NY doesn't matter)
- If RSI crossed above oversold → CALL is valid (expect bounce up)
- If RSI crossed below overbought → PUT is valid (expect pullback down)
- Only say NO_TRADE if RSI is clearly mid-range (40-60) or trend strongly contradicts
- Confidence ≥ 50% = trade. Don't be overly cautious
- This is DEMO account ($4000+) — safe to experiment

You MUST respond in this exact JSON format:
{
  "action": "CALL" or "PUT" or "NO_TRADE",
  "confidence": 0-100,
  "reason": "brief explanation in Thai",
  "risk_factors": "potential risks in Thai"
}

Respond ONLY with the JSON, nothing else."""


def build_analysis_prompt(asset: str, indicators: dict, 
                          trade_history: dict = None,
                          session_info: dict = None) -> str:
    """Build the analysis prompt for LLM"""

    now = datetime.now()
    hour = now.hour

    # Session mapping (UTC+7)
    if 14 <= hour < 20:
        session = "London Session (volatility สูง)"
    elif 20 <= hour or hour < 3:
        session = "New York Session (volatility สูง)"
    elif 3 <= hour < 10:
        session = "Asian Session (volatility ปานกลาง)"
    else:
        session = "London-NY Overlap (volatility สูงสุด)"

    prompt = f"""📊 วิเคราะห์ {asset} เวลา {now.strftime('%H:%M:%S')} (UTC+7)

=== Market Data ===
Session: {session}

Indicators:
- RSI(14): {indicators.get('rsi', 'N/A'):.1f}
- EMA Fast(9): {indicators.get('ema_fast', 'N/A'):.5f}
- EMA Slow(21): {indicators.get('ema_slow', 'N/A'):.5f}
- Trend: {indicators.get('trend', 'N/A')}
- ATR: {indicators.get('atr', 'N/A'):.5f}
- BB Upper: {indicators.get('bb_upper', 'N/A'):.5f}
- BB Lower: {indicators.get('bb_lower', 'N/A'):.5f}
- BB Mid: {indicators.get('bb_mid', 'N/A'):.5f}
- Candle Pattern: {indicators.get('pattern', 'N/A')}

Candles (last 5):
"""
    # Add last 5 candles
    candles = indicators.get("recent_candles", [])
    for i, c in enumerate(candles[-5:]):
        body = "📈" if c.get("close", 0) > c.get("open", 0) else "📉"
        prompt += (f"  {body} O={c.get('open', 0):.5f} "
                   f"H={c.get('max', 0):.5f} "
                   f"L={c.get('min', 0):.5f} "
                   f"C={c.get('close', 0):.5f}\n")

    # Add trade history context
    if trade_history:
        prompt += f"""
=== AI Performance History ({asset}) ===
- Win Rate ทั้งหมด: {trade_history.get('win_rate', 'N/A')}
- Win Rate 30 วัน: {trade_history.get('win_rate_30d', 'N/A')}
- Total Trades: {trade_history.get('total_trades', 0)}
- Best Session: {trade_history.get('best_session', 'N/A')}
- AI Confidence: {trade_history.get('confidence', 'N/A')}
- Strategy: {trade_history.get('strategy', 'rsi_reversal')}
"""

    prompt += """
ตัดสินใจ: ควรเทรด CALL, PUT, หรือ NO_TRADE?
ตอบเป็น JSON เท่านั้น"""

    return prompt


def parse_llm_response(response: str) -> dict:
    """Parse LLM JSON response"""
    try:
        # Try to extract JSON from response
        response = response.strip()
        
        # Handle markdown code blocks
        if "```" in response:
            start = response.find("{")
            end = response.rfind("}") + 1
            if start >= 0 and end > start:
                response = response[start:end]

        data = json.loads(response)

        # Validate
        action = data.get("action", "NO_TRADE").upper()
        if action not in ("CALL", "PUT", "NO_TRADE"):
            action = "NO_TRADE"

        confidence = float(data.get("confidence", 0))
        confidence = max(0, min(100, confidence))

        return {
            "action": action,
            "confidence": confidence,
            "reason": data.get("reason", ""),
            "risk_factors": data.get("risk_factors", ""),
        }

    except (json.JSONDecodeError, KeyError, ValueError) as e:
        log.error(f"Failed to parse LLM response: {e}\nResponse: {response}")
        return {
            "action": "NO_TRADE",
            "confidence": 0,
            "reason": f"Parse error: {e}",
            "risk_factors": "LLM response ผิด format",
        }


class LLMDecisionMaker:
    """
    Uses mimo-text @ 9router as the brain for trading decisions.
    
    Flow:
    1. Math AI calculates indicators (fast)
    2. LLM analyzes everything (smart)
    3. LLM makes final decision + explains reason
    """

    def __init__(self):
        self.call_count = 0
        self.last_response = None

    def analyze(self, asset: str, indicators: dict,
                trade_history: dict = None) -> dict:
        """
        Ask LLM to analyze and decide.
        
        Returns: {action, confidence, reason, risk_factors}
        """
        prompt = build_analysis_prompt(asset, indicators, trade_history)

        try:
            log.info(f"🤖 Calling mimo-text for {asset} analysis...")
            response = call_llm_sync(prompt, SYSTEM_PROMPT)
            self.call_count += 1

            result = parse_llm_response(response)
            self.last_response = result

            log.info(
                f"🧠 LLM Decision: {asset} → {result['action']} "
                f"(conf={result['confidence']:.0f}) "
                f"| {result['reason']}"
            )

            return result

        except Exception as e:
            log.error(f"❌ LLM call failed: {e}")
            return {
                "action": "NO_TRADE",
                "confidence": 0,
                "reason": f"LLM error: {e}",
                "risk_factors": "ไม่สามารถเชื่อมต่อ LLM ได้",
            }

    def get_explanation(self, asset: str, action: str, 
                       result: str, profit: float) -> str:
        """Ask LLM to explain a trade result"""
        prompt = f"""เทรด {asset} {action} → ผล: {result} (กำไร ${profit:+.2f})

ช่วยอธิบายสั้น ๆ เป็นภาษาไทยว่าทำไมผลออกมาแบบนี้ 1-2 ประโยค"""

        try:
            response = call_llm_sync(prompt, "ตอบสั้น ๆ เป็นภาษาไทย ไม่เกิน 2 ประโยค")
            return response.strip()
        except Exception as e:
            return f"{result} ${profit:+.2f}"
