"""
SARIMAX forecasting with sentiment analysis as exogenous variable.
Combines Holt-Winters trend/seasonality with news sentiment to adjust predictions.
"""

import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from statsmodels.tsa.statespace.sarimax import SARIMAX
from loguru import logger

warnings.filterwarnings("ignore")

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from config.settings import USAGE_PATH, NEWS_FORMATTED, STOCK_SYMBOLS

FORECAST_DAYS = 30
HISTORY_DAYS = 90


def build_daily_sentiment(news_df: pd.DataFrame, symbol: str) -> pd.Series:
    """Aggregate daily sentiment score for a symbol."""
    df = news_df[news_df["symbol"] == symbol].copy()
    df["date"] = pd.to_datetime(df["pub_date_utc"]).dt.normalize()
    daily = df.groupby("date")["sentiment_score"].mean()
    return daily


def forecast_symbol(
    df_symbol: pd.DataFrame, sentiment: pd.Series, symbol: str
) -> pd.DataFrame:
    """Fit SARIMAX with sentiment as exogenous variable."""
    df_symbol = df_symbol.sort_values("date").set_index("date")
    series = df_symbol["close"].dropna()

    if len(series) < 60:
        logger.warning(f"{symbol}: not enough data ({len(series)} points), skipping")
        return pd.DataFrame()

    # Use last year for fitting
    series = series.tail(252)

    # Align sentiment with stock dates, fill missing days with 0 (neutral)
    exog = sentiment.reindex(series.index).fillna(0).values.reshape(-1, 1)

    try:
        model = SARIMAX(
            series,
            exog=exog,
            order=(2, 1, 2),
            seasonal_order=(1, 1, 1, 5),
            enforce_stationarity=False,
            enforce_invertibility=False,
        )
        fit = model.fit(disp=False, maxiter=200)

        # For future predictions, use the average recent sentiment (last 30 days)
        recent_sentiment = sentiment.reindex(series.index).tail(30).mean()
        if np.isnan(recent_sentiment):
            recent_sentiment = 0.0
        future_exog = np.full((FORECAST_DAYS, 1), recent_sentiment)

        forecast = fit.get_forecast(steps=FORECAST_DAYS, exog=future_exog)
        pred = forecast.predicted_mean
        conf = forecast.conf_int(alpha=0.05)

        last_date = series.index.max()
        future_dates = pd.date_range(
            start=last_date + pd.Timedelta(days=1), periods=FORECAST_DAYS, freq="B"
        )

        # Recent actual data for visual continuity
        recent = series.tail(HISTORY_DAYS)
        recent_sent = sentiment.reindex(recent.index).fillna(0)
        actual_df = pd.DataFrame({
            "symbol": symbol,
            "date": recent.index,
            "predicted_close": recent.values,
            "confidence_lower": recent.values,
            "confidence_upper": recent.values,
            "sentiment_score": recent_sent.values,
            "type": "actual",
        })

        # Forecast data
        forecast_df = pd.DataFrame({
            "symbol": symbol,
            "date": future_dates,
            "predicted_close": pred.values,
            "confidence_lower": conf.iloc[:, 0].values,
            "confidence_upper": conf.iloc[:, 1].values,
            "sentiment_score": recent_sentiment,
            "type": "forecast",
        })

        result = pd.concat([actual_df, forecast_df], ignore_index=True)
        logger.info(
            f"{symbol}: SARIMAX+Sentiment OK — sentiment moyen={recent_sentiment:.3f}, "
            f"{HISTORY_DAYS}d history + {FORECAST_DAYS}d forecast"
        )
        return result

    except Exception as e:
        logger.error(f"{symbol}: SARIMAX failed — {e}")
        return pd.DataFrame()


def main():
    """Run SARIMAX forecasting with sentiment for all symbols."""
    logger.info("Starting SARIMAX + Sentiment predictions")

    parquet_path = USAGE_PATH / "stock_analysis" / "enriched_stocks.parquet"
    news_path = NEWS_FORMATTED / "financial_news" / "news.parquet"

    if not parquet_path.exists():
        logger.error(f"Enriched data not found: {parquet_path}")
        return

    df = pd.read_parquet(parquet_path)
    df["date"] = pd.to_datetime(df["date"])
    logger.info(f"Read {len(df)} stock records")

    # Load news sentiment
    if news_path.exists():
        news_df = pd.read_parquet(news_path, columns=["symbol", "pub_date_utc", "sentiment_score"])
        logger.info(f"Read {len(news_df)} news records for sentiment")
    else:
        logger.warning("No news data found, using neutral sentiment")
        news_df = pd.DataFrame(columns=["symbol", "pub_date_utc", "sentiment_score"])

    all_forecasts = []
    for symbol in STOCK_SYMBOLS:
        df_symbol = df[df["symbol"] == symbol]
        if df_symbol.empty:
            logger.warning(f"{symbol}: no data found")
            continue

        sentiment = build_daily_sentiment(news_df, symbol)
        forecast = forecast_symbol(df_symbol, sentiment, symbol)
        if not forecast.empty:
            all_forecasts.append(forecast)

    if not all_forecasts:
        logger.error("No forecasts generated")
        return

    result_df = pd.concat(all_forecasts, ignore_index=True)

    output_path = USAGE_PATH / "predictions"
    output_path.mkdir(parents=True, exist_ok=True)
    result_df.to_parquet(output_path / "arima_predictions.parquet", index=False)

    logger.info(f"Saved {len(result_df)} predictions to {output_path / 'arima_predictions.parquet'}")


if __name__ == "__main__":
    main()
