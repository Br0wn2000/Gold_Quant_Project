"""
dual_ma_strategy.py - 双均线交叉策略模块

实现基于短期和长期简单移动平均线（SMA）交叉信号的交易策略。
当短期均线上穿长期均线时产生买入信号（金叉），
当短期均线下穿长期均线时产生卖出信号（死叉）。

本策略继承自 backtrader.Strategy，可直接在 Backtrader 回测引擎中运行。
"""

import backtrader as bt


class DualMAStrategy(bt.Strategy):
    """双均线交叉策略

    利用短期均线和长期均线的交叉关系生成交易信号：
    - 金叉（短期均线上穿长期均线）：买入开仓
    - 死叉（短期均线下穿长期均线）：卖出平仓

    Params:
        short_period (int): 短期均线周期，默认 10
        long_period (int): 长期均线周期，默认 30
        printlog (bool): 是否打印交易日志，默认 True
    """

    params = (
        ("short_period", 10),
        ("long_period", 30),
        ("printlog", True),
    )

    def __init__(self):
        """初始化策略

        创建短期和长期 SMA 指标，以及交叉信号检测器。
        """
        # 保存收盘价引用，方便后续使用
        self.dataclose = self.datas[0].close

        # 订单跟踪变量
        self.order = None
        self.buy_price = None
        self.buy_comm = None

        # 创建短期和长期均线指标
        self.sma_short = bt.indicators.SimpleMovingAverage(
            self.datas[0], period=self.params.short_period
        )
        self.sma_long = bt.indicators.SimpleMovingAverage(
            self.datas[0], period=self.params.long_period
        )

        # 交叉信号检测器：crossover > 0 表示金叉，< 0 表示死叉
        self.crossover = bt.indicators.CrossOver(self.sma_short, self.sma_long)

    def log(self, txt: str, dt=None) -> None:
        """策略日志输出

        打印带有日期前缀的交易日志信息。

        Args:
            txt: 要输出的日志文本
            dt: 日期对象，默认使用当前 K 线日期
        """
        if self.params.printlog:
            dt = dt or self.datas[0].datetime.date(0)
            print(f"[{dt.isoformat()}] {txt}")

    def notify_order(self, order) -> None:
        """订单状态回调

        接收并处理订单状态变更通知，包括提交、接受、完成和取消等状态。

        Args:
            order: backtrader Order 对象，包含订单状态和执行信息
        """
        if order.status in [order.Submitted, order.Accepted]:
            # 订单已提交/已接受，无需处理
            return

        if order.status in [order.Completed]:
            if order.isbuy():
                self.log(
                    f"✅ 买入成交 | 价格: {order.executed.price:.2f} | "
                    f"成本: {order.executed.value:.2f} | 手续费: {order.executed.comm:.2f}"
                )
                self.buy_price = order.executed.price
                self.buy_comm = order.executed.comm
            else:
                self.log(
                    f"✅ 卖出成交 | 价格: {order.executed.price:.2f} | "
                    f"成本: {order.executed.value:.2f} | 手续费: {order.executed.comm:.2f}"
                )

        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            self.log("⚠️ 订单被取消/保证金不足/被拒绝")

        # 重置订单跟踪变量
        self.order = None

    def notify_trade(self, trade) -> None:
        """交易完成回调

        当一笔交易（开仓到平仓的完整过程）结束时触发，
        打印交易盈亏信息。

        Args:
            trade: backtrader Trade 对象，包含交易盈亏信息
        """
        if not trade.isclosed:
            return

        self.log(
            f"💰 交易完成 | 毛利润: {trade.pnl:.2f} | 净利润: {trade.pnlcomm:.2f}"
        )

    def next(self) -> None:
        """策略主逻辑（逐 K 线执行）

        在每根新 K 线到来时执行：
        1. 检查是否存在持仓
        2. 若无持仓，检测金叉信号 → 买入
        3. 若有持仓，检测死叉信号 → 卖出
        """
        # 如果有未完成订单，等待
        if self.order:
            return

        # 当前无持仓
        if not self.position:
            # 金叉：短期均线上穿长期均线 → 买入
            if self.crossover > 0:
                self.log(
                    f"📈 金叉信号 | 收盘价: {self.dataclose[0]:.2f} | "
                    f"短MA: {self.sma_short[0]:.2f} | 长MA: {self.sma_long[0]:.2f}"
                )
                self.order = self.buy()

        else:
            # 死叉：短期均线下穿长期均线 → 卖出
            if self.crossover < 0:
                self.log(
                    f"📉 死叉信号 | 收盘价: {self.dataclose[0]:.2f} | "
                    f"短MA: {self.sma_short[0]:.2f} | 长MA: {self.sma_long[0]:.2f}"
                )
                self.order = self.sell()

    def stop(self) -> None:
        """策略结束回调

        回测结束时执行，输出最终账户价值等汇总信息。
        """
        self.log(
            f"📊 回测结束 | 短MA周期: {self.params.short_period} | "
            f"长MA周期: {self.params.long_period} | "
            f"最终净值: {self.broker.getvalue():.2f}",
        )
