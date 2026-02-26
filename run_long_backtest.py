"""
run_long_backtest.py - 长周期回测对比脚本

获取最长可用历史数据，对比基础双均线策略 vs 增强版策略的表现。
输出结果到 JSON 文件。
"""
import sys
import json

sys.path.insert(0, ".")

results = {}

try:
    # ============================================================
    # 1. 获取长周期数据
    # ============================================================
    from data.data_fetcher import YFinanceDataFetcher

    fetcher = YFinanceDataFetcher(symbol="GC=F")

    # 拉取最长可用数据（日K）
    df = fetcher.fetch_ohlcv(period="max", interval="1d")

    if df is None or df.empty:
        results["error"] = "数据获取失败"
        raise RuntimeError("No data")

    fetcher.save_to_csv(df, "gc_futures_max.csv")

    results["data"] = {
        "rows": len(df),
        "date_range": f"{df['time'].iloc[0]} ~ {df['time'].iloc[-1]}",
        "price_range": f"{df['close'].min():.2f} ~ {df['close'].max():.2f}",
    }

    # ============================================================
    # 2. 基础双均线策略回测（最优参数 MA 15/45）
    # ============================================================
    from backtest.engine import BacktestEngine
    from strategies.dual_ma_strategy import DualMAStrategy
    from strategies.enhanced_ma_strategy import EnhancedMAStrategy

    # --- 基础策略 ---
    engine_basic = BacktestEngine(initial_cash=100000.0, commission=0.001)
    engine_basic.load_data(df=df)
    engine_basic.add_strategy(strategy_class=DualMAStrategy, short_period=15, long_period=45)
    engine_basic.run()
    perf_basic = engine_basic.print_performance()
    results["basic_strategy"] = perf_basic

    # ============================================================
    # 3. 增强策略回测 — 多组参数
    # ============================================================
    enhanced_configs = [
        {"name": "增强-保守型", "short_period": 15, "long_period": 45,
         "rsi_upper": 50, "atr_sl_mult": 2.5, "atr_tp_mult": 4.0,
         "trail_atr_mult": 2.0, "risk_pct": 0.01},
        {"name": "增强-均衡型", "short_period": 15, "long_period": 45,
         "rsi_upper": 50, "atr_sl_mult": 2.0, "atr_tp_mult": 3.0,
         "trail_atr_mult": 1.5, "risk_pct": 0.02},
        {"name": "增强-激进型", "short_period": 10, "long_period": 30,
         "rsi_upper": 45, "atr_sl_mult": 1.5, "atr_tp_mult": 2.5,
         "trail_atr_mult": 1.0, "risk_pct": 0.03},
        {"name": "增强-长趋势", "short_period": 20, "long_period": 60,
         "rsi_upper": 55, "atr_sl_mult": 2.0, "atr_tp_mult": 3.5,
         "trail_atr_mult": 1.5, "risk_pct": 0.02},
    ]

    enhanced_results = []
    for cfg in enhanced_configs:
        name = cfg.pop("name")
        eng = BacktestEngine(initial_cash=100000.0, commission=0.001)
        eng.load_data(df=df)
        eng.add_strategy(strategy_class=EnhancedMAStrategy, printlog=False, **cfg)
        eng.run()
        p = eng.print_performance()
        enhanced_results.append({
            "name": name,
            "params": f"MA({cfg['short_period']}/{cfg['long_period']}) RSI>{cfg['rsi_upper']} "
                      f"SL:{cfg['atr_sl_mult']}ATR TP:{cfg['atr_tp_mult']}ATR Risk:{cfg['risk_pct']*100}%",
            "return": round(p.get("total_return", 0), 2),
            "sharpe": round(p["sharpe_ratio"], 4) if p.get("sharpe_ratio") else None,
            "max_dd": round(p.get("max_drawdown", 0), 2),
            "trades": p.get("total_trades", 0),
            "won": p.get("won_trades", 0),
            "lost": p.get("lost_trades", 0),
            "win_rate": round(p.get("won_trades", 0) / max(p.get("total_trades", 1), 1) * 100, 1),
            "final": round(p.get("final_value", 0), 2),
        })

    results["enhanced_strategies"] = enhanced_results
    results["status"] = "success"

except Exception as e:
    import traceback
    results["error"] = str(e)
    results["traceback"] = traceback.format_exc()

import os
_output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
os.makedirs(_output_dir, exist_ok=True)
with open(os.path.join(_output_dir, "gold_long_backtest.json"), "w") as f:
    json.dump(results, f, indent=2, default=str, ensure_ascii=False)
