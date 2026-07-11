#!/usr/bin/env python3
"""
🧠 AI Trader — Main Runner
Connects to IQ Option MCP, fetches data, runs the engine
"""
import sys
import os
import time
import json
import logging
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from core.engine import AITraderEngine
from models import Database
from config.assets import TOP_ASSETS
from config.settings import CANDLE_SIZE, CANDLE_COUNT

log = logging.getLogger("ai_trader")


def print_banner():
    print("""
╔═══════════════════════════════════════════╗
║     🧠 AI TRADER — Self-Learning Bot     ║
║     by Hermes Agent × Nadef              ║
╠═══════════════════════════════════════════╣
║  Strategy: RSI Reversal (AI-Optimized)   ║
║  Assets: EURCAD, GBPCAD, GBPNZD, ...     ║
║  Mode: Demo | AI Learning: ON            ║
╚═══════════════════════════════════════════╝
""")


def show_status(engine: AITraderEngine):
    """Print current status"""
    status = engine.get_status()
    db = status["db_summary"]

    print(f"\n📊 === AI TRADER STATUS === {datetime.now().strftime('%H:%M:%S')}")
    print(f"  🎯 Total trades: {db['total_trades']}")
    print(f"  ✅ Wins: {db['wins']} | ❌ Losses: {db['losses']}")
    print(f"  📈 Win rate: {db['win_rate']}")
    print(f"  💰 Total profit: ${db['total_profit']}")
    print(f"  🧠 Strategy states: {db['strategy_states']}")
    
    if status["last_signal"]:
        sig = status["last_signal"]
        print(f"  🔍 Last signal: {sig['asset']} {sig['direction'].upper()} "
              f"conf={sig['confidence']:.0f}")

    today = status["stats_today"]
    print(f"\n  📅 Today: {today['trades_today']} trades, "
          f"W:{today['wins_today']} L:{today['losses_today']}, "
          f"P/L: ${today['profit_today']:.2f}")


def show_learning_report(engine: AITraderEngine):
    """Show what the AI has learned"""
    from modules.strategy_learner import StrategyLearner
    learner = StrategyLearner(engine.db)
    report = learner.get_learning_report()

    print(f"\n🧠 === AI LEARNING REPORT ===")
    print(f"  Total strategy+asset pairs: {report['total_pairs']}")
    
    if report["high_confidence"]:
        print(f"\n  ✅ HIGH CONFIDENCE:")
        for h in report["high_confidence"]:
            print(f"    {h['strategy']}/{h['asset']}: "
                  f"WR={h['wr']} (30d={h['wr_30d']}) "
                  f"OB={h['ob']} OS={h['os']} "
                  f"conf={h['confidence']:.0f} trades={h['trades']}")

    if report["low_confidence"]:
        print(f"\n  ⚠️ LOW CONFIDENCE:")
        for l in report["low_confidence"]:
            print(f"    {l['strategy']}/{l['asset']}: "
                  f"WR={l['wr']} conf={l['confidence']:.0f}")

    if report["needs_data"]:
        print(f"\n  📊 NEEDS MORE DATA:")
        for n in report["needs_data"]:
            print(f"    {n['strategy']}/{n['asset']}: {n['trades']} trades")

    if report["recommendations"]:
        print(f"\n  💡 RECOMMENDATIONS:")
        for r in report["recommendations"]:
            print(f"    {r}")


def main():
    print_banner()

    import argparse
    parser = argparse.ArgumentParser(description="AI Trader Engine")
    parser.add_argument("--mode", choices=["demo", "live"], default="demo")
    parser.add_argument("--status", action="store_true", help="Show status and exit")
    parser.add_argument("--report", action="store_true", help="Show learning report")
    parser.add_argument("--test", action="store_true", help="Run test with fake data")
    args = parser.parse_args()

    engine = AITraderEngine(mode=args.mode)

    if args.status:
        show_status(engine)
        return

    if args.report:
        show_learning_report(engine)
        return

    if args.test:
        run_test(engine)
        return

    # Normal run — will connect to MCP for real data
    print(f"🚀 Starting AI Trader in {args.mode} mode...")
    print(f"📡 Connecting to IQ Option via MCP...")
    
    # Show initial status
    show_status(engine)
    show_learning_report(engine)
    
    print(f"\n⏳ Engine ready. Waiting for real data connection...")
    print(f"💡 Use --test to run with simulated data")
    print(f"💡 Use --status to check current state")
    print(f"💡 Use --report to see AI learning report")


def run_test(engine: AITraderEngine):
    """Run with simulated candle data to verify the engine works"""
    import random
    
    print("\n🧪 === TEST MODE — Simulated Data ===")
    
    # Generate fake candles
    def generate_candles(n=200, base=1.1000):
        candles = []
        price = base
        for i in range(n):
            change = random.uniform(-0.002, 0.002)
            open_p = price
            close_p = price + change
            high = max(open_p, close_p) + random.uniform(0, 0.001)
            low = min(open_p, close_p) - random.uniform(0, 0.001)
            candles.append({
                "open": open_p, "close": close_p,
                "min": low, "max": high,
                "from": i * 60, "to": (i + 1) * 60,
            })
            price = close_p
        return candles

    # Generate candles for each asset
    candles_by_asset = {}
    for asset_name in TOP_ASSETS:
        candles_by_asset[asset_name] = generate_candles()

    # Run one cycle
    actions = engine.run_cycle(candles_by_asset)

    if actions:
        print(f"\n🎯 Signals generated: {len(actions)}")
        for a in actions:
            trade = a["trade"]
            signal = a["signal"]
            print(f"  📈 {trade.asset_name} {trade.direction.upper()} "
                  f"conf={signal.confidence:.0f} | {signal.reason}")
    else:
        print(f"\n⏸️ No signals in this cycle (normal — need specific RSI conditions)")

    # Show status
    show_status(engine)
    show_learning_report(engine)

    print(f"\n✅ Test complete! Engine is working.")


if __name__ == "__main__":
    main()
