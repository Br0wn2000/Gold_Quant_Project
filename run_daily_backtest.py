"""
run_daily_backtest.py - 日线级别完整回测

使用最长可用日线数据，全面测试波段策略。
输出详细逐笔交易报告 + 年度分析 + 中期周期分析。
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
    # ============================================================
    # 1. 获取最长日线数据
    # ============================================================
    from data.data_fetcher import YFinanceDataFetcher
    from backtest.engine import BacktestEngine
    from strategies.swing_strategy import SwingStrategy

    print("[1/3] 获取数据...")
    fetcher = YFinanceDataFetcher(symbol="GC=F")
    df = fetcher.fetch_ohlcv(period="max", interval="1d")
    if df is None or df.empty:
        raise RuntimeError("数据获取失败")
    fetcher.save_to_csv(df, "gc_futures_daily_max.csv")
    print(f"  日线: {len(df)} 条 | {df['time'].iloc[0]} ~ {df['time'].iloc[-1]}")
    print(f"  价格: ${df['close'].min():.2f} ~ ${df['close'].max():.2f}")

    report["data"] = {
        "bars": len(df),
        "date_range": f"{df['time'].iloc[0]} ~ {df['time'].iloc[-1]}",
        "price_range": f"${df['close'].min():.2f} ~ ${df['close'].max():.2f}",
    }

    # ============================================================
    # 2. 策略参数组合
    # ============================================================
    configs = [
        {
            "name": "宽松波段 MA(40/120)",
            "params": {"short_period": 40, "long_period": 120,
                       "adx_threshold": 18, "atr_sl_mult": 5.0,
                       "atr_tp_mult": 8.0, "trail_atr_mult": 4.0,
                       "rsi_upper": 40, "risk_pct": 0.02, "reentry_cooldown": 15},
        },
        {
            "name": "标准波段 MA(50/150)",
            "params": {"short_period": 50, "long_period": 150,
                       "adx_threshold": 20, "atr_sl_mult": 4.0,
                       "atr_tp_mult": 6.0, "trail_atr_mult": 3.0,
                       "rsi_upper": 45, "risk_pct": 0.02, "reentry_cooldown": 10},
        },
        {
            "name": "经典金叉 MA(50/200)",
            "params": {"short_period": 50, "long_period": 200,
                       "adx_threshold": 22, "atr_sl_mult": 4.0,
                       "atr_tp_mult": 7.0, "trail_atr_mult": 3.5,
                       "rsi_upper": 50, "risk_pct": 0.02, "reentry_cooldown": 20},
        },
        {
            "name": "超长波段 MA(60/200)",
            "params": {"short_period": 60, "long_period": 200,
                       "adx_threshold": 20, "atr_sl_mult": 5.0,
                       "atr_tp_mult": 8.0, "trail_atr_mult": 4.0,
                       "rsi_upper": 45, "risk_pct": 0.02, "reentry_cooldown": 20},
        },
        {
            "name": "稳健波段 MA(30/90)",
            "params": {"short_period": 30, "long_period": 90,
                       "adx_threshold": 20, "atr_sl_mult": 4.0,
                       "atr_tp_mult": 6.0, "trail_atr_mult": 3.0,
                       "rsi_upper": 45, "risk_pct": 0.02, "reentry_cooldown": 10},
        },
    ]

    # ============================================================
    # 3. 回测
    # ============================================================
    print("[2/3] 运行回测...")

    trade_log_global = []

    class ReportingSwing(SwingStrategy):
        def notify_trade(self, trade):
            super().notify_trade(trade)
            if trade.isclosed:
                entry_dt = bt.num2date(trade.dtopen)
                exit_dt = bt.num2date(trade.dtclose)
                duration_days = (exit_dt - entry_dt).days
                trade_log_global.append({
                    "entry_date": entry_dt.strftime("%Y-%m-%d"),
                    "exit_date": exit_dt.strftime("%Y-%m-%d"),
                    "size": abs(trade.size),
                    "entry_price": round(trade.price, 2),
                    "exit_price": round(trade.price + trade.pnl / abs(trade.size), 2) if trade.size != 0 else 0,
                    "pnl": round(trade.pnl, 2),
                    "pnlcomm": round(trade.pnlcomm, 2),
                    "duration_bars": trade.barlen,
                    "duration_days": duration_days,
                })

    all_results = []

    for cfg in configs:
        trade_log_global = []

        eng = BacktestEngine(initial_cash=INITIAL_CASH, commission=0.001)
        eng.load_data(df=df)
        eng.add_strategy(strategy_class=ReportingSwing, printlog=False, **cfg["params"])
        eng.run()
        perf = eng.print_performance()

        trades = trade_log_global.copy()
        won = [t for t in trades if t["pnlcomm"] > 0]
        lost = [t for t in trades if t["pnlcomm"] <= 0]

        avg_hold = sum(t["duration_days"] for t in trades) / max(len(trades), 1)
        avg_hold_win = sum(t["duration_days"] for t in won) / max(len(won), 1)
        avg_hold_loss = sum(t["duration_days"] for t in lost) / max(len(lost), 1)
        avg_pnl_win = sum(t["pnlcomm"] for t in won) / max(len(won), 1)
        avg_pnl_loss = sum(t["pnlcomm"] for t in lost) / max(len(lost), 1)
        total_pnl = sum(t["pnlcomm"] for t in trades)
        max_single_win = max((t["pnlcomm"] for t in trades), default=0)
        max_single_loss = min((t["pnlcomm"] for t in trades), default=0)

        # 连续亏损统计
        max_consec_loss = 0
        cur_consec = 0
        for t in trades:
            if t["pnlcomm"] <= 0:
                cur_consec += 1
                max_consec_loss = max(max_consec_loss, cur_consec)
            else:
                cur_consec = 0

        # 年度分析
        yearly = defaultdict(lambda: {"trades": 0, "pnl": 0.0, "won": 0, "lost": 0})
        for t in trades:
            y = t["entry_date"][:4]
            yearly[y]["trades"] += 1
            yearly[y]["pnl"] += t["pnlcomm"]
            if t["pnlcomm"] > 0:
                yearly[y]["won"] += 1
            else:
                yearly[y]["lost"] += 1

        # 中期周期：按连续盈/亏 划分
        cycles = []
        if trades:
            cycle_trades = [trades[0]]
            for t in trades[1:]:
                prev_positive = cycle_trades[-1]["pnlcomm"] > 0
                cur_positive = t["pnlcomm"] > 0
                if cur_positive == prev_positive:
                    cycle_trades.append(t)
                else:
                    cpnl = sum(ct["pnlcomm"] for ct in cycle_trades)
                    cycles.append({
                        "start": cycle_trades[0]["entry_date"],
                        "end": cycle_trades[-1]["exit_date"],
                        "num_trades": len(cycle_trades),
                        "total_pnl": round(cpnl, 2),
                        "profitable": cpnl > 0,
                        "type": "盈利周期" if cpnl > 0 else "亏损周期",
                    })
                    cycle_trades = [t]
            # 最后一组
            cpnl = sum(ct["pnlcomm"] for ct in cycle_trades)
            cycles.append({
                "start": cycle_trades[0]["entry_date"],
                "end": cycle_trades[-1]["exit_date"],
                "num_trades": len(cycle_trades),
                "total_pnl": round(cpnl, 2),
                "profitable": cpnl > 0,
                "type": "盈利周期" if cpnl > 0 else "亏损周期",
            })

        profitable_cycles = sum(1 for c in cycles if c["profitable"])

        res = {
            "name": cfg["name"],
            "performance": {
                "total_return": round(perf.get("total_return", 0), 2),
                "sharpe_ratio": round(perf["sharpe_ratio"], 4) if perf.get("sharpe_ratio") else None,
                "max_drawdown": round(perf.get("max_drawdown", 0), 2),
                "final_value": round(perf.get("final_value", 0), 2),
                "total_trades": perf.get("total_trades", 0),
                "won_trades": perf.get("won_trades", 0),
                "lost_trades": perf.get("lost_trades", 0),
                "win_rate": round(perf.get("won_trades", 0) / max(perf.get("total_trades", 1), 1) * 100, 1),
            },
            "holding": {
                "avg_all": round(avg_hold, 1),
                "avg_winners": round(avg_hold_win, 1),
                "avg_losers": round(avg_hold_loss, 1),
            },
            "risk": {
                "avg_win": round(avg_pnl_win, 2),
                "avg_loss": round(avg_pnl_loss, 2),
                "profit_factor": round(abs(avg_pnl_win / avg_pnl_loss), 2) if avg_pnl_loss != 0 else None,
                "max_win": round(max_single_win, 2),
                "max_loss": round(max_single_loss, 2),
                "max_consec_loss": max_consec_loss,
            },
            "yearly": {k: {kk: round(vv, 2) if isinstance(vv, float) else vv
                           for kk, vv in v.items()} for k, v in sorted(yearly.items())},
            "cycles": cycles,
            "cycle_summary": {
                "total": len(cycles),
                "profitable": profitable_cycles,
                "rate": round(profitable_cycles / max(len(cycles), 1) * 100, 1),
            },
            "trades": trades,
        }
        all_results.append(res)
        print(f"  ✅ {cfg['name']}: 收益{res['performance']['total_return']}%, "
              f"{len(trades)}笔, 均持{avg_hold:.0f}天, 胜率{res['performance']['win_rate']}%")

    report["strategies"] = all_results
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
_output_path = os.path.join(_output_dir, "gold_daily_backtest.json")
with open(_output_path, "w") as f:
    json.dump(report, f, indent=2, default=str, ensure_ascii=False)
print(f"结果已保存至 {_output_path}")
