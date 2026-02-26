"""
optimized_swing_v2.py - 优化版波段策略 V2

设计原则（基于多轮回测反馈）：
1. 保持原始策略的 "耐心" 优势 — 宽止损、让利润奔跑
2. 新增做空能力 — 25年中有大量下跌趋势未被捕获
3. MACD 零线过滤做空 — 仅 MACD 柱状图 < 0 时做空
4. 去掉过早的 "趋势衰竭" 退出 — 仅依赖均线交叉 + 止损
5. 分阶段止损上移 — 不是部分平仓，而是浮盈达标后收紧止损
6. 均线偏离度过滤 — 防止趋势末端追高追低
"""

import backtrader as bt


class OptimizedSwingV2(bt.Strategy):
    """优化波段策略 V2

    与旧策略的核心区别：
    - 做空能力（可通过参数关闭）
    - 三阶段止损: 初始(宽) → 保本 → 移动跟踪
    - MACD 仅用于做空确认
    - 均线偏离上限，避免追高/追低
    """

    params = (
        ("short_period", 40),
        ("long_period", 120),
        ("rsi_period", 21),
        ("rsi_long_min", 40),
        ("rsi_short_max", 60),
        ("adx_period", 14),
        ("adx_threshold", 18),
        ("atr_period", 20),
        ("atr_sl_mult", 5.0),      # 宽止损（保持原策略优势）
        ("atr_trail_trigger", 6.0), # 浮盈达到 N 倍 ATR 后激活跟踪
        ("trail_atr_mult", 3.5),    # 跟踪距离
        ("breakeven_trigger", 3.0), # 浮盈达 3x ATR → 止损移到保本
        ("risk_pct", 0.02),
        ("max_ma_spread", 10.0),    # 均线偏离上限%
        ("reentry_cooldown", 10),
        ("macd_fast", 12),
        ("macd_slow", 26),
        ("macd_signal", 9),
        ("enable_short", True),
        ("printlog", True),
    )

    def __init__(self):
        self.dataclose = self.datas[0].close
        self.datahigh = self.datas[0].high
        self.datalow = self.datas[0].low

        # 状态
        self.order = None
        self.entry_price = None
        self.entry_bar = None
        self.stop_price = None
        self.direction = 0        # +1=多 -1=空
        self.breakeven_done = False
        self.trail_activated = False
        self.extreme_since_entry = None
        self.last_exit_bar = -999

        # 均线
        self.sma_short = bt.indicators.SMA(self.datas[0], period=self.params.short_period)
        self.sma_long = bt.indicators.SMA(self.datas[0], period=self.params.long_period)
        self.crossover = bt.indicators.CrossOver(self.sma_short, self.sma_long)

        # RSI
        self.rsi = bt.indicators.RSI(self.datas[0], period=self.params.rsi_period)

        # ADX + DMI
        self.adx = bt.indicators.ADX(self.datas[0], period=self.params.adx_period)
        self.plus_di = bt.indicators.PlusDI(self.datas[0], period=self.params.adx_period)
        self.minus_di = bt.indicators.MinusDI(self.datas[0], period=self.params.adx_period)

        # MACD
        self.macd = bt.indicators.MACD(
            self.datas[0],
            period_me1=self.params.macd_fast,
            period_me2=self.params.macd_slow,
            period_signal=self.params.macd_signal,
        )
        self.macd_hist = self.macd.macd - self.macd.signal

        # ATR
        self.atr = bt.indicators.ATR(self.datas[0], period=self.params.atr_period)

    def log(self, txt, dt=None):
        if self.params.printlog:
            dt = dt or self.datas[0].datetime.date(0)
            print(f"[{dt.isoformat()}] {txt}")

    def _ma_spread_pct(self):
        if self.sma_long[0] == 0:
            return 0
        return (self.sma_short[0] - self.sma_long[0]) / self.sma_long[0] * 100

    def _calc_size(self):
        if self.atr[0] <= 0:
            return 1
        risk_amount = self.broker.getvalue() * self.params.risk_pct
        risk_per_unit = self.atr[0] * self.params.atr_sl_mult
        return max(int(risk_amount / risk_per_unit), 1)

    def _reset_state(self):
        self.entry_price = None
        self.entry_bar = None
        self.stop_price = None
        self.direction = 0
        self.breakeven_done = False
        self.trail_activated = False
        self.extreme_since_entry = None

    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:
            return

        if order.status == order.Completed:
            if self.entry_price is None:
                # 新仓
                self.entry_price = order.executed.price
                self.entry_bar = len(self)
                self.extreme_since_entry = order.executed.price
                self.breakeven_done = False
                self.trail_activated = False

                if self.direction == 1:
                    self.stop_price = self.entry_price - self.atr[0] * self.params.atr_sl_mult
                elif self.direction == -1:
                    self.stop_price = self.entry_price + self.atr[0] * self.params.atr_sl_mult

                self.log(
                    f"✅ {'买入' if order.isbuy() else '卖空'} | "
                    f"价: {order.executed.price:.2f} | "
                    f"量: {abs(order.executed.size):.0f} | "
                    f"止损: {self.stop_price:.2f} | "
                    f"ADX: {self.adx[0]:.1f}"
                )

        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            self.log("⚠️ 订单异常")

        self.order = None

    def notify_trade(self, trade):
        if not trade.isclosed:
            return
        hold = len(self) - self.entry_bar if self.entry_bar else 0
        d = "多" if self.direction == 1 else "空"
        self.log(
            f"💰 平仓 | {d} | 持仓: {hold} bars | "
            f"净利: {trade.pnlcomm:.2f}"
        )
        self.last_exit_bar = len(self)
        self._reset_state()

    def next(self):
        if self.order:
            return

        price = self.dataclose[0]

        if self.position:
            self._manage_position(price)
        else:
            self._check_entry(price)

    def _manage_position(self, price):
        """三阶段止损管理"""
        atr = self.atr[0]

        # 更新极值
        if self.direction == 1:
            self.extreme_since_entry = max(
                self.extreme_since_entry or price, self.datahigh[0])
            float_pnl = price - self.entry_price
        else:
            self.extreme_since_entry = min(
                self.extreme_since_entry or price, self.datalow[0])
            float_pnl = self.entry_price - price

        # ── 阶段1 → 阶段2: 保本止损 ──
        if not self.breakeven_done and atr > 0:
            if float_pnl >= atr * self.params.breakeven_trigger:
                self.breakeven_done = True
                if self.direction == 1:
                    self.stop_price = max(self.stop_price, self.entry_price)
                else:
                    self.stop_price = min(self.stop_price, self.entry_price)
                self.log(f"🔒 止损移至保本 | 浮盈: {float_pnl:.2f}")

        # ── 阶段2 → 阶段3: 移动跟踪 ──
        if not self.trail_activated and atr > 0:
            if float_pnl >= atr * self.params.atr_trail_trigger:
                self.trail_activated = True
                self.log(f"🔄 移动止盈激活 | 浮盈: {float_pnl:.2f}")

        if self.trail_activated and atr > 0:
            if self.direction == 1:
                new_stop = self.extreme_since_entry - atr * self.params.trail_atr_mult
                self.stop_price = max(self.stop_price, new_stop)
            else:
                new_stop = self.extreme_since_entry + atr * self.params.trail_atr_mult
                self.stop_price = min(self.stop_price, new_stop)

        # ── 止损触发 ──
        triggered = False
        if self.direction == 1 and price <= self.stop_price:
            triggered = True
        elif self.direction == -1 and price >= self.stop_price:
            triggered = True

        if triggered:
            hold = len(self) - self.entry_bar if self.entry_bar else 0
            phase = "移动止盈" if self.trail_activated else ("保本止损" if self.breakeven_done else "固定止损")
            self.log(
                f"🛑 {phase} | 价: {price:.2f} | "
                f"止损线: {self.stop_price:.2f} | 持仓: {hold} bars"
            )
            self.order = self.close()
            return

        # ── 均线交叉平仓 ──
        if self.direction == 1 and self.crossover < 0:
            # 死叉：短MA必须明确低于长MA
            gap = self._ma_spread_pct()
            if gap < -0.5:
                hold = len(self) - self.entry_bar if self.entry_bar else 0
                self.log(
                    f"📉 死叉平仓 | MA差: {gap:.2f}% | 持仓: {hold} bars"
                )
                self.order = self.close()
        elif self.direction == -1 and self.crossover > 0:
            gap = self._ma_spread_pct()
            if gap > 0.5:
                hold = len(self) - self.entry_bar if self.entry_bar else 0
                self.log(
                    f"📈 金叉平空 | MA差: {gap:.2f}% | 持仓: {hold} bars"
                )
                self.order = self.close()

    def _check_entry(self, price):
        """入场"""
        if len(self) - self.last_exit_bar < self.params.reentry_cooldown:
            return

        spread = self._ma_spread_pct()

        # ── 做多 ──
        if self.crossover > 0:
            if abs(spread) > self.params.max_ma_spread:
                return
            if self.rsi[0] < self.params.rsi_long_min:
                return
            if self.adx[0] < self.params.adx_threshold:
                return
            if self.plus_di[0] <= self.minus_di[0]:
                return

            size = self._calc_size()
            self.direction = 1
            self.log(
                f"📈 做多 | 价: {price:.2f} | RSI: {self.rsi[0]:.1f} | "
                f"ADX: {self.adx[0]:.1f} | +DI: {self.plus_di[0]:.1f} | "
                f"仓位: {size}"
            )
            self.order = self.buy(size=size)

        # ── 做空 ──
        elif self.crossover < 0 and self.params.enable_short:
            if abs(spread) > self.params.max_ma_spread:
                return
            if self.rsi[0] > self.params.rsi_short_max:
                return
            if self.adx[0] < self.params.adx_threshold:
                return
            if self.minus_di[0] <= self.plus_di[0]:
                return
            # MACD 零线以下（空头额外过滤）
            if self.macd_hist[0] >= 0:
                return

            size = self._calc_size()
            self.direction = -1
            self.log(
                f"📉 做空 | 价: {price:.2f} | RSI: {self.rsi[0]:.1f} | "
                f"ADX: {self.adx[0]:.1f} | -DI: {self.minus_di[0]:.1f} | "
                f"MACD: {self.macd_hist[0]:.2f} | 仓位: {size}"
            )
            self.order = self.sell(size=size)

    def stop(self):
        self.log(
            f"📊 回测结束 | MA({self.params.short_period}/{self.params.long_period}) | "
            f"做空: {'开' if self.params.enable_short else '关'} | "
            f"最终净值: {self.broker.getvalue():.2f}"
        )
