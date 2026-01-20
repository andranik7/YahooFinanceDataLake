# Yahoo Finance Data Lake

Projet Big Data : pipeline de données financières avec ingestion, transformation et visualisation.

## Architecture

```
[Yahoo Finance API] ──┐                                    ┌──► [Elasticsearch]
                      ├──► [Raw] ──► [Formatted] ──► [Usage] ──► [Kibana Dashboard]
[News API] ───────────┘      │           │            │
                          (JSON)     (Parquet)    (Combined)
```

## Structure

```
data/
├── raw/                # Données brutes (JSON)
├── formatted/          # Données nettoyées (Parquet)
└── usage/              # Données combinées finales

scripts/
├── ingestion/          # Fetch API → Raw
├── formatting/         # Raw → Formatted (Spark)
├── combination/        # Join sources → Usage
└── indexing/           # Usage → Elasticsearch

airflow/dags/           # Orchestration du pipeline
spark/jobs/             # Jobs Spark
```

## Stack

| Composant | Outil |
|-----------|-------|
| Orchestration | Airflow |
| Processing | Spark |
| Stockage | Filesystem local (Parquet) |
| Indexation | Elasticsearch |
| Dashboard | Kibana |

## Installation

```bash
# Dépendances Python
poetry install

# Services Docker
docker-compose up -d
```

## Services

| Service | URL | Credentials |
|---------|-----|-------------|
| Airflow | http://localhost:8080 | admin/admin |
| Spark UI | http://localhost:8081 | - |
| Elasticsearch | http://localhost:9200 | - |
| Kibana | http://localhost:5601 | - |

## Arrêt

```bash
docker-compose down           # Stopper les services
docker-compose down -v        # Stopper + supprimer les volumes
```

## Sources de données

1. **Yahoo Finance** (`yfinance`) - Cours boursiers, volumes, historiques
2. **News API** - Actualités financières

## Pipeline

```bash
poetry run ingest-stocks    # Ingestion Yahoo Finance
poetry run ingest-news      # Ingestion News
poetry run format-data      # Transformation Parquet
poetry run combine-data     # Jointure des sources
poetry run index-data       # Indexation Elasticsearch
```
