"""
🧠 AI Trader — Database Layer (PostgreSQL)
Replaces SQLite for the Docker Microservice Architecture.
"""
import os
import psycopg2
from psycopg2.extras import RealDictCursor
import json
from datetime import datetime, timedelta, timezone
from typing import Optional, List
from contextlib import contextmanager

from models.trade import Trade, StrategyPerformance
from models.strategy_state import StrategyState

# Read from env (set by docker-compose or .env)
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://trader_user:trader_password_safe_99@localhost:5432/ai_trader")


def normalize_utc_timestamp(value: str) -> str:
    """Make legacy UTC timestamps explicit so clients can convert to local time."""
    if not value or not isinstance(value, str):
        return value

    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.isoformat()

class Database:
    """PostgreSQL database for AI Trader in Docker"""

    def __init__(self, db_path: str = None):
        # db_path param is ignored in PostgreSQL version to match interface
        self.db_url = DATABASE_URL
        self._init_db()

    @contextmanager
    def _conn(self):
        conn = psycopg2.connect(self.db_url)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_db(self):
        with self._conn() as conn:
            with conn.cursor() as cursor:
                # Create trades table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS trades (
                        id SERIAL PRIMARY KEY,
                        timestamp VARCHAR(50) NOT NULL,
                        asset_name VARCHAR(50) NOT NULL,
                        asset_id INTEGER DEFAULT 0,
                        strategy VARCHAR(50) NOT NULL,
                        direction VARCHAR(10) NOT NULL,
                        amount DOUBLE PRECISION DEFAULT 0.0,
                        confidence DOUBLE PRECISION DEFAULT 0.0,
                        rsi_value DOUBLE PRECISION DEFAULT 0.0,
                        ema_fast DOUBLE PRECISION DEFAULT 0.0,
                        ema_slow DOUBLE PRECISION DEFAULT 0.0,
                        bb_upper DOUBLE PRECISION DEFAULT 0.0,
                        bb_lower DOUBLE PRECISION DEFAULT 0.0,
                        bb_mid DOUBLE PRECISION DEFAULT 0.0,
                        atr_value DOUBLE PRECISION DEFAULT 0.0,
                        candle_pattern VARCHAR(100) DEFAULT '',
                        trend_direction VARCHAR(20) DEFAULT '',
                        result VARCHAR(20) DEFAULT 'pending',
                        profit DOUBLE PRECISION DEFAULT 0.0,
                        close_price DOUBLE PRECISION DEFAULT 0.0,
                        close_time VARCHAR(50) DEFAULT '',
                        broker_order_id VARCHAR(100) DEFAULT '',
                        broker_position_id VARCHAR(100) DEFAULT '',
                        mg_level INTEGER DEFAULT 0,
                        session_hour INTEGER DEFAULT 0,
                        session_type VARCHAR(20) DEFAULT '',
                        account_type VARCHAR(20) DEFAULT 'demo'
                    );
                """)
                # Existing deployments need the column as well as new databases.
                cursor.execute("ALTER TABLE trades ADD COLUMN IF NOT EXISTS broker_order_id VARCHAR(100) DEFAULT '';")
                cursor.execute("ALTER TABLE trades ADD COLUMN IF NOT EXISTS broker_position_id VARCHAR(100) DEFAULT '';")

                # Create strategy_states table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS strategy_states (
                        id SERIAL PRIMARY KEY,
                        strategy_name VARCHAR(50) NOT NULL,
                        asset_name VARCHAR(50) NOT NULL,
                        rsi_period INTEGER DEFAULT 14,
                        rsi_ob DOUBLE PRECISION DEFAULT 70.0,
                        rsi_os DOUBLE PRECISION DEFAULT 30.0,
                        ema_fast_period INTEGER DEFAULT 9,
                        ema_slow_period INTEGER DEFAULT 21,
                        bb_period INTEGER DEFAULT 20,
                        bb_std DOUBLE PRECISION DEFAULT 2.0,
                        atr_period INTEGER DEFAULT 14,
                        win_rate DOUBLE PRECISION DEFAULT 0.0,
                        total_trades INTEGER DEFAULT 0,
                        confidence_score DOUBLE PRECISION DEFAULT 50.0,
                        last_30d_wr DOUBLE PRECISION DEFAULT 0.0,
                        last_optimized VARCHAR(50) DEFAULT '',
                        optimization_count INTEGER DEFAULT 0,
                        CONSTRAINT unique_strategy_asset UNIQUE(strategy_name, asset_name)
                    );
                """)

                # Create indexes
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_trades_asset ON trades(asset_name);")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_trades_strategy ON trades(strategy);")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_trades_result ON trades(result);")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_trades_timestamp ON trades(timestamp);")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_trades_broker_position_id ON trades(broker_position_id);")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_trades_broker_order_id ON trades(broker_order_id);")

    # ========== TRADE OPERATIONS ==========

    def save_trade(self, trade: Trade) -> int:
        """Save a trade record, returns trade id"""
        with self._conn() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO trades (
                        timestamp, asset_name, asset_id, strategy, direction,
                        amount, confidence, rsi_value, ema_fast, ema_slow,
                        bb_upper, bb_lower, bb_mid, atr_value, candle_pattern,
                        trend_direction, result, profit, close_price, close_time, broker_order_id, broker_position_id,
                        mg_level, session_hour, session_type, account_type
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                """, (
                    trade.timestamp, trade.asset_name, trade.asset_id,
                    trade.strategy, trade.direction, trade.amount, trade.confidence,
                    trade.rsi_value, trade.ema_fast, trade.ema_slow,
                    trade.bb_upper, trade.bb_lower, trade.bb_mid, trade.atr_value,
                        trade.candle_pattern, trade.trend_direction, trade.result,
                        trade.profit, trade.close_price, trade.close_time,
                        trade.broker_order_id, trade.broker_position_id,
                        trade.mg_level, trade.session_hour, trade.session_type, trade.account_type
                ))
                row = cursor.fetchone()
                return row[0]

    def update_trade_result(self, trade_id: int, result: str, 
                           profit: float, close_price: float):
        """Update trade result after expiry"""
        with self._conn() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    UPDATE trades 
                    SET result = %s, profit = %s, close_price = %s, close_time = %s
                    WHERE id = %s
                """, (result, profit, close_price, datetime.now(timezone.utc).isoformat(), trade_id))

    def update_trade_result_by_broker_position_id(self, broker_position_id: str,
                                                  result: str, profit: float,
                                                  close_price: float,
                                                  close_time: str = ""):
        """Update exactly the trade returned by the broker, never by asset name."""
        if not broker_position_id:
            raise ValueError("broker_position_id is required")
        with self._conn() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    UPDATE trades
                    SET result = %s, profit = %s, close_price = %s, close_time = %s
                    WHERE broker_position_id = %s AND result = 'pending'
                """, (
                    result, profit, close_price,
                    close_time or datetime.now(timezone.utc).isoformat(),
                    broker_position_id,
                ))

    def find_pending_trade_for_broker_result(self, asset_id: int, direction: str,
                                             amount: float, open_time: str,
                                             account_type: str) -> Optional[Trade]:
        """Find the one bot trade matching a settled broker position.

        The placement endpoint returns an order ID, while history returns a
        different position ID.  Match the immutable entry details and time,
        then persist the broker position ID once it is known.
        """
        try:
            broker_opened_at = datetime.fromisoformat(open_time.replace("Z", "+00:00"))
            if broker_opened_at.tzinfo is None:
                broker_opened_at = broker_opened_at.replace(tzinfo=timezone.utc)
        except (AttributeError, ValueError):
            return None

        candidates = []
        for trade in self.get_trades(limit=100, result="pending", account_type=account_type):
            if trade.asset_id != asset_id or trade.direction != direction:
                continue
            if abs(float(trade.amount) - float(amount)) > 0.000001:
                continue
            try:
                opened_at = datetime.fromisoformat(trade.timestamp.replace("Z", "+00:00"))
                if opened_at.tzinfo is None:
                    opened_at = opened_at.replace(tzinfo=timezone.utc)
            except (AttributeError, ValueError):
                continue
            if abs((opened_at - broker_opened_at).total_seconds()) <= 120:
                candidates.append(trade)

        return candidates[0] if len(candidates) == 1 else None

    def record_broker_result(self, trade_id: int, broker_position_id: str,
                             result: str, profit: float, close_price: float,
                             close_time: str = ""):
        """Attach the broker position ID and settle exactly one pending trade."""
        with self._conn() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    UPDATE trades
                    SET broker_position_id = %s, result = %s, profit = %s,
                        close_price = %s, close_time = %s
                    WHERE id = %s AND result = 'pending'
                """, (
                    broker_position_id, result, profit, close_price,
                    close_time or datetime.now(timezone.utc).isoformat(), trade_id,
                ))

    def clear_past_losses(self):
        """Reset past losses by marking them as canceled so Martingale is reset"""
        with self._conn() as conn:
            with conn.cursor() as cursor:
                cursor.execute("UPDATE trades SET result = 'canceled' WHERE result = 'loss'")

    def delete_trades_for_account(self, account_type: str) -> int:
        """Delete all trade history for one account."""
        if account_type not in ("demo", "real"):
            raise ValueError("account_type must be 'demo' or 'real'")

        with self._conn() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM trades WHERE account_type = %s",
                    (account_type,),
                )
                return cursor.rowcount

    def get_trades(self, limit: int = 100, strategy: str = None,
                   asset: str = None, result: str = None,
                   days: int = None, account_type: str = None) -> list:
        """Query trades with filters"""
        conditions = []
        params = []

        if strategy:
            conditions.append("strategy = %s")
            params.append(strategy)
        if asset:
            conditions.append("asset_name = %s")
            params.append(asset)
        if result:
            conditions.append("result = %s")
            params.append(result)
        if account_type:
            conditions.append("account_type = %s")
            params.append(account_type)
        if days:
            cutoff = (datetime.now() - timedelta(days=days)).isoformat()
            conditions.append("timestamp >= %s")
            params.append(cutoff)

        where = "WHERE " + " AND ".join(conditions) if conditions else ""
        sql = f"SELECT * FROM trades {where} ORDER BY timestamp DESC LIMIT %s"
        params.append(limit)

        with self._conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(sql, params)
                rows = cursor.fetchall()

        return [self._row_to_trade(r) for r in rows]

    def get_trade_count(self, strategy: str = None, asset: str = None,
                        result: str = None, days: int = None) -> int:
        """Count trades with filters"""
        conditions = []
        params = []

        if strategy:
            conditions.append("strategy = %s")
            params.append(strategy)
        if asset:
            conditions.append("asset_name = %s")
            params.append(asset)
        if result:
            conditions.append("result = %s")
            params.append(result)
        if days:
            cutoff = (datetime.now() - timedelta(days=days)).isoformat()
            conditions.append("timestamp >= %s")
            params.append(cutoff)

        where = "WHERE " + " AND ".join(conditions) if conditions else ""
        sql = f"SELECT COUNT(*) as cnt FROM trades {where}"

        with self._conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(sql, params)
                row = cursor.fetchone()
                return row["cnt"]

    def get_performance(self, strategy: str = None, 
                        asset: str = None, days: int = 30) -> list:
        """Get aggregated performance stats"""
        conditions = ["result IN ('win', 'loss', 'equal')"]
        params = []

        if strategy:
            conditions.append("strategy = %s")
            params.append(strategy)
        if asset:
            conditions.append("asset_name = %s")
            params.append(asset)
        if days:
            cutoff = (datetime.now() - timedelta(days=days)).isoformat()
            conditions.append("timestamp >= %s")
            params.append(cutoff)

        where = "WHERE " + " AND ".join(conditions)
        sql = f"""
            SELECT 
                strategy,
                asset_name,
                COUNT(*) as total,
                SUM(CASE WHEN result = 'win' THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN result = 'loss' THEN 1 ELSE 0 END) as losses,
                SUM(CASE WHEN result = 'equal' THEN 1 ELSE 0 END) as equals,
                SUM(profit) as total_profit,
                AVG(confidence) as avg_conf
            FROM trades {where}
            GROUP BY strategy, asset_name
            ORDER BY total DESC
        """

        with self._conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(sql, params)
                rows = cursor.fetchall()

        results = []
        for r in rows:
            perf = StrategyPerformance(
                strategy_name=r["strategy"],
                asset_name=r["asset_name"],
                total_trades=r["total"],
                wins=r["wins"],
                losses=r["losses"],
                equals=r["equals"],
                win_rate=r["wins"] / max(1, r["total"]),
                total_profit=r["total_profit"],
                avg_confidence=r["avg_conf"] if r["avg_conf"] is not None else 0.0,
            )
            results.append(perf)
        return results

    # ========== STRATEGY STATE OPERATIONS ==========

    def save_strategy_state(self, state: StrategyState):
        """Upsert strategy state"""
        with self._conn() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO strategy_states (
                        strategy_name, asset_name, rsi_period, rsi_ob, rsi_os,
                        ema_fast_period, ema_slow_period, bb_period, bb_std,
                        atr_period, win_rate, total_trades, confidence_score,
                        last_30d_wr, last_optimized, optimization_count
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT(strategy_name, asset_name) DO UPDATE SET
                        rsi_period = EXCLUDED.rsi_period,
                        rsi_ob = EXCLUDED.rsi_ob,
                        rsi_os = EXCLUDED.rsi_os,
                        ema_fast_period = EXCLUDED.ema_fast_period,
                        ema_slow_period = EXCLUDED.ema_slow_period,
                        bb_period = EXCLUDED.bb_period,
                        bb_std = EXCLUDED.bb_std,
                        atr_period = EXCLUDED.atr_period,
                        win_rate = EXCLUDED.win_rate,
                        total_trades = EXCLUDED.total_trades,
                        confidence_score = EXCLUDED.confidence_score,
                        last_30d_wr = EXCLUDED.last_30d_wr,
                        last_optimized = EXCLUDED.last_optimized,
                        optimization_count = EXCLUDED.optimization_count
                """, (
                    state.strategy_name, state.asset_name,
                    state.rsi_period, state.rsi_ob, state.rsi_os,
                    state.ema_fast_period, state.ema_slow_period,
                    state.bb_period, state.bb_std, state.atr_period,
                    state.win_rate, state.total_trades, state.confidence_score,
                    state.last_30d_wr, state.last_optimized, state.optimization_count
                ))

    def get_strategy_state(self, strategy: str, asset: str) -> Optional[StrategyState]:
        """Get strategy state for a specific strategy+asset pair"""
        with self._conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute("""
                    SELECT * FROM strategy_states 
                    WHERE strategy_name = %s AND asset_name = %s
                """, (strategy, asset))
                row = cursor.fetchone()

        if not row:
            return None

        return StrategyState(
            id=row["id"],
            strategy_name=row["strategy_name"],
            asset_name=row["asset_name"],
            rsi_period=row["rsi_period"],
            rsi_ob=row["rsi_ob"],
            rsi_os=row["rsi_os"],
            ema_fast_period=row["ema_fast_period"],
            ema_slow_period=row["ema_slow_period"],
            bb_period=row["bb_period"],
            bb_std=row["bb_std"],
            atr_period=row["atr_period"],
            win_rate=row["win_rate"],
            total_trades=row["total_trades"],
            confidence_score=row["confidence_score"],
            last_30d_wr=row["last_30d_wr"],
            last_optimized=row["last_optimized"],
            optimization_count=row["optimization_count"],
        )

    def get_all_strategy_states(self) -> list:
        """Get all strategy states"""
        with self._conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute("SELECT * FROM strategy_states ORDER BY confidence_score DESC")
                rows = cursor.fetchall()

        return [StrategyState(
            id=r["id"], strategy_name=r["strategy_name"],
            asset_name=r["asset_name"], rsi_period=r["rsi_period"],
            rsi_ob=r["rsi_ob"], rsi_os=r["rsi_os"],
            ema_fast_period=r["ema_fast_period"], ema_slow_period=r["ema_slow_period"],
            bb_period=r["bb_period"], bb_std=r["bb_std"],
            atr_period=r["atr_period"], win_rate=r["win_rate"],
            total_trades=r["total_trades"], confidence_score=r["confidence_score"],
            last_30d_wr=r["last_30d_wr"], last_optimized=r["last_optimized"],
            optimization_count=r["optimization_count"],
        ) for r in rows]

    # ========== HELPERS ==========

    def _row_to_trade(self, row) -> Trade:
        return Trade(
            id=row["id"], timestamp=normalize_utc_timestamp(row["timestamp"]),
            asset_name=row["asset_name"], asset_id=row["asset_id"],
            strategy=row["strategy"], direction=row["direction"],
            amount=row["amount"], confidence=row["confidence"],
            rsi_value=row["rsi_value"], ema_fast=row["ema_fast"],
            ema_slow=row["ema_slow"], bb_upper=row["bb_upper"],
            bb_lower=row["bb_lower"], bb_mid=row["bb_mid"],
            atr_value=row["atr_value"], candle_pattern=row["candle_pattern"],
            trend_direction=row["trend_direction"], result=row["result"],
            profit=row["profit"], close_price=row["close_price"],
            close_time=normalize_utc_timestamp(row["close_time"]),
            broker_order_id=row.get("broker_order_id", ""),
            broker_position_id=row.get("broker_position_id", ""), mg_level=row["mg_level"],
            session_hour=row["session_hour"], session_type=row["session_type"],
            account_type=row.get("account_type", "demo"),
        )

    def get_summary(self) -> dict:
        """Quick summary stats"""
        with self._conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute("SELECT COUNT(*) as c FROM trades")
                total = cursor.fetchone()["c"]
                
                cursor.execute("SELECT COUNT(*) as c FROM trades WHERE result='win'")
                wins = cursor.fetchone()["c"]
                
                cursor.execute("SELECT COUNT(*) as c FROM trades WHERE result='loss'")
                losses = cursor.fetchone()["c"]
                
                cursor.execute("SELECT COALESCE(SUM(profit), 0) as p FROM trades")
                profit = cursor.fetchone()["p"]
                
                cursor.execute("SELECT COUNT(*) as c FROM strategy_states")
                strategies = cursor.fetchone()["c"]

        return {
            "total_trades": total,
            "wins": wins,
            "losses": losses,
            "win_rate": f"{wins/max(1,total)*100:.1f}%",
            "total_profit": round(profit, 2),
            "strategy_states": strategies,
        }
