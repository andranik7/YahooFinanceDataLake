"""
Airflow DAG for Yahoo Finance Data Lake Pipeline.
Orchestrates: Ingestion → Formatting → Combination → Indexation

Uses SparkSubmitOperator for Spark jobs.
"""

from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.bash import BashOperator
from airflow.operators.empty import EmptyOperator

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


def run_predict_arima():
    """Task: Run ARIMA predictions on stock data."""
    from scripts.prediction.arima_forecast import main
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

    # Spark tasks using BashOperator to run spark-submit directly
    # Scripts are mounted in Airflow at /opt/airflow/scripts
    format_data = BashOperator(
        task_id="format_data",
        bash_command="spark-submit --master spark://spark-master:7077 --deploy-mode client /opt/airflow/scripts/formatting/format_to_parquet.py",
)

    combine_data = BashOperator(
        task_id="combine_data",
        bash_command="spark-submit --master spark://spark-master:7077 --deploy-mode client /opt/airflow/scripts/combination/combine_sources.py",
)
    # ARIMA prediction task
    predict_arima = PythonOperator(
        task_id="predict_arima",
        python_callable=run_predict_arima,
    )

    # Indexation task - use Python as no Spark needed
    index_data = PythonOperator(
        task_id="index_data",
        python_callable=run_index_data,
    )

    # End task
    end = EmptyOperator(task_id="end")

    # Define task dependencies
    # To skip ingest_news for testing, set SKIP_NEWS=true in Airflow env
    start >> [ingest_stocks, ingest_news]
    [ingest_stocks, ingest_news] >> format_data
    format_data >> combine_data >> predict_arima >> index_data >> end
