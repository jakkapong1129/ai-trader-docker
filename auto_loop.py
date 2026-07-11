#!/usr/bin/env python3
"""
AI Trader Auto Loop — MCP-based, runs in tmux
Only calls LLM when Math AI detects a signal.
"""

import os
import sys
import json
import time
import asyncio
import statistics
from datetime import datetime, timezone, timedelta

from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from modules.rsi_strategy import RSIReversalStrategy, calc_rsi, calc_ema, detect_trend, detect_candle_pattern
from modules.llm_decision import LLMDecisionMaker
from config.assets import TOP_ASSETS

# ── MCP Config ──────────────────────────────────────────
MCP_URL = os.getenv("MCP_URL", "https://digital-options.mcp.iqoption.com")
MCP_TOKEN = os.getenv("MCP_TOKEN", "Bearer YOUR_MCP_TOKEN_HERE")

# ── Trading Settings (from .env) ──────────────────────────────────
TRADE_AMOUNT = int(os.getenv("BASE_AMOUNT", "30"))       # Use BASE_AMOUNT from .env, default 30
MG_MULTIPLIER = float(os.getenv("MG_MULTIPLIER", "2.0")) # Double after loss
MG_MAX = int(os.getenv("MAX_MG_LEVEL", "5"))             # Max 5 levels

def get_account_type():
    """Read account type from shared file or fallback to ENV"""
    try:
        path = "/app/shared/account_type.txt"
        if os.path.exists(path):
            with open(path, "r") as f:
                val = f.read().strip().lower()
                if val in ("real", "demo"):
                    return val
    except Exception:
        pass
    return os.getenv("ACCOUNT_TYPE", "demo").lower()

ACCOUNT_TYPE = get_account_type()

# Per-asset RSI OB/OS (will be optimized by learner)
ASSET_PARAMS = {
    2117: {"rsi_ob": 75, "rsi_os": 28},  # EURCAD
    2114: {"rsi_ob": 75, "rsi_os": 22},  # GBPCAD
    77:   {"rsi_ob": 75, "rsi_os": 30},  # EURGBP
    2131: {"rsi_ob": 70, "rsi_os": 30},  # EURCHF
    76:   {"rsi_ob": 70, "rsi_os": 30},  # EURUSD
    81:   {"rsi_ob": 70, "rsi_os": 30},  # GBPUSD
    85:   {"rsi_ob": 70, "rsi_os": 30},  # USDJPY
    84:   {"rsi_ob": 70, "rsi_os": 30},  # GBPJPY
    2137: {"rsi_ob": 70, "rsi_os": 30},  # USDCHF
    80:   {"rsi_ob": 70, "rsi_os": 30},  # NZDUSD
    2116: {"rsi_ob": 70, "rsi_os": 30},  # AUDCAD
    2119: {"rsi_ob": 70, "rsi_os": 30},  # CADCHF
    2134: {"rsi_ob": 70, "rsi_os": 30},  # EURAUD
    2113: {"rsi_ob": 70, "rsi_os": 30},  # AUDJPY
    2140: {"rsi_ob": 70, "rsi_os": 30},  # CHFJPY
}
INTERVAL_SEC = 120       # Check every 2min (5-min candles need less frequent)
CANDLE_SIZE = 300        # 5-min candles
CANDLE_COUNT = 100       # Last 100 candles (500 min ~8 hours)

# Top 15 assets with asset_ids
TRADE_ASSETS = {
    "EURCAD": 2117,
    "GBPCAD": 2114,
    "EURGBP": 77,
    "EURCHF": 2131,
    "EURUSD": 76,
    "GBPUSD": 81,
    "USDJPY": 85,
    "GBPJPY": 84,
    "USDCHF": 78,
    "NZDUSD": 80,
    "AUDCAD": 86,
    "CADCHF": 2119,
    "EURAUD": 2120,
    "AUDJPY": 2113,
    "CHFJPY": 2118,
}
TRADE_ASSET_ITEMS = tuple(TRADE_ASSETS.items())

# ── Helpers ─────────────────────────────────────────────
THA = timezone(timedelta(hours=7))
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
os.makedirs(LOG_DIR, exist_ok=True)

def log(msg, level="INFO"):
    ts = datetime.now(THA).strftime("%H:%M:%S")
    line = f"[{ts}] [{level}] {msg}"
    print(line, flush=True)
    try:
        with open(os.path.join(LOG_DIR, "auto_loop.log"), "a") as f:
            f.write(line + "\n")
    except:
        pass

class MCPClient:
    """Async MCP client that maintains session"""
    def __init__(self):
        self.session = None
        self.read = None
        self.write = None
        self._ctx = None
        self._http_ctx = None
        self.active_balance_id = None  # type: ignore
    
    async def connect(self):
        from mcp.client.streamable_http import streamablehttp_client
        from mcp import ClientSession
        
        headers = {"Authorization": MCP_TOKEN}
        self._http_ctx = streamablehttp_client(MCP_URL, headers=headers)
        streams = await self._http_ctx.__aenter__()
        self.read, self.write, _ = streams
        self._ctx = ClientSession(self.read, self.write)
        self.session = await self._ctx.__aenter__()
        await self.session.initialize()
        log("✅ MCP Connected!")
    
    async def disconnect(self):
        try:
            if self._ctx:
                await self._ctx.__aexit__(None, None, None)
            if self._http_ctx:
                await self._http_ctx.__aexit__(None, None, None)
        except:
            pass
    
    async def call(self, tool_name, arguments=None):
        try:
            result = await self.session.call_tool(tool_name, arguments or {})
            if result.content:
                text = result.content[0].text
                try:
                    return json.loads(text)
                except:
                    return text
            return None
        except Exception as e:
            log(f"MCP call {tool_name} failed: {e}", "ERROR")
            return None
    
    async def get_candles(self, asset_id):
        data = await self.call("get_candles", {
            "asset_id": asset_id, "size": CANDLE_SIZE, "count": CANDLE_COUNT
        })
        if data and "candles" in data:
            return data["candles"]
        return None
    
    async def get_instruments(self, asset_id, direction):
        data = await self.call("get_instruments", {
            "asset_id": asset_id, "direction": direction
        })
        return data
    
    async def place_trade(self, asset_id, direction, amount):
        """Place a demo trade. direction = 'call' or 'put'"""
        balance_id_to_use = self.active_balance_id if self.active_balance_id else int(os.getenv("BALANCE_ID", "1069191215"))
        
        # Get instruments
        instruments = await self.get_instruments(asset_id, direction)
        if not instruments:
            log(f"No instruments for {asset_id}", "ERROR")
            return None
        
        # Response is {"instruments": [{instrument_index, instruments: [{instrument_id, strike, direction}]}]}
        windows = instruments.get("instruments", []) if isinstance(instruments, dict) else instruments
        
        # Sort by period_seconds DESC — prefer 5min/15min over 1min (more time to fill)
        windows_sorted = sorted(windows, key=lambda w: w.get("period_seconds", 0), reverse=False)  # 1min first
        
        # Try each window until we get a valid trade
        for window in windows_sorted:
            period = window.get("period_seconds", 0)
            strikes = window.get("instruments", [])
            if len(strikes) == 0:
                continue
            
            instrument_index = window.get("instrument_index")
            
            # Pick SPT (spot) strike — always available, best price
            instrument_id = None
            for s in strikes:
                if s.get("strike") == "SPT":
                    instrument_id = s.get("instrument_id")
                    break
            # Fallback to first strike
            if not instrument_id and strikes:
                instrument_id = strikes[0].get("instrument_id")
            
            if not instrument_id:
                continue
            
            log(f"  Trying {period}s window, index={instrument_index}, strike=SPT")
            result = await self.call("place_trade", {
                "balance_id": balance_id_to_use,
                "instrument_id": instrument_id,
                "instrument_index": instrument_index,
                "asset_id": asset_id,
                "amount": amount
            })
            
            if result:
                result_str = str(result)
                # Check for rejection
                if "trade_rejected" in result_str or "error" in result_str.lower():
                    log(f"  ⚠️ Window {period}s rejected: {result_str[:150]}", "WARN")
                    continue  # Try next window
                else:
                    log(f"✅ TRADE: {direction.upper()} ${amount} asset={asset_id} period={period}s → {result}", "TRADE")
                    return result
        
        log(f"❌ All windows exhausted for {asset_id}", "ERROR")
        return None
    
    async def get_history(self, limit=5):
        return await self.call("get_trade_history", {"limit": limit})
    
    async def get_positions(self):
        return await self.call("list_positions", {})
    
    async def get_balance(self):
        data = await self.call("list_balances", {})
        return data


# ── Main Loop ───────────────────────────────────────────
async def main():
    # Set up client and find balance ID
    client = MCPClient()
    try:
        await client.connect()
    except Exception as e:
        log(f"💥 MCP connect failed: {e}", "ERROR")
        return
        
    b_response = await client.get_balance()
    active_balance_id = None
    if b_response and isinstance(b_response, dict):
        b_list = b_response.get("balances", b_response)
        if isinstance(b_list, list):
            for b in b_list:
                if b.get("type") == ("regular" if get_account_type() == "real" else "training"):
                    active_balance_id = b.get("balance_id") or b.get("id")
                    break
                    
    active_balance_id = active_balance_id or int(os.getenv("BALANCE_ID", "1069191216"))
    client.active_balance_id = active_balance_id

    log("=" * 50)
    log("🚀 AI TRADER AUTO LOOP (MCP)")
    log(f"   Assets: {', '.join(TRADE_ASSETS.keys())}")
    log(f"   Interval: {INTERVAL_SEC}s | Base: ${TRADE_AMOUNT} | MG: x{MG_MULTIPLIER} max {MG_MAX} levels")
    
    acc_type = get_account_type().capitalize()
    log(f"   Balance ID: {active_balance_id} ({acc_type})")
    log("=" * 50)
    
    # Show balance
    if b_response:
        log(f"💰 Balance: {json.dumps(b_response)[:200]}")
    
    strategy = RSIReversalStrategy()
    llm = LLMDecisionMaker()
    round_num = 0
    total_trades = 0
    total_wins = 0
    total_losses = 0
    processed_trades = set()  # Track which trades we've already counted
    startup_time = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")  # Only process trades after this
    asset_rotation_offset = 0  # Rotate priority so the same first pair is not always selected
    
    # Martingale state (global, shared across all assets)
    mg_level = 0  # 0=base, 1=x2, 2=x4, 3=x8
    last_trade_result = None  # 'win' or 'loss'
    consecutive_losses = 0
    MAX_CONSECUTIVE_LOSSES = 3  # Stop after 3 losses in a row
    trading_paused = False
    has_open_trade = False  # Only 1 trade at a time

    def get_mg_amount():
        """Calculate current bet amount with martingale"""
        return TRADE_AMOUNT * (MG_MULTIPLIER ** min(mg_level, MG_MAX - 1))
    
    def update_mg(result):
        """Update martingale after trade result"""
        nonlocal mg_level, last_trade_result, total_wins, total_losses, consecutive_losses, trading_paused
        last_trade_result = result
        if result == "win":
            total_wins += 1
            consecutive_losses = 0
            if mg_level > 0:
                log(f"🔄 MG RESET: level {mg_level} → 0 (won!)", "TRADE")
            mg_level = 0
            trading_paused = False
        else:
            total_losses += 1
            consecutive_losses += 1
            mg_level = min(mg_level + 1, MG_MAX - 1)
            log(f"📈 MG LEVEL: {mg_level} (next bet: ${get_mg_amount()}) (streak: {consecutive_losses}L)", "TRADE")
            if consecutive_losses >= MAX_CONSECUTIVE_LOSSES:
                trading_paused = True
                mg_level = 0
                consecutive_losses = 0
                log(f"🛑 SAFETY STOP: {MAX_CONSECUTIVE_LOSSES} consecutive losses! Pausing 30 min...", "TRADE")

    def reset_mg_state(reason):
        """Start a new bot run at the base stake without modifying trade history."""
        nonlocal mg_level, last_trade_result, consecutive_losses, trading_paused
        mg_level = 0
        last_trade_result = None
        consecutive_losses = 0
        trading_paused = False
        log(f"🔄 MG RESET: level 0 ({reason})", "TRADE")

    # Init DB helper in local context
    from models import Database
    db_conn = Database()

    # Keep recent statistics for the dashboard, but every new bot process starts at MG level 0.
    # Recovering consecutive losses here caused a restarted bot to continue its old Martingale chain.
    try:
        current_acc_type = get_account_type()
        past_trades = db_conn.get_trades(limit=10, account_type=current_acc_type)
        if past_trades:
            total_trades = len(past_trades)
            total_wins = sum(1 for t in past_trades if t.result == "win")
            total_losses = sum(1 for t in past_trades if t.result == "loss")
            log(f"🔄 New bot session at MG level 0 (recent history: {total_wins}W/{total_losses}L)", "TRADE")
    except Exception as e:
        log(f"⚠️ Failed to load recent stats from DB: {e}", "WARN")

    # A process restart must not forget a position that is still live.  MG is
    # reset above, while new entries remain blocked until that position settles.
    try:
        startup_positions = await client.get_positions()
        if isinstance(startup_positions, dict):
            startup_positions = startup_positions.get("positions", [])
        if isinstance(startup_positions, list) and startup_positions:
            has_open_trade = True
            log(f"📊 Found {len(startup_positions)} open position(s) at startup; waiting for settlement.", "TRADE")
    except Exception as e:
        log(f"⚠️ Could not check open positions at startup: {e}", "WARN")

    # Endpoint to send update reports
    API_SERVER_URL = os.getenv("API_SERVER_URL", "http://localhost:8000")
    
    # Store list of active assets for the dashboard
    active_assets_list = []
    open_positions = []
    next_scan_at = None

    def extract_open_positions(response):
        """Normalize the broker's position response without inventing values."""
        if isinstance(response, dict):
            response = response.get("positions", response.get("data", []))
        return [position for position in response if isinstance(position, dict)] if isinstance(response, list) else []
    
    async def report_to_api(status_str="Running", phase=None):
        balances = []
        try:
            # Refresh balance dynamically to get the latest amount
            new_bal_resp = await client.get_balance()
            if new_bal_resp and "balances" in new_bal_resp:
                balances = new_bal_resp["balances"]
        except Exception as e:
            log(f"Error refreshing balance: {e}", "DEBUG")
            
        try:
            # Get latest 10 trades from PostgreSQL filtered by current account type
            latest_trades_db = []
            try:
                latest_trades_db = [t.to_dict() for t in db_conn.get_trades(limit=10, account_type=current_account_type)]
            except Exception as e:
                log(f"Error fetching DB trades for report: {e}", "DEBUG")
            
            # Construct standard report payload
            payload = {
                # Keep balances explicitly named by account type.  `balance`
                # remains for older dashboard clients and is set below.
                "balance": 0.0,
                "real_balance": 0.0,
                "demo_balance": 0.0,
                "bot_status": status_str,
                "bot_phase": phase or status_str,
                "next_scan_at": next_scan_at,
                "open_positions": open_positions,
                "mg_level": int(mg_level),
                "round_num": int(round_num),
                "total_trades": int(total_trades),
                "total_wins": int(total_wins),
                "total_losses": int(total_losses),
                "account_type": current_account_type,
                "history": latest_trades_db,
                "assets": active_assets_list
            }
            
            # MCP calls the real account "regular" and the demo account
            # "training".  Populate both values every report, regardless of
            # which account the bot is currently using.
            if isinstance(balances, list):
                for balance_info in balances:
                    amount = float(balance_info.get("amount", 0.0))
                    if balance_info.get("type") == "regular":
                        payload["real_balance"] = amount
                    elif balance_info.get("type") == "training":
                        payload["demo_balance"] = amount

            payload["balance"] = payload[
                "demo_balance" if current_account_type == "demo" else "real_balance"
            ]
            
            # Post async to API
            import httpx
            async with httpx.AsyncClient() as httpx_client:
                await httpx_client.post(f"{API_SERVER_URL}/api/update", json=payload, timeout=2.0)
        except Exception as e:
            # Non-blocking log if API server is not up yet
            pass
    
    while True:
        round_num += 1
        
        current_account_type = get_account_type()
        next_scan_at = None
        
        log(f"─── Round #{round_num} ─────────────────────────")
        
        # ── Check bot control status (Start/Stop/Pause) from API or local control file ──
        control_path = "/app/shared/bot_control.txt"
        if os.path.exists(control_path):
            try:
                with open(control_path, "r") as f:
                    action = f.read().strip()
                
                # Check for restart action first before loops
                if action == "restart":
                    reset_mg_state("dashboard restart")
                    with open(control_path, "w") as f:
                        f.write("start")
                    action = "start"
                    await report_to_api("Running", "Scanning market")

                if action == "stop":
                    log("🛑 BOT CONTROL: Stopped by dashboard. Sleeping...")
                    next_scan_at = None
                    await report_to_api("Stopped")
                    for _ in range(INTERVAL_SEC):
                        if os.path.exists(control_path):
                            with open(control_path, "r") as f_check:
                                check_act = f_check.read().strip()
                                if check_act == "start":
                                    reset_mg_state("started after stop")
                                    log("▶️ BOT CONTROL: Resumed from Stopped state!")
                                    break
                                elif check_act == "restart":
                                    break
                        await asyncio.sleep(1)
                    continue
                elif action == "pause":
                    log("⏸️ BOT CONTROL: Paused by dashboard. Skipping rounds...")
                    next_scan_at = None
                    await report_to_api("Paused")
                    for _ in range(INTERVAL_SEC):
                        if os.path.exists(control_path):
                            with open(control_path, "r") as f_check:
                                check_act = f_check.read().strip()
                                if check_act == "start":
                                    log("▶️ BOT CONTROL: Resumed from Paused state!")
                                    break
                                elif check_act == "restart":
                                    break
                        await asyncio.sleep(1)
                    continue
            except Exception as ce:
                log(f"Control file error: {ce}", "WARN")

        # Clear assets status list for new round
        active_assets_list.clear()
        try:
            open_positions = extract_open_positions(await client.get_positions())
        except Exception as e:
            log(f"Could not refresh open positions before scan: {e}", "DEBUG")
        await report_to_api("Running", "Scanning market")
        
        # ── Auto-resume after 30 min pause ──
        if trading_paused:
            pause_rounds = getattr(main, '_pause_counter', 0) + 1
            main._pause_counter = pause_rounds
            if pause_rounds >= 15:  # 15 rounds × 2min = 30min
                trading_paused = False
                main._pause_counter = 0
                log("▶️ RESUME: 30 min pause ended, trading again!", "TRADE")
            else:
                log(f"⏸️ Paused... {15 - pause_rounds} rounds until resume")
        
        # ── Check previous trade results ──
        try:
            history = await client.get_history(5)
            if history and "history" in str(history):
                hist_data = history if isinstance(history, list) else history.get("history", history)
                if isinstance(hist_data, dict):
                    hist_data = hist_data.get("history", [])
                if isinstance(hist_data, list):
                    for trade in hist_data:
                        trade_time = trade.get("close_time", "")
                        # Only process trades AFTER bot startup (not old history)
                        if trade_time and trade_time > startup_time:
                            trade_ts = trade_time.replace("Z", "").split("T")
                            # Check if this trade was already processed
                            pos_id = trade.get("position_id")
                            if pos_id and pos_id not in processed_trades:
                                processed_trades.add(pos_id)
                                result = trade.get("result", "unknown")
                                profit = trade.get("profit", 0)
                                if result in ("win", "loss", "equal"):
                                    # An equal/draw is settled: unblock trading, but do not change MG.
                                    has_open_trade = False
                                    if result in ("win", "loss"):
                                        update_mg(result)
                                    else:
                                        log("➖ RESULT: equal — MG level unchanged", "TRADE")

                                    emoji = {"win": "✅", "loss": "❌", "equal": "➖"}[result]
                                    log(f"{emoji} RESULT: {trade.get('asset_name','')} {trade.get('direction','')} {result} ${profit:+.0f} (total: {total_wins}W/{total_losses}L)", "TRADE")
                                    
                                    # Update PostgreSQL trade result
                                    try:
                                        # Find matching pending trade in DB filtered by current account type
                                        raw_asset = trade.get("asset_name", "")
                                        clean_asset = raw_asset.replace("/", "").replace(" (OTC)", "").strip()
                                        pending_trades = db_conn.get_trades(limit=10, result="pending", asset=clean_asset, account_type=current_account_type)
                                        if not pending_trades and raw_asset:
                                            pending_trades = db_conn.get_trades(limit=10, result="pending", asset=raw_asset, account_type=current_account_type)
                                        
                                        if pending_trades:
                                            # Update the most recent pending trade for this asset
                                            target_trade = pending_trades[0]
                                            db_conn.update_trade_result(
                                                trade_id=target_trade.id,
                                                result=result,
                                                profit=float(profit),
                                                close_price=float(trade.get("close_price", 0.0))
                                            )
                                            log(f"💾 Updated trade #{target_trade.id} result in DB!", "DEBUG")
                                    except Exception as dbe2:
                                        log(f"⚠️ Failed to update DB trade result: {dbe2}", "WARN")
        except Exception as e:
            pass  # Don't crash on history check
        
        signals_found = 0
        
        # Only one position may be open at once. Rotate the first asset checked each
        # round, then continue from the pair after the one that placed a trade.
        asset_count = len(TRADE_ASSET_ITEMS)
        rotated_assets = (
            TRADE_ASSET_ITEMS[asset_rotation_offset:]
            + TRADE_ASSET_ITEMS[:asset_rotation_offset]
        )
        asset_rotation_offset = (asset_rotation_offset + 1) % asset_count

        for asset_name, asset_id in rotated_assets:
            try:
                # Get candles
                candles = await client.get_candles(asset_id)
                if not candles or len(candles) < 50:
                    log(f"{asset_name}: No candle data ({len(candles) if candles else 0} candles)")
                    continue
                
                closes = [c["close"] for c in candles]
                price = closes[-1]
                
                # ── Math Analysis ── (per-asset params)
                asset_params = ASSET_PARAMS.get(asset_id, {"rsi_ob": 70, "rsi_os": 30})
                ob = asset_params.get("rsi_ob", 70)
                os_val = asset_params.get("rsi_os", 30)
                
                rsi_vals = calc_rsi(closes, 14)
                rsi = rsi_vals[-1] if rsi_vals else 50
                
                signal = strategy.analyze(candles, {
                    "rsi_period": 14, "rsi_ob": ob, "rsi_os": os_val,
                    "ema_fast": 9, "ema_slow": 21, "atr_period": 14
                })
                
                trend = detect_trend(closes)
                log(f"{asset_name}: price={price:.5f} RSI={rsi:.1f} trend={trend} OB={ob} OS={os_val}")
                
                # Append status for dashboard
                active_assets_list.append({
                    "name": asset_name,
                    "rsi": float(rsi),
                    "trend": trend,
                    "ob": int(ob),
                    "os": int(os_val),
                    "state": "SIGNAL" if (signal and signal.is_valid) else ""
                })
                
                # ── Check for Signal ──
                if signal and signal.is_valid:
                    signals_found += 1
                    log(f"🎯 SIGNAL: {asset_name} {signal.direction.upper()} conf={signal.confidence:.0f}%", "SIGNAL")
                    
                    # ── LLM Confirmation (only when math signal exists) ──
                    ema_fast = calc_ema(closes, 9)
                    ema_slow = calc_ema(closes, 21)
                    pattern = detect_candle_pattern(candles)
                
                    # Calculate ATR properly
                    atr_vals = []
                    for i in range(1, len(candles)):
                        high = candles[i].get("max", candles[i]["close"])
                        low = candles[i].get("min", candles[i]["close"])
                        prev_close = candles[i-1]["close"]
                        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
                        atr_vals.append(tr)
                    atr = sum(atr_vals[-14:]) / min(14, len(atr_vals)) if atr_vals else 0
                
                    bb_mid = statistics.mean(closes[-20:])
                    bb_std = statistics.stdev(closes[-20:])
                
                    indicators = {
                        "rsi": rsi,
                        "ema_fast": ema_fast[-1] if ema_fast else 0,
                        "ema_slow": ema_slow[-1] if ema_slow else 0,
                        "trend": trend,
                        "atr": atr,
                        "bb_upper": bb_mid + 2 * bb_std,
                        "bb_lower": bb_mid - 2 * bb_std,
                        "bb_mid": bb_mid,
                        "pattern": pattern,
                        "recent_candles": candles[-10:],
                    }
                    
                    llm_result = llm.analyze(asset_name, indicators)
                    action = llm_result["action"]
                    confidence = llm_result["confidence"]
                    
                    log(f"🤖 LLM: {asset_name} → {action} conf={confidence:.0f}%", "LLM")
                    log(f"   💬 {llm_result['reason']}", "LLM")
                    
                    # ── Execute Trade (with trend filter) ──
                    if trading_paused:
                        log(f"⏸️ PAUSED: Safety stop active, skipping trade")
                    elif has_open_trade:
                        log(f"⏳ มีไม้เปิดอยู่ รอผลก่อน")
                    elif action in ("CALL", "PUT") and confidence >= 45:
                        # Only block PUT in uptrend (selling in uptrend = bad)
                        # CALL in downtrend is OK (oversold bounce)
                        if action == "PUT" and trend == "up":
                            log(f"⏭️ Skip PUT: trend=up (against trend)")
                        else:
                            direction = action.lower()
                            trend_note = " ⚠️ counter-trend" if (action == "CALL" and trend == "down") else ""
                            current_amount = get_mg_amount()
                            mg_info = f" (MG:{mg_level}=${current_amount})" if mg_level > 0 else ""
                            log(f"🔥 EXECUTING: {asset_name} {direction.upper()} ${current_amount}{mg_info}{trend_note}", "TRADE")
                            
                            trade_result = await client.place_trade(asset_id, direction, current_amount)
                            if trade_result:
                                total_trades += 1
                                has_open_trade = True  # Block new trades until result
                                traded_index = next(
                                    index for index, (name, _) in enumerate(TRADE_ASSET_ITEMS)
                                    if name == asset_name
                                )
                                asset_rotation_offset = (traded_index + 1) % asset_count
                                log(f"✅ Trade #{total_trades} placed! (waiting for result)", "TRADE")
                                
                                # Save trade to PostgreSQL Database
                                try:
                                    from models.trade import Trade
                                    
                                    # Safe fallback parameters
                                    local_bb_mid = statistics.mean(closes[-20:])
                                    local_bb_std = statistics.stdev(closes[-20:])
                                    
                                    t_obj = Trade(
                                        timestamp=datetime.now().isoformat(),
                                        asset_name=asset_name,
                                        asset_id=asset_id,
                                        strategy="rsi_reversal",
                                        direction=direction,
                                        amount=float(current_amount),
                                        confidence=float(confidence),
                                        rsi_value=float(rsi),
                                        ema_fast=float(ema_fast[-1] if ema_fast else 0.0),
                                        ema_slow=float(ema_slow[-1] if ema_slow else 0.0),
                                        bb_upper=float(local_bb_mid + 2 * local_bb_std),
                                        bb_lower=float(local_bb_mid - 2 * local_bb_std),
                                        bb_mid=float(local_bb_mid),
                                        atr_value=float(atr),
                                        candle_pattern=pattern or "",
                                        trend_direction=trend or "",
                                        result="pending",
                                        profit=0.0,
                                        mg_level=int(mg_level),
                                        account_type=current_account_type
                                    )
                                    db_conn.save_trade(t_obj)
                                    log(f"💾 Trade saved to PostgreSQL successfully!", "DEBUG")
                                except Exception as dbe:
                                    log(f"⚠️ Failed to save trade to DB: {dbe}", "WARN")
                            else:
                                log(f"❌ Trade failed!", "ERROR")
                    else:
                        log(f"⏭️ Skip: action={action} conf={confidence:.0f}%")
                
            except Exception as e:
                log(f"{asset_name}: Error - {e}", "ERROR")
        
        if signals_found == 0:
            log(f"No signals. Next in {INTERVAL_SEC}s... (Total trades: {total_trades})")
        
        # Ask the broker for live positions before reporting the wait period.
        try:
            open_positions = extract_open_positions(await client.get_positions())
            if open_positions:
                log(f"📊 Open positions: {len(open_positions)}")
        except Exception as e:
            log(f"Could not refresh open positions: {e}", "DEBUG")

        next_scan_at = (datetime.now(timezone.utc) + timedelta(seconds=INTERVAL_SEC)).isoformat().replace("+00:00", "Z")
        if trading_paused:
            next_scan_at = None
            await report_to_api("Paused")
        elif open_positions or has_open_trade:
            await report_to_api("Running", "Open position — waiting for settlement")
        else:
            await report_to_api("Running", "Waiting for next scan")
        
        await asyncio.sleep(INTERVAL_SEC)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log("🛑 Stopped by user")
    except asyncio.exceptions.CancelledError:
        pass
    except Exception as e:
        if "cancel scope" not in str(e).lower() and not isinstance(e, asyncio.CancelledError):
            log(f"💥 Fatal: {e}", "ERROR")
            import traceback
            traceback.print_exc()
