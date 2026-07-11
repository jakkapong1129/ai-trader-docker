"""
🧠 AI Trader — Strategy Learner
The BRAIN: analyzes trade history and optimizes parameters
"""
import logging
from datetime import datetime, timedelta
from typing import Optional
from itertools import product

from models import Database
from models.trade import Trade, StrategyPerformance
from models.strategy_state import StrategyState
from config.settings import MIN_TRADES_FOR_LEARNING, LOOKBACK_WINDOW

log = logging.getLogger("ai_trader")


class StrategyLearner:
    """
    Analyzes trade history and optimizes strategy parameters.
    
    This is the "AI" part — it learns from mistakes and adjusts.
    """

    def __init__(self, db: Database):
        self.db = db

    def optimize(self, strategy_name: str, asset_name: str) -> Optional[StrategyState]:
        """
        Re-optimize parameters for a strategy+asset pair.
        
        Uses historical trades to find the best parameter set.
        """
        # Get recent trades
        trades = self.db.get_trades(
            limit=LOOKBACK_WINDOW,
            strategy=strategy_name,
            asset=asset_name,
            result=None  # Include all results
        )

        completed = [t for t in trades if t.result in ("win", "loss", "equal")]

        if len(completed) < MIN_TRADES_FOR_LEARNING:
            log.debug(
                f"  Not enough data for {strategy_name}/{asset_name}: "
                f"{len(completed)} < {MIN_TRADES_FOR_LEARNING}"
            )
            return None

        # Get current state
        state = self.db.get_strategy_state(strategy_name, asset_name)
        if not state:
            state = StrategyState(
                strategy_name=strategy_name,
                asset_name=asset_name,
            )

        # === OPTIMIZATION METHODS ===

        # 1. Optimize OB/OS thresholds
        new_ob, new_os = self._optimize_thresholds(completed, state)
        state.rsi_ob = new_ob
        state.rsi_os = new_os

        # 2. Update performance metrics
        state.total_trades = len(completed)
        wins = sum(1 for t in completed if t.result == "win")
        state.win_rate = wins / len(completed)

        # 3. Recent performance (last 30 days)
        recent = [t for t in completed 
                  if t.timestamp >= (datetime.now() - timedelta(days=30)).isoformat()]
        if recent:
            recent_wins = sum(1 for t in recent if t.result == "win")
            state.last_30d_wr = recent_wins / len(recent)

        # 4. Calculate confidence score
        state.confidence_score = self._calc_confidence(state, completed)

        # 5. Detect best session
        self._analyze_sessions(completed)

        # 6. Detect declining assets
        declining = self._detect_decline(completed)

        state.last_optimized = datetime.now().isoformat()
        state.optimization_count += 1

        if declining:
            state.confidence_score *= 0.5  # Penalize declining assets
            log.warning(f"  ⚠️ {asset_name} showing decline pattern")

        return state

    def _optimize_thresholds(self, trades: list[Trade], 
                             state: StrategyState) -> tuple[float, float]:
        """
        Find optimal OB/OS thresholds by testing ranges against history.
        
        Method: For each (ob, os) pair, calculate what the win rate would have been.
        """
        best_ob = state.rsi_ob
        best_os = state.rsi_os
        best_wr = 0

        # Test range with step size
        ob_range = range(60, 86, 2)     # 60, 62, 64, ..., 84
        os_range = range(15, 41, 2)     # 15, 17, 19, ..., 39

        for ob in ob_range:
            for os in os_range:
                if ob - os < 20:  # OB must be significantly above OS
                    continue

                # Simulate: which trades would have been taken with these thresholds?
                hypothetical_wr = self._simulate_trades(trades, ob, os)

                if hypothetical_wr > best_wr:
                    best_wr = hypothetical_wr
                    best_ob = ob
                    best_os = os

        log.debug(f"  Optimized OB/OS: {best_ob}/{best_os} (WR={best_wr:.1%})")
        return float(best_ob), float(best_os)

    def _simulate_trades(self, trades: list[Trade], 
                         ob: float, os: float) -> float:
        """
        Simulate what would have happened with different OB/OS thresholds.
        Uses the actual RSI values at trade time to determine if a trade 
        would have been taken.
        """
        would_trade = 0
        would_win = 0

        for t in trades:
            rsi = t.rsi_value
            if rsi == 0:
                continue

            # Would this trade have been taken with these thresholds?
            taken = False
            if t.direction == "call" and rsi <= os:
                taken = True
            elif t.direction == "put" and rsi >= ob:
                taken = True

            if taken:
                would_trade += 1
                if t.result == "win":
                    would_win += 1

        if would_trade < 10:  # Need minimum sample
            return 0

        return would_win / would_trade

    def _calc_confidence(self, state: StrategyState, 
                         trades: list[Trade]) -> float:
        """Calculate overall confidence in this strategy+asset pair"""
        score = 50.0

        # Win rate contribution
        if state.win_rate >= 0.65:
            score += 25
        elif state.win_rate >= 0.60:
            score += 15
        elif state.win_rate >= 0.55:
            score += 5
        elif state.win_rate < 0.50:
            score -= 20

        # Recent performance contribution
        if state.last_30d_wr >= 0.65:
            score += 15
        elif state.last_30d_wr >= 0.55:
            score += 5
        elif state.last_30d_wr < 0.45:
            score -= 15

        # Sample size contribution
        if state.total_trades >= 500:
            score += 10
        elif state.total_trades >= 200:
            score += 5
        elif state.total_trades < 50:
            score -= 10

        # Trend consistency
        if abs(state.win_rate - state.last_30d_wr) < 0.05:
            score += 5  # Consistent = good
        elif state.last_30d_wr < state.win_rate - 0.10:
            score -= 10  # Declining = bad

        return max(0, min(100, score))

    def _analyze_sessions(self, trades: list[Trade]) -> dict:
        """Analyze which time sessions perform best"""
        sessions = {}
        for t in trades:
            s = t.session_type
            if s not in sessions:
                sessions[s] = {"trades": 0, "wins": 0, "profit": 0}
            sessions[s]["trades"] += 1
            if t.result == "win":
                sessions[s]["wins"] += 1
            sessions[s]["profit"] += t.profit

        for s, d in sessions.items():
            if d["trades"] > 0:
                d["win_rate"] = d["wins"] / d["trades"]
                log.debug(f"  Session {s}: {d['win_rate']:.1%} ({d['trades']} trades)")

        return sessions

    def _detect_decline(self, trades: list[Trade], 
                        window: int = 50) -> bool:
        """
        Detect if performance is declining.
        Compare recent N trades vs older N trades.
        """
        if len(trades) < window * 2:
            return False

        recent = trades[:window]
        older = trades[window:window*2]

        recent_wr = sum(1 for t in recent if t.result == "win") / len(recent)
        older_wr = sum(1 for t in older if t.result == "win") / len(older)

        declining = recent_wr < older_wr - 0.10  # 10% drop
        if declining:
            log.warning(
                f"  📉 Decline detected: {older_wr:.1%} → {recent_wr:.1%}"
            )
        return declining

    def get_learning_report(self) -> dict:
        """Generate a summary of what the AI has learned"""
        states = self.db.get_all_strategy_states()
        
        report = {
            "total_pairs": len(states),
            "high_confidence": [],
            "low_confidence": [],
            "needs_data": [],
            "recommendations": [],
        }

        for s in states:
            entry = {
                "strategy": s.strategy_name,
                "asset": s.asset_name,
                "ob": s.rsi_ob,
                "os": s.rsi_os,
                "wr": f"{s.win_rate:.1%}",
                "wr_30d": f"{s.last_30d_wr:.1%}",
                "trades": s.total_trades,
                "confidence": s.confidence_score,
            }

            if s.total_trades < MIN_TRADES_FOR_LEARNING:
                report["needs_data"].append(entry)
            elif s.confidence_score >= 70:
                report["high_confidence"].append(entry)
            else:
                report["low_confidence"].append(entry)

        # Recommendations
        for s in states:
            if s.confidence_score < 30:
                report["recommendations"].append(
                    f"⚠️ {s.strategy_name}/{s.asset_name}: confidence too low ({s.confidence_score:.0f}), consider stopping"
                )
            elif s.last_30d_wr > s.win_rate + 0.05:
                report["recommendations"].append(
                    f"📈 {s.strategy_name}/{s.asset_name}: improving! Recent WR {s.last_30d_wr:.1%}"
                )

        return report
