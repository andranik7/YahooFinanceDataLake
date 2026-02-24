"""
Stock price forecasting using Holt-Winters exponential smoothing.
Captures trend + weekly seasonality for more dynamic predictions.
Outputs both recent actual data and forecasts for visual continuity.
"""

import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from statsmodels.tsa.holtwinters import ExponentialSmoothing
from loguru import logger

warnings.filterwarnings("ignore")

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from config.settings import USAGE_PATH, STOCK_SYMBOLS

FORECAST_DAYS = 30
HISTORY_DAYS = 90  # Recent actual days to include for visual continuity


def forecast_symbol(df_symbol: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """Fit Holt-Winters on a single symbol and return history + forecast."""
    df_symbol = df_symbol.sort_values("date").set_index("date")
    series = df_symbol["close"].dropna()

    if len(series) < 60:
        logger.warning(f"{symbol}: not enough data ({len(series)} points), skipping")
        return pd.DataFrame()

    # Use last year for fitting
    series = series.tail(252)

    try:
        model = ExponentialSmoothing(
            series,
            trend="add",
            seasonal="add",
            seasonal_periods=5,  # Weekly cycle (5 business days)
        )
        fit = model.fit(optimized=True)

        # Forecast
        forecast = fit.forecast(steps=FORECAST_DAYS)
        last_date = series.index.max()
        future_dates = pd.date_range(start=last_date + pd.Timedelta(days=1), periods=FORECAST_DAYS, freq="B")

        # Simulate confidence intervals (Holt-Winters doesn't provide them natively)
        residuals_std = fit.resid.std()
        steps = np.arange(1, FORECAST_DAYS + 1)
        margin = 1.96 * residuals_std * np.sqrt(steps)

        # Recent actual data (for visual transition on the chart)
        recent = series.tail(HISTORY_DAYS)
        actual_df = pd.DataFrame({
            "symbol": symbol,
            "date": recent.index,
            "predicted_close": recent.values,
            "confidence_lower": recent.values,
            "confidence_upper": recent.values,
            "type": "actual",
        })

        # Forecast data
        forecast_df = pd.DataFrame({
            "symbol": symbol,
            "date": future_dates,
            "predicted_close": forecast.values,
            "confidence_lower": forecast.values - margin,
            "confidence_upper": forecast.values + margin,
            "type": "forecast",
        })

        result = pd.concat([actual_df, forecast_df], ignore_index=True)
        logger.info(f"{symbol}: Holt-Winters OK — {HISTORY_DAYS}d history + {FORECAST_DAYS}d forecast")
        return result

    except Exception as e:
        logger.error(f"{symbol}: Holt-Winters failed — {e}")
        return pd.DataFrame()


def main():
    """Run forecasting for all symbols."""
    logger.info("Starting Holt-Winters predictions")

    parquet_path = USAGE_PATH / "stock_analysis" / "enriched_stocks.parquet"
    if not parquet_path.exists():
        logger.error(f"Enriched data not found: {parquet_path}")
        return

    df = pd.read_parquet(parquet_path)
    logger.info(f"Read {len(df)} records")

    df["date"] = pd.to_datetime(df["date"])

    all_forecasts = []
    for symbol in STOCK_SYMBOLS:
        df_symbol = df[df["symbol"] == symbol]
        if df_symbol.empty:
            logger.warning(f"{symbol}: no data found")
            continue
        forecast = forecast_symbol(df_symbol, symbol)
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
