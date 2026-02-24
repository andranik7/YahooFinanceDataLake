"""
Formatting script: transforms raw JSON data to Parquet format using Spark.
Applies normalization (dates in UTC, clean column names).
"""

import sys
from pathlib import Path

from pyspark.sql import SparkSession
from pyspark.sql.functions import col, to_utc_timestamp, lit
from pyspark.sql.types import StructType, StructField, StringType, DoubleType, LongType
from loguru import logger

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from config.settings import (
    YAHOO_FINANCE_RAW,
    YAHOO_FINANCE_FORMATTED,
    NEWS_RAW,
    NEWS_FORMATTED,
    SPARK_APP_NAME,
    SPARK_MASTER_URL,
)


def get_spark_session() -> SparkSession:
    """Create or get Spark session."""
    return (
        SparkSession.builder
        .appName(SPARK_APP_NAME)
        .config("spark.sql.legacy.timeParserPolicy", "LEGACY")
        .getOrCreate()
    )


def format_stocks(spark: SparkSession) -> None:
    """Format stock data from JSON to Parquet."""
    raw_path = YAHOO_FINANCE_RAW / "stocks"

    if not raw_path.exists():
        logger.warning(f"No raw stocks data found at {raw_path}")
        return

    # Find all JSON files in date partitions
    json_files = list(raw_path.glob("*/stocks.json"))
    if not json_files:
        logger.warning("No stocks JSON files found")
        return

    logger.info(f"Processing {len(json_files)} stocks files")

    # Read all JSON files (multiLine for pretty-printed JSON arrays)
    df = spark.read.option("multiLine", "true").json([str(f) for f in json_files])

    # Normalize: ensure consistent types and UTC timestamps
    df_normalized = (
        df.withColumn("open", col("open").cast(DoubleType()))
        .withColumn("high", col("high").cast(DoubleType()))
        .withColumn("low", col("low").cast(DoubleType()))
        .withColumn("close", col("close").cast(DoubleType()))
        .withColumn("volume", col("volume").cast(LongType()))
        .withColumn("fetched_at_utc", to_utc_timestamp(col("fetched_at"), "UTC"))
    )

    # Write to Parquet
    output_path = YAHOO_FINANCE_FORMATTED / "stocks"
    output_path.mkdir(parents=True, exist_ok=True)

    df_normalized.write.mode("overwrite").parquet(str(output_path / "stocks.parquet"))
    logger.info(f"Saved {df_normalized.count()} stock records to {output_path}")


def format_company_info(spark: SparkSession) -> None:
    """Format company info data from JSON to Parquet."""
    raw_path = YAHOO_FINANCE_RAW / "company_info"

    if not raw_path.exists():
        logger.warning(f"No raw company_info data found at {raw_path}")
        return

    json_files = list(raw_path.glob("*/company_info.json"))
    if not json_files:
        logger.warning("No company_info JSON files found")
        return

    logger.info(f"Processing {len(json_files)} company_info files")

    df = spark.read.option("multiLine", "true").json([str(f) for f in json_files])

    # Normalize
    df_normalized = (
        df.withColumn("market_cap", col("market_cap").cast(LongType()))
        .withColumn("fetched_at_utc", to_utc_timestamp(col("fetched_at"), "UTC"))
    )

    output_path = YAHOO_FINANCE_FORMATTED / "company_info"
    output_path.mkdir(parents=True, exist_ok=True)

    df_normalized.write.mode("overwrite").parquet(str(output_path / "company_info.parquet"))
    logger.info(f"Saved {df_normalized.count()} company records to {output_path}")


def format_news(spark: SparkSession) -> None:
    """Format news data from JSON to Parquet."""
    raw_path = NEWS_RAW / "financial_news"

    if not raw_path.exists():
        logger.warning(f"No raw news data found at {raw_path}")
        return

    json_files = list(raw_path.glob("*/news.json"))
    if not json_files:
        logger.warning("No news JSON files found")
        return

    logger.info(f"Processing {len(json_files)} news files")

    df = spark.read.option("multiLine", "true").json([str(f) for f in json_files])

    # Normalize: parse pub_date to timestamp
    df_normalized = (
        df.withColumn("pub_date_utc", to_utc_timestamp(col("pub_date"), "UTC"))
        .withColumn("fetched_at_utc", to_utc_timestamp(col("fetched_at"), "UTC"))
    )

    # Filter out invalid dates (keep only dates from 2020 onwards)
    df_normalized = df_normalized.filter(col("pub_date_utc") >= "2020-01-01")
    logger.info(f"Filtered to {df_normalized.count()} news with valid dates (>= 2020)")

    output_path = NEWS_FORMATTED / "financial_news"
    output_path.mkdir(parents=True, exist_ok=True)

    df_normalized.write.mode("overwrite").parquet(str(output_path / "news.parquet"))
    logger.info(f"Saved news records to {output_path}")


def main():
    """Main formatting function."""
    logger.info("Starting formatting: JSON → Parquet")

    spark = get_spark_session()
    spark.sparkContext.setLogLevel("WARN")

    try:
        format_stocks(spark)
        format_company_info(spark)
        format_news(spark)
        logger.info("Formatting complete")
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
