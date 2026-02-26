"""
main.py - Gold_Quant_Project 项目启动总入口

现货黄金（XAUUSD）量化交易系统主程序，
按顺序执行：数据获取 → 因子计算 → 回测验证 → 实盘交易 四个阶段。

使用方法：
    python main.py
"""

from data.data_fetcher import YFinanceDataFetcher
# from data.data_fetcher import MT5DataFetcher  # Windows 实盘环境使用
from factors.technical_indicators import add_all_indicators
from backtest.engine import BacktestEngine
from execution.mt5_trader import MT5Trader


def main():
    """项目主函数

    按顺序调度各模块，完成从数据获取到实盘交易的完整流程。
    """

    # ============================================================
    # 第一阶段：数据获取
    # 通过 MT5 API 拉取 XAUUSD 历史 OHLCV 数据并缓存到本地
    # ============================================================
    print("=" * 60)
    print("【第一阶段】数据获取 - 拉取 XAUUSD 历史数据")
    print("=" * 60)

    fetcher = YFinanceDataFetcher(symbol="GC=F")  # 黄金期货，走势贴近 XAUUSD
    # fetcher = MT5DataFetcher(symbol="XAUUSD")  # Windows 实盘环境使用
    # df = fetcher.fetch_ohlcv(period="1y", interval="1h")
    # fetcher.save_to_csv(df)

    # ============================================================
    # 第二阶段：因子计算
    # 基于历史数据计算 RSI、MACD、SMA、ATR 等技术指标
    # ============================================================
    print("\n" + "=" * 60)
    print("【第二阶段】因子计算 - 计算技术指标")
    print("=" * 60)

    # df = add_all_indicators(df)
    # print(df.tail())

    # ============================================================
    # 第三阶段：策略回测
    # 使用 Backtrader 引擎对双均线策略进行历史回测与绩效评估
    # ============================================================
    print("\n" + "=" * 60)
    print("【第三阶段】策略回测 - 双均线策略回测")
    print("=" * 60)

    # engine = BacktestEngine(initial_cash=100000.0, commission=0.001)
    # engine.load_data(df=df)
    # engine.add_strategy()
    # engine.run()
    # engine.print_performance()
    # engine.plot()

    # ============================================================
    # 第四阶段：实盘交易
    # ⚠️ 警告：以下代码连接真实交易账户，执行前请确认参数正确
    # ============================================================
    print("\n" + "=" * 60)
    print("【第四阶段】实盘交易 - MT5 实盘执行（默认关闭）")
    print("=" * 60)

    # trader = MT5Trader(symbol="XAUUSD")
    # trader.connect()
    # account = trader.get_account_info()
    # print(f"账户余额: {account['balance']}")
    # result = trader.buy(lot=0.01, sl_points=500, tp_points=1000)
    # positions = trader.get_positions()
    # trader.disconnect()

    print("\n" + "=" * 60)
    print("Gold_Quant_Project 执行完毕")
    print("=" * 60)


if __name__ == "__main__":
    main()
