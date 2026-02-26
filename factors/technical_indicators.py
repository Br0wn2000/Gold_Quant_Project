"""
technical_indicators.py - 技术指标计算模块

提供常用技术指标的计算函数，包括 RSI、MACD、SMA、ATR 等，
基于 ta（Technical Analysis）库进行封装，供因子挖掘和策略信号生成使用。
"""

import pandas as pd
import ta


def calculate_rsi(df: pd.DataFrame, period: int = 14, column: str = "close") -> pd.Series:
    """计算相对强弱指标（RSI）

    基于收盘价序列计算 RSI 指标，衡量价格涨跌的相对强弱程度。
    RSI > 70 通常被视为超买，RSI < 30 被视为超卖。

    Args:
        df: 包含价格数据的 DataFrame，至少包含 column 指定的列
        period: RSI 计算周期，默认 14
        column: 用于计算的价格列名，默认 'close'

    Returns:
        pd.Series: RSI 指标序列，值域 [0, 100]
    """
    indicator = ta.momentum.RSIIndicator(close=df[column], window=period)
    return indicator.rsi()


def calculate_macd(
    df: pd.DataFrame,
    fast_period: int = 12,
    slow_period: int = 26,
    signal_period: int = 9,
    column: str = "close",
) -> pd.DataFrame:
    """计算 MACD 指标（指数平滑异同移动平均线）

    通过快慢两条指数移动平均线（EMA）的差值，反映价格的趋势变化和动量。

    Args:
        df: 包含价格数据的 DataFrame
        fast_period: 快线 EMA 周期，默认 12
        slow_period: 慢线 EMA 周期，默认 26
        signal_period: 信号线 EMA 周期，默认 9
        column: 用于计算的价格列名，默认 'close'

    Returns:
        pd.DataFrame: 包含以下列的 DataFrame：
            - macd (float): MACD 线（快线 - 慢线）
            - macd_signal (float): 信号线
            - macd_hist (float): MACD 柱状图（MACD 线 - 信号线）
    """
    indicator = ta.trend.MACD(
        close=df[column],
        window_fast=fast_period,
        window_slow=slow_period,
        window_sign=signal_period,
    )
    return pd.DataFrame({
        "macd": indicator.macd(),
        "macd_signal": indicator.macd_signal(),
        "macd_hist": indicator.macd_diff(),
    })


def calculate_sma(df: pd.DataFrame, period: int = 20, column: str = "close") -> pd.Series:
    """计算简单移动平均线（SMA）

    对指定周期内的价格取算术平均值，用于平滑价格波动、判断趋势方向。

    Args:
        df: 包含价格数据的 DataFrame
        period: 移动平均周期，默认 20
        column: 用于计算的价格列名，默认 'close'

    Returns:
        pd.Series: SMA 指标序列
    """
    indicator = ta.trend.SMAIndicator(close=df[column], window=period)
    return indicator.sma_indicator()


def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """计算真实波动幅度均值（ATR）

    衡量市场波动性大小，常用于设置止损距离和仓位管理。
    ATR 越大说明市场波动越剧烈。

    Args:
        df: 包含价格数据的 DataFrame，必须包含 'high', 'low', 'close' 三列
        period: ATR 计算周期，默认 14

    Returns:
        pd.Series: ATR 指标序列
    """
    indicator = ta.volatility.AverageTrueRange(
        high=df["high"],
        low=df["low"],
        close=df["close"],
        window=period,
    )
    return indicator.average_true_range()


def add_all_indicators(
    df: pd.DataFrame,
    rsi_period: int = 14,
    macd_fast: int = 12,
    macd_slow: int = 26,
    macd_signal: int = 9,
    sma_period: int = 20,
    atr_period: int = 14,
) -> pd.DataFrame:
    """批量计算所有技术指标并合并到原始 DataFrame

    一次性计算 RSI、MACD、SMA、ATR 四个技术指标，
    将结果作为新列添加到输入 DataFrame 中。

    Args:
        df: 包含 OHLCV 数据的 DataFrame
        rsi_period: RSI 周期，默认 14
        macd_fast: MACD 快线周期，默认 12
        macd_slow: MACD 慢线周期，默认 26
        macd_signal: MACD 信号线周期，默认 9
        sma_period: SMA 周期，默认 20
        atr_period: ATR 周期，默认 14

    Returns:
        pd.DataFrame: 添加了所有技术指标列的 DataFrame
    """
    result = df.copy()

    # RSI
    result["rsi"] = calculate_rsi(result, period=rsi_period)

    # MACD
    macd_df = calculate_macd(
        result,
        fast_period=macd_fast,
        slow_period=macd_slow,
        signal_period=macd_signal,
    )
    result["macd"] = macd_df["macd"].values
    result["macd_signal"] = macd_df["macd_signal"].values
    result["macd_hist"] = macd_df["macd_hist"].values

    # SMA
    result[f"sma_{sma_period}"] = calculate_sma(result, period=sma_period)

    # ATR
    result[f"atr_{atr_period}"] = calculate_atr(result, period=atr_period)

    print(f"[Indicators] ✅ 已计算全部技术指标: RSI({rsi_period}), "
          f"MACD({macd_fast}/{macd_slow}/{macd_signal}), "
          f"SMA({sma_period}), ATR({atr_period})")
    print(f"[Indicators] 有效数据行数: {result.dropna().shape[0]} / {len(result)}")

    return result
