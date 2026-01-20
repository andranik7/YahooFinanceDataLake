"""
Ingestion script for Yahoo Finance stock data.
Fetches stock prices and saves them to the raw layer of the data lake.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import yfinance as yf
from loguru import logger

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from config.settings import STOCK_SYMBOLS, YAHOO_FINANCE_RAW


def fetch_stock_data(symbol: str, period: str = "1y") -> list[dict]:
    """Fetch stock data history for a given symbol."""
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period=period)

        if hist.empty:
            logger.warning(f"No data for {symbol}")
            return []

        records = []
        for date, row in hist.iterrows():
            records.append({
                "symbol": symbol,
                "date": date.strftime("%Y-%m-%d"),
                "open": float(row["Open"]),
                "high": float(row["High"]),
                "low": float(row["Low"]),
                "close": float(row["Close"]),
                "volume": int(row["Volume"]),
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            })

        return records
    except Exception as e:
        logger.error(f"Error fetching {symbol}: {e}")
        return []


def fetch_company_info(symbol: str) -> dict | None:
    """Fetch company info for a given symbol."""
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info

        return {
            "symbol": symbol,
            "name": info.get("longName", ""),
            "sector": info.get("sector", ""),
            "industry": info.get("industry", ""),
            "country": info.get("country", ""),
            "market_cap": info.get("marketCap", 0),
            "currency": info.get("currency", "USD"),
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        logger.error(f"Error fetching info for {symbol}: {e}")
        return None


def save_to_raw(data: list[dict], data_type: str) -> Path:
    """Save data to the raw layer with date partitioning."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    output_dir = YAHOO_FINANCE_RAW / data_type / today
    output_dir.mkdir(parents=True, exist_ok=True)

    output_file = output_dir / f"{data_type}.json"

    with open(output_file, "w") as f:
        json.dump(data, f, indent=2)

    logger.info(f"Saved {len(data)} records to {output_file}")
    return output_file


def main():
    """Main ingestion function."""
    logger.info(f"Starting Yahoo Finance ingestion for {len(STOCK_SYMBOLS)} symbols")

    # Fetch stock prices (12 months history)
    stocks_data = []
    for symbol in STOCK_SYMBOLS:
        records = fetch_stock_data(symbol, period="1y")
        stocks_data.extend(records)
        if records:
            logger.info(f"Fetched {symbol}: {len(records)} days")

    if stocks_data:
        save_to_raw(stocks_data, "stocks")

    # Fetch company info
    company_data = []
    for symbol in STOCK_SYMBOLS:
        data = fetch_company_info(symbol)
        if data:
            company_data.append(data)

    if company_data:
        save_to_raw(company_data, "company_info")

    logger.info(f"Ingestion complete: {len(stocks_data)} stocks, {len(company_data)} companies")


if __name__ == "__main__":
    main()
