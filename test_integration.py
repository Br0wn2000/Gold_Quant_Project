"""集成测试脚本：数据 → 指标 → 回测全流程，输出到文件"""
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, ".")

output = []
def log(msg):
    output.append(str(msg))

try:
    # === 1. 生成模拟黄金 OHLCV 数据 ===
    np.random.seed(123)
    n = 200
    base = 1950.0
    trend = np.linspace(0, 100, n)
    noise = np.cumsum(np.random.randn(n) * 5)
    close = base + trend + noise
    high = close + np.abs(np.random.randn(n) * 8)
    low = close - np.abs(np.random.randn(n) * 8)
    opn = close + np.random.randn(n) * 3
    vol = np.random.randint(1000, 10000, n)

    df = pd.DataFrame({
        "time": pd.date_range("2024-01-01", periods=n, freq="D"),
        "open": opn, "high": high, "low": low, "close": close, "volume": vol,
    })
    log(f"[1/3] 数据生成: {len(df)} 条, 价格: {close.min():.0f}~{close.max():.0f}")

    # === 2. 计算技术指标 ===
    from factors.technical_indicators import add_all_indicators
    df_ind = add_all_indicators(df)
    non_null = df_ind.dropna().shape[0]
    log(f"[2/3] 指标计算完成: {list(df_ind.columns)}, 有效行: {non_null}/{len(df_ind)}")

    # === 3. 回测引擎测试 ===
    from backtest.engine import BacktestEngine
    engine = BacktestEngine(initial_cash=100000.0, commission=0.001)
    engine.load_data(df=df)
    engine.add_strategy(short_period=10, long_period=30)
    results = engine.run()
    perf = engine.print_performance()

    log(f"[3/3] 回测完成: sharpe={perf.get('sharpe_ratio')}, "
        f"return={perf.get('total_return', 0):.2f}%, "
        f"trades={perf.get('total_trades', 0)}, "
        f"final={perf.get('final_value', 0):,.2f}")
    log("✅ 全流程集成测试通过")

except Exception as e:
    import traceback
    log(f"❌ 测试失败: {e}")
    log(traceback.format_exc())

# 写入结果文件
import os
_output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
os.makedirs(_output_dir, exist_ok=True)
with open(os.path.join(_output_dir, "gold_test_result.txt"), "w") as f:
    f.write("\n".join(output))
