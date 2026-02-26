"""
enhanced_ma_strategy.py - 增强版双均线策略

在基础双均线交叉策略上增加以下优化：
1. RSI 趋势过滤：仅在 RSI 支持的方向开仓（RSI>50 做多，RSI<50 做空）
2. ATR 动态止损：基于 ATR 设置自适应止损距离
3. 移动止盈（Trailing Stop）：盈利达到一定倍数 ATR 后启动移动止盈
4. ATR 动态仓位管理：根据波动性调整每笔交易的风险敞口
"""

import backtrader as bt


class EnhancedMAStrategy(bt.Strategy):
    """增强版双均线交叉策略

    在金叉/死叉信号基础上，加入 RSI 过滤、ATR 止损和移动止盈，
    显著降低假信号带来的亏损，提升风险收益比。

    Params:
        short_period (int): 短期均线周期，默认 15
        long_period (int): 长期均线周期，默认 45
        rsi_period (int): RSI 周期，默认 14
        rsi_upper (float): RSI 多头过滤阈值，RSI > 此值才做多，默认 50
        atr_period (int): ATR 周期，默认 14
        atr_sl_mult (float): 止损倍数（N 倍 ATR），默认 2.0
        atr_tp_mult (float): 止盈倍数（N 倍 ATR），默认 3.0
        trail_atr_mult (float): 移动止盈触发后的跟踪距离（N 倍 ATR），默认 1.5
        risk_pct (float): 每笔交易最大风险占总资金比例，默认 0.02（2%）
        printlog (bool): 是否打印日志，默认 True
    """

    params = (
        ("short_period", 15),
        ("long_period", 45),
        ("rsi_period", 14),
        ("rsi_upper", 50),
        ("atr_period", 14),
        ("atr_sl_mult", 2.0),
        ("atr_tp_mult", 3.0),
        ("trail_atr_mult", 1.5),
        ("risk_pct", 0.02),
        ("printlog", True),
    )

    def __init__(self):
        """初始化策略指标和信号"""
        self.dataclose = self.datas[0].close

        # 订单与持仓跟踪
        self.order = None
        self.entry_price = None
        self.stop_price = None
        self.trail_activated = False
        self.highest_since_entry = None

        # 均线
        self.sma_short = bt.indicators.SimpleMovingAverage(
            self.datas[0], period=self.params.short_period
        )
        self.sma_long = bt.indicators.SimpleMovingAverage(
            self.datas[0], period=self.params.long_period
        )
        self.crossover = bt.indicators.CrossOver(self.sma_short, self.sma_long)

        # RSI
        self.rsi = bt.indicators.RSI(self.datas[0], period=self.params.rsi_period)

        # ATR
        self.atr = bt.indicators.ATR(self.datas[0], period=self.params.atr_period)

    def log(self, txt: str, dt=None) -> None:
        """日志输出"""
        if self.params.printlog:
            dt = dt or self.datas[0].datetime.date(0)
            print(f"[{dt.isoformat()}] {txt}")

    def _calc_position_size(self) -> int:
        """基于 ATR 计算动态仓位大小

        根据公式：仓位 = (总资金 × 风险比例) / (ATR × 止损倍数)
        确保每笔交易的最大亏损不超过总资金的 risk_pct。

        Returns:
            int: 买入的股数/手数（至少为 1）
        """
        if self.atr[0] <= 0:
            return 1

        risk_amount = self.broker.getvalue() * self.params.risk_pct
        risk_per_unit = self.atr[0] * self.params.atr_sl_mult

        size = int(risk_amount / risk_per_unit)
        return max(size, 1)

    def notify_order(self, order) -> None:
        """订单状态回调"""
        if order.status in [order.Submitted, order.Accepted]:
            return

        if order.status in [order.Completed]:
            if order.isbuy():
                self.entry_price = order.executed.price
                self.stop_price = self.entry_price - self.atr[0] * self.params.atr_sl_mult
                self.highest_since_entry = self.entry_price
                self.trail_activated = False
                self.log(
                    f"✅ 买入 | 价格: {order.executed.price:.2f} | "
                    f"数量: {order.executed.size:.0f} | "
                    f"止损: {self.stop_price:.2f} | "
                    f"ATR: {self.atr[0]:.2f}"
                )
            else:
                pnl = (order.executed.price - self.entry_price) if self.entry_price else 0
                self.log(
                    f"✅ 卖出 | 价格: {order.executed.price:.2f} | "
                    f"单位盈亏: {pnl:.2f}"
                )
                self.entry_price = None
                self.stop_price = None
                self.highest_since_entry = None
                self.trail_activated = False

        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            self.log("⚠️ 订单取消/保证金不足/被拒")

        self.order = None

    def notify_trade(self, trade) -> None:
        """交易完成回调"""
        if not trade.isclosed:
            return
        self.log(f"💰 交易闭合 | 毛利: {trade.pnl:.2f} | 净利: {trade.pnlcomm:.2f}")

    def next(self) -> None:
        """策略主逻辑

        开仓条件：金叉 + RSI > rsi_upper
        平仓条件：死叉 或 触及 ATR 止损 或 移动止盈
        """
        if self.order:
            return

        current_price = self.dataclose[0]

        if self.position:
            # --- 持仓管理 ---

            # 更新最高价
            if self.highest_since_entry is not None:
                self.highest_since_entry = max(self.highest_since_entry, current_price)

            # 检查是否触发移动止盈
            if (self.entry_price is not None and self.highest_since_entry is not None
                    and not self.trail_activated):
                profit_distance = self.highest_since_entry - self.entry_price
                if profit_distance >= self.atr[0] * self.params.atr_tp_mult:
                    self.trail_activated = True
                    self.log(f"🔄 移动止盈已激活 | 最高价: {self.highest_since_entry:.2f}")

            # 移动止盈：更新止损线
            if self.trail_activated:
                trail_stop = self.highest_since_entry - self.atr[0] * self.params.trail_atr_mult
                if trail_stop > self.stop_price:
                    self.stop_price = trail_stop

            # 触及止损 → 平仓
            if self.stop_price is not None and current_price <= self.stop_price:
                self.log(
                    f"🛑 止损触发 | 价格: {current_price:.2f} | "
                    f"止损线: {self.stop_price:.2f} | "
                    f"{'移动止盈' if self.trail_activated else '固定止损'}"
                )
                self.order = self.close()
                return

            # 死叉 → 平仓
            if self.crossover < 0:
                self.log(
                    f"📉 死叉平仓 | 价格: {current_price:.2f} | "
                    f"短MA: {self.sma_short[0]:.2f} | 长MA: {self.sma_long[0]:.2f}"
                )
                self.order = self.close()

        else:
            # --- 开仓判断 ---

            # 金叉 + RSI 过滤
            if self.crossover > 0 and self.rsi[0] > self.params.rsi_upper:
                size = self._calc_position_size()
                self.log(
                    f"📈 开仓信号 | 价格: {current_price:.2f} | "
                    f"RSI: {self.rsi[0]:.1f} | ATR: {self.atr[0]:.2f} | "
                    f"仓位: {size}"
                )
                self.order = self.buy(size=size)

            elif self.crossover > 0:
                self.log(
                    f"🚫 金叉但 RSI 不满足 ({self.rsi[0]:.1f} < {self.params.rsi_upper}) | "
                    f"跳过开仓"
                )

    def stop(self) -> None:
        """回测结束汇总"""
        self.log(
            f"📊 回测结束 | MA({self.params.short_period}/{self.params.long_period}) | "
            f"RSI阈值: {self.params.rsi_upper} | "
            f"ATR止损: {self.params.atr_sl_mult}x | "
            f"最终净值: {self.broker.getvalue():.2f}"
        )
