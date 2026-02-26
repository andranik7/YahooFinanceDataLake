# Building a Financial Data Lake with Sentiment-Powered Stock Predictions

*How we built an end-to-end Big Data pipeline that combines 5 years of stock data, 21,000 news articles, and NLP sentiment analysis to forecast stock prices — all running in Docker.*

---

## The Problem

Stock prices don't move in isolation. A single earnings report, a CEO tweet, or a geopolitical event can shift a stock by 10% in hours. Traditional time series models like ARIMA only look at historical prices — they're blind to what the market is *feeling*.

We wanted to build something different: a pipeline that **ingests financial data and news in parallel**, runs sentiment analysis on every article, and feeds that sentiment directly into the forecasting model as a mathematical variable.

The result is a fully containerized Data Lake that goes from raw API calls to interactive dashboards in under 7 minutes.

> **[Screenshot : dashboard principal — vue d'ensemble avec les cours, prédictions, Top/Flop, sentiment]**

---

## What We Built

A complete ETL pipeline tracking 10 major US stocks (AAPL, GOOGL, MSFT, AMZN, META, TSLA, NVDA, JPM, V, WMT) across two data sources:

- **Yahoo Finance** — 5 years of daily OHLCV prices + company metadata
- **Finnhub API** — 12 months of financial news (~21,000 articles)

Every article is analyzed for sentiment at ingestion time. That sentiment feeds into a SARIMAX model that produces 30-day forecasts with 95% confidence intervals. Everything is indexed in Elasticsearch and visualized in Kibana through two interactive dashboards.

---

## Architecture

> **[Image : diagramme d'architecture — refais ton diagramme ASCII en image propre avec Excalidraw ou draw.io]**

The pipeline follows a **medallion architecture** (Bronze → Silver → Gold) orchestrated by Apache Airflow:

```
Sources → Raw (JSON) → Formatted (Parquet) → Usage (Parquet) → Elasticsearch → Kibana
```

**The stack:**

| Layer | Technology | Why |
|-------|-----------|-----|
| Orchestration | Apache Airflow | DAG-based scheduling, retry logic, parallel tasks |
| Processing | Apache Spark | Distributed JSON → Parquet transformation |
| Sentiment | VADER | Fast, no GPU needed, good enough for financial headlines |
| Forecasting | SARIMAX (statsmodels) | Handles trend + seasonality + exogenous variables |
| Indexing | Elasticsearch | Full-text search on news + numeric aggregations on prices |
| Visualization | Kibana | Interactive dashboards with drill-down |
| Infrastructure | Docker Compose | 6 services, one command to start |

**Why these choices?**

- **Spark over pandas** — Not for the data volume (105 MB fits in memory), but because this is a Data Lake project. Spark gives us distributed processing patterns that scale if we add more symbols or switch to streaming.
- **VADER over FinBERT/LLMs** — VADER runs in milliseconds per article with zero infrastructure. For financial headlines (short, direct language), it's surprisingly effective. A fine-tuned FinBERT would be better, but VADER keeps the pipeline fast and dependency-light.
- **Parquet over CSV/JSON** — 3x compression, columnar reads, schema enforcement. A raw JSON file of 77 MB becomes 23 MB in Parquet.

---

## The Pipeline in Detail

The Airflow DAG runs 6 tasks in sequence (with the two ingestion tasks running in parallel):

> **[Screenshot : DAG Airflow avec les tâches en vert (success)]**

### 1. Ingestion (~3 min)

Two independent tasks fetch data in parallel:

**Stock data** pulls 5 years of daily prices for each symbol via `yfinance`. That's ~12,600 price records plus company metadata (sector, industry, market cap).

**News data** calls the Finnhub API month by month (to avoid pagination limits), respecting the 60 calls/min rate limit. Each article's headline and summary are concatenated and scored by VADER at ingestion time:

```python
def analyze_sentiment(text: str) -> dict:
    scores = sentiment_analyzer.polarity_scores(text)
    compound = scores["compound"]  # -1.0 to +1.0

    if compound >= 0.05:   label = "positive"
    elif compound <= -0.05: label = "negative"
    else:                   label = "neutral"

    return {"sentiment_score": compound, "sentiment_label": label}
```

The sentiment score and label are stored alongside each article from day one — no reprocessing needed downstream.

### 2. Formatting (~1 min)

Spark reads all raw JSON files (glob across date partitions), normalizes types (cast prices to Double, volumes to Long), converts all timestamps to UTC, and writes Parquet with Snappy compression.

### 3. Enrichment (~1 min)

This is where the data gets interesting. Spark joins three sources:

```
stocks LEFT JOIN company_info ON symbol
       LEFT JOIN news_aggregated ON symbol
```

The news are aggregated by symbol: article count and latest publication date. Two derived metrics are computed:

- **daily_range** = high - low (intraday volatility)
- **daily_change_pct** = (close - open) / open × 100 (daily return)

### 4. Prediction (~30s)

This is the core of the project. More on this below.

### 5. Indexing (~1 min)

Three Elasticsearch indices are populated via bulk API:
- `stock_analysis` — 12,800 enriched stock records (upserted by `symbol_date`)
- `stock_news` — 21,000 articles (deduplicated by Finnhub UUID)
- `stock_predictions` — 1,200 forecast records (recreated each run)

**Total pipeline duration: ~7 minutes.** Dominated by the Finnhub rate limit.

---

## The Interesting Part: Sentiment-Powered Predictions

Most ARIMA tutorials stop at `model.fit(series)`. We wanted to go further by telling the model: "here's what the news are saying about this stock."

### How it works

**SARIMAX** = Seasonal ARIMA with eXogenous variables. The "X" is what makes it different. The model sees two inputs:

1. **Historical prices** — the last 252 trading days (~1 year)
2. **Daily sentiment** — the average VADER score for each day, aligned to trading dates

```python
# Aggregate daily sentiment per symbol
daily_sentiment = news_df.groupby("date")["sentiment_score"].mean()

# Align with stock dates, fill gaps with 0 (neutral)
exog = sentiment.reindex(series.index).fillna(0)

model = SARIMAX(
    series,
    exog=exog,
    order=(2, 1, 2),            # 2 AR, 1 differencing, 2 MA
    seasonal_order=(1, 1, 1, 5), # Weekly cycle (5 trading days)
)
```

**For future predictions**, we use the average sentiment of the last 30 days as a constant projection. It's a simplification, but it captures the current market mood.

The output includes 90 days of actual prices (for visual context) and 30 days of forecasts with 95% confidence bands.

> **[Screenshot : graphique de prédiction SARIMAX dans Kibana — cours réel en bleu, prédiction en pointillés, bandes de confiance en gris]**

### The parameters

| Parameter | Value | Why |
|-----------|-------|-----|
| ARIMA order (2,1,2) | 2 AR + 1 diff + 2 MA terms | Captures short-term autocorrelation |
| Seasonal (1,1,1,5) | Weekly cycle | Markets have a 5-day trading week pattern |
| Training window | 252 days | One trading year — balances recency and stability |
| Forecast horizon | 30 business days | ~6 weeks — beyond that, confidence bands explode |
| Confidence level | 95% | Standard for financial forecasting |

---

## What Broke (and How We Fixed It)

### The Spark cluster mystery

Our Spark jobs were running, but always in `local[*]` mode — never on the actual cluster. Turns out, setting `.master()` in the Python code **overrides** the `--master` flag from `spark-submit`. The fix: remove `.master()` from the code and let `spark-submit` control it.

### The Windows/WSL2 nightmare

Our teammate runs Windows with Docker on WSL2. Everything worked on macOS, but on his machine:

1. **`Mkdirs failed to create`** — Spark worker couldn't create directories on bind-mounted volumes. Fix: run Spark containers as root (`user: "0"`).

2. **`Failed to rename`** — Hadoop's `FileOutputCommitter` uses atomic `rename` to move files from `_temporary/` to the final location. The WSL2 filesystem (9p/grpcfuse) doesn't support cross-directory renames. Fix: write Parquet to `/tmp` first, then copy to the mounted volume. We also switched from bind mounts to a **named Docker volume**, which doesn't have these filesystem limitations.

3. **`Permission denied` on cleanup** — Files created by Spark (running as root) couldn't be deleted by Airflow (running as user `airflow`). Fix: set `umask 000` on Spark containers and use `shutil.rmtree(path, ignore_errors=True)`.

Three bugs, three different root causes, all related to how Docker handles filesystem operations on Windows. **If your data pipeline needs to run cross-platform, use named Docker volumes instead of bind mounts.**

---

## The Dashboards

### Main dashboard — Market Overview

> **[Screenshot : dashboard principal complet]**

Seven visualizations in one view:
- **Line chart** — closing prices over 90 days, one line per symbol
- **Predictions** — SARIMAX forecasts with confidence bands
- **Top/Flop** — daily ranking by price variation (with drill-down to the detail dashboard)
- **Treemap** — market capitalization by sector and symbol
- **Bar chart** — average sentiment score per stock
- **Donut** — overall sentiment distribution (positive / negative / neutral)
- **News table** — latest articles with sentiment scores

### Detail dashboard — Single Stock Deep Dive

> **[Screenshot : dashboard détaillé pour un symbole, ex: AAPL]**

Accessible by clicking a symbol in the Top/Flop table. Shows:
- Key metrics (last close, volume, J+1 estimate)
- Price history and SARIMAX prediction
- Daily return vs sentiment correlation
- Media buzz (article volume over time)
- Latest news for the symbol

All dashboards are **version-controlled** as an NDJSON file and automatically imported at startup via a shell script that polls Kibana's API.

---

## By the Numbers

| Metric | Value |
|--------|-------|
| Stock symbols tracked | 10 |
| Historical data | 5 years (~12,600 records) |
| News articles analyzed | ~21,000 |
| Sentiment analysis | VADER on every article at ingestion |
| Prediction horizon | 30 business days with 95% CI |
| Elasticsearch documents | ~35,000 across 3 indices |
| Pipeline duration | ~7 minutes |
| Docker services | 6 (Airflow, Spark master/worker, PostgreSQL, ES, Kibana) |
| Total data size | 105 MB (Raw 77 MB + Formatted 23 MB + Usage 5 MB) |

---

## What We'd Do Differently

- **Delta Lake instead of raw Parquet** — ACID transactions, schema evolution, and time travel would make the pipeline more robust
- **FinBERT instead of VADER** — A transformer model fine-tuned on financial text would capture nuances VADER misses ("the stock *only* dropped 2%" → VADER sees "dropped" as negative)
- **Streaming instead of batch** — Kafka + Spark Structured Streaming for near real-time news ingestion and sentiment updates
- **More symbols, more markets** — The architecture scales, but the Finnhub free tier (60 calls/min) is the bottleneck
- **Backtesting framework** — We predict, but we don't systematically measure accuracy. Adding MAPE/RMSE tracking per symbol would close the loop

---

## Try It Yourself

The entire project runs with three commands:

```bash
git clone <repository>
cp .env.example .env  # Add your Finnhub API key
docker-compose up --build -d
```

Open Airflow at `localhost:8080`, trigger the DAG, and watch the dashboards populate at `localhost:5601`.

---

*If you're building data pipelines and want to chat, feel free to connect. We learned a lot from breaking things on this project — especially on Windows.*

**Tags**: `#DataEngineering` `#ApacheSpark` `#TimeSeries` `#SentimentAnalysis` `#Docker` `#Python` `#BigData`
