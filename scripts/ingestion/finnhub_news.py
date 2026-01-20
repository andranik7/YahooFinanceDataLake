"""
Ingestion script for Finnhub news data.
Fetches historical news for each stock symbol (up to 1 year) and saves to the raw layer.
"""

import json
import sys
import time
import requests
from datetime import datetime, timezone, timedelta
from pathlib import Path

from loguru import logger

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from config.settings import STOCK_SYMBOLS, NEWS_RAW, FINNHUB_API_KEY


FINNHUB_BASE_URL = "https://finnhub.io/api/v1"


def fetch_news(symbol: str, from_date: str, to_date: str) -> list[dict]:
    """
    Fetch news for a given stock symbol from Finnhub API.

    Args:
        symbol: Stock ticker symbol
        from_date: Start date (YYYY-MM-DD)
        to_date: End date (YYYY-MM-DD)

    Returns:
        List of parsed news articles
    """
    if not FINNHUB_API_KEY:
        logger.error("FINNHUB_API_KEY not set. Please set it in your environment.")
        return []

    try:
        url = f"{FINNHUB_BASE_URL}/company-news"
        params = {
            "symbol": symbol,
            "from": from_date,
            "to": to_date,
            "token": FINNHUB_API_KEY,
        }

        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()

        news = response.json()

        if not news:
            logger.warning(f"No news for {symbol}")
            return []

        parsed_news = []
        for item in news:
            # Convert UNIX timestamp to ISO format
            pub_timestamp = item.get("datetime", 0)
            pub_date = datetime.fromtimestamp(pub_timestamp, tz=timezone.utc).isoformat()

            parsed_news.append({
                "id": str(item.get("id", "")),
                "symbol": symbol,
                "title": item.get("headline", ""),
                "summary": item.get("summary", ""),
                "pub_date": pub_date,
                "provider": item.get("source", ""),
                "url": item.get("url", ""),
                "category": item.get("category", ""),
                "image": item.get("image", ""),
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            })

        return parsed_news

    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching news for {symbol}: {e}")
        return []


def save_to_raw(data: list[dict]) -> Path:
    """Save news data to the raw layer with date partitioning."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    output_dir = NEWS_RAW / "financial_news" / today
    output_dir.mkdir(parents=True, exist_ok=True)

    output_file = output_dir / "news.json"

    with open(output_file, "w") as f:
        json.dump(data, f, indent=2)

    logger.info(f"Saved {len(data)} news articles to {output_file}")
    return output_file


def main():
    """Main ingestion function for Finnhub news."""
    logger.info(f"Starting Finnhub news ingestion for {len(STOCK_SYMBOLS)} symbols")

    if not FINNHUB_API_KEY:
        logger.error("FINNHUB_API_KEY not set. Aborting.")
        return

    # Fetch news for the last 12 months
    to_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    from_date = (datetime.now(timezone.utc) - timedelta(days=365)).strftime("%Y-%m-%d")

    logger.info(f"Fetching news from {from_date} to {to_date}")

    all_news = []
    seen_ids = set()

    for symbol in STOCK_SYMBOLS:
        news = fetch_news(symbol, from_date, to_date)
        for article in news:
            # Deduplicate by news ID (same article can appear for multiple symbols)
            if article["id"] not in seen_ids:
                seen_ids.add(article["id"])
                all_news.append(article)

        logger.info(f"Fetched {len(news)} news for {symbol}")

        # Rate limiting: Finnhub allows 60 calls/min on free tier
        time.sleep(1)

    if all_news:
        save_to_raw(all_news)

    logger.info(f"Finnhub news ingestion complete: {len(all_news)} unique articles")


if __name__ == "__main__":
    main()
