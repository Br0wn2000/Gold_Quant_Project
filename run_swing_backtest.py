"""
run_swing_backtest.py - 中长期波段策略回测

测试 SwingStrategy 在不同时间框架和参数组合下的表现。
目标：每笔持仓 3-6 个月。
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
    # 1. 加载数据
    # ============================================================
    from data.data_fetcher import YFinanceDataFetcher
    from backtest.engine import BacktestEngine
    from strategies.swing_strategy import SwingStrategy

    # === 日线数据（5年，充足的样本量）===
    print("[1/3] 获取数据...")
    fetcher_d = YFinanceDataFetcher(symbol="GC=F")
    df_daily = fetcher_d.fetch_ohlcv(period="5y", interval="1d")
    if df_daily is None or df_daily.empty:
        raise RuntimeError("日线数据获取失败")
    fetcher_d.save_to_csv(df_daily, "gc_futures_5y_daily.csv")
    print(f"  日线: {len(df_daily)} 条 | {df_daily['time'].iloc[0]} ~ {df_daily['time'].iloc[-1]}")

    # === 4H 数据（已缓存）===
    df_4h = pd.read_csv("/media/jskj/Data/quant/Gold/Gold_Quant_Project/data/gc_futures_4h_2y.csv",
                         parse_dates=["time"])
    print(f"  4H: {len(df_4h)} 条 | {df_4h['time'].iloc[0]} ~ {df_4h['time'].iloc[-1]}")

    report["data"] = {
        "daily": {"bars": len(df_daily),
                  "range": f"{df_daily['time'].iloc[0]} ~ {df_daily['time'].iloc[-1]}",
                  "price": f"${df_daily['close'].min():.0f} ~ ${df_daily['close'].max():.0f}"},
        "4h":    {"bars": len(df_4h),
                  "range": f"{df_4h['time'].iloc[0]} ~ {df_4h['time'].iloc[-1]}",
                  "price": f"${df_4h['close'].min():.0f} ~ ${df_4h['close'].max():.0f}"},
    }

    # ============================================================
    # 2. 定义参数组合
    # ============================================================
    configs = [
        # --- 日线参数 ---
        {
            "name": "日线-标准波段",
            "df": df_daily,
            "desc": "MA(50/150) ADX>20 SL:4xATR Trail:6xATR RSI>45",
            "params": {"short_period": 50, "long_period": 150,
                       "adx_threshold": 20, "atr_sl_mult": 4.0,
                       "atr_tp_mult": 6.0, "trail_atr_mult": 3.0,
                       "rsi_upper": 45, "risk_pct": 0.02, "reentry_cooldown": 10},
        },
        {
            "name": "日线-宽松波段",
            "df": df_daily,
            "desc": "MA(40/120) ADX>18 SL:5xATR Trail:8xATR RSI>40",
            "params": {"short_period": 40, "long_period": 120,
                       "adx_threshold": 18, "atr_sl_mult": 5.0,
                       "atr_tp_mult": 8.0, "trail_atr_mult": 4.0,
                       "rsi_upper": 40, "risk_pct": 0.02, "reentry_cooldown": 15},
        },
        {
            "name": "日线-经典金叉",
            "df": df_daily,
            "desc": "MA(50/200) ADX>22 SL:4xATR Trail:7xATR RSI>50",
            "params": {"short_period": 50, "long_period": 200,
                       "adx_threshold": 22, "atr_sl_mult": 4.0,
                       "atr_tp_mult": 7.0, "trail_atr_mult": 3.5,
                       "rsi_upper": 50, "risk_pct": 0.02, "reentry_cooldown": 20},
        },
        # --- 4H 参数 ---
        {
            "name": "4H-中期波段",
            "df": df_4h,
            "desc": "MA(120/360) ADX>20 SL:4xATR Trail:6xATR RSI>45",
            "params": {"short_period": 120, "long_period": 360,
                       "adx_threshold": 20, "atr_sl_mult": 4.0,
                       "atr_tp_mult": 6.0, "trail_atr_mult": 3.0,
                       "rsi_upper": 45, "risk_pct": 0.02, "reentry_cooldown": 30},
        },
        {
            "name": "4H-超宽容波段",
            "df": df_4h,
            "desc": "MA(100/300) ADX>18 SL:5xATR Trail:8xATR RSI>42",
            "params": {"short_period": 100, "long_period": 300,
                       "adx_threshold": 18, "atr_sl_mult": 5.0,
                       "atr_tp_mult": 8.0, "trail_atr_mult": 4.0,
                       "rsi_upper": 42, "risk_pct": 0.02, "reentry_cooldown": 20},
        },
    ]

    # ============================================================
    # 3. 回测
    # ============================================================
    print("[2/3] 运行回测...")

    trade_log_global = []

    class ReportingSwing(SwingStrategy):
        """带交易记录的波段策略"""
        def notify_trade(self, trade):
            super().notify_trade(trade)
            if trade.isclosed:
                entry_dt = bt.num2date(trade.dtopen)
                exit_dt = bt.num2date(trade.dtclose)
                duration_days = (exit_dt - entry_dt).days
                trade_log_global.append({
                    "entry_date": entry_dt.strftime("%Y-%m-%d %H:%M"),
                    "exit_date": exit_dt.strftime("%Y-%m-%d %H:%M"),
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
        eng.load_data(df=cfg["df"])
        eng.add_strategy(strategy_class=ReportingSwing, printlog=False, **cfg["params"])
        eng.run()
        perf = eng.print_performance()

        # 统计
        trades = trade_log_global.copy()
        won_trades = [t for t in trades if t["pnlcomm"] > 0]
        lost_trades = [t for t in trades if t["pnlcomm"] <= 0]

        avg_hold = sum(t["duration_days"] for t in trades) / max(len(trades), 1)
        avg_hold_win = sum(t["duration_days"] for t in won_trades) / max(len(won_trades), 1)
        avg_hold_loss = sum(t["duration_days"] for t in lost_trades) / max(len(lost_trades), 1)
        avg_pnl_win = sum(t["pnlcomm"] for t in won_trades) / max(len(won_trades), 1)
        avg_pnl_loss = sum(t["pnlcomm"] for t in lost_trades) / max(len(lost_trades), 1)

        # 按年度分析
        yearly_stats = defaultdict(lambda: {"trades": 0, "pnl": 0, "won": 0, "lost": 0})
        for t in trades:
            y = t["entry_date"][:4]
            yearly_stats[y]["trades"] += 1
            yearly_stats[y]["pnl"] += t["pnlcomm"]
            if t["pnlcomm"] > 0:
                yearly_stats[y]["won"] += 1
            else:
                yearly_stats[y]["lost"] += 1

        res = {
            "name": cfg["name"],
            "description": cfg["desc"],
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
            "holding_period": {
                "avg_days": round(avg_hold, 1),
                "avg_days_winners": round(avg_hold_win, 1),
                "avg_days_losers": round(avg_hold_loss, 1),
            },
            "profit_analysis": {
                "avg_win": round(avg_pnl_win, 2),
                "avg_loss": round(avg_pnl_loss, 2),
                "profit_factor": round(
                    abs(avg_pnl_win / avg_pnl_loss), 2) if avg_pnl_loss != 0 else None,
            },
            "yearly_analysis": {k: dict(v) for k, v in sorted(yearly_stats.items())},
            "trade_log": trades,
        }
        all_results.append(res)
        print(f"  ✅ {cfg['name']}: 收益 {res['performance']['total_return']}%, "
              f"{len(trades)} 笔, 平均持仓 {avg_hold:.0f} 天")

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
_output_path = os.path.join(_output_dir, "gold_swing_backtest.json")
with open(_output_path, "w") as f:
    json.dump(report, f, indent=2, default=str, ensure_ascii=False)
print(f"结果已保存至 {_output_path}")
