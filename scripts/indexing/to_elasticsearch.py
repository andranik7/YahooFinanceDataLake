"""
Indexing script: pushes enriched data to Elasticsearch.
"""

import sys
from pathlib import Path

import pandas as pd
from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk
from loguru import logger

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from config.settings import (
    USAGE_PATH,
    NEWS_FORMATTED,
    ELASTICSEARCH_HOST,
    ELASTICSEARCH_PORT,
    ELASTICSEARCH_INDEX,
    ELASTICSEARCH_NEWS_INDEX,
)


def get_es_client() -> Elasticsearch:
    """Create Elasticsearch client."""
    return Elasticsearch(
        hosts=[f"http://{ELASTICSEARCH_HOST}:{ELASTICSEARCH_PORT}"],
        request_timeout=30,
    )


def create_index(es: Elasticsearch, index_name: str) -> None:
    """Create index with mapping if it doesn't exist."""
    if es.indices.exists(index=index_name):
        logger.info(f"Index already exists: {index_name}")
        return

    mapping = {
        "mappings": {
            "properties": {
                "symbol": {"type": "keyword"},
                "name": {"type": "text"},
                "sector": {"type": "keyword"},
                "industry": {"type": "keyword"},
                "date": {"type": "date"},
                "open": {"type": "float"},
                "high": {"type": "float"},
                "low": {"type": "float"},
                "close": {"type": "float"},
                "volume": {"type": "long"},
                "market_cap": {"type": "long"},
                "daily_range": {"type": "float"},
                "daily_change_pct": {"type": "float"},
                "news_count": {"type": "integer"},
                "latest_news_date": {"type": "date"},
                "fetched_at_utc": {"type": "date"},
            }
        }
    }

    es.indices.create(index=index_name, body=mapping)
    logger.info(f"Created index: {index_name}")


def generate_actions(df: pd.DataFrame, index_name: str):
    """Generate bulk actions for Elasticsearch."""
    for _, row in df.iterrows():
        doc = row.to_dict()

        # Convert NaT/NaN to None for JSON serialization
        for key, value in doc.items():
            if pd.isna(value):
                doc[key] = None

        yield {
            "_index": index_name,
            "_id": f"{doc['symbol']}_{doc['date']}",
            "_source": doc,
        }


def index_stocks(es: Elasticsearch) -> None:
    """Read enriched stocks parquet and index to Elasticsearch."""
    parquet_path = USAGE_PATH / "stock_analysis" / "enriched_stocks.parquet"

    if not parquet_path.exists():
        logger.error(f"Enriched data not found: {parquet_path}")
        return

    # Read parquet with pandas
    df = pd.read_parquet(parquet_path)
    logger.info(f"Read {len(df)} stock records from parquet")

    # Convert datetime columns to ISO format strings
    for col in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            df[col] = df[col].dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    # Create index
    create_index(es, ELASTICSEARCH_INDEX)

    # Bulk index
    success, errors = bulk(es, generate_actions(df, ELASTICSEARCH_INDEX), raise_on_error=False)
    logger.info(f"Indexed {success} stock documents, {len(errors) if errors else 0} errors")

    if errors:
        for error in errors[:5]:
            logger.error(f"Error: {error}")


def create_news_index(es: Elasticsearch, index_name: str) -> None:
    """Create news index with mapping if it doesn't exist."""
    if es.indices.exists(index=index_name):
        logger.info(f"Index already exists: {index_name}")
        return

    mapping = {
        "mappings": {
            "properties": {
                "symbol": {"type": "keyword"},
                "title": {
                    "type": "text",
                    "fields": {"keyword": {"type": "keyword", "ignore_above": 512}}
                },
                "summary": {
                    "type": "text",
                    "fields": {"keyword": {"type": "keyword", "ignore_above": 1024}}
                },
                "provider": {"type": "keyword"},
                "category": {"type": "keyword"},
                "url": {"type": "keyword"},
                "image": {"type": "keyword"},
                "pub_date": {"type": "date"},
                "pub_date_utc": {"type": "date"},
                "fetched_at": {"type": "date"},
                "fetched_at_utc": {"type": "date"},
            }
        }
    }

    es.indices.create(index=index_name, body=mapping)
    logger.info(f"Created index: {index_name}")


def generate_news_actions(df: pd.DataFrame, index_name: str):
    """Generate bulk actions for news Elasticsearch index."""
    for _, row in df.iterrows():
        doc = row.to_dict()

        # Convert NaT/NaN to None for JSON serialization
        for key, value in doc.items():
            if pd.isna(value):
                doc[key] = None

        # Use uuid from news or generate unique id
        doc_id = doc.get("uuid", f"{doc['symbol']}_{doc.get('pub_date_utc', '')}")

        yield {
            "_index": index_name,
            "_id": doc_id,
            "_source": doc,
        }


def index_news(es: Elasticsearch) -> None:
    """Read news parquet and index to Elasticsearch."""
    parquet_path = NEWS_FORMATTED / "financial_news" / "news.parquet"

    if not parquet_path.exists():
        logger.warning(f"News data not found: {parquet_path}")
        return

    # Read parquet with pandas
    df = pd.read_parquet(parquet_path)
    logger.info(f"Read {len(df)} news records from parquet")

    # Convert datetime columns to ISO format strings
    for col in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            df[col] = df[col].dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    # Create news index
    create_news_index(es, ELASTICSEARCH_NEWS_INDEX)

    # Bulk index
    success, errors = bulk(es, generate_news_actions(df, ELASTICSEARCH_NEWS_INDEX), raise_on_error=False)
    logger.info(f"Indexed {success} news documents, {len(errors) if errors else 0} errors")

    if errors:
        for error in errors[:5]:
            logger.error(f"Error: {error}")


def main():
    """Main indexing function."""
    logger.info("Starting indexation to Elasticsearch")

    es = get_es_client()

    # Check connection
    if not es.ping():
        logger.error("Cannot connect to Elasticsearch")
        return

    logger.info(f"Connected to Elasticsearch at {ELASTICSEARCH_HOST}:{ELASTICSEARCH_PORT}")

    index_stocks(es)
    index_news(es)
    logger.info("Indexation complete")


if __name__ == "__main__":
    main()
