"""
Configuration settings for the Yahoo Finance Data Lake project.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Base paths
PROJECT_ROOT = Path(__file__).parent.parent
DATA_LAKE_PATH = Path(os.getenv("DATA_LAKE_PATH", PROJECT_ROOT / "data"))

# Data Lake layers
RAW_PATH = DATA_LAKE_PATH / "raw"
FORMATTED_PATH = DATA_LAKE_PATH / "formatted"
USAGE_PATH = DATA_LAKE_PATH / "usage"

# Data sources paths
YAHOO_FINANCE_RAW = RAW_PATH / "yahoo_finance"
NEWS_RAW = RAW_PATH / "news"

YAHOO_FINANCE_FORMATTED = FORMATTED_PATH / "yahoo_finance"
NEWS_FORMATTED = FORMATTED_PATH / "news"

# Stock symbols to track
STOCK_SYMBOLS = [
    "AAPL",   # Apple
    "GOOGL",  # Google
    "MSFT",   # Microsoft
    "AMZN",   # Amazon
    "META",   # Meta
    "TSLA",   # Tesla
    "NVDA",   # Nvidia
    "JPM",    # JPMorgan
    "V",      # Visa
    "WMT",    # Walmart
]

# API Keys
NEWS_API_KEY = os.getenv("NEWS_API_KEY", "")
FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY", "")

# Elasticsearch
ELASTICSEARCH_HOST = os.getenv("ELASTICSEARCH_HOST", "elasticsearch")
ELASTICSEARCH_PORT = int(os.getenv("ELASTICSEARCH_PORT", 9200))
ELASTICSEARCH_INDEX = "stock_analysis"
ELASTICSEARCH_NEWS_INDEX = "stock_news"
ELASTICSEARCH_PREDICTIONS_INDEX = "stock_predictions"

# Spark
SPARK_MASTER_URL = os.getenv("SPARK_MASTER_URL", "local[*]")
SPARK_APP_NAME = "YahooFinanceDataLake"
