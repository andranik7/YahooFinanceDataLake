"""
Ingestion script for Yahoo Finance news data.
Fetches news for each stock symbol and saves to the raw layer.
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import yfinance as yf
from loguru import logger

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from config.settings import STOCK_SYMBOLS, NEWS_RAW


def fetch_news(symbol: str) -> list[dict]:
    """Fetch news for a given stock symbol."""
    try:
        ticker = yf.Ticker(symbol)
        news = ticker.news

        if not news:
            logger.warning(f"No news for {symbol}")
            return []

        parsed_news = []
        for item in news:
            content = item.get("content", {})
            parsed_news.append({
                "id": item.get("id", ""),
                "symbol": symbol,
                "title": content.get("title", ""),
                "summary": content.get("summary", ""),
                "pub_date": content.get("pubDate", ""),
                "provider": content.get("provider", {}).get("displayName", ""),
                "url": content.get("canonicalUrl", {}).get("url", ""),
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            })

        return parsed_news

    except Exception as e:
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
    """Main ingestion function for news."""
    logger.info(f"Starting news ingestion for {len(STOCK_SYMBOLS)} symbols")

    all_news = []
    seen_ids = set()

    for symbol in STOCK_SYMBOLS:
        news = fetch_news(symbol)
        for article in news:
            # Deduplicate by news ID (same article can appear for multiple symbols)
            if article["id"] not in seen_ids:
                seen_ids.add(article["id"])
                all_news.append(article)

        logger.info(f"Fetched {len(news)} news for {symbol}")

    if all_news:
        save_to_raw(all_news)

    logger.info(f"News ingestion complete: {len(all_news)} unique articles")


if __name__ == "__main__":
    main()
