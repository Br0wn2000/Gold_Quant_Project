# 🥇 Gold Quant Project

> XAUUSD Quantitative Trading System — Multi-Timeframe Multi-Strategy Channel Analysis + Backtesting

A Python-based quantitative trading project for gold, covering the complete pipeline: **data acquisition → technical indicators → multi-strategy channel analysis → multi-period backtesting → live trading interface**.

---

## 📁 Project Structure

```
Gold_Quant_Project/
├── analysis/                    # Channel analysis module
│   ├── channel_analyzer.py      # Multi-timeframe analyzer (aggregates strategies + consensus)
│   └── strategies.py            # 4 channel analysis strategies
├── backtest/                    # Backtesting engine
│   └── engine.py                # Backtrader-based engine wrapper
├── data/                        # Data layer
│   └── data_fetcher.py          # Data fetchers (YFinance / MT5)
├── execution/                   # Live execution
│   └── mt5_trader.py            # MetaTrader5 trading interface (Windows only)
├── factors/                     # Factor computation
│   └── technical_indicators.py  # RSI, MACD, SMA, ATR, etc.
├── strategies/                  # Trading strategies
│   ├── dual_ma_strategy.py      # Dual moving average strategy
│   ├── enhanced_ma_strategy.py  # Enhanced MA strategy
│   ├── swing_strategy.py        # Swing trading strategy
│   ├── optimized_swing.py       # Optimized swing V1
│   └── optimized_swing_v2.py    # Optimized swing V2
├── output/                      # Analysis output directory (.gitignore)
├── main.py                      # Main entry point
├── run_channel_analysis.py      # Multi-timeframe channel analysis script
├── run_backtest.py              # Basic backtest
├── run_4h_backtest.py           # 4H timeframe backtest
├── run_daily_backtest.py        # Daily timeframe backtest
├── run_long_backtest.py         # 25-year long-term backtest
├── run_swing_backtest.py        # Swing strategy backtest
├── run_optimized_backtest.py    # Optimized strategy backtest
├── run_optimized_v2_backtest.py # Optimized V2 backtest
├── test_integration.py          # Integration tests
├── requirements.txt             # Python dependencies
└── .gitignore
```

---

## ⚙️ Environment Setup

### 1. Create Conda Environment

```bash
conda create -n gold_quant python=3.11 -y
conda activate gold_quant
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

**Dependencies:**

| Package | Purpose |
|---|---|
| `pandas` | Data processing |
| `numpy` | Numerical computation |
| `ta` | Technical indicators (ADX, Bollinger Bands, Donchian, etc.) |
| `backtrader` | Backtesting engine |
| `yfinance` | Yahoo Finance data source |
| `python-dotenv` | Environment variable management |

> **Note:** `MetaTrader5` is Windows-only. On Linux, `yfinance` is used as the data source.

### 3. Environment Variables (Optional)

Create a `.env` file for configuration (e.g., MT5 account credentials):

```bash
cp .env.example .env  # Edit as needed
```

---

## 🚀 Features

### 1. Multi-Timeframe Multi-Strategy Channel Analysis

Analyzes gold price data across **1H / 4H / Daily / Weekly** timeframes using **4 independent strategies**, then aggregates results into a **multi-strategy consensus**.

#### 4 Analysis Strategies

| Strategy | CLI Name | Core Method | Best For |
|---|---|---|---|
| **Linear Regression** | `regression` | Regression slope + R² + ADX | Trend strength quantification |
| **Bollinger Bands** | `bollinger` | SMA(20) ± 2σ, bandwidth + %B | Volatility + overbought/oversold |
| **Donchian Channel** | `donchian` | N-period highest high / lowest low | Breakout confirmation |
| **Trendline** | `trendline` | Pivot high/low regression | Closest to manual chart drawing |

#### Channel Types

| Type | Condition |
|---|---|
| 📈 Uptrend Channel | Positive trend indicators + sufficient strength |
| 📉 Downtrend Channel | Negative trend indicators + sufficient strength |
| ↔️ Sideways / Ranging | No clear trend or insufficient strength |
| 🔄 Transitioning | Direction emerging but strength not confirmed |

#### Usage

```bash
# Run all strategies (default)
conda run -n gold_quant python run_channel_analysis.py

# Select a single strategy
conda run -n gold_quant python run_channel_analysis.py --strategy bollinger

# Select multiple strategies (comma-separated)
conda run -n gold_quant python run_channel_analysis.py --strategy regression,donchian

# Analyze a different symbol
conda run -n gold_quant python run_channel_analysis.py --symbol SI=F  # Silver
```

#### Sample Output

```
╔══════════════════════════════════════════════════════════════╗
║         XAUUSD Multi-Timeframe · Multi-Strategy Report       ║
╠══════════════════════════════════════════════════════════════╣
║  📊 1H (Intraday)                                            ║
║     Regression  ↔️ Sideways   Pos:59%  5298/5062              ║
║     Bollinger   ↔️ Sideways   Pos:41%  5237/5176              ║
║     Donchian    ↔️ Sideways   Pos:50%  5237/5163              ║
║     Trendline   🔄 Transition Pos:68%  5225/5149              ║
║     ── Consensus: 🔄 Mixed (0 up / 0 down / 4 other)         ║
║  ...                                                         ║
║  📊 Weekly (Long-term)                                       ║
║     ── Consensus: 📈 Bullish (3/4 strategies agree)          ║
╚══════════════════════════════════════════════════════════════╝
```

Results are saved as timestamped JSON files in `output/`:
```
output/channel_gcf_20260226_152500_all.json
```

---

### 2. Strategy Backtesting

Built on the **Backtrader** engine, supports multiple trading strategies across different timeframes.

#### Available Strategies

| Strategy | Description | Script |
|---|---|---|
| Dual MA | SMA golden/death cross | `run_backtest.py` |
| Enhanced MA | MA + momentum filter | `run_optimized_backtest.py` |
| Swing Trading | Trend following + swing capture | `run_swing_backtest.py` |
| Optimized Swing V2 | Improved stops + short selling | `run_optimized_v2_backtest.py` |

#### Backtesting Timeframes

| Script | Timeframe | Description |
|---|---|---|
| `run_backtest.py` | 1H | Quick short-period verification |
| `run_4h_backtest.py` | 4H | Medium-period swing trading |
| `run_daily_backtest.py` | Daily | Medium-to-long-term trends |
| `run_long_backtest.py` | Daily (25 years) | Long-term robustness validation |

#### Usage

```bash
# Run a backtest (e.g., swing strategy)
conda run -n gold_quant python run_swing_backtest.py

# View results
cat output/gold_swing_backtest.json
```

Backtest reports include: return rate, Sharpe ratio, max drawdown, trade count, win rate, and other key metrics.

---

### 3. Data Acquisition

- **YFinance (default):** Fetches `GC=F` (Gold Futures) OHLCV data via `yfinance`. Supports 1m to 1wk intervals. Cross-platform.
- **MT5 (optional):** Fetches `XAUUSD` real-time data via MetaTrader5 API. Windows only.

```python
from data.data_fetcher import YFinanceDataFetcher

fetcher = YFinanceDataFetcher(symbol="GC=F")
df = fetcher.fetch_ohlcv(period="1y", interval="1d")
```

---

### 4. Technical Indicators

`factors/technical_indicators.py` provides one-call computation of all indicators:

- **Trend:** SMA (multiple periods), EMA, MACD
- **Momentum:** RSI
- **Volatility:** ATR, Bollinger Bands
- **Trend Strength:** ADX

---

### 5. Live Trading Interface (Windows Only)

`execution/mt5_trader.py` interfaces with MetaTrader5:

- Account info query
- Market / pending order placement
- Position management & closing
- Stop-loss / take-profit configuration

> ⚠️ **Warning:** Live trading involves real financial risk. Always test thoroughly on a demo account first.

---

## 📊 Quick Start

```bash
# 1. Clone the repository
git clone git@github.com:Br0wn2000/Gold_Quant_Project.git
cd Gold_Quant_Project

# 2. Setup environment
conda create -n gold_quant python=3.11 -y
conda activate gold_quant
pip install -r requirements.txt

# 3. Run channel analysis
python run_channel_analysis.py

# 4. Run strategy backtest
python run_swing_backtest.py
```

---

## 📄 License

This project is for educational and research purposes only. It does not constitute investment advice.
