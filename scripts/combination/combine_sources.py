"""
Combination script: joins stocks, company info, and news data.
Creates enriched dataset in the usage layer.
"""

import sys
from pathlib import Path

from pyspark.sql import SparkSession
from pyspark.sql.functions import col, count, max as spark_max
from loguru import logger

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from config.settings import (
    YAHOO_FINANCE_FORMATTED,
    NEWS_FORMATTED,
    USAGE_PATH,
    SPARK_APP_NAME,
    SPARK_MASTER_URL,
)


def get_spark_session() -> SparkSession:
    """Create or get Spark session."""
    return (
        SparkSession.builder
        .appName(SPARK_APP_NAME)
        .getOrCreate()
    )


def combine_sources(spark: SparkSession) -> None:
    """Combine stocks, company info, and news into enriched dataset."""

    # Paths
    stocks_path = YAHOO_FINANCE_FORMATTED / "stocks" / "stocks.parquet"
    company_path = YAHOO_FINANCE_FORMATTED / "company_info" / "company_info.parquet"
    news_path = NEWS_FORMATTED / "financial_news" / "news.parquet"

    # Check paths exist
    if not stocks_path.exists():
        logger.error(f"Stocks data not found: {stocks_path}")
        return
    if not company_path.exists():
        logger.error(f"Company data not found: {company_path}")
        return
    if not news_path.exists():
        logger.error(f"News data not found: {news_path}")
        return

    # Read parquet files
    logger.info("Reading formatted data...")
    stocks_df = spark.read.parquet(str(stocks_path))
    company_df = spark.read.parquet(str(company_path))
    news_df = spark.read.parquet(str(news_path))

    # Aggregate news per symbol
    news_agg = (
        news_df.groupBy("symbol")
        .agg(
            count("*").alias("news_count"),
            spark_max("pub_date_utc").alias("latest_news_date")
        )
    )

    # Join stocks with company info
    stocks_enriched = stocks_df.join(
        company_df.select("symbol", "name", "sector", "industry", "market_cap"),
        on="symbol",
        how="left"
    )

    # Join with news aggregates
    final_df = stocks_enriched.join(
        news_agg,
        on="symbol",
        how="left"
    )

    # Add derived metrics
    final_df = final_df.withColumn(
        "daily_range", col("high") - col("low")
    ).withColumn(
        "daily_change_pct", ((col("close") - col("open")) / col("open")) * 100
    )

    # Select final columns
    final_df = final_df.select(
        "symbol",
        "name",
        "sector",
        "industry",
        "date",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "market_cap",
        "daily_range",
        "daily_change_pct",
        "news_count",
        "latest_news_date",
        "fetched_at_utc"
    )

    # Write to usage layer
    output_path = USAGE_PATH / "stock_analysis"
    output_path.mkdir(parents=True, exist_ok=True)

    final_df.write.mode("overwrite").parquet(str(output_path / "enriched_stocks.parquet"))

    logger.info(f"Saved {final_df.count()} enriched records to {output_path}")

    # Show sample
    logger.info("Sample data:")
    final_df.show(5, truncate=False)


def main():
    """Main combination function."""
    logger.info("Starting combination: joining data sources")

    spark = get_spark_session()
    spark.sparkContext.setLogLevel("WARN")

    try:
        combine_sources(spark)
        logger.info("Combination complete")
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
