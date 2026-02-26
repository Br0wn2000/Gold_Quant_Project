"""
engine.py - 回测引擎模块

封装 Backtrader 的 Cerebro 引擎，提供统一的回测执行接口，
支持注入历史数据、添加策略、配置初始资金/手续费，
并在回测完成后输出夏普比率等关键绩效指标。
"""

import os
import sys
from datetime import datetime
from typing import Optional, Type

import backtrader as bt
import backtrader.analyzers as btanalyzers
import pandas as pd

# 将项目根目录加入 sys.path，以支持模块间导入
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from strategies.dual_ma_strategy import DualMAStrategy


class BacktestEngine:
    """回测引擎

    对 Backtrader Cerebro 进行封装，提供简洁的一站式回测执行流程。

    Attributes:
        cerebro (bt.Cerebro): Backtrader 回测引擎核心实例
        initial_cash (float): 初始资金
        commission (float): 交易手续费比例
        results (list): 回测结果
    """

    def __init__(self, initial_cash: float = 100000.0, commission: float = 0.001):
        """初始化回测引擎

        创建 Cerebro 实例并配置初始资金和手续费。

        Args:
            initial_cash: 初始账户资金，默认 100,000
            commission: 手续费比例，默认 0.1%（0.001）
        """
        self.initial_cash = initial_cash
        self.commission = commission
        self.results = None

        # 创建 Cerebro 引擎
        self.cerebro = bt.Cerebro()

        # 设置初始资金
        self.cerebro.broker.setcash(initial_cash)

        # 设置手续费
        self.cerebro.broker.setcommission(commission=commission)

        # 添加内置分析器
        self.cerebro.addanalyzer(btanalyzers.SharpeRatio, _name="sharpe",
                                timeframe=bt.TimeFrame.Days, annualize=True)
        self.cerebro.addanalyzer(btanalyzers.DrawDown, _name="drawdown")
        self.cerebro.addanalyzer(btanalyzers.Returns, _name="returns")
        self.cerebro.addanalyzer(btanalyzers.TradeAnalyzer, _name="trades")

        print(f"[BacktestEngine] 初始化完成 | 初始资金: {initial_cash:,.0f} | 手续费: {commission*100:.2f}%")

    def load_data(
        self,
        df: Optional[pd.DataFrame] = None,
        csv_path: Optional[str] = None,
        fromdate: Optional[str] = None,
        todate: Optional[str] = None,
    ) -> None:
        """加载回测数据

        支持从 pandas DataFrame 或 CSV 文件加载 OHLCV 数据到 Cerebro 引擎。

        Args:
            df: 包含 OHLCV 数据的 DataFrame（与 csv_path 二选一）。
                需包含 'time'/'date'/'datetime'（索引或列）、'open'、'high'、'low'、'close'、'volume' 列。
            csv_path: CSV 文件路径（与 df 二选一）
            fromdate: 数据起始日期，格式 'YYYY-MM-DD'
            todate: 数据截止日期，格式 'YYYY-MM-DD'

        Raises:
            ValueError: 当 df 和 csv_path 均未提供时抛出异常
        """
        if df is None and csv_path is None:
            raise ValueError("必须提供 df（DataFrame）或 csv_path（CSV路径）之一")

        if csv_path is not None:
            # 从 CSV 文件加载
            df = pd.read_csv(csv_path, parse_dates=True)
            print(f"[BacktestEngine] 从 CSV 加载数据: {csv_path}")

        # 确保有 datetime 索引
        df = df.copy()
        time_col = None
        for col_name in ["time", "date", "datetime", "Date", "Time", "Datetime"]:
            if col_name in df.columns:
                time_col = col_name
                break

        if time_col is not None:
            df[time_col] = pd.to_datetime(df[time_col])
            df = df.set_index(time_col)
        elif not isinstance(df.index, pd.DatetimeIndex):
            raise ValueError("DataFrame 必须包含 'time'/'date'/'datetime' 列或 DatetimeIndex 索引")

        # 日期筛选
        if fromdate:
            df = df[df.index >= pd.to_datetime(fromdate)]
        if todate:
            df = df[df.index <= pd.to_datetime(todate)]

        # 标准化列名为小写
        df.columns = [c.lower() for c in df.columns]

        # 创建 Backtrader 数据源
        data = bt.feeds.PandasData(
            dataname=df,
            openinterest=-1,  # 无持仓量数据
        )

        self.cerebro.adddata(data)
        print(f"[BacktestEngine] ✅ 数据加载完成 | {len(df)} 条 | "
              f"{df.index[0].strftime('%Y-%m-%d')} ～ {df.index[-1].strftime('%Y-%m-%d')}")

    def add_strategy(self, strategy_class: Type[bt.Strategy] = DualMAStrategy, **kwargs) -> None:
        """添加交易策略

        将策略类注册到 Cerebro 引擎中。

        Args:
            strategy_class: 策略类，默认为 DualMAStrategy
            **kwargs: 传递给策略的参数
        """
        self.cerebro.addstrategy(strategy_class, **kwargs)
        print(f"[BacktestEngine] 策略已添加: {strategy_class.__name__}")

    def run(self) -> list:
        """执行回测

        运行 Cerebro 引擎，执行完整的回测流程。

        Returns:
            list: 回测结果列表（包含策略实例及其状态）
        """
        print("\n" + "=" * 60)
        print(f"[BacktestEngine] 🚀 开始回测...")
        print(f"  初始资金: {self.cerebro.broker.getvalue():,.2f}")
        print("=" * 60 + "\n")

        self.results = self.cerebro.run()

        final_value = self.cerebro.broker.getvalue()
        print("\n" + "=" * 60)
        print(f"[BacktestEngine] 🏁 回测完成 | 最终净值: {final_value:,.2f}")
        print("=" * 60)

        return self.results

    def print_performance(self) -> dict:
        """打印并返回回测绩效指标

        输出包括夏普比率、最大回撤、总收益率等关键绩效指标。

        Returns:
            dict: 包含以下键值的绩效字典：
                - sharpe_ratio (float): 夏普比率
                - max_drawdown (float): 最大回撤百分比
                - total_return (float): 总收益率
                - final_value (float): 最终账户净值
                - total_trades (int): 总交易次数
                - won_trades (int): 盈利交易次数
                - lost_trades (int): 亏损交易次数
        """
        if self.results is None:
            print("[BacktestEngine] ⚠️ 请先执行 run() 进行回测")
            return {}

        strat = self.results[0]

        # 提取分析器数据
        sharpe = strat.analyzers.sharpe.get_analysis()
        drawdown = strat.analyzers.drawdown.get_analysis()
        returns = strat.analyzers.returns.get_analysis()
        trades = strat.analyzers.trades.get_analysis()

        # 安全获取值
        sharpe_ratio = sharpe.get("sharperatio", None)
        max_dd = drawdown.get("max", {}).get("drawdown", 0.0)
        total_return = returns.get("rtot", 0.0) * 100  # 转为百分比
        final_value = self.cerebro.broker.getvalue()

        # 交易统计
        total_trades = trades.get("total", {}).get("total", 0)
        won_trades = trades.get("won", {}).get("total", 0)
        lost_trades = trades.get("lost", {}).get("total", 0)

        perf = {
            "sharpe_ratio": sharpe_ratio,
            "max_drawdown": max_dd,
            "total_return": total_return,
            "final_value": final_value,
            "total_trades": total_trades,
            "won_trades": won_trades,
            "lost_trades": lost_trades,
        }

        # 打印绩效报告
        print("\n" + "=" * 60)
        print("📊 回测绩效报告")
        print("=" * 60)
        print(f"  初始资金:     {self.initial_cash:>15,.2f}")
        print(f"  最终净值:     {final_value:>15,.2f}")
        print(f"  总收益率:     {total_return:>14.2f}%")
        print(f"  夏普比率:     {sharpe_ratio if sharpe_ratio else 'N/A':>15}")
        print(f"  最大回撤:     {max_dd:>14.2f}%")
        print("-" * 60)
        print(f"  总交易次数:   {total_trades:>15}")
        print(f"  盈利次数:     {won_trades:>15}")
        print(f"  亏损次数:     {lost_trades:>15}")
        if total_trades > 0:
            win_rate = won_trades / total_trades * 100
            print(f"  胜率:         {win_rate:>14.1f}%")
        print("=" * 60 + "\n")

        return perf

    def plot(self) -> None:
        """绘制回测结果图表

        使用 Backtrader 内置绘图功能，展示 K 线图、交易信号和账户净值曲线。
        """
        if self.results is None:
            print("[BacktestEngine] ⚠️ 请先执行 run() 进行回测")
            return

        try:
            self.cerebro.plot(style="candlestick", barup="green", bardown="red")
        except Exception as e:
            print(f"[BacktestEngine] ⚠️ 绘图失败（可能缺少 matplotlib 或在无 GUI 环境下运行）: {e}")
