"""
run_4h_backtest.py - 4小时K线回测脚本（含详细报告）

1. 拉取近2年 1H 数据 → 重采样为 4H K线
2. 运行增强版策略回测
3. 按中期周期分析每笔交易
4. 输出详细 JSON 报告
"""
import sys
import json
from datetime import datetime, timedelta
from collections import defaultdict

import numpy as np
import pandas as pd

sys.path.insert(0, ".")

report = {}

try:
    # ============================================================
    # 1. 获取 1H 数据并重采样为 4H
    # ============================================================
    from data.data_fetcher import YFinanceDataFetcher

    fetcher = YFinanceDataFetcher(symbol="GC=F")

    # YFinance 1h 数据最多730天，分两段拉取拼接确保覆盖2年
    print("[1/5] 拉取近2年 1H 数据...")
    end_date = "2026-02-24"
    mid_date = "2025-02-24"
    start_date = "2024-02-24"

    df_p1 = fetcher.fetch_ohlcv(start_date=start_date, end_date=mid_date, interval="1h")
    df_p2 = fetcher.fetch_ohlcv(start_date=mid_date, end_date=end_date, interval="1h")

    if df_p1 is not None and df_p2 is not None:
        df_1h = pd.concat([df_p1, df_p2], ignore_index=True)
        df_1h.drop_duplicates(subset="time", keep="last", inplace=True)
        df_1h.sort_values("time", inplace=True)
        df_1h.reset_index(drop=True, inplace=True)
    elif df_p1 is not None:
        df_1h = df_p1
    elif df_p2 is not None:
        df_1h = df_p2
    else:
        raise RuntimeError("数据获取失败")

    print(f"  1H 数据: {len(df_1h)} 条 | {df_1h['time'].iloc[0]} ~ {df_1h['time'].iloc[-1]}")

    # 重采样为 4H
    print("[2/5] 重采样为 4H K线...")
    df_1h_indexed = df_1h.set_index("time")
    df_4h = df_1h_indexed.resample("4h").agg({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    }).dropna().reset_index()
    df_4h.rename(columns={"time": "time"}, inplace=True)

    fetcher.save_to_csv(df_4h, "gc_futures_4h_2y.csv")

    report["data"] = {
        "source": "GC=F (COMEX Gold Futures)",
        "original_bars_1h": len(df_1h),
        "resampled_bars_4h": len(df_4h),
        "date_range": f"{df_4h['time'].iloc[0]} ~ {df_4h['time'].iloc[-1]}",
        "price_range": f"${df_4h['close'].min():.2f} ~ ${df_4h['close'].max():.2f}",
    }
    print(f"  4H 数据: {len(df_4h)} 条 | {df_4h['time'].iloc[0]} ~ {df_4h['time'].iloc[-1]}")

    # ============================================================
    # 2. 计算技术指标
    # ============================================================
    print("[3/5] 计算技术指标...")
    from factors.technical_indicators import add_all_indicators
    df_4h_ind = add_all_indicators(df_4h)

    # ============================================================
    # 3. 回测 - 增强均衡型策略（参考之前最优参数，微调适配4H周期）
    # ============================================================
    print("[4/5] 运行回测...")
    import backtrader as bt
    from backtest.engine import BacktestEngine
    from strategies.enhanced_ma_strategy import EnhancedMAStrategy

    # 自定义 Observer 记录每笔交易详情
    class TradeCollector(bt.Strategy):
        """用于收集交易详情的 mixin，需与实际策略搭配使用"""
        pass

    trade_log = []

    class ReportingStrategy(EnhancedMAStrategy):
        """带详细交易记录的增强策略"""
        def notify_trade(self, trade):
            super().notify_trade(trade)
            if trade.isclosed:
                trade_log.append({
                    "entry_date": bt.num2date(trade.dtopen).strftime("%Y-%m-%d %H:%M"),
                    "exit_date": bt.num2date(trade.dtclose).strftime("%Y-%m-%d %H:%M"),
                    "direction": "LONG",
                    "size": abs(trade.size),
                    "entry_price": round(trade.price, 2),
                    "exit_price": round(trade.price + trade.pnl / abs(trade.size), 2) if trade.size != 0 else 0,
                    "pnl": round(trade.pnl, 2),
                    "pnlcomm": round(trade.pnlcomm, 2),
                    "duration_bars": trade.barlen,
                })

    # 测试多组参数
    configs = [
        {
            "name": "4H-保守型",
            "desc": "MA(20/60) RSI>50 SL:2.5xATR 移动止盈:4xATR 风险1%",
            "params": {"short_period": 20, "long_period": 60, "rsi_upper": 50,
                       "atr_sl_mult": 2.5, "atr_tp_mult": 4.0, "trail_atr_mult": 2.0,
                       "risk_pct": 0.01},
        },
        {
            "name": "4H-均衡型",
            "desc": "MA(15/45) RSI>50 SL:2xATR 移动止盈:3xATR 风险2%",
            "params": {"short_period": 15, "long_period": 45, "rsi_upper": 50,
                       "atr_sl_mult": 2.0, "atr_tp_mult": 3.0, "trail_atr_mult": 1.5,
                       "risk_pct": 0.02},
        },
        {
            "name": "4H-趋势跟踪",
            "desc": "MA(12/36) RSI>48 SL:2xATR 移动止盈:3.5xATR 风险2%",
            "params": {"short_period": 12, "long_period": 36, "rsi_upper": 48,
                       "atr_sl_mult": 2.0, "atr_tp_mult": 3.5, "trail_atr_mult": 1.5,
                       "risk_pct": 0.02},
        },
    ]

    strategy_results = []
    all_trade_logs = {}

    for cfg in configs:
        trade_log = []  # 重置

        eng = BacktestEngine(initial_cash=100000.0, commission=0.001)
        eng.load_data(df=df_4h)
        eng.add_strategy(strategy_class=ReportingStrategy, printlog=False, **cfg["params"])
        eng.run()
        perf = eng.print_performance()

        # 按季度分组分析交易
        quarterly_stats = defaultdict(lambda: {"trades": 0, "pnl": 0, "won": 0, "lost": 0})
        for t in trade_log:
            q = pd.Timestamp(t["entry_date"]).to_period("Q").strftime("%Y-Q%q")
            quarterly_stats[q]["trades"] += 1
            quarterly_stats[q]["pnl"] += t["pnlcomm"]
            if t["pnlcomm"] > 0:
                quarterly_stats[q]["won"] += 1
            else:
                quarterly_stats[q]["lost"] += 1

        # 中期周期分析（以连续盈亏划分 cycle）
        cycles = []
        if trade_log:
            cycle_trades = []
            cycle_pnl = 0
            for t in trade_log:
                cycle_trades.append(t)
                cycle_pnl += t["pnlcomm"]
                # 当累计盈利超过一定阈值或交易结束时形成一个周期
                if len(cycle_trades) >= 3 or t == trade_log[-1]:
                    cycles.append({
                        "start": cycle_trades[0]["entry_date"],
                        "end": cycle_trades[-1]["exit_date"],
                        "num_trades": len(cycle_trades),
                        "total_pnl": round(cycle_pnl, 2),
                        "profitable": cycle_pnl > 0,
                        "trades": [
                            {"entry": ct["entry_date"], "exit": ct["exit_date"],
                             "pnl": ct["pnlcomm"], "size": ct["size"],
                             "entry_price": ct["entry_price"], "exit_price": ct["exit_price"],
                             "duration": ct["duration_bars"]}
                            for ct in cycle_trades
                        ],
                    })
                    cycle_trades = []
                    cycle_pnl = 0

        profitable_cycles = sum(1 for c in cycles if c["profitable"])

        res = {
            "name": cfg["name"],
            "description": cfg["desc"],
            "params": cfg["params"],
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
            "trade_log": trade_log,
            "quarterly_analysis": {k: dict(v) for k, v in sorted(quarterly_stats.items())},
            "cycle_analysis": {
                "total_cycles": len(cycles),
                "profitable_cycles": profitable_cycles,
                "cycle_win_rate": round(profitable_cycles / max(len(cycles), 1) * 100, 1),
                "cycles": cycles,
            },
        }
        strategy_results.append(res)

    report["strategies"] = strategy_results
    report["status"] = "success"

    print("[5/5] 报告生成完成")

except Exception as e:
    import traceback
    report["error"] = str(e)
    report["traceback"] = traceback.format_exc()

import os
_output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
os.makedirs(_output_dir, exist_ok=True)
_output_path = os.path.join(_output_dir, "gold_4h_backtest.json")
with open(_output_path, "w") as f:
    json.dump(report, f, indent=2, default=str, ensure_ascii=False)
print(f"结果已保存至 {_output_path}")
