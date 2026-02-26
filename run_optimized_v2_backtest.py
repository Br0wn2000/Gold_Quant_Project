"""
run_optimized_v2_backtest.py - 优化V2 vs 原始策略对比回测
"""
import sys
import json
from collections import defaultdict

import pandas as pd
import backtrader as bt

sys.path.insert(0, ".")

report = {}
INITIAL_CASH = 100000.0

try:
    from backtest.engine import BacktestEngine
    from strategies.optimized_swing_v2 import OptimizedSwingV2
    from strategies.swing_strategy import SwingStrategy

    print("[1/3] 加载数据...")
    csv_path = "/media/jskj/Data/quant/Gold/Gold_Quant_Project/data/gc_futures_daily_max.csv"
    df = pd.read_csv(csv_path, parse_dates=["time"])
    print(f"  {len(df)} 条 | {df['time'].iloc[0]} ~ {df['time'].iloc[-1]}")

    report["data"] = {"bars": len(df),
                      "range": f"{df['time'].iloc[0]} ~ {df['time'].iloc[-1]}"}

    configs = [
        # 基准
        {"name": "旧-宽松波段(基准)", "cls": SwingStrategy,
         "p": {"short_period": 40, "long_period": 120, "adx_threshold": 18,
               "atr_sl_mult": 5.0, "atr_tp_mult": 8.0, "trail_atr_mult": 4.0,
               "rsi_upper": 40, "risk_pct": 0.02, "reentry_cooldown": 15}},
        # V2 变体
        {"name": "V2-双向标准", "cls": OptimizedSwingV2,
         "p": {"short_period": 40, "long_period": 120, "adx_threshold": 18,
               "atr_sl_mult": 5.0, "atr_trail_trigger": 6.0, "trail_atr_mult": 3.5,
               "breakeven_trigger": 3.0, "rsi_long_min": 40, "rsi_short_max": 60,
               "risk_pct": 0.02, "max_ma_spread": 10.0, "reentry_cooldown": 10,
               "enable_short": True}},
        {"name": "V2-纯多头", "cls": OptimizedSwingV2,
         "p": {"short_period": 40, "long_period": 120, "adx_threshold": 18,
               "atr_sl_mult": 5.0, "atr_trail_trigger": 6.0, "trail_atr_mult": 3.5,
               "breakeven_trigger": 3.0, "rsi_long_min": 40,
               "risk_pct": 0.02, "max_ma_spread": 10.0, "reentry_cooldown": 10,
               "enable_short": False}},
        {"name": "V2-经典双向", "cls": OptimizedSwingV2,
         "p": {"short_period": 50, "long_period": 150, "adx_threshold": 20,
               "atr_sl_mult": 5.0, "atr_trail_trigger": 6.0, "trail_atr_mult": 3.5,
               "breakeven_trigger": 3.0, "rsi_long_min": 45, "rsi_short_max": 55,
               "risk_pct": 0.02, "max_ma_spread": 10.0, "reentry_cooldown": 10,
               "enable_short": True}},
        {"name": "V2-激进双向", "cls": OptimizedSwingV2,
         "p": {"short_period": 40, "long_period": 120, "adx_threshold": 15,
               "atr_sl_mult": 4.0, "atr_trail_trigger": 5.0, "trail_atr_mult": 3.0,
               "breakeven_trigger": 2.5, "rsi_long_min": 38, "rsi_short_max": 62,
               "risk_pct": 0.025, "max_ma_spread": 12.0, "reentry_cooldown": 5,
               "enable_short": True}},
    ]

    print("[2/3] 回测中...")
    trade_log_g = []

    class RptOld(SwingStrategy):
        def notify_trade(self, trade):
            super().notify_trade(trade)
            if trade.isclosed:
                e = bt.num2date(trade.dtopen); x = bt.num2date(trade.dtclose)
                trade_log_g.append({"entry": e.strftime("%Y-%m-%d"), "exit": x.strftime("%Y-%m-%d"),
                    "dir": "多", "size": abs(trade.size), "price": round(trade.price,2),
                    "pnl": round(trade.pnl,2), "pnlcomm": round(trade.pnlcomm,2),
                    "bars": trade.barlen, "days": (x-e).days})

    class RptV2(OptimizedSwingV2):
        def notify_trade(self, trade):
            super().notify_trade(trade)
            if trade.isclosed:
                e = bt.num2date(trade.dtopen); x = bt.num2date(trade.dtclose)
                trade_log_g.append({"entry": e.strftime("%Y-%m-%d"), "exit": x.strftime("%Y-%m-%d"),
                    "dir": "多" if trade.long else "空", "size": abs(trade.size),
                    "price": round(trade.price,2), "pnl": round(trade.pnl,2),
                    "pnlcomm": round(trade.pnlcomm,2), "bars": trade.barlen,
                    "days": (x-e).days})

    results = []
    for cfg in configs:
        trade_log_g = []
        cls = RptOld if cfg["cls"] == SwingStrategy else RptV2
        eng = BacktestEngine(initial_cash=INITIAL_CASH, commission=0.001)
        eng.load_data(df=df)
        eng.add_strategy(strategy_class=cls, printlog=False, **cfg["p"])
        eng.run()
        perf = eng.print_performance()
        trades = trade_log_g.copy()

        won = [t for t in trades if t["pnlcomm"] > 0]
        lost = [t for t in trades if t["pnlcomm"] <= 0]
        longs = [t for t in trades if t["dir"] == "多"]
        shorts = [t for t in trades if t["dir"] == "空"]

        avg_hold = sum(t["days"] for t in trades) / max(len(trades),1)
        avg_win = sum(t["pnlcomm"] for t in won) / max(len(won),1)
        avg_loss = sum(t["pnlcomm"] for t in lost) / max(len(lost),1)

        mc = 0; c = 0
        for t in trades:
            if t["pnlcomm"] <= 0: c += 1; mc = max(mc, c)
            else: c = 0

        yearly = defaultdict(lambda: {"n":0,"pnl":0.0,"w":0,"l":0})
        for t in trades:
            y = t["entry"][:4]
            yearly[y]["n"] += 1; yearly[y]["pnl"] += t["pnlcomm"]
            yearly[y]["w" if t["pnlcomm"]>0 else "l"] += 1

        r = {
            "name": cfg["name"],
            "perf": {
                "ret": round(perf.get("total_return",0),2),
                "sharpe": round(perf["sharpe_ratio"],4) if perf.get("sharpe_ratio") else None,
                "mdd": round(perf.get("max_drawdown",0),2),
                "final": round(perf.get("final_value",0),2),
                "trades": perf.get("total_trades",0),
                "won": perf.get("won_trades",0),
                "lost": perf.get("lost_trades",0),
                "wr": round(perf.get("won_trades",0)/max(perf.get("total_trades",1),1)*100,1),
            },
            "hold": {"avg": round(avg_hold,1),
                     "avg_win": round(sum(t["days"] for t in won)/max(len(won),1),1),
                     "avg_loss": round(sum(t["days"] for t in lost)/max(len(lost),1),1)},
            "risk": {"avg_win": round(avg_win,2), "avg_loss": round(avg_loss,2),
                     "pf": round(abs(avg_win/avg_loss),2) if avg_loss != 0 else None,
                     "max_win": round(max((t["pnlcomm"] for t in trades), default=0),2),
                     "max_loss": round(min((t["pnlcomm"] for t in trades), default=0),2),
                     "max_consec_loss": mc},
            "dir": {"long": len(longs), "short": len(shorts),
                    "long_pnl": round(sum(t["pnlcomm"] for t in longs),2),
                    "short_pnl": round(sum(t["pnlcomm"] for t in shorts),2)},
            "yearly": {k: dict(v) for k,v in sorted(yearly.items())},
            "trades": trades,
        }
        results.append(r)
        print(f"  ✅ {cfg['name']}: {r['perf']['ret']}%, "
              f"{len(trades)}笔(多{len(longs)}/空{len(shorts)}), "
              f"均持{avg_hold:.0f}天, 胜率{r['perf']['wr']}%")

    report["strategies"] = results
    report["status"] = "success"
    print("[3/3] 完成")

except Exception as e:
    import traceback
    report["error"] = str(e)
    report["traceback"] = traceback.format_exc()
    print(f"错误: {e}")
    traceback.print_exc()

import os
_output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
os.makedirs(_output_dir, exist_ok=True)
_output_path = os.path.join(_output_dir, "gold_v2_backtest.json")
with open(_output_path, "w") as f:
    json.dump(report, f, indent=2, default=str, ensure_ascii=False)
print(f"结果已保存至 {_output_path}")
