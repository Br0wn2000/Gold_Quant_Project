"""
strategies.py - 通道分析策略集合

提供 4 种通道分析策略，统一接口：
1. LinearRegressionStrategy  — 线性回归通道（回归斜率 + R² + ADX）
2. BollingerBandStrategy     — 布林带通道（SMA ± Nσ）
3. DonchianChannelStrategy   — 唐奇安通道（N 周期最高/最低价）
4. TrendlineStrategy         — 高低点趋势线（局部极值连线）

每个策略返回统一格式的 dict，方便 ChannelAnalyzer 聚合。
"""

import numpy as np
import pandas as pd
import ta
from abc import ABC, abstractmethod


# ============================================================
# 通道类型常量
# ============================================================
CHANNEL_UP = "📈 上涨通道"
CHANNEL_DOWN = "📉 下跌通道"
CHANNEL_SIDEWAYS = "↔️  横盘震荡"
CHANNEL_TRANSITION = "🔄 趋势转换中"


# ============================================================
# 策略基类
# ============================================================
class BaseChannelStrategy(ABC):
    """通道分析策略基类

    所有策略须实现 analyze() 方法，返回统一格式的分析结果。
    """

    name: str = "base"
    display_name: str = "基类"

    @abstractmethod
    def analyze(self, df: pd.DataFrame, lookback: int = 60, **kwargs) -> dict:
        """分析通道

        Args:
            df: 完整的 OHLCV DataFrame
            lookback: 回看 K 线数量
            **kwargs: 策略特有参数

        Returns:
            dict: 统一格式的分析结果
        """
        pass

    def _calc_position_pct(self, price: float, upper: float, lower: float) -> float:
        """计算价格在通道中的位置百分比"""
        width = upper - lower
        if width > 0:
            pct = ((price - lower) / width) * 100
            return round(max(0, min(100, pct)), 1)
        return 50.0

    def _calc_adx(self, df: pd.DataFrame, lookback: int) -> float:
        """计算 ADX 值"""
        adx_data = df.tail(lookback + 20).copy()
        if len(adx_data) < 16:
            return 0.0
        try:
            indicator = ta.trend.ADXIndicator(
                high=adx_data["high"],
                low=adx_data["low"],
                close=adx_data["close"],
                window=14,
            )
            adx_series = indicator.adx()
            val = adx_series.iloc[-1]
            return round(val, 1) if not np.isnan(val) else 0.0
        except Exception:
            return 0.0

    def _calc_sma_cross(self, df: pd.DataFrame, short: int, long: int) -> tuple:
        """计算均线排列状态，返回 (short_val, long_val, cross_label)"""
        close = df["close"]
        sma_s = close.rolling(window=short).mean().iloc[-1]
        sma_l = close.rolling(window=long).mean().iloc[-1]
        if np.isnan(sma_s) or np.isnan(sma_l):
            return None, None, "数据不足"
        label = "多头排列" if sma_s > sma_l else "空头排列"
        return round(sma_s, 2), round(sma_l, 2), label


# ============================================================
# 策略 1：线性回归通道
# ============================================================
class LinearRegressionStrategy(BaseChannelStrategy):
    """线性回归通道策略

    对收盘价做线性回归，用斜率方向判断趋势，
    R² 衡量趋势的线性度，结合 ADX 确认趋势强度。
    通道上下轨 = 回归线 ± 1.5σ。
    """

    name = "regression"
    display_name = "线性回归"

    def __init__(self, adx_threshold: float = 25.0, r2_threshold: float = 0.5):
        self.adx_threshold = adx_threshold
        self.r2_threshold = r2_threshold

    def analyze(self, df: pd.DataFrame, lookback: int = 60, **kwargs) -> dict:
        sma_short = kwargs.get("sma_short", 20)
        sma_long = kwargs.get("sma_long", 60)

        min_bars = max(lookback, sma_long + 10)
        if len(df) < min_bars:
            return {"error": f"数据不足：需要 {min_bars} 根，实际 {len(df)} 根"}

        data = df.tail(lookback).copy().reset_index(drop=True)
        close = data["close"].values

        # 线性回归
        x = np.arange(len(close))
        coeffs = np.polyfit(x, close, 1)
        slope = coeffs[0]
        regression_line = np.polyval(coeffs, x)

        # R²
        ss_res = np.sum((close - regression_line) ** 2)
        ss_tot = np.sum((close - np.mean(close)) ** 2)
        r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0

        # 通道上下轨
        residuals = close - regression_line
        std_dev = np.std(residuals)
        center = regression_line[-1]
        upper = center + 1.5 * std_dev
        lower = center - 1.5 * std_dev

        # ADX & SMA
        adx = self._calc_adx(df, lookback)
        sma_s, sma_l, sma_cross = self._calc_sma_cross(df, sma_short, sma_long)

        current_price = close[-1]
        slope_pct = (slope / current_price) * 100 if current_price > 0 else 0

        # 通道判定
        if r_squared >= self.r2_threshold and adx >= self.adx_threshold:
            channel_type = CHANNEL_UP if slope > 0 else CHANNEL_DOWN
        elif r_squared >= self.r2_threshold:
            channel_type = CHANNEL_TRANSITION
        else:
            channel_type = CHANNEL_SIDEWAYS

        # 均线修正
        if sma_cross == "多头排列" and channel_type == CHANNEL_DOWN:
            channel_type = CHANNEL_TRANSITION
        elif sma_cross == "空头排列" and channel_type == CHANNEL_UP:
            channel_type = CHANNEL_TRANSITION

        return {
            "strategy_name": self.display_name,
            "channel_type": channel_type,
            "current_price": round(current_price, 2),
            "upper_band": round(upper, 2),
            "lower_band": round(lower, 2),
            "center": round(center, 2),
            "position_pct": self._calc_position_pct(current_price, upper, lower),
            "sma_cross": sma_cross,
            "details": {
                "slope": round(slope, 4),
                "slope_pct": round(slope_pct, 4),
                "r_squared": round(r_squared, 4),
                "adx": adx,
                "sma_short_val": sma_s,
                "sma_long_val": sma_l,
                "band_width": round(std_dev * 3, 2),
            },
        }


# ============================================================
# 策略 2：布林带通道
# ============================================================
class BollingerBandStrategy(BaseChannelStrategy):
    """布林带通道策略

    使用 SMA(N) ± K 倍标准差构建通道：
    - 带宽（Bandwidth）衡量波动性大小
    - %B 衡量价格在通道中的位置
    - 结合均线斜率判断趋势方向
    """

    name = "bollinger"
    display_name = "布林带"

    def __init__(self, bb_period: int = 20, bb_std: float = 2.0):
        self.bb_period = bb_period
        self.bb_std = bb_std

    def analyze(self, df: pd.DataFrame, lookback: int = 60, **kwargs) -> dict:
        bb_period = kwargs.get("bb_period", self.bb_period)
        bb_std = kwargs.get("bb_std", self.bb_std)

        if len(df) < bb_period + 10:
            return {"error": f"数据不足：需要 {bb_period + 10} 根，实际 {len(df)} 根"}

        # 布林带计算
        bb = ta.volatility.BollingerBands(
            close=df["close"], window=bb_period, window_dev=bb_std
        )

        upper = bb.bollinger_hband().iloc[-1]
        lower = bb.bollinger_lband().iloc[-1]
        middle = bb.bollinger_mavg().iloc[-1]
        bandwidth = bb.bollinger_wband().iloc[-1]  # (上轨-下轨)/中轨
        pct_b = bb.bollinger_pband().iloc[-1]      # %B = (价格-下轨)/(上轨-下轨)

        current_price = df["close"].iloc[-1]

        # 均线斜率（中轨走向）
        ma_vals = bb.bollinger_mavg().dropna().tail(lookback)
        if len(ma_vals) >= 10:
            x = np.arange(len(ma_vals))
            ma_slope = np.polyfit(x, ma_vals.values, 1)[0]
        else:
            ma_slope = 0

        # ADX
        adx = self._calc_adx(df, lookback)

        # 带宽判断：带宽收窄 → 横盘蓄力
        # 带宽用最近值与历史中位数对比
        bw_series = bb.bollinger_wband().dropna().tail(lookback)
        bw_median = bw_series.median() if len(bw_series) > 0 else bandwidth
        bw_is_narrow = bandwidth < bw_median * 0.7

        # 通道判定
        if bw_is_narrow and adx < 20:
            channel_type = CHANNEL_SIDEWAYS
        elif ma_slope > 0 and adx >= 20:
            channel_type = CHANNEL_UP
        elif ma_slope < 0 and adx >= 20:
            channel_type = CHANNEL_DOWN
        elif abs(ma_slope) > 0 and adx < 20:
            channel_type = CHANNEL_TRANSITION
        else:
            channel_type = CHANNEL_SIDEWAYS

        return {
            "strategy_name": self.display_name,
            "channel_type": channel_type,
            "current_price": round(current_price, 2),
            "upper_band": round(upper, 2),
            "lower_band": round(lower, 2),
            "center": round(middle, 2),
            "position_pct": self._calc_position_pct(current_price, upper, lower),
            "sma_cross": "中轨上方" if current_price > middle else "中轨下方",
            "details": {
                "bandwidth": round(bandwidth, 4),
                "pct_b": round(pct_b, 4) if not np.isnan(pct_b) else 0,
                "ma_slope": round(ma_slope, 4),
                "adx": adx,
                "bw_vs_median": f"{'收窄' if bw_is_narrow else '正常/扩张'}",
            },
        }


# ============================================================
# 策略 3：唐奇安通道
# ============================================================
class DonchianChannelStrategy(BaseChannelStrategy):
    """唐奇安通道策略

    N 周期内最高价/最低价构成通道：
    - 突破上轨 → 强势做多信号
    - 跌破下轨 → 强势做空信号
    - 通道中部 → 方向不明确
    结合通道斜率和宽度变化判断趋势。
    """

    name = "donchian"
    display_name = "唐奇安"

    def __init__(self, dc_period: int = 20):
        self.dc_period = dc_period

    def analyze(self, df: pd.DataFrame, lookback: int = 60, **kwargs) -> dict:
        dc_period = kwargs.get("dc_period", self.dc_period)

        if len(df) < dc_period + 10:
            return {"error": f"数据不足：需要 {dc_period + 10} 根，实际 {len(df)} 根"}

        # 唐奇安通道
        dc = ta.volatility.DonchianChannel(
            high=df["high"], low=df["low"], close=df["close"],
            window=dc_period,
        )

        upper = dc.donchian_channel_hband().iloc[-1]
        lower = dc.donchian_channel_lband().iloc[-1]
        middle = dc.donchian_channel_mband().iloc[-1]
        width = dc.donchian_channel_wband().iloc[-1]

        current_price = df["close"].iloc[-1]

        # 上轨斜率 — 最近 N 根上轨值做回归
        upper_series = dc.donchian_channel_hband().dropna().tail(lookback)
        lower_series = dc.donchian_channel_lband().dropna().tail(lookback)

        upper_slope = 0
        lower_slope = 0
        if len(upper_series) >= 10:
            x = np.arange(len(upper_series))
            upper_slope = np.polyfit(x, upper_series.values, 1)[0]
        if len(lower_series) >= 10:
            x = np.arange(len(lower_series))
            lower_slope = np.polyfit(x, lower_series.values, 1)[0]

        # ADX
        adx = self._calc_adx(df, lookback)

        # 通道判定
        # 上下轨同时上移 → 上涨通道
        # 上下轨同时下移 → 下跌通道
        # 通道收窄且方向不一致 → 横盘
        if upper_slope > 0 and lower_slope > 0 and adx >= 20:
            channel_type = CHANNEL_UP
        elif upper_slope < 0 and lower_slope < 0 and adx >= 20:
            channel_type = CHANNEL_DOWN
        elif adx < 15:
            channel_type = CHANNEL_SIDEWAYS
        elif (upper_slope > 0) != (lower_slope > 0):
            channel_type = CHANNEL_TRANSITION
        else:
            channel_type = CHANNEL_SIDEWAYS

        # 价格接近上/下轨的程度
        proximity = ""
        dist_to_upper = (upper - current_price) / (upper - lower) if (upper - lower) > 0 else 0.5
        if dist_to_upper < 0.1:
            proximity = "接近上轨（可能突破）"
        elif dist_to_upper > 0.9:
            proximity = "接近下轨（可能跌破）"
        else:
            proximity = "通道内部"

        return {
            "strategy_name": self.display_name,
            "channel_type": channel_type,
            "current_price": round(current_price, 2),
            "upper_band": round(upper, 2),
            "lower_band": round(lower, 2),
            "center": round(middle, 2),
            "position_pct": self._calc_position_pct(current_price, upper, lower),
            "sma_cross": proximity,
            "details": {
                "upper_slope": round(upper_slope, 4),
                "lower_slope": round(lower_slope, 4),
                "channel_width": round(width, 4) if not np.isnan(width) else 0,
                "adx": adx,
                "dc_period": dc_period,
            },
        }


# ============================================================
# 策略 4：高低点趋势线
# ============================================================
class TrendlineStrategy(BaseChannelStrategy):
    """高低点趋势线策略

    自动识别局部高点和低点，分别做线性回归拟合趋势线：
    - 高点连线 = 压力线（通道上轨）
    - 低点连线 = 支撑线（通道下轨）
    - 两线斜率一致上移 → 上涨通道
    """

    name = "trendline"
    display_name = "高低点趋势线"

    def __init__(self, pivot_window: int = 5):
        self.pivot_window = pivot_window

    def analyze(self, df: pd.DataFrame, lookback: int = 60, **kwargs) -> dict:
        pivot_window = kwargs.get("pivot_window", self.pivot_window)

        if len(df) < lookback:
            return {"error": f"数据不足：需要 {lookback} 根，实际 {len(df)} 根"}

        data = df.tail(lookback).copy().reset_index(drop=True)
        high = data["high"].values
        low = data["low"].values
        close = data["close"].values

        # 找局部高点和低点
        highs_idx, highs_val = self._find_pivots(high, pivot_window, mode="high")
        lows_idx, lows_val = self._find_pivots(low, pivot_window, mode="low")

        current_price = close[-1]
        result_base = {
            "strategy_name": self.display_name,
            "current_price": round(current_price, 2),
        }

        # 至少需要 3 个高点和 3 个低点才能拟合有意义的趋势线
        if len(highs_idx) < 3 or len(lows_idx) < 3:
            result_base.update({
                "channel_type": CHANNEL_SIDEWAYS,
                "upper_band": round(np.max(high), 2),
                "lower_band": round(np.min(low), 2),
                "center": round(np.mean(close), 2),
                "position_pct": 50.0,
                "sma_cross": "极值点不足",
                "details": {
                    "high_pivots": len(highs_idx),
                    "low_pivots": len(lows_idx),
                    "note": "局部极值点不足，无法拟合趋势线",
                },
            })
            return result_base

        # 高点趋势线回归
        h_coeffs = np.polyfit(highs_idx, highs_val, 1)
        h_slope = h_coeffs[0]
        upper_at_end = np.polyval(h_coeffs, len(data) - 1)

        # 低点趋势线回归
        l_coeffs = np.polyfit(lows_idx, lows_val, 1)
        l_slope = l_coeffs[0]
        lower_at_end = np.polyval(l_coeffs, len(data) - 1)

        center = (upper_at_end + lower_at_end) / 2

        # ADX
        adx = self._calc_adx(df, lookback)

        # 通道判定
        both_up = h_slope > 0 and l_slope > 0
        both_down = h_slope < 0 and l_slope < 0

        if both_up and adx >= 20:
            channel_type = CHANNEL_UP
        elif both_down and adx >= 20:
            channel_type = CHANNEL_DOWN
        elif both_up or both_down:
            channel_type = CHANNEL_TRANSITION
        else:
            # 高点下移 + 低点上移 = 收敛三角形（横盘）
            # 高点上移 + 低点下移 = 扩张（横盘/不确定）
            channel_type = CHANNEL_SIDEWAYS

        # 趋势线形态描述
        if h_slope > 0 and l_slope > 0:
            pattern = "上升通道"
        elif h_slope < 0 and l_slope < 0:
            pattern = "下降通道"
        elif h_slope < 0 and l_slope > 0:
            pattern = "收敛三角形"
        elif h_slope > 0 and l_slope < 0:
            pattern = "扩张形态"
        else:
            pattern = "不明确"

        result_base.update({
            "channel_type": channel_type,
            "upper_band": round(upper_at_end, 2),
            "lower_band": round(lower_at_end, 2),
            "center": round(center, 2),
            "position_pct": self._calc_position_pct(current_price, upper_at_end, lower_at_end),
            "sma_cross": pattern,
            "details": {
                "high_slope": round(h_slope, 4),
                "low_slope": round(l_slope, 4),
                "high_pivots": len(highs_idx),
                "low_pivots": len(lows_idx),
                "pattern": pattern,
                "adx": adx,
            },
        })
        return result_base

    def _find_pivots(self, values: np.ndarray, window: int, mode: str = "high") -> tuple:
        """找局部极值点

        Args:
            values: 价格序列
            window: 前后各 window 根 K 线内的极值
            mode: 'high' 找局部高点, 'low' 找局部低点

        Returns:
            (indices, values) 两个数组
        """
        indices = []
        vals = []
        for i in range(window, len(values) - window):
            left = values[i - window : i]
            right = values[i + 1 : i + window + 1]
            if mode == "high":
                if values[i] >= np.max(left) and values[i] >= np.max(right):
                    indices.append(i)
                    vals.append(values[i])
            else:
                if values[i] <= np.min(left) and values[i] <= np.min(right):
                    indices.append(i)
                    vals.append(values[i])
        return np.array(indices), np.array(vals)


# ============================================================
# 策略注册表
# ============================================================
ALL_STRATEGIES = {
    "regression": LinearRegressionStrategy,
    "bollinger": BollingerBandStrategy,
    "donchian": DonchianChannelStrategy,
    "trendline": TrendlineStrategy,
}

DEFAULT_STRATEGY_NAMES = ["regression", "bollinger", "donchian", "trendline"]


def get_strategies(names: list = None, **kwargs) -> list:
    """根据名称列表创建策略实例

    Args:
        names: 策略名称列表，None 表示全部
        **kwargs: 传给各策略的参数

    Returns:
        list[BaseChannelStrategy]: 策略实例列表
    """
    names = names or DEFAULT_STRATEGY_NAMES
    strategies = []
    for n in names:
        n = n.strip().lower()
        if n in ALL_STRATEGIES:
            strategies.append(ALL_STRATEGIES[n](**kwargs))
        else:
            print(f"  ⚠️ 未知策略: {n}，已跳过")
    return strategies
