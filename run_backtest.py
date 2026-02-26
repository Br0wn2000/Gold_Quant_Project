"""
run_backtest.py - 真实黄金数据回测脚本

使用 YFinanceDataFetcher 拉取 GC=F（COMEX 黄金期货）真实历史数据，
计算技术指标，并使用双均线策略进行回测。
"""
import sys
import json

sys.path.insert(0, ".")

results = {}

try:
    # ============================================================
    # 第一阶段：获取真实黄金数据
    # ============================================================
    from data.data_fetcher import YFinanceDataFetcher

    fetcher = YFinanceDataFetcher(symbol="GC=F")

    # 拉取近2年日K数据
    df = fetcher.fetch_ohlcv(period="2y", interval="1d")

    if df is None or df.empty:
        results["error"] = "数据获取失败"
    else:
        # 缓存到本地
        fetcher.save_to_csv(df, "gc_futures_2y.csv")

        results["data"] = {
            "rows": len(df),
            "date_range": f"{df['time'].iloc[0]} ~ {df['time'].iloc[-1]}",
            "price_range": f"{df['close'].min():.2f} ~ {df['close'].max():.2f}",
        }

        # ============================================================
        # 第二阶段：计算技术指标
        # ============================================================
        from factors.technical_indicators import add_all_indicators

        df_ind = add_all_indicators(df)
        valid = df_ind.dropna().shape[0]
        results["indicators"] = {"total_rows": len(df_ind), "valid_rows": valid}

        # ============================================================
        # 第三阶段：双均线策略回测
        # ============================================================
        from backtest.engine import BacktestEngine

        engine = BacktestEngine(initial_cash=100000.0, commission=0.001)
        engine.load_data(df=df)
        engine.add_strategy(short_period=10, long_period=30)
        engine.run()
        perf = engine.print_performance()
        results["backtest"] = perf

        # ============================================================
        # 第四阶段：参数敏感性 - 多组均线参数对比
        # ============================================================
        param_results = []
        param_sets = [
            (5, 20),
            (10, 30),
            (10, 50),
            (20, 60),
            (15, 45),
        ]
        for short_p, long_p in param_sets:
            eng = BacktestEngine(initial_cash=100000.0, commission=0.001)
            eng.load_data(df=df)
            eng.add_strategy(short_period=short_p, long_period=long_p)
            eng.run()
            p = eng.print_performance()
            param_results.append({
                "params": f"MA({short_p}/{long_p})",
                "return": round(p.get("total_return", 0), 2),
                "sharpe": round(p["sharpe_ratio"], 4) if p.get("sharpe_ratio") else None,
                "max_dd": round(p.get("max_drawdown", 0), 2),
                "trades": p.get("total_trades", 0),
                "win_rate": round(p.get("won_trades", 0) / max(p.get("total_trades", 1), 1) * 100, 1),
                "final": round(p.get("final_value", 0), 2),
            })
        results["param_comparison"] = param_results

        results["status"] = "success"

except Exception as e:
    import traceback
    results["error"] = str(e)
    results["traceback"] = traceback.format_exc()

# 输出到文件
import os
_output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
os.makedirs(_output_dir, exist_ok=True)
with open(os.path.join(_output_dir, "gold_backtest_result.json"), "w") as f:
    json.dump(results, f, indent=2, default=str, ensure_ascii=False)
