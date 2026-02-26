"""
run_optimized_backtest.py - 优化版波段策略回测

对比优化前后在25年日线数据上的表现。
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
    from data.data_fetcher import YFinanceDataFetcher
    from backtest.engine import BacktestEngine
    from strategies.optimized_swing import OptimizedSwingStrategy
    from strategies.swing_strategy import SwingStrategy

    # ── 加载数据 ──
    print("[1/4] 加载数据...")
    csv_path = "/media/jskj/Data/quant/Gold/Gold_Quant_Project/data/gc_futures_daily_max.csv"
    df = pd.read_csv(csv_path, parse_dates=["time"])
    print(f"  日线: {len(df)} 条 | {df['time'].iloc[0]} ~ {df['time'].iloc[-1]}")

    report["data"] = {
        "bars": len(df),
        "range": f"{df['time'].iloc[0]} ~ {df['time'].iloc[-1]}",
    }

    # ── 策略配置 ──
    configs = [
        # === 旧策略基准 ===
        {
            "name": "旧策略-宽松波段(基准)",
            "strategy_class": SwingStrategy,
            "params": {"short_period": 40, "long_period": 120,
                       "adx_threshold": 18, "atr_sl_mult": 5.0,
                       "atr_tp_mult": 8.0, "trail_atr_mult": 4.0,
                       "rsi_upper": 40, "risk_pct": 0.02, "reentry_cooldown": 15},
        },
        # === 优化策略 ===
        {
            "name": "优化-标准双向",
            "strategy_class": OptimizedSwingStrategy,
            "params": {"short_period": 40, "long_period": 120,
                       "adx_threshold": 18, "atr_sl_mult": 3.5,
                       "atr_tp1_mult": 4.0, "tp1_close_pct": 0.5,
                       "trail_atr_mult": 2.5, "rsi_long_min": 40,
                       "rsi_short_max": 60, "risk_pct": 0.02,
                       "max_ma_spread": 8.0, "reentry_cooldown": 5,
                       "enable_short": True},
        },
        {
            "name": "优化-纯多头",
            "strategy_class": OptimizedSwingStrategy,
            "params": {"short_period": 40, "long_period": 120,
                       "adx_threshold": 18, "atr_sl_mult": 3.5,
                       "atr_tp1_mult": 4.0, "tp1_close_pct": 0.5,
                       "trail_atr_mult": 2.5, "rsi_long_min": 40,
                       "risk_pct": 0.02, "max_ma_spread": 8.0,
                       "reentry_cooldown": 5, "enable_short": False},
        },
        {
            "name": "优化-紧凑止损双向",
            "strategy_class": OptimizedSwingStrategy,
            "params": {"short_period": 40, "long_period": 120,
                       "adx_threshold": 20, "atr_sl_mult": 3.0,
                       "atr_tp1_mult": 3.5, "tp1_close_pct": 0.5,
                       "trail_atr_mult": 2.0, "rsi_long_min": 42,
                       "rsi_short_max": 58, "risk_pct": 0.02,
                       "max_ma_spread": 6.0, "reentry_cooldown": 5,
                       "enable_short": True},
        },
        {
            "name": "优化-宽松双向",
            "strategy_class": OptimizedSwingStrategy,
            "params": {"short_period": 50, "long_period": 150,
                       "adx_threshold": 18, "atr_sl_mult": 4.0,
                       "atr_tp1_mult": 5.0, "tp1_close_pct": 0.5,
                       "trail_atr_mult": 3.0, "rsi_long_min": 40,
                       "rsi_short_max": 60, "risk_pct": 0.02,
                       "max_ma_spread": 10.0, "reentry_cooldown": 8,
                       "enable_short": True},
        },
        {
            "name": "优化-经典金叉双向",
            "strategy_class": OptimizedSwingStrategy,
            "params": {"short_period": 50, "long_period": 200,
                       "adx_threshold": 20, "atr_sl_mult": 3.5,
                       "atr_tp1_mult": 4.5, "tp1_close_pct": 0.5,
                       "trail_atr_mult": 2.5, "rsi_long_min": 45,
                       "rsi_short_max": 55, "risk_pct": 0.02,
                       "max_ma_spread": 8.0, "reentry_cooldown": 10,
                       "enable_short": True},
        },
    ]

    # ── 回测 ──
    print("[2/4] 运行回测...")
    trade_log_global = []

    class ReportingOpt(OptimizedSwingStrategy):
        def notify_trade(self, trade):
            super().notify_trade(trade)
            if trade.isclosed:
                entry_dt = bt.num2date(trade.dtopen)
                exit_dt = bt.num2date(trade.dtclose)
                trade_log_global.append({
                    "entry": entry_dt.strftime("%Y-%m-%d"),
                    "exit": exit_dt.strftime("%Y-%m-%d"),
                    "dir": "多" if self.direction == 1 or trade.pnl == (trade.price * abs(trade.size) - trade.price * abs(trade.size)) else ("多" if trade.long else "空"),
                    "size": abs(trade.size),
                    "price": round(trade.price, 2),
                    "pnl": round(trade.pnl, 2),
                    "pnlcomm": round(trade.pnlcomm, 2),
                    "bars": trade.barlen,
                    "days": (exit_dt - entry_dt).days,
                })

    class ReportingOld(SwingStrategy):
        def notify_trade(self, trade):
            super().notify_trade(trade)
            if trade.isclosed:
                entry_dt = bt.num2date(trade.dtopen)
                exit_dt = bt.num2date(trade.dtclose)
                trade_log_global.append({
                    "entry": entry_dt.strftime("%Y-%m-%d"),
                    "exit": exit_dt.strftime("%Y-%m-%d"),
                    "dir": "多",
                    "size": abs(trade.size),
                    "price": round(trade.price, 2),
                    "pnl": round(trade.pnl, 2),
                    "pnlcomm": round(trade.pnlcomm, 2),
                    "bars": trade.barlen,
                    "days": (exit_dt - entry_dt).days,
                })

    all_results = []

    for cfg in configs:
        trade_log_global = []
        is_old = cfg["strategy_class"] == SwingStrategy
        cls = ReportingOld if is_old else ReportingOpt

        eng = BacktestEngine(initial_cash=INITIAL_CASH, commission=0.001)
        eng.load_data(df=df)
        eng.add_strategy(strategy_class=cls, printlog=False, **cfg["params"])
        eng.run()
        perf = eng.print_performance()

        trades = trade_log_global.copy()
        won = [t for t in trades if t["pnlcomm"] > 0]
        lost = [t for t in trades if t["pnlcomm"] <= 0]
        long_trades = [t for t in trades if t["dir"] == "多"]
        short_trades = [t for t in trades if t["dir"] == "空"]

        avg_hold = sum(t["days"] for t in trades) / max(len(trades), 1)
        avg_pnl_win = sum(t["pnlcomm"] for t in won) / max(len(won), 1)
        avg_pnl_loss = sum(t["pnlcomm"] for t in lost) / max(len(lost), 1)
        total_pnl = sum(t["pnlcomm"] for t in trades)

        # 连续亏损
        max_consec = 0
        cur = 0
        for t in trades:
            if t["pnlcomm"] <= 0:
                cur += 1
                max_consec = max(max_consec, cur)
            else:
                cur = 0

        # 年度分析
        yearly = defaultdict(lambda: {"trades": 0, "pnl": 0.0, "won": 0, "lost": 0})
        for t in trades:
            y = t["entry"][:4]
            yearly[y]["trades"] += 1
            yearly[y]["pnl"] += t["pnlcomm"]
            yearly[y]["won"] += 1 if t["pnlcomm"] > 0 else 0
            yearly[y]["lost"] += 1 if t["pnlcomm"] <= 0 else 0

        res = {
            "name": cfg["name"],
            "perf": {
                "ret": round(perf.get("total_return", 0), 2),
                "sharpe": round(perf["sharpe_ratio"], 4) if perf.get("sharpe_ratio") else None,
                "mdd": round(perf.get("max_drawdown", 0), 2),
                "final": round(perf.get("final_value", 0), 2),
                "trades": perf.get("total_trades", 0),
                "won": perf.get("won_trades", 0),
                "lost": perf.get("lost_trades", 0),
                "wr": round(perf.get("won_trades", 0) / max(perf.get("total_trades", 1), 1) * 100, 1),
            },
            "hold": {
                "avg": round(avg_hold, 1),
                "avg_win": round(sum(t["days"] for t in won) / max(len(won), 1), 1),
                "avg_loss": round(sum(t["days"] for t in lost) / max(len(lost), 1), 1),
            },
            "risk": {
                "avg_win": round(avg_pnl_win, 2),
                "avg_loss": round(avg_pnl_loss, 2),
                "pf": round(abs(avg_pnl_win / avg_pnl_loss), 2) if avg_pnl_loss != 0 else None,
                "max_win": round(max((t["pnlcomm"] for t in trades), default=0), 2),
                "max_loss": round(min((t["pnlcomm"] for t in trades), default=0), 2),
                "max_consec_loss": max_consec,
            },
            "direction": {
                "long": len(long_trades),
                "short": len(short_trades),
                "long_pnl": round(sum(t["pnlcomm"] for t in long_trades), 2),
                "short_pnl": round(sum(t["pnlcomm"] for t in short_trades), 2),
            },
            "yearly": {k: {kk: round(vv, 2) if isinstance(vv, float) else vv
                           for kk, vv in v.items()}
                       for k, v in sorted(yearly.items())},
            "trades": trades,
        }
        all_results.append(res)
        print(f"  ✅ {cfg['name']}: 收益{res['perf']['ret']}%, "
              f"{len(trades)}笔(多{len(long_trades)}/空{len(short_trades)}), "
              f"均持{avg_hold:.0f}天, 胜率{res['perf']['wr']}%")

    report["strategies"] = all_results
    report["status"] = "success"
    print("[3/4] 完成")

except Exception as e:
    import traceback
    report["error"] = str(e)
    report["traceback"] = traceback.format_exc()
    print(f"错误: {e}")
    traceback.print_exc()

import os
_output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
os.makedirs(_output_dir, exist_ok=True)
_output_path = os.path.join(_output_dir, "gold_optimized_backtest.json")
with open(_output_path, "w") as f:
    json.dump(report, f, indent=2, default=str, ensure_ascii=False)
print(f"[4/4] 结果已保存至 {_output_path}")
