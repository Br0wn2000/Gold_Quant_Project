"""
data_fetcher.py - 数据获取模块

提供多种数据源的 XAUUSD（现货黄金）历史 OHLCV 数据获取能力：
- YFinanceDataFetcher: 基于 Yahoo Finance，适用于 Linux/macOS 开发环境
- MT5DataFetcher: 基于 MetaTrader 5 API，适用于 Windows 实盘环境
"""

import os
import sys
from datetime import datetime
from typing import Optional

import pandas as pd
import yfinance as yf
from dotenv import load_dotenv

load_dotenv()

# 项目 data 目录（用于 CSV 缓存）
_DATA_DIR = os.path.dirname(os.path.abspath(__file__))


# ============================================================
# Yahoo Finance 数据获取器（Linux 开发环境推荐）
# ============================================================

class YFinanceDataFetcher:
    """Yahoo Finance 数据获取器

    通过 yfinance 库拉取黄金（GC=F 期货 / GLD ETF）历史数据，
    适用于 Linux 环境下的策略研发和回测。

    Attributes:
        symbol (str): Yahoo Finance 品种代码，默认 'GC=F'（黄金期货）
        data_dir (str): 本地数据缓存目录
    """

    def __init__(self, symbol: str = "GC=F"):
        """初始化 Yahoo Finance 数据获取器

        Args:
            symbol: Yahoo Finance 品种代码。常用选项：
                - 'GC=F': COMEX 黄金期货（推荐，走势贴近 XAUUSD）
                - 'GLD': SPDR 黄金 ETF
                - 'XAUUSD=X': 现货黄金（部分时段数据可能不全）
        """
        self.symbol = symbol
        self.data_dir = _DATA_DIR
        self._ticker = yf.Ticker(self.symbol)

    def fetch_ohlcv(
        self,
        period: str = "1y",
        interval: str = "1h",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> Optional[pd.DataFrame]:
        """拉取指定周期的 OHLCV 数据

        从 Yahoo Finance 获取历史 K 线数据。

        Args:
            period: 数据时间跨度，默认 '1y'。
                    可选值：'1d','5d','1mo','3mo','6mo','1y','2y','5y','10y','max'
            interval: K 线时间周期，默认 '1h'。
                      可选值：'1m','2m','5m','15m','30m','60m','90m','1h','1d','5d','1wk','1mo'
            start_date: 起始日期，格式 'YYYY-MM-DD'（与 period 互斥）
            end_date: 截止日期，格式 'YYYY-MM-DD'（与 period 互斥）

        Returns:
            pd.DataFrame: 包含 open, high, low, close, volume 列的 DataFrame。
            若获取失败返回 None。
        """
        try:
            print(f"[DataFetcher] 正在从 Yahoo Finance 获取 {self.symbol} 数据...")
            print(f"  周期={period}, 间隔={interval}, 起始={start_date}, 截止={end_date}")

            if start_date and end_date:
                # 使用日期范围模式
                df = self._ticker.history(
                    start=start_date,
                    end=end_date,
                    interval=interval,
                )
            elif start_date:
                df = self._ticker.history(
                    start=start_date,
                    interval=interval,
                )
            else:
                # 使用 period 模式
                df = self._ticker.history(
                    period=period,
                    interval=interval,
                )

            if df is None or df.empty:
                print("[DataFetcher] ⚠️ 未获取到数据，请检查品种代码或网络连接")
                return None

            # 标准化列名为小写
            df.columns = [c.lower() for c in df.columns]

            # 只保留核心 OHLCV 列
            ohlcv_cols = ["open", "high", "low", "close", "volume"]
            available_cols = [c for c in ohlcv_cols if c in df.columns]
            df = df[available_cols].copy()

            # 确保索引是 datetime 且列名为 'time'
            df.index.name = "time"
            df = df.reset_index()

            # 去掉时区信息（backtrader 不兼容 tz-aware datetime）
            if pd.api.types.is_datetime64_any_dtype(df["time"]):
                df["time"] = df["time"].dt.tz_localize(None)

            # 去除 NaN 行
            df.dropna(inplace=True)

            print(f"[DataFetcher] ✅ 成功获取 {len(df)} 条数据")
            print(f"  时间范围: {df['time'].iloc[0]} ～ {df['time'].iloc[-1]}")
            return df

        except Exception as e:
            print(f"[DataFetcher] ❌ 数据获取失败: {e}")
            return None

    def save_to_csv(self, df: pd.DataFrame, filename: str = "xauusd_ohlcv.csv") -> str:
        """将 DataFrame 保存为本地 CSV 文件

        Args:
            df: 包含 OHLCV 数据的 DataFrame
            filename: 保存的文件名，默认 'xauusd_ohlcv.csv'

        Returns:
            str: 保存文件的完整路径
        """
        filepath = os.path.join(self.data_dir, filename)
        df.to_csv(filepath, index=False)
        print(f"[DataFetcher] 💾 数据已保存至: {filepath}")
        return filepath

    def load_from_csv(self, filename: str = "xauusd_ohlcv.csv") -> Optional[pd.DataFrame]:
        """从本地 CSV 文件加载数据

        Args:
            filename: CSV 文件名，默认 'xauusd_ohlcv.csv'

        Returns:
            pd.DataFrame: 加载的数据 DataFrame，文件不存在则返回 None
        """
        filepath = os.path.join(self.data_dir, filename)
        if not os.path.exists(filepath):
            print(f"[DataFetcher] ⚠️ 本地缓存文件不存在: {filepath}")
            return None

        df = pd.read_csv(filepath, parse_dates=["time"])
        print(f"[DataFetcher] 📂 从本地加载 {len(df)} 条数据: {filepath}")
        return df


# ============================================================
# MT5 数据获取器（Windows 实盘环境）
# ============================================================

class MT5DataFetcher:
    """MT5 数据获取器

    通过 MetaTrader 5 终端 API 拉取现货黄金（XAUUSD）的历史 K 线数据，
    并提供本地 CSV 缓存功能以减少重复请求。

    ⚠️ 注意：MetaTrader5 仅支持 Windows 平台。
    Linux 开发环境请使用 YFinanceDataFetcher。

    Attributes:
        login (int): MT5 账户登录号
        password (str): MT5 账户密码
        server (str): MT5 服务器地址
        mt5_path (str): MT5 终端安装路径
        symbol (str): 交易品种，默认 'XAUUSD'
    """

    def __init__(self, symbol: str = "XAUUSD"):
        """初始化 MT5 数据获取器

        从 .env 文件加载 MT5 连接配置信息。

        Args:
            symbol: 交易品种代码，默认为 'XAUUSD'
        """
        self.login = int(os.getenv("MT5_LOGIN", "0"))
        self.password = os.getenv("MT5_PASSWORD", "")
        self.server = os.getenv("MT5_SERVER", "")
        self.mt5_path = os.getenv("MT5_PATH", "")
        self.symbol = symbol
        self.data_dir = _DATA_DIR
        self._mt5 = None  # 延迟导入

    def _import_mt5(self):
        """延迟导入 MetaTrader5，避免在 Linux 上直接报错"""
        if self._mt5 is None:
            try:
                import MetaTrader5 as mt5
                self._mt5 = mt5
            except ImportError:
                raise ImportError(
                    "MetaTrader5 模块仅支持 Windows 平台。"
                    "Linux 环境请使用 YFinanceDataFetcher 作为替代数据源。"
                )
        return self._mt5

    def connect(self) -> bool:
        """初始化并连接 MT5 终端

        Returns:
            bool: 连接成功返回 True，失败返回 False
        """
        mt5 = self._import_mt5()

        # 初始化 MT5 终端
        init_kwargs = {}
        if self.mt5_path:
            init_kwargs["path"] = self.mt5_path

        if not mt5.initialize(**init_kwargs):
            print(f"[MT5DataFetcher] ❌ MT5 初始化失败: {mt5.last_error()}")
            return False

        # 登录账户
        if self.login:
            authorized = mt5.login(
                login=self.login,
                password=self.password,
                server=self.server,
            )
            if not authorized:
                print(f"[MT5DataFetcher] ❌ MT5 登录失败: {mt5.last_error()}")
                mt5.shutdown()
                return False

        account = mt5.account_info()
        print(f"[MT5DataFetcher] ✅ 已连接 MT5 - 账户: {account.login}, 服务器: {account.server}")
        return True

    def disconnect(self) -> None:
        """断开 MT5 终端连接"""
        mt5 = self._import_mt5()
        mt5.shutdown()
        print("[MT5DataFetcher] 🔌 MT5 连接已断开")

    def fetch_ohlcv(
        self,
        timeframe=None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        num_bars: int = 1000,
    ) -> Optional[pd.DataFrame]:
        """拉取指定周期的 OHLCV 数据

        从 MT5 服务器获取指定品种、指定时间框架的历史 K 线数据。

        Args:
            timeframe: MT5 K 线时间周期，如 mt5.TIMEFRAME_H1。
                       默认为 None，将使用 TIMEFRAME_H1。
            start_date: 数据起始日期
            end_date: 数据截止日期。若为 None 则使用当前时间。
            num_bars: 拉取的 K 线数量，默认 1000 根

        Returns:
            pd.DataFrame: OHLCV DataFrame，获取失败返回 None
        """
        mt5 = self._import_mt5()

        if timeframe is None:
            timeframe = mt5.TIMEFRAME_H1

        print(f"[MT5DataFetcher] 正在获取 {self.symbol} 数据 (bars={num_bars})...")

        try:
            if start_date and end_date:
                # 按日期范围获取
                rates = mt5.copy_rates_range(self.symbol, timeframe, start_date, end_date)
            elif start_date:
                # 从指定日期开始获取 num_bars 根
                rates = mt5.copy_rates_from(self.symbol, timeframe, start_date, num_bars)
            else:
                # 从当前时间向前获取 num_bars 根
                rates = mt5.copy_rates_from_pos(self.symbol, timeframe, 0, num_bars)

            if rates is None or len(rates) == 0:
                print(f"[MT5DataFetcher] ⚠️ 未获取到数据: {mt5.last_error()}")
                return None

            # 转为 DataFrame
            df = pd.DataFrame(rates)
            df["time"] = pd.to_datetime(df["time"], unit="s")

            # 标准化列名
            col_map = {
                "time": "time",
                "open": "open",
                "high": "high",
                "low": "low",
                "close": "close",
                "tick_volume": "volume",
                "real_volume": "real_volume",
                "spread": "spread",
            }
            df = df.rename(columns=col_map)

            # 只保留核心列
            keep_cols = [c for c in ["time", "open", "high", "low", "close", "volume"] if c in df.columns]
            df = df[keep_cols].copy()

            print(f"[MT5DataFetcher] ✅ 成功获取 {len(df)} 条数据")
            print(f"  时间范围: {df['time'].iloc[0]} ～ {df['time'].iloc[-1]}")
            return df

        except Exception as e:
            print(f"[MT5DataFetcher] ❌ 数据获取失败: {e}")
            return None

    def save_to_csv(self, df: pd.DataFrame, filename: str = "xauusd_ohlcv.csv") -> str:
        """将 DataFrame 保存为本地 CSV 文件

        Args:
            df: 包含 OHLCV 数据的 DataFrame
            filename: 保存的文件名

        Returns:
            str: 保存文件的完整路径
        """
        filepath = os.path.join(self.data_dir, filename)
        df.to_csv(filepath, index=False)
        print(f"[MT5DataFetcher] 💾 数据已保存至: {filepath}")
        return filepath

    def load_from_csv(self, filename: str = "xauusd_ohlcv.csv") -> Optional[pd.DataFrame]:
        """从本地 CSV 文件加载数据

        Args:
            filename: CSV 文件名

        Returns:
            pd.DataFrame: 加载的数据 DataFrame，文件不存在则返回 None
        """
        filepath = os.path.join(self.data_dir, filename)
        if not os.path.exists(filepath):
            print(f"[MT5DataFetcher] ⚠️ 本地缓存文件不存在: {filepath}")
            return None

        df = pd.read_csv(filepath, parse_dates=["time"])
        print(f"[MT5DataFetcher] 📂 从本地加载 {len(df)} 条数据: {filepath}")
        return df
