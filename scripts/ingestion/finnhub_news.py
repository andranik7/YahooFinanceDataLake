"""
Ingestion script for Finnhub news data.
Fetches historical news for each stock symbol (up to 1 year) and saves to the raw layer.
Includes sentiment analysis using VADER.
"""

import json
import sys
import time
import requests
from datetime import datetime, timezone, timedelta
from pathlib import Path

from loguru import logger
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from config.settings import STOCK_SYMBOLS, NEWS_RAW, FINNHUB_API_KEY


FINNHUB_BASE_URL = "https://finnhub.io/api/v1"

# Initialize sentiment analyzer
sentiment_analyzer = SentimentIntensityAnalyzer()


def analyze_sentiment(text: str) -> dict:
    """
    Analyze sentiment of text using VADER.

    Returns:
        dict with sentiment_score (compound) and sentiment_label
    """
    if not text:
        return {"sentiment_score": 0.0, "sentiment_label": "neutral"}

    scores = sentiment_analyzer.polarity_scores(text)
    compound = scores["compound"]

    # Classify sentiment
    if compound >= 0.05:
        label = "positive"
    elif compound <= -0.05:
        label = "negative"
    else:
        label = "neutral"

    return {
        "sentiment_score": round(compound, 4),
        "sentiment_label": label
    }


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

            title = item.get("headline", "")
            summary = item.get("summary", "")

            # Analyze sentiment on title + summary combined
            text_for_sentiment = f"{title}. {summary}" if summary else title
            sentiment = analyze_sentiment(text_for_sentiment)

            parsed_news.append({
                "id": str(item.get("id", "")),
                "symbol": symbol,
                "title": title,
                "summary": summary,
                "pub_date": pub_date,
                "provider": item.get("source", ""),
                "url": item.get("url", ""),
                "category": item.get("category", ""),
                "image": item.get("image", ""),
                "sentiment_score": sentiment["sentiment_score"],
                "sentiment_label": sentiment["sentiment_label"],
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


def generate_month_ranges(months_back: int = 12) -> list[tuple[str, str]]:
    """
    Generate list of (from_date, to_date) tuples for each month.
    Fetching month by month avoids API result limits.
    """
    ranges = []
    now = datetime.now(timezone.utc)
    current = now

    for _ in range(months_back):
        month_end = current
        month_start = current.replace(day=1)
        ranges.append((
            month_start.strftime("%Y-%m-%d"),
            month_end.strftime("%Y-%m-%d")
        ))
        # Go to previous month
        current = month_start - timedelta(days=1)

    return ranges


def main():
    """Main ingestion function for Finnhub news."""
    logger.info(f"Starting Finnhub news ingestion for {len(STOCK_SYMBOLS)} symbols")

    if not FINNHUB_API_KEY:
        logger.error("FINNHUB_API_KEY not set. Aborting.")
        return

    # Generate month-by-month date ranges (12 months)
    month_ranges = generate_month_ranges(12)
    total_calls = len(STOCK_SYMBOLS) * len(month_ranges)
    logger.info(f"Will make {total_calls} API calls (~{total_calls // 60 + 1} minutes)")

    all_news = []
    seen_ids = set()
    call_count = 0

    for symbol in STOCK_SYMBOLS:
        symbol_count = 0

        for from_date, to_date in month_ranges:
            news = fetch_news(symbol, from_date, to_date)

            for article in news:
                if article["id"] not in seen_ids:
                    seen_ids.add(article["id"])
                    all_news.append(article)
                    symbol_count += 1

            call_count += 1

            # Rate limiting: 60 calls/min = 1 call/second
            time.sleep(1.1)

            # Log progress every 10 calls
            if call_count % 10 == 0:
                logger.info(f"Progress: {call_count}/{total_calls} calls")

        logger.info(f"Fetched {symbol_count} unique news for {symbol}")

    if all_news:
        save_to_raw(all_news)

    logger.info(f"Finnhub news ingestion complete: {len(all_news)} unique articles")


if __name__ == "__main__":
    main()
