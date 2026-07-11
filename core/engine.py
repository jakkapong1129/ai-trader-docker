"""
🧠 AI Trader — Core Engine
Main loop: collect → analyze → decide → trade → learn
"""
import time
import json
import logging
from datetime import datetime
from typing import Optional

from models import Database
from models.trade import Trade
from models.strategy_state import StrategyState
from modules.rsi_strategy import RSIReversalStrategy, Signal
from config.settings import (
    CONFIDENCE_THRESHOLD, MIN_TRADES_FOR_LEARNING,
    RE_OPTIMIZE_INTERVAL, CANDLE_SIZE, CANDLE_COUNT
)
from config.assets import TOP_ASSETS

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("logs/ai_trader.log"),
    ]
)
log = logging.getLogger("ai_trader")


class AITraderEngine:
    """
    Main AI Trader Engine
    
    Loop:
    1. Fetch candles for each asset
    2. Run strategy analysis
    3. Decision engine decides whether to trade
    4. Execute trade
    5. Log result
    6. Periodically re-optimize parameters
    """

    def __init__(self, mode: str = "demo"):
        self.mode = mode  # "demo" or "live"
        self.db = Database()
        self.strategies = {
            "rsi_reversal": RSIReversalStrategy(),
        }
        self.running = False
        self.stats = {
            "trades_today": 0,
            "wins_today": 0,
            "losses_today": 0,
            "profit_today": 0.0,
            "last_signal": None,
            "last_trade_time": None,
        }

        # Initialize strategy states from DB or defaults
        self._init_strategy_states()
        
        log.info(f"🧠 AI Trader Engine initialized | mode={mode}")
        log.info(f"📊 Strategies: {list(self.strategies.keys())}")
        log.info(f"📈 Assets: {list(TOP_ASSETS.keys())}")

    def _init_strategy_states(self):
        """Load or create strategy states for each strategy+asset pair"""
        for strategy_name, strategy in self.strategies.items():
            for asset_name in TOP_ASSETS:
                state = self.db.get_strategy_state(strategy_name, asset_name)
                if not state:
                    # Create default state with per-asset optimized OB/OS
                    asset_cfg = TOP_ASSETS[asset_name]
                    defaults = strategy.get_default_params()
                    state = StrategyState(
                        strategy_name=strategy_name,
                        asset_name=asset_name,
                        rsi_ob=asset_cfg.get("ob", defaults["rsi_ob"]),
                        rsi_os=asset_cfg.get("os", defaults["rsi_os"]),
                        rsi_period=defaults["rsi_period"],
                        ema_fast_period=defaults.get("ema_fast", 9),
                        ema_slow_period=defaults.get("ema_slow", 21),
                    )
                    self.db.save_strategy_state(state)
                    log.info(f"  Created state: {strategy_name}/{asset_name} OB={state.rsi_ob} OS={state.rsi_os}")

    def run_cycle(self, candles_by_asset: dict[str, list[dict]]) -> list[dict]:
        """
        Run one trading cycle.
        
        candles_by_asset: {asset_name: [candle_dicts]}
        
        Returns list of trade actions taken.
        """
        actions = []

        for asset_name, candles in candles_by_asset.items():
            if asset_name not in TOP_ASSETS:
                continue

            for strategy_name, strategy in self.strategies.items():
                # Get optimized params for this strategy+asset
                state = self.db.get_strategy_state(strategy_name, asset_name)
                if not state:
                    continue

                params = {
                    "rsi_period": state.rsi_period,
                    "rsi_ob": state.rsi_ob,
                    "rsi_os": state.rsi_os,
                    "ema_fast": state.ema_fast_period,
                    "ema_slow": state.ema_slow_period,
                    "atr_period": state.atr_period,
                }

                # Analyze
                signal = strategy.analyze(candles, params)

                if signal and signal.is_valid:
                    self.stats["last_signal"] = {
                        "asset": asset_name,
                        "strategy": strategy_name,
                        "direction": signal.direction,
                        "confidence": signal.confidence,
                        "reason": signal.reason,
                        "time": datetime.now().isoformat(),
                    }

                    # Decision: trade only if confidence is high enough
                    if signal.confidence >= CONFIDENCE_THRESHOLD:
                        trade = self._prepare_trade(
                            asset_name=asset_name,
                            signal=signal,
                            candles=candles,
                        )
                        actions.append({
                            "action": "trade",
                            "trade": trade,
                            "signal": signal,
                        })
                        log.info(
                            f"🎯 SIGNAL: {asset_name} {signal.direction.upper()} "
                            f"conf={signal.confidence:.0f} | {signal.reason}"
                        )
                    else:
                        log.debug(
                            f"⏸️ SKIP: {asset_name} conf={signal.confidence:.0f} "
                            f"< threshold {CONFIDENCE_THRESHOLD}"
                        )

        return actions

    def _prepare_trade(self, asset_name: str, signal: Signal, 
                       candles: list[dict]) -> Trade:
        """Prepare a Trade object from signal"""
        from modules.rsi_strategy import detect_trend, detect_candle_pattern
        
        closes = [c["close"] for c in candles]
        trend = detect_trend(closes)
        pattern = detect_candle_pattern(candles)
        last = candles[-1] if candles else {}

        return Trade(
            asset_name=asset_name,
            asset_id=0,  # Will be set by executor
            strategy=signal.strategy_name,
            direction=signal.direction,
            amount=30,  # Base amount, adjusted by executor
            confidence=signal.confidence,
            rsi_value=signal.indicators.get("rsi", 0),
            trend_direction=trend,
            candle_pattern=pattern,
            session_type=self._get_session_type(),
        )

    def record_result(self, trade_id: int, result: str, 
                      profit: float, close_price: float):
        """Record trade result and trigger learning if needed"""
        self.db.update_trade_result(trade_id, result, profit, close_price)
        
        self.stats["trades_today"] += 1
        if result == "win":
            self.stats["wins_today"] += 1
        elif result == "loss":
            self.stats["losses_today"] += 1
        self.stats["profit_today"] += profit
        self.stats["last_trade_time"] = datetime.now().isoformat()

        # Check if we should re-optimize
        total = self.db.get_trade_count()
        if total > 0 and total % RE_OPTIMIZE_INTERVAL == 0:
            self._trigger_learning()

    def _trigger_learning(self):
        """Trigger strategy parameter re-optimization"""
        log.info("🧠 Triggering strategy re-optimization...")
        
        from modules.strategy_learner import StrategyLearner
        learner = StrategyLearner(self.db)
        
        for strategy_name in self.strategies:
            for asset_name in TOP_ASSETS:
                new_state = learner.optimize(strategy_name, asset_name)
                if new_state:
                    self.db.save_strategy_state(new_state)
                    log.info(
                        f"  ✅ Optimized {strategy_name}/{asset_name}: "
                        f"OB={new_state.rsi_ob:.1f} OS={new_state.rsi_os:.1f} "
                        f"WR={new_state.win_rate:.1%} conf={new_state.confidence_score:.0f}"
                    )

    def get_status(self) -> dict:
        """Get current engine status"""
        summary = self.db.get_summary()
        return {
            "mode": self.mode,
            "running": self.running,
            "strategies": list(self.strategies.keys()),
            "assets": list(TOP_ASSETS.keys()),
            "stats_today": self.stats.copy(),
            "db_summary": summary,
            "last_signal": self.stats["last_signal"],
        }

    def _get_session_type(self) -> str:
        h = datetime.now().hour
        if 6 <= h < 12: return "morning"
        elif 12 <= h < 18: return "afternoon"
        elif 18 <= h < 24: return "evening"
        else: return "night"

    def start(self):
        """Start the main trading loop"""
        self.running = True
        log.info("🚀 AI Trader Engine STARTED")
        log.info(f"📊 Mode: {self.mode} | Confidence threshold: {CONFIDENCE_THRESHOLD}")

        while self.running:
            try:
                # This will be connected to real data in the main runner
                # For now, it's the framework
                log.info("⏳ Waiting for next cycle...")
                time.sleep(60)  # 1-minute cycle

            except KeyboardInterrupt:
                log.info("🛑 Stopped by user")
                self.running = False
                break
            except Exception as e:
                log.error(f"❌ Error in main loop: {e}", exc_info=True)
                time.sleep(10)

    def stop(self):
        """Stop the engine"""
        self.running = False
        log.info("🛑 AI Trader Engine STOPPED")
