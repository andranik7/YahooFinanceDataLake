"""
Airflow DAG for Yahoo Finance Data Lake Pipeline.
Orchestrates: Ingestion → Formatting → Combination → Indexation

Uses SparkSubmitOperator for Spark jobs.
"""

from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.empty import EmptyOperator
from airflow.providers.apache.spark.operators.spark_submit import SparkSubmitOperator

import sys
from pathlib import Path

# Add project root to path for imports (works in Docker container)
AIRFLOW_HOME = Path("/opt/airflow")
sys.path.insert(0, str(AIRFLOW_HOME))


# Default arguments for the DAG
default_args = {
    "owner": "airflow",
    "depends_on_past": False,
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}


def run_ingest_stocks():
    """Task: Ingest stock data from Yahoo Finance."""
    from scripts.ingestion.yahoo_stocks import main
    main()


def run_ingest_news():
    """Task: Ingest news data from Finnhub API."""
    from scripts.ingestion.finnhub_news import main
    main()


def run_index_data():
    """Task: Index data to Elasticsearch."""
    from scripts.indexing.to_elasticsearch import main
    main()


# Define the DAG
with DAG(
    dag_id="yahoo_finance_pipeline",
    default_args=default_args,
    description="ETL pipeline for Yahoo Finance data",
    schedule_interval="@daily",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["yahoo_finance", "etl", "data_lake"],
) as dag:

    # Start task
    start = EmptyOperator(task_id="start")

    # Ingestion tasks (can run in parallel) - use Python as no Java needed
    ingest_stocks = PythonOperator(
        task_id="ingest_stocks",
        python_callable=run_ingest_stocks,
    )

    ingest_news = PythonOperator(
        task_id="ingest_news",
        python_callable=run_ingest_news,
    )

    # Spark tasks using SparkSubmitOperator
    # Scripts are mounted in Airflow at /opt/airflow/scripts
    format_data = SparkSubmitOperator(
        task_id="format_data",
        application="/opt/airflow/scripts/formatting/format_to_parquet.py",
        conn_id="spark_default",
        deploy_mode="client",
        verbose=True,
        conf={
            "spark.master": "spark://spark-master:7077",
        },
    )

    combine_data = SparkSubmitOperator(
        task_id="combine_data",
        application="/opt/airflow/scripts/combination/combine_sources.py",
        conn_id="spark_default",
        deploy_mode="client",
        verbose=True,
        conf={
            "spark.master": "spark://spark-master:7077",
        },
    )

    # Indexation task - use Python as no Spark needed
    index_data = PythonOperator(
        task_id="index_data",
        python_callable=run_index_data,
    )

    # End task
    end = EmptyOperator(task_id="end")

    # Define task dependencies
    start >> [ingest_stocks, ingest_news]
    [ingest_stocks, ingest_news] >> format_data
    format_data >> combine_data >> index_data >> end
