"""
run_channel_analysis.py - 多级别 · 多策略 K 线通道分析脚本

拉取 XAUUSD（GC=F）实时数据，对 1H/4H/日线/周线 四个级别
用多种策略进行通道判定并输出分析报告。

使用方法：
    # 全部策略
    conda run -n gold_quant python run_channel_analysis.py

    # 指定策略
    conda run -n gold_quant python run_channel_analysis.py --strategy bollinger
    conda run -n gold_quant python run_channel_analysis.py --strategy regression,donchian

可选策略: regression(线性回归), bollinger(布林带), donchian(唐奇安), trendline(高低点趋势线)
"""

import sys
import json
import argparse
import os
from datetime import datetime

sys.path.insert(0, ".")

from analysis.channel_analyzer import ChannelAnalyzer


def main():
    parser = argparse.ArgumentParser(description="XAUUSD 多级别通道分析")
    parser.add_argument(
        "--strategy", "-s",
        type=str,
        default=None,
        help="策略名称，逗号分隔。可选: regression, bollinger, donchian, trendline（默认: 全部）",
    )
    parser.add_argument(
        "--symbol",
        type=str,
        default="GC=F",
        help="Yahoo Finance 品种代码（默认: GC=F）",
    )
    args = parser.parse_args()

    strategy_names = None
    if args.strategy:
        strategy_names = [s.strip() for s in args.strategy.split(",")]

    print("=" * 62)
    print("  XAUUSD 多级别通道分析")
    if strategy_names:
        print(f"  策略: {', '.join(strategy_names)}")
    else:
        print("  策略: 全部（线性回归 | 布林带 | 唐奇安 | 高低点趋势线）")
    print("=" * 62)

    analyzer = ChannelAnalyzer(
        symbol=args.symbol,
        strategy_names=strategy_names,
    )

    print("\n[1/2] 拉取数据并分析各级别通道...")
    report = analyzer.multi_timeframe_report()

    print("\n[2/2] 输出分析报告")
    analyzer.print_report(report)

    # 保存 JSON — 文件名包含日期、时间、品种和策略信息
    _output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
    os.makedirs(_output_dir, exist_ok=True)

    now_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    symbol_tag = args.symbol.replace("=", "").replace(".", "").lower()
    strategy_tag = "+".join(strategy_names) if strategy_names else "all"
    filename = f"channel_{symbol_tag}_{now_str}_{strategy_tag}.json"

    output_path = os.path.join(_output_dir, filename)
    with open(output_path, "w") as f:
        json.dump(report, f, indent=2, default=str, ensure_ascii=False)
    print(f"📁 详细数据已保存至 {output_path}")


if __name__ == "__main__":
    main()
