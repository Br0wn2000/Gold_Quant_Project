"""
optimized_swing.py - 优化版中长期波段策略

基于25年日线回测结果的优化点：
1. 双向交易 —— 做多 + 做空，捕捉完整趋势周期
2. 均线趋势带 —— 用价格与均线的相对位置做方向过滤
3. 波动率自适应止损 —— 低波动期收紧止损，高波动期放宽
4. 分批止盈 —— 第一次目标位止盈50%，剩余移动止损
5. MACD 动量确认 —— 金叉/死叉时 MACD 柱状图方向一致
6. 改进死叉平仓 —— 用均线斜率而非简单交叉判断趋势衰竭
7. 均线距离百分比入场 —— 避免趋势末端追高
"""

import backtrader as bt


class OptimizedSwingStrategy(bt.Strategy):
    """优化版波段策略

    Params:
        short_period (int): 短均线周期，默认 40
        long_period (int): 长均线周期，默认 120
        rsi_period (int): RSI 周期，默认 21
        rsi_long_min (float): 做多RSI下限，默认 40
        rsi_short_max (float): 做空RSI上限，默认 60
        adx_period (int): ADX 周期，默认 14
        adx_threshold (float): ADX 阈值，默认 18
        atr_period (int): ATR 周期，默认 20
        atr_sl_mult (float): 基础止损倍数，默认 3.5
        atr_tp1_mult (float): 第一止盈目标倍数，默认 4.0
        tp1_close_pct (float): 第一止盈平仓比例，默认 0.5
        trail_atr_mult (float): 移动止盈跟踪距离，默认 2.5
        risk_pct (float): 每笔风险比，默认 0.02
        max_ma_spread (float): 最大均线偏离%（避免追高），默认 8.0
        reentry_cooldown (int): 冷却bar数，默认 5
        macd_fast (int): MACD 快线，默认 12
        macd_slow (int): MACD 慢线，默认 26
        macd_signal (int): MACD 信号线，默认 9
        slope_period (int): 均线斜率回看周期，默认 5
        enable_short (bool): 是否启用做空，默认 True
        printlog (bool): 日志开关
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
        ("atr_sl_mult", 4.0),
        ("atr_tp1_mult", 5.0),
        ("tp1_close_pct", 0.5),
        ("trail_atr_mult", 3.0),
        ("risk_pct", 0.02),
        ("max_ma_spread", 8.0),
        ("reentry_cooldown", 5),
        ("macd_fast", 12),
        ("macd_slow", 26),
        ("macd_signal", 9),
        ("slope_period", 5),
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
        self.direction = 0  # +1=多 -1=空 0=空仓
        self.trail_activated = False
        self.tp1_done = False
        self.extreme_since_entry = None  # 多头最高价/空头最低价
        self.last_exit_bar = -999
        self.initial_size = 0

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

    # ── 斜率计算 ──
    def _ma_slope(self, ma, period=None):
        """均线斜率（百分比/bar）"""
        p = period or self.params.slope_period
        if len(ma) <= p or ma[-p] == 0:
            return 0
        return (ma[0] - ma[-p]) / ma[-p] * 100 / p

    # ── 均线偏离度 ──
    def _ma_spread_pct(self):
        """短均线与长均线偏离百分比"""
        if self.sma_long[0] == 0:
            return 0
        return (self.sma_short[0] - self.sma_long[0]) / self.sma_long[0] * 100

    # ── 动态仓位 ──
    def _calc_size(self):
        if self.atr[0] <= 0:
            return 1
        risk_amount = self.broker.getvalue() * self.params.risk_pct
        risk_per_unit = self.atr[0] * self.params.atr_sl_mult
        return max(int(risk_amount / risk_per_unit), 1)

    # ── 订单回调 ──
    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:
            return

        if order.status == order.Completed:
            action = "买入" if order.isbuy() else "卖出"
            self.log(
                f"✅ {action} | 价: {order.executed.price:.2f} | "
                f"量: {order.executed.size:.0f}"
            )

            # 入场
            if (self.direction == 0 or
                    (self.direction == 1 and order.isbuy()) or
                    (self.direction == -1 and not order.isbuy())):
                if self.entry_price is None:
                    self.entry_price = order.executed.price
                    self.entry_bar = len(self)
                    self.initial_size = abs(order.executed.size)
                    self.trail_activated = False
                    self.tp1_done = False
                    self.extreme_since_entry = order.executed.price

                    if self.direction == 1:
                        self.stop_price = self.entry_price - self.atr[0] * self.params.atr_sl_mult
                    elif self.direction == -1:
                        self.stop_price = self.entry_price + self.atr[0] * self.params.atr_sl_mult

                    self.log(
                        f"  → 方向: {'多' if self.direction == 1 else '空'} | "
                        f"止损: {self.stop_price:.2f} | ADX: {self.adx[0]:.1f}"
                    )

        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            self.log("⚠️ 订单异常")

        self.order = None

    def notify_trade(self, trade):
        if not trade.isclosed:
            return
        hold = len(self) - self.entry_bar if self.entry_bar else 0
        self.log(
            f"💰 平仓 | 方向: {'多' if self.direction == 1 else '空'} | "
            f"持仓: {hold} bars | 净利: {trade.pnlcomm:.2f}"
        )
        self.last_exit_bar = len(self)
        self._reset_state()

    def _reset_state(self):
        self.entry_price = None
        self.entry_bar = None
        self.stop_price = None
        self.direction = 0
        self.trail_activated = False
        self.tp1_done = False
        self.extreme_since_entry = None
        self.initial_size = 0

    # ── 主逻辑 ──
    def next(self):
        if self.order:
            return

        price = self.dataclose[0]

        if self.position:
            self._manage_position(price)
        else:
            self._check_entry(price)

    def _manage_position(self, price):
        """持仓管理"""
        # 更新极值
        if self.direction == 1:
            self.extreme_since_entry = max(self.extreme_since_entry or price,
                                            self.datahigh[0])
            float_pnl = price - self.entry_price
        else:
            self.extreme_since_entry = min(self.extreme_since_entry or price,
                                            self.datalow[0])
            float_pnl = self.entry_price - price

        atr = self.atr[0]

        # ── 第一止盈：到达 tp1 目标，平仓50% ──
        if not self.tp1_done and atr > 0:
            if float_pnl >= atr * self.params.atr_tp1_mult:
                close_size = max(int(self.initial_size * self.params.tp1_close_pct), 1)
                current_size = abs(self.position.size)
                close_size = min(close_size, current_size - 1) if current_size > 1 else 0

                if close_size > 0:
                    self.tp1_done = True
                    self.log(
                        f"🎯 第一止盈 | 平仓 {close_size} 手 | "
                        f"浮盈: {float_pnl:.2f}"
                    )
                    if self.direction == 1:
                        self.order = self.sell(size=close_size)
                    else:
                        self.order = self.buy(size=close_size)

                    # 止损移到保本
                    self.stop_price = self.entry_price
                    self.trail_activated = True
                    return

        # ── 移动止盈 ──
        if self.trail_activated and atr > 0:
            if self.direction == 1:
                new_stop = self.extreme_since_entry - atr * self.params.trail_atr_mult
                if new_stop > self.stop_price:
                    self.stop_price = new_stop
            else:
                new_stop = self.extreme_since_entry + atr * self.params.trail_atr_mult
                if new_stop < self.stop_price:
                    self.stop_price = new_stop

        # ── 止损检查 ──
        if self.stop_price is not None:
            triggered = False
            if self.direction == 1 and price <= self.stop_price:
                triggered = True
            elif self.direction == -1 and price >= self.stop_price:
                triggered = True

            if triggered:
                hold = len(self) - self.entry_bar if self.entry_bar else 0
                sl_type = "移动止盈" if self.trail_activated else "固定止损"
                self.log(
                    f"🛑 {sl_type} | 价: {price:.2f} | "
                    f"止损线: {self.stop_price:.2f} | 持仓: {hold} bars"
                )
                self.order = self.close()
                return

        # ── 趋势衰竭检查（仅在持仓一段时间后） ──
        hold = len(self) - self.entry_bar if self.entry_bar else 0
        if hold > 20:  # 至少持仓20天后才检查
            short_slope = self._ma_slope(self.sma_short, period=10)
            if self.direction == 1 and short_slope < -0.1:
                # 多头：短均线明确下弯且价格跌破短均线
                if price < self.sma_short[0]:
                    self.log(
                        f"📉 趋势衰竭平仓 | 均线斜率: {short_slope:.3f}%/bar | "
                        f"持仓: {hold} bars"
                    )
                    self.order = self.close()
            elif self.direction == -1 and short_slope > 0.1:
                # 空头：短均线明确上弯且价格涨破短均线
                if price > self.sma_short[0]:
                    self.log(
                        f"📈 趋势衰竭平空 | 均线斜率: {short_slope:.3f}%/bar | "
                        f"持仓: {hold} bars"
                    )
                    self.order = self.close()

    def _check_entry(self, price):
        """入场检查"""
        # 冷却期
        if len(self) - self.last_exit_bar < self.params.reentry_cooldown:
            return

        spread = self._ma_spread_pct()
        short_slope = self._ma_slope(self.sma_short)

        # ── 做多 ──
        if self.crossover > 0:
            # 检查偏离度（避免追高）
            if abs(spread) > self.params.max_ma_spread:
                self.log(f"🚫 金叉但偏离过大 ({spread:.1f}%)")
                return
            # RSI
            if self.rsi[0] < self.params.rsi_long_min:
                return
            # ADX
            if self.adx[0] < self.params.adx_threshold:
                return
            # DMI
            if self.plus_di[0] <= self.minus_di[0]:
                return

            # 全部条件满足 → 做多
            size = self._calc_size()
            self.direction = 1
            self.log(
                f"📈 做多 | 价: {price:.2f} | RSI: {self.rsi[0]:.1f} | "
                f"ADX: {self.adx[0]:.1f} | MACD柱: {self.macd_hist[0]:.2f} | "
                f"斜率: {short_slope:.3f}%/bar | 仓位: {size}"
            )
            self.order = self.buy(size=size)

        # ── 做空 ──
        elif self.crossover < 0 and self.params.enable_short:
            if abs(spread) > self.params.max_ma_spread:
                return
            # RSI
            if self.rsi[0] > self.params.rsi_short_max:
                return
            # ADX
            if self.adx[0] < self.params.adx_threshold:
                return
            # DMI
            if self.minus_di[0] <= self.plus_di[0]:
                return
            # MACD 柱状图下降（做空额外确认）
            if self.macd_hist[0] >= 0:
                return

            size = self._calc_size()
            self.direction = -1
            self.log(
                f"📉 做空 | 价: {price:.2f} | RSI: {self.rsi[0]:.1f} | "
                f"ADX: {self.adx[0]:.1f} | MACD柱: {self.macd_hist[0]:.2f} | "
                f"斜率: {short_slope:.3f}%/bar | 仓位: {size}"
            )
            self.order = self.sell(size=size)

    def stop(self):
        self.log(
            f"📊 回测结束 | MA({self.params.short_period}/{self.params.long_period}) | "
            f"做空: {'开' if self.params.enable_short else '关'} | "
            f"最终净值: {self.broker.getvalue():.2f}"
        )
