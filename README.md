# 🧠 AI Trader — Self-Learning Trading Bot

## What is this?

An AI-powered trading bot for IQ Option that **learns from its mistakes** and automatically optimizes its strategy parameters.

Unlike regular bots with fixed rules, this system:
- 📊 Records every trade with full market context
- 🧠 Analyzes patterns in wins vs losses  
- ⚙️ Auto-tunes RSI/EMA/BB parameters per asset
- 📈 Adapts to changing market conditions
- 📱 Reports via Telegram

## Architecture

```
┌─────────────────────────────────────┐
│         📊 AI TRADER ENGINE         │
├─────────────────────────────────────┤
│  🔍 Data Collector → 🧠 Learner    │
│  🎯 Decision Engine → 📈 Executor  │
│  💾 Trade Logger → 📊 Reporter     │
│         🔄 Self-Improvement Loop    │
└─────────────────────────────────────┘
```

## Quick Start

```bash
# Test with simulated data
python main.py --test

# Check status
python main.py --status

# View AI learning report
python main.py --report

# Start in demo mode
python main.py --mode demo
```

## Strategies

### RSI Reversal (Primary)
- RSI crosses below oversold → CALL
- RSI crosses above overbought → PUT
- Enhanced with EMA trend + candle patterns
- AI auto-optimizes OB/OS per asset

## Assets
EURCAD, GBPCAD, GBPNZD, EURGBP, EURCHF (top 5 from backtest)

## AI Learning

The bot re-optimizes parameters every 100 trades:
- Tests OB/OS ranges (60-85 / 15-40) against history
- Tracks win rate trends (improving vs declining)
- Detects best trading sessions (morning/afternoon/evening)
- Penalizes assets showing decline patterns

## Files

```
ai-trader/
├── main.py              # Entry point
├── config/
│   ├── settings.py      # Configuration
│   └── assets.py        # Asset settings
├── core/
│   ├── engine.py        # Main trading engine
│   └── base_strategy.py # Strategy interface
├── modules/
│   ├── rsi_strategy.py  # RSI Reversal implementation
│   ├── strategy_learner.py # AI optimization brain
│   └── reporter.py      # Telegram reports
├── models/
│   ├── __init__.py      # Database layer
│   ├── trade.py         # Trade model
│   └── strategy_state.py # Optimized params
├── data/                # SQLite DB
├── logs/                # Log files
└── reports/             # Generated reports
```

## ⚠️ Disclaimer

- Always test on DEMO first
- Past performance ≠ future results
- AI optimizes based on history — markets can change
- Never trade money you can't afford to lose
