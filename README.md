# Yahoo Finance Data Lake

Projet Big Data : architecture complète de collecte, transformation et visualisation de données financières.

## Description

Ce projet implémente un Data Lake pour l'analyse boursière avec :
- Ingestion de données Yahoo Finance (cours, volumes, infos entreprises)
- Collecte d'actualités financières
- Transformation et enrichissement avec Apache Spark
- Indexation dans Elasticsearch
- Visualisation via dashboards Kibana

**Symboles suivis** : AAPL, GOOGL, MSFT, AMZN, META, TSLA, NVDA, JPM, V, WMT

## Architecture

```
┌─────────────────┐     ┌─────────┐     ┌─────────────┐     ┌─────────┐     ┌───────────────┐
│  Yahoo Finance  │────►│   RAW   │────►│  FORMATTED  │────►│  USAGE  │────►│ Elasticsearch │
│  (yfinance)     │     │  (JSON) │     │  (Parquet)  │     │(Parquet)│     │    Kibana     │
└─────────────────┘     └─────────┘     └─────────────┘     └─────────┘     └───────────────┘
                              │               │                  │
                         Partitionné     Normalisé UTC      Jointures
                         par date        Types validés      Métriques
```

## Prérequis

- Docker & Docker Compose
- Python 3.10+
- Poetry (optionnel, pour exécution locale)

## Structure du projet

```
YahooFinance/
├── config/
│   └── settings.py         # Configuration centralisée
├── data/
│   ├── raw/                # Données brutes (JSON partitionné par date)
│   │   ├── yahoo_finance/
│   │   └── news/
│   ├── formatted/          # Données normalisées (Parquet)
│   └── usage/              # Données enrichies finales
├── scripts/
│   ├── ingestion/          # Collecte des données
│   │   ├── yahoo_stocks.py # Stocks + Company Info
│   │   └── news.py         # Actualités
│   ├── formatting/         # Transformation Spark
│   ├── combination/        # Jointure des sources
│   └── indexing/           # Indexation Elasticsearch
├── airflow/dags/           # Orchestration du pipeline
│   └── yahoo_finance_pipeline.py
├── docs/
│   └── rapport.tex         # Documentation LaTeX
├── docker-compose.yml
└── Dockerfile.airflow      # Image Airflow avec Java/Spark
```

## Stack technique

| Composant | Technologie | Version |
|-----------|-------------|---------|
| Orchestration | Apache Airflow | 2.7.3 |
| Transformation | Apache Spark | 3.5.0 |
| Indexation | Elasticsearch | 8.11.0 |
| Visualisation | Kibana | 8.11.0 |
| Base métadonnées | PostgreSQL | 15 |
| Runtime Java | OpenJDK | 11 |

> Airflow utilise une image Docker custom (`Dockerfile.airflow`) avec Java et PySpark pour soumettre les jobs Spark via `SparkSubmitOperator`.

## Installation

```bash
# 1. Cloner le projet
git clone <repository>
cd YahooFinance

# 2. Construire l'image Airflow (avec Java pour Spark)
docker-compose build

# 3. Démarrer les services Docker
docker-compose up -d

# 4. Vérifier que les services sont up
docker-compose ps

# 5. Configurer la connexion Spark dans Airflow
docker-compose exec airflow airflow connections add spark_default \
    --conn-type spark \
    --conn-host spark://spark-master \
    --conn-port 7077
```

> **Note** : L'installation locale via Poetry (`poetry install`) est optionnelle, pour le développement uniquement.

## Services

| Service | URL | Credentials |
|---------|-----|-------------|
| Airflow | http://localhost:8080 | admin/admin |
| Spark UI | http://localhost:8081 | - |
| Elasticsearch | http://localhost:9200 | - |
| Kibana | http://localhost:5601 | - |

## Orchestration Airflow

Le pipeline est orchestré via un DAG Airflow qui enchaîne automatiquement toutes les étapes.

### DAG : `yahoo_finance_pipeline`

```
start → [ingest_stocks, ingest_news] → format_data → combine_data → index_data → end
              (parallèle)                (Spark)       (Spark)
```

| Task | Opérateur | Description |
|------|-----------|-------------|
| ingest_stocks | PythonOperator | Collecte cours + infos entreprises |
| ingest_news | PythonOperator | Collecte actualités |
| format_data | SparkSubmitOperator | Conversion JSON → Parquet |
| combine_data | SparkSubmitOperator | Jointure + métriques |
| index_data | PythonOperator | Indexation Elasticsearch |

### Exécution

1. Accéder à Airflow : http://localhost:8080 (admin/admin)
2. Activer le DAG `yahoo_finance_pipeline`
3. Déclencher manuellement avec "Trigger DAG" ou attendre l'exécution planifiée (@daily)

> **Indexation incrémentale** : Le pipeline ajoute les nouvelles données sans supprimer l'historique. Les documents sont mis à jour via leur identifiant unique (`symbol_date` pour les stocks, `uuid` pour les news).

## Pipeline manuel (optionnel)

Pour exécuter les étapes individuellement en local :

```bash
# 1. Ingestion (collecte des données Yahoo Finance)
poetry run ingest-stocks    # Stocks + Company Info (12 mois d'historique)
poetry run ingest-news      # Actualités financières

# 2. Transformation (JSON → Parquet avec Spark)
poetry run format-data

# 3. Combinaison (jointure + métriques dérivées)
poetry run combine-data

# 4. Indexation (Elasticsearch)
poetry run index-data
```

## Schéma des données

### Index `stock_analysis` (données enrichies)

| Champ | Type | Description |
|-------|------|-------------|
| symbol | keyword | Symbole boursier (AAPL, GOOGL...) |
| name | text | Nom de l'entreprise |
| sector | keyword | Secteur d'activité |
| industry | keyword | Industrie |
| date | date | Date du cours |
| open | float | Prix d'ouverture |
| high | float | Prix le plus haut |
| low | float | Prix le plus bas |
| close | float | Prix de clôture |
| volume | long | Volume échangé |
| market_cap | long | Capitalisation boursière |
| daily_range | float | Amplitude (high - low) |
| daily_change_pct | float | Variation journalière % |
| news_count | integer | Nombre d'articles |

### Index `stock_news` (actualités)

| Champ | Type | Description |
|-------|------|-------------|
| symbol | keyword | Symbole associé |
| title | text | Titre de l'article |
| publisher | keyword | Éditeur |
| pub_date_utc | date | Date de publication |
| link | keyword | URL de l'article |

## Visualisation Kibana

### 1. Créer les Data Views

1. Aller sur http://localhost:5601
2. Stack Management → Data Views → Create data view
3. Créer deux data views :
   - `stock_analysis` avec timestamp `date`
   - `stock_news` avec timestamp `pub_date_utc`

### 2. Créer un dashboard

1. Analytics → Dashboard → Create
2. Ajouter des visualisations :
   - **Line chart** : Évolution du prix de clôture
   - **Bar chart** : Volume par symbole
   - **Pie chart** : Répartition par secteur
   - **Data table** : Dernières news

### Exemple : Graphique prix AAPL

1. Create visualization → Lens
2. Data view : `stock_analysis`
3. Horizontal axis : `date`
4. Vertical axis : `Average of close`
5. Filter : `symbol: AAPL`
6. Time range : Last 12 months

## Arrêt

```bash
docker-compose down           # Stopper les services
docker-compose down -v        # Stopper + supprimer les volumes
```

## Documentation

Le rapport technique complet est disponible dans `docs/rapport.tex`. Pour générer le PDF :

```bash
cd docs
pdflatex rapport.tex
pdflatex rapport.tex  # 2ème fois pour la table des matières
```
