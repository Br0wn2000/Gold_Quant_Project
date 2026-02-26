"""
channel_analyzer.py - 多级别 · 多策略 K 线通道分析模块

聚合多种通道分析策略（线性回归 / 布林带 / 唐奇安 / 高低点趋势线），
对多个时间框架（1H/4H/日线/周线）进行通道判定，
输出分策略结果和多策略共识报告。

使用方法：
    from analysis.channel_analyzer import ChannelAnalyzer
    analyzer = ChannelAnalyzer()
    report = analyzer.multi_timeframe_report()
    analyzer.print_report(report)
"""

import numpy as np
import pandas as pd
from datetime import datetime
from typing import Optional, List

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from data.data_fetcher import YFinanceDataFetcher
from analysis.strategies import (
    BaseChannelStrategy,
    get_strategies,
    DEFAULT_STRATEGY_NAMES,
    CHANNEL_UP,
    CHANNEL_DOWN,
    CHANNEL_SIDEWAYS,
    CHANNEL_TRANSITION,
)


# ============================================================
# 时间框架配置
# ============================================================
TIMEFRAME_CONFIGS = [
    {
        "name": "1H",
        "label": "日内",
        "interval": "1h",
        "period": "2mo",
        "lookback": 240,
        "sma_short": 20,
        "sma_long": 60,
    },
    {
        "name": "4H",
        "label": "波段",
        "interval": "1h",
        "period": "6mo",
        "lookback": 180,
        "sma_short": 20,
        "sma_long": 60,
        "resample": "4h",
    },
    {
        "name": "日线",
        "label": "中期",
        "interval": "1d",
        "period": "2y",
        "lookback": 120,
        "sma_short": 20,
        "sma_long": 60,
    },
    {
        "name": "周线",
        "label": "长期",
        "interval": "1wk",
        "period": "4y",
        "lookback": 80,
        "sma_short": 10,
        "sma_long": 30,
    },
]


class ChannelAnalyzer:
    """多级别 · 多策略通道分析器

    Attributes:
        symbol: Yahoo Finance 品种代码
        fetcher: 数据获取器
        strategies: 策略实例列表
    """

    def __init__(
        self,
        symbol: str = "GC=F",
        strategy_names: Optional[List[str]] = None,
        **strategy_kwargs,
    ):
        self.symbol = symbol
        self.fetcher = YFinanceDataFetcher(symbol=symbol)
        self.strategies = get_strategies(strategy_names, **strategy_kwargs)

    # ============================================================
    # 单级别：用所有策略分析
    # ============================================================
    def analyze_timeframe(self, config: dict) -> dict:
        """拉取指定级别数据，用所有策略分析"""
        interval = config["interval"]
        period = config["period"]

        df = self.fetcher.fetch_ohlcv(period=period, interval=interval)
        if df is None or df.empty:
            return {"name": config["name"], "label": config["label"], "error": "数据获取失败"}

        # 4H 重采样
        if "resample" in config:
            df = self._resample(df, config["resample"])
            if df is None or len(df) < 20:
                return {"name": config["name"], "label": config["label"], "error": "重采样后数据不足"}

        # 逐策略分析
        results = []
        for strat in self.strategies:
            res = strat.analyze(
                df,
                lookback=config["lookback"],
                sma_short=config.get("sma_short", 20),
                sma_long=config.get("sma_long", 60),
            )
            results.append(res)

        # 共识判定
        consensus = self._consensus(results)

        return {
            "name": config["name"],
            "label": config["label"],
            "bars_total": len(df),
            "strategies": results,
            "consensus": consensus,
        }

    # ============================================================
    # 多级别综合报告
    # ============================================================
    def multi_timeframe_report(
        self,
        timeframes: Optional[list] = None,
    ) -> dict:
        configs = timeframes or TIMEFRAME_CONFIGS
        report = {
            "symbol": self.symbol,
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "strategies_used": [s.display_name for s in self.strategies],
            "timeframes": [],
        }

        for cfg in configs:
            print(f"  分析 {cfg['name']}（{cfg['label']}）...")
            result = self.analyze_timeframe(cfg)
            report["timeframes"].append(result)

        report["summary"] = self._generate_summary(report["timeframes"])
        return report

    # ============================================================
    # 格式化输出
    # ============================================================
    def print_report(self, report: dict) -> None:
        width = 62
        single_strategy = len(self.strategies) == 1

        print()
        print("╔" + "═" * width + "╗")
        title = f"{self.symbol} 多级别通道分析报告"
        if not single_strategy:
            title = f"{self.symbol} 多级别 · 多策略通道分析报告"
        print("║" + f"  {title}".center(width - 6) + "      ║")
        print("║" + f"  {report['generated_at']}".center(width - 6) + "      ║")
        if not single_strategy:
            strat_list = " | ".join(report["strategies_used"])
            print("║" + f"  策略: {strat_list}".center(width - 6) + "      ║")
        print("╠" + "═" * width + "╣")

        for tf in report["timeframes"]:
            if "error" in tf:
                print("║" + " " * width + "║")
                print("║" + f"  📊 {tf['name']}（{tf['label']}）".ljust(width - 4) + "    ║")
                print("║" + f"     ❌ {tf['error']}".ljust(width - 4) + "    ║")
                continue

            print("║" + " " * width + "║")
            print("║" + f"  📊 {tf['name']}（{tf['label']}）".ljust(width - 4) + "    ║")

            for sr in tf["strategies"]:
                if "error" in sr:
                    line = f"     {sr.get('strategy_name', '?')}: ❌ {sr['error']}"
                    print("║" + line.ljust(width - 2) + "  ║")
                    continue

                name = sr["strategy_name"]
                ch = sr["channel_type"]
                pos = sr["position_pct"]
                upper = sr["upper_band"]
                lower = sr["lower_band"]
                extra = sr.get("sma_cross", "")

                if single_strategy:
                    # 单策略模式，展示更多细节
                    print("║" + f"     通道: {ch}".ljust(width - 2) + "  ║")
                    print("║" + f"     当前价: ${sr['current_price']:.0f}  上轨: ${upper:.0f}  下轨: ${lower:.0f}".ljust(width - 2) + "  ║")
                    print("║" + f"     位置: {pos:.0f}%  |  {extra}".ljust(width - 2) + "  ║")
                    # 输出策略特有指标
                    details = sr.get("details", {})
                    detail_parts = []
                    for k, v in details.items():
                        if isinstance(v, float):
                            detail_parts.append(f"{k}: {v:.2f}")
                        else:
                            detail_parts.append(f"{k}: {v}")
                    if detail_parts:
                        detail_line = "     " + " | ".join(detail_parts[:4])
                        print("║" + detail_line.ljust(width - 2) + "  ║")
                else:
                    # 多策略模式，紧凑显示
                    line = f"     {name:<8} {ch}  位置:{pos:.0f}%  {upper:.0f}/{lower:.0f}"
                    print("║" + line.ljust(width - 2) + "  ║")

            # 共识
            if not single_strategy:
                consensus = tf.get("consensus", {})
                con_text = consensus.get("label", "")
                print("║" + f"     ── 共识: {con_text}".ljust(width - 2) + "  ║")

        print("║" + " " * width + "║")
        print("╠" + "═" * width + "╣")

        # 综合结论
        summary = report.get("summary", {})
        print("║" + " " * width + "║")
        print("║" + f"  🎯 综合判断".ljust(width - 4) + "    ║")
        if summary:
            print("║" + f"     {summary.get('conclusion', '')}".ljust(width - 2) + "  ║")
            for detail in summary.get("details", []):
                print("║" + f"     • {detail}".ljust(width - 2) + "  ║")
        print("║" + " " * width + "║")
        print("╚" + "═" * width + "╝")
        print()

    # ============================================================
    # 内部方法
    # ============================================================
    def _consensus(self, strategy_results: list) -> dict:
        """对同一级别的多策略结果进行共识判断"""
        valid = [r for r in strategy_results if "error" not in r]
        if not valid:
            return {"label": "❓ 无有效数据", "up": 0, "down": 0, "total": 0}

        up = sum(1 for r in valid if r["channel_type"] == CHANNEL_UP)
        down = sum(1 for r in valid if r["channel_type"] == CHANNEL_DOWN)
        total = len(valid)

        if up == total:
            label = f"📈 全部看涨 ({up}/{total})"
        elif down == total:
            label = f"📉 全部看跌 ({down}/{total})"
        elif up > down and up >= total / 2:
            label = f"📈 偏多 ({up}/{total} 看涨)"
        elif down > up and down >= total / 2:
            label = f"📉 偏空 ({down}/{total} 看跌)"
        else:
            label = f"🔄 分歧 ({up}涨/{down}跌/{total - up - down}其他)"

        return {"label": label, "up": up, "down": down, "total": total}

    def _resample(self, df: pd.DataFrame, rule: str) -> Optional[pd.DataFrame]:
        """将 K 线重采样到更大时间周期"""
        try:
            temp = df.copy()
            if "time" in temp.columns:
                temp.set_index("time", inplace=True)
            if not isinstance(temp.index, pd.DatetimeIndex):
                temp.index = pd.to_datetime(temp.index)

            resampled = temp.resample(rule).agg({
                "open": "first",
                "high": "max",
                "low": "min",
                "close": "last",
                "volume": "sum",
            }).dropna()

            resampled.reset_index(inplace=True)
            if "time" not in resampled.columns:
                first_col = resampled.columns[0]
                if pd.api.types.is_datetime64_any_dtype(resampled[first_col]):
                    resampled.rename(columns={first_col: "time"}, inplace=True)
            return resampled
        except Exception as e:
            print(f"  ⚠️ 重采样失败: {e}")
            return None

    def _generate_summary(self, timeframes: list) -> dict:
        """多级别综合判断"""
        valid_tfs = [tf for tf in timeframes if "error" not in tf]
        if not valid_tfs:
            return {"conclusion": "数据不足，无法综合判断", "details": []}

        details = []

        # 方法1：基于共识统计
        consensus_up = 0
        consensus_down = 0
        for tf in valid_tfs:
            con = tf.get("consensus", {})
            if con.get("up", 0) > con.get("down", 0):
                consensus_up += 1
            elif con.get("down", 0) > con.get("up", 0):
                consensus_down += 1

        total = len(valid_tfs)
        if consensus_up == total:
            conclusion = "📈 全级别偏多 — 强烈多头趋势"
        elif consensus_down == total:
            conclusion = "📉 全级别偏空 — 强烈空头趋势"
        elif consensus_up > consensus_down:
            conclusion = f"📈 整体偏多（{consensus_up}/{total} 级别看涨）"
        elif consensus_down > consensus_up:
            conclusion = f"📉 整体偏空（{consensus_down}/{total} 级别看跌）"
        else:
            conclusion = "🔄 多空分歧 — 各级别方向不一致"

        # 各级别共识情况
        for tf in valid_tfs:
            con = tf.get("consensus", {})
            details.append(f"{tf['name']}: {con.get('label', '?')}")

        # 大小级别冲突
        long_tfs = [tf for tf in valid_tfs if tf["name"] in ("日线", "周线")]
        short_tfs = [tf for tf in valid_tfs if tf["name"] in ("1H", "4H")]
        long_bullish = any(tf.get("consensus", {}).get("up", 0) > tf.get("consensus", {}).get("down", 0) for tf in long_tfs)
        short_bearish = any(tf.get("consensus", {}).get("down", 0) > tf.get("consensus", {}).get("up", 0) for tf in short_tfs)
        long_bearish = any(tf.get("consensus", {}).get("down", 0) > tf.get("consensus", {}).get("up", 0) for tf in long_tfs)
        short_bullish = any(tf.get("consensus", {}).get("up", 0) > tf.get("consensus", {}).get("down", 0) for tf in short_tfs)

        if long_bullish and short_bearish:
            details.append("⚠️ 大级别看多但小级别回调中")
        elif long_bearish and short_bullish:
            details.append("⚠️ 大级别看空但小级别反弹中")

        return {"conclusion": conclusion, "details": details}
