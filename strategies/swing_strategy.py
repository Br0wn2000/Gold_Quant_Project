"""
swing_strategy.py - 中长期波段策略（目标持仓 3-6 个月）

核心设计：
1. 使用长周期均线（MA 50/150）捕捉中期趋势
2. 极宽止损（4x ATR）避免被短期波动洗出
3. 移动止盈仅在大趋势确立后激活（6x ATR）
4. 结合 ADX 趋势强度过滤，仅在明确趋势中入场
5. 周线级 RSI 确认大方向
"""

import backtrader as bt


class SwingStrategy(bt.Strategy):
    """中长期波段策略

    目标：每次交易持有 3-6 个月，捕捉中期趋势。
    适合日线或 4H 时间框架使用。

    Params:
        short_period (int): 短期均线周期，默认 50
        long_period (int): 长期均线周期，默认 150
        rsi_period (int): RSI 周期，默认 21（更慢的 RSI）
        rsi_upper (float): 做多时 RSI 下限，默认 45
        adx_period (int): ADX 周期，默认 14
        adx_threshold (float): ADX 趋势确认阈值，默认 20
        atr_period (int): ATR 周期，默认 20
        atr_sl_mult (float): 初始止损（N 倍 ATR），默认 4.0
        atr_tp_mult (float): 移动止盈触发（N 倍 ATR），默认 6.0
        trail_atr_mult (float): 跟踪距离（N 倍 ATR），默认 3.0
        risk_pct (float): 每笔风险占比，默认 0.02
        reentry_cooldown (int): 平仓后冷却 bar 数，默认 10
        printlog (bool): 是否打印日志
    """

    params = (
        ("short_period", 50),
        ("long_period", 150),
        ("rsi_period", 21),
        ("rsi_upper", 45),
        ("adx_period", 14),
        ("adx_threshold", 20),
        ("atr_period", 20),
        ("atr_sl_mult", 4.0),
        ("atr_tp_mult", 6.0),
        ("trail_atr_mult", 3.0),
        ("risk_pct", 0.02),
        ("reentry_cooldown", 10),
        ("printlog", True),
    )

    def __init__(self):
        self.dataclose = self.datas[0].close

        # 订单与持仓管理
        self.order = None
        self.entry_price = None
        self.entry_bar = None
        self.stop_price = None
        self.trail_activated = False
        self.highest_since_entry = None
        self.last_exit_bar = -999

        # 均线
        self.sma_short = bt.indicators.SimpleMovingAverage(
            self.datas[0], period=self.params.short_period
        )
        self.sma_long = bt.indicators.SimpleMovingAverage(
            self.datas[0], period=self.params.long_period
        )
        self.crossover = bt.indicators.CrossOver(self.sma_short, self.sma_long)

        # RSI —— 慢速
        self.rsi = bt.indicators.RSI(self.datas[0], period=self.params.rsi_period)

        # ADX —— 趋势强度
        self.adx = bt.indicators.AverageDirectionalMovementIndex(
            self.datas[0], period=self.params.adx_period
        )

        # DMI 方向指标（+DI / -DI）
        self.plus_di = bt.indicators.PlusDirectionalIndicator(
            self.datas[0], period=self.params.adx_period
        )
        self.minus_di = bt.indicators.MinusDirectionalIndicator(
            self.datas[0], period=self.params.adx_period
        )

        # ATR
        self.atr = bt.indicators.ATR(self.datas[0], period=self.params.atr_period)

    def log(self, txt, dt=None):
        if self.params.printlog:
            dt = dt or self.datas[0].datetime.date(0)
            print(f"[{dt.isoformat()}] {txt}")

    def _calc_position_size(self):
        """基于 ATR 的动态仓位"""
        if self.atr[0] <= 0:
            return 1
        risk_amount = self.broker.getvalue() * self.params.risk_pct
        risk_per_unit = self.atr[0] * self.params.atr_sl_mult
        return max(int(risk_amount / risk_per_unit), 1)

    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:
            return

        if order.status == order.Completed:
            if order.isbuy():
                self.entry_price = order.executed.price
                self.entry_bar = len(self)
                self.stop_price = self.entry_price - self.atr[0] * self.params.atr_sl_mult
                self.highest_since_entry = self.entry_price
                self.trail_activated = False
                self.log(
                    f"✅ 买入 | 价: {order.executed.price:.2f} | "
                    f"量: {order.executed.size:.0f} | "
                    f"止损: {self.stop_price:.2f} | "
                    f"ADX: {self.adx[0]:.1f}"
                )
            else:
                hold_bars = len(self) - self.entry_bar if self.entry_bar else 0
                pnl = (order.executed.price - self.entry_price) if self.entry_price else 0
                self.log(
                    f"✅ 卖出 | 价: {order.executed.price:.2f} | "
                    f"持仓: {hold_bars} bars | "
                    f"单位PnL: {pnl:.2f} | "
                    f"{'移动止盈' if self.trail_activated else '信号/止损'}"
                )
                self.last_exit_bar = len(self)
                self.entry_price = None
                self.entry_bar = None
                self.stop_price = None
                self.highest_since_entry = None
                self.trail_activated = False

        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            self.log("⚠️ 订单取消/保证金不足/被拒")

        self.order = None

    def notify_trade(self, trade):
        if not trade.isclosed:
            return
        self.log(f"💰 平仓 | 毛利: {trade.pnl:.2f} | 净利: {trade.pnlcomm:.2f}")

    def next(self):
        if self.order:
            return

        current_price = self.dataclose[0]

        if self.position:
            # ── 持仓管理 ──

            # 更新最高价
            if self.highest_since_entry is not None:
                self.highest_since_entry = max(self.highest_since_entry, current_price)

            # 检查移动止盈触发
            if (self.entry_price and self.highest_since_entry
                    and not self.trail_activated):
                profit = self.highest_since_entry - self.entry_price
                if profit >= self.atr[0] * self.params.atr_tp_mult:
                    self.trail_activated = True
                    self.log(
                        f"🔄 移动止盈激活 | 浮盈: {profit:.2f} | "
                        f"最高: {self.highest_since_entry:.2f}"
                    )

            # 更新跟踪止损
            if self.trail_activated:
                trail_stop = self.highest_since_entry - self.atr[0] * self.params.trail_atr_mult
                if trail_stop > self.stop_price:
                    self.stop_price = trail_stop

            # 止损检查
            if self.stop_price and current_price <= self.stop_price:
                hold_bars = len(self) - self.entry_bar if self.entry_bar else 0
                self.log(
                    f"🛑 止损 | 价: {current_price:.2f} | "
                    f"止损线: {self.stop_price:.2f} | "
                    f"持仓: {hold_bars} bars | "
                    f"{'移动止盈回撤' if self.trail_activated else '固定止损'}"
                )
                self.order = self.close()
                return

            # 死叉平仓 —— 仅在短MA明确低于长MA一段距离时才平仓
            # （避免短暂回穿导致过早离场）
            if self.crossover < 0:
                ma_gap = (self.sma_short[0] - self.sma_long[0]) / self.sma_long[0] * 100
                if ma_gap < -0.3:  # 短MA低于长MA 0.3% 才确认死叉
                    hold_bars = len(self) - self.entry_bar if self.entry_bar else 0
                    self.log(
                        f"📉 死叉平仓 | 价: {current_price:.2f} | "
                        f"MA差: {ma_gap:.2f}% | 持仓: {hold_bars} bars"
                    )
                    self.order = self.close()

        else:
            # ── 开仓逻辑 ──

            # 冷却期检查
            if len(self) - self.last_exit_bar < self.params.reentry_cooldown:
                return

            # 条件1: 金叉
            if self.crossover <= 0:
                return

            # 条件2: RSI 确认
            if self.rsi[0] < self.params.rsi_upper:
                self.log(
                    f"🚫 金叉但 RSI 不足 ({self.rsi[0]:.1f} < {self.params.rsi_upper})"
                )
                return

            # 条件3: ADX 趋势强度
            if self.adx[0] < self.params.adx_threshold:
                self.log(
                    f"🚫 金叉但 ADX 不足 ({self.adx[0]:.1f} < {self.params.adx_threshold})"
                )
                return

            # 条件4: +DI > -DI（上升趋势确认）
            if self.plus_di[0] <= self.minus_di[0]:
                self.log(f"🚫 金叉但 +DI({self.plus_di[0]:.1f}) <= -DI({self.minus_di[0]:.1f})")
                return

            # 全部条件满足 → 入场
            size = self._calc_position_size()
            self.log(
                f"📈 开仓 | 价: {current_price:.2f} | "
                f"RSI: {self.rsi[0]:.1f} | ADX: {self.adx[0]:.1f} | "
                f"+DI: {self.plus_di[0]:.1f} -DI: {self.minus_di[0]:.1f} | "
                f"ATR: {self.atr[0]:.2f} | 仓位: {size}"
            )
            self.order = self.buy(size=size)

    def stop(self):
        self.log(
            f"📊 回测结束 | MA({self.params.short_period}/{self.params.long_period}) | "
            f"ADX>{self.params.adx_threshold} | "
            f"SL:{self.params.atr_sl_mult}xATR | "
            f"最终净值: {self.broker.getvalue():.2f}"
        )
