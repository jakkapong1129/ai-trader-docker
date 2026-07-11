"""
🧠 AI Trader — Reporter
Generates reports for Telegram and console
"""
import json
from datetime import datetime, timedelta
from models import Database
from models.trade import StrategyPerformance


class Reporter:
    """Generate formatted reports"""

    def __init__(self, db: Database):
        self.db = db

    def daily_report(self) -> str:
        """Generate daily report for Telegram"""
        today = datetime.now().strftime("%Y-%m-%d")
        
        # Today's trades
        trades = self.db.get_trades(days=1)
        completed = [t for t in trades if t.result in ("win", "loss", "equal")]
        
        if not completed:
            return f"📊 **AI Trader Report** {today}\n\nยังไม่มีเทรดวันนี้"

        wins = sum(1 for t in completed if t.result == "win")
        losses = sum(1 for t in completed if t.result == "loss")
        profit = sum(t.profit for t in completed)
        wr = wins / len(completed) * 100

        # Best asset
        asset_stats = {}
        for t in completed:
            if t.asset_name not in asset_stats:
                asset_stats[t.asset_name] = {"w": 0, "t": 0, "p": 0}
            asset_stats[t.asset_name]["t"] += 1
            asset_stats[t.asset_name]["p"] += t.profit
            if t.result == "win":
                asset_stats[t.asset_name]["w"] += 1

        best_asset = max(asset_stats.items(), 
                        key=lambda x: x[1]["w"]/max(1, x[1]["t"]))

        report = f"""🧠 **AI Trader Daily Report** {today}

📈 **สรุปวันนี้**
• เทรดทั้งหมด: {len(completed)}
• ชนะ: {wins} | แพ้: {losses}
• Win Rate: {wr:.1f}%
• กำไร/ขาดทุน: ${profit:+.2f}

🏆 **Asset ดีที่สุด**: {best_asset[0]} ({best_asset[1]['w']}/{best_asset[1]['t']})

📊 **แยกตาม Asset**
"""
        for asset, stats in sorted(asset_stats.items(), 
                                    key=lambda x: x[1]["p"], reverse=True):
            awr = stats["w"] / max(1, stats["t"]) * 100
            emoji = "✅" if stats["p"] >= 0 else "❌"
            report += f"  {emoji} {asset}: {awr:.0f}% ({stats['w']}/{stats['t']}) ${stats['p']:+.2f}\n"

        return report

    def weekly_report(self) -> str:
        """Generate weekly report"""
        trades = self.db.get_trades(days=7)
        completed = [t for t in trades if t.result in ("win", "loss", "equal")]
        
        if not completed:
            return "📊 **Weekly Report**\n\nไม่มีเทรดในสัปดาห์นี้"

        wins = sum(1 for t in completed if t.result == "win")
        profit = sum(t.profit for t in completed)
        wr = wins / len(completed) * 100

        # Per strategy
        strats = {}
        for t in completed:
            if t.strategy not in strats:
                strats[t.strategy] = {"w": 0, "t": 0, "p": 0}
            strats[t.strategy]["t"] += 1
            strats[t.strategy]["p"] += t.profit
            if t.result == "win":
                strats[t.strategy]["w"] += 1

        report = f"""🧠 **AI Trader Weekly Report**

📈 **สรุปสัปดาห์**
• เทรดทั้งหมด: {len(completed)}
• Win Rate: {wr:.1f}%
• กำไร/ขาดทุน: ${profit:+.2f}

📊 **แยกตาม Strategy**
"""
        for strat, stats in strats.items():
            swr = stats["w"] / max(1, stats["t"]) * 100
            report += f"  • {strat}: {swr:.0f}% ({stats['t']} trades) ${stats['p']:+.2f}\n"

        return report

    def signal_report(self, asset: str, direction: str, 
                      confidence: float, reason: str) -> str:
        """Format a signal notification for Telegram"""
        emoji = "🟢" if direction == "call" else "🔴"
        dir_thai = "📈 ขึ้น (CALL)" if direction == "call" else "📉 ลง (PUT)"
        
        return f"""{emoji} **AI Signal**

• Asset: **{asset}**
• Direction: {dir_thai}
• Confidence: **{confidence:.0f}/100**
• Reason: {reason}
• Time: {datetime.now().strftime('%H:%M:%S')}
"""
