# Yahoo Finance Data Lake

Pipeline Big Data de bout en bout : ingestion, transformation Spark, prédiction SARIMAX avec analyse de sentiment, et visualisation Kibana.

**Symboles suivis** : AAPL, GOOGL, MSFT, AMZN, META, TSLA, NVDA, JPM, V, WMT

## Architecture

```
Sources                 Data Lake                              ML              Exposition
┌──────────────┐     ┌─────────┐     ┌───────────┐     ┌──────────┐     ┌─────────────┐     ┌────────────┐
│Yahoo Finance │────►│   RAW   │────►│ FORMATTED │────►│  USAGE   │────►│ PREDICTION  │────►│Elasticsearch│
│  (yfinance)  │     │ (JSON)  │     │ (Parquet) │     │(Parquet) │     │  (SARIMAX)  │     │  + Kibana  │
├──────────────┤     └─────────┘     └───────────┘     └──────────┘     └─────────────┘     └────────────┘
│ Finnhub API  │     Partitionné     Types validés     Jointures +      Sentiment comme
│(news + VADER)│     par date        Timestamps UTC    Métriques         variable exogène
└──────────────┘                                       dérivées          IC 95%
```

## Stack technique

| Composant | Technologie | Version |
|-----------|-------------|---------|
| Orchestration | Apache Airflow | 2.7.3 |
| Transformation | Apache Spark | 3.5.0 |
| Prédiction | statsmodels (SARIMAX) | - |
| Analyse de sentiment | VADER | 3.3.2 |
| Indexation | Elasticsearch | 8.11.0 |
| Visualisation | Kibana | 8.11.0 |
| Base métadonnées | PostgreSQL | 15 |
| Conteneurisation | Docker Compose | - |

## Prérequis

- Docker & Docker Compose
- Clé API Finnhub gratuite ([finnhub.io](https://finnhub.io/))

## Démarrage rapide

```bash
# Cloner et configurer
git clone <repository>
cd YahooFinance
cp .env.example .env
# Éditer .env : FINNHUB_API_KEY=votre_cle_ici

# Lancer
docker-compose build
docker-compose up -d

# Vérifier
docker-compose ps
```

Les dashboards Kibana sont importés automatiquement au démarrage.

## Services

| Service | URL | Identifiants |
|---------|-----|--------------|
| Airflow | http://localhost:8080 | admin / admin |
| Spark UI | http://localhost:8081 | - |
| Elasticsearch | http://localhost:9200 | - |
| Kibana | http://localhost:5601 | - |

## Pipeline Airflow

```
start → [ingest_stocks | ingest_news] → format_data → combine_data → predict_arima → index_data → end
           (parallèle)                    (Spark)       (Spark)        (SARIMAX)        (ES)
```

| Tâche | Opérateur | Description | Durée |
|-------|-----------|-------------|-------|
| `ingest_stocks` | PythonOperator | Cours + infos entreprises via yfinance (5 ans) | ~30s |
| `ingest_news` | PythonOperator | Actualités Finnhub + sentiment VADER (12 mois) | ~3 min |
| `format_data` | BashOperator | spark-submit : JSON → Parquet | ~1 min |
| `combine_data` | BashOperator | spark-submit : jointures + métriques | ~1 min |
| `predict_arima` | PythonOperator | SARIMAX + sentiment par symbole | ~30s |
| `index_data` | PythonOperator | Indexation bulk (3 index ES) | ~1 min |

**Exécution** : Airflow → activer le DAG `yahoo_finance_pipeline` → Trigger DAG. Planification : `@daily`.

L'indexation est incrémentale (mise à jour par `symbol_date` / `uuid`). Les prédictions sont recalculées intégralement à chaque exécution.

## Structure du projet

```
YahooFinance/
├── config/settings.py                # Configuration centralisée
├── data/
│   ├── raw/                          # JSON partitionné par date
│   │   ├── yahoo_finance/
│   │   └── news/
│   ├── formatted/                    # Parquet normalisé
│   └── usage/
│       ├── stock_analysis/           # Données enrichies
│       └── predictions/              # Prédictions SARIMAX
├── scripts/
│   ├── ingestion/
│   │   ├── yahoo_stocks.py           # Collecte cours + company info
│   │   └── finnhub_news.py           # Collecte news + sentiment VADER
│   ├── formatting/format_to_parquet.py   # Spark : JSON → Parquet
│   ├── combination/combine_sources.py    # Spark : jointures + métriques
│   ├── prediction/arima_forecast.py      # SARIMAX + sentiment
│   ├── indexing/to_elasticsearch.py      # Indexation ES (3 index)
│   └── init_kibana.sh                    # Import auto dashboards
├── kibana/kibana_saved_objects.ndjson # Dashboards exportés
├── airflow/dags/yahoo_finance_pipeline.py
├── docker-compose.yml
└── Dockerfile.airflow                # Image custom (Java + Spark + statsmodels)
```

## Data Lake

| Couche | Format | Contenu |
|--------|--------|---------|
| Raw | JSON | Données brutes des APIs, partitionnées par date |
| Formatted | Parquet | Types validés, timestamps UTC, compression Snappy |
| Usage | Parquet | Jointures (cours + entreprises + news), métriques dérivées |

**Métriques dérivées** : `daily_range` (high - low), `daily_change_pct` ((close - open) / open × 100)

## Analyse de sentiment (VADER)

Chaque article (titre + résumé) est analysé lors de l'ingestion :
- Score `compound` entre -1.0 et +1.0
- Labels : `positive` (≥ 0.05), `negative` (≤ -0.05), `neutral` (entre les deux)

## Prédiction SARIMAX

| Paramètre | Valeur |
|-----------|--------|
| Ordre ARIMA | (2, 1, 2) |
| Ordre saisonnier | (1, 1, 1, 5) — cycle hebdomadaire |
| Variable exogène | Sentiment quotidien agrégé par symbole |
| Entraînement | 252 derniers jours (~1 an) |
| Horizon | 30 jours ouvrés |
| Intervalle de confiance | 95% |

Le sentiment des 30 derniers jours est moyenné pour projeter les jours futurs. Les 90 derniers jours de données réelles sont inclus dans la sortie pour la continuité visuelle.

## Index Elasticsearch

### `stock_analysis` (~12 800 docs)

| Champ | Type | Description |
|-------|------|-------------|
| symbol | keyword | Symbole boursier |
| name | text | Nom de l'entreprise |
| sector, industry | keyword | Secteur et industrie |
| date | date | Date du cours |
| open, high, low, close | float | Prix OHLC |
| volume | long | Volume échangé |
| market_cap | long | Capitalisation boursière |
| daily_range | float | Amplitude journalière |
| daily_change_pct | float | Variation journalière % |
| news_count | integer | Nombre d'articles |

### `stock_news` (~21 000 docs)

| Champ | Type | Description |
|-------|------|-------------|
| symbol | keyword | Symbole associé |
| title, summary | text | Titre et résumé (full-text search) |
| provider | keyword | Éditeur |
| category | keyword | Catégorie |
| pub_date_utc | date | Date de publication UTC |
| sentiment_score | float | Score VADER (-1.0 à 1.0) |
| sentiment_label | keyword | positive / negative / neutral |

### `stock_predictions` (~1 200 docs)

| Champ | Type | Description |
|-------|------|-------------|
| symbol | keyword | Symbole boursier |
| date | date | Date de la valeur |
| predicted_close | float | Cours prédit ou réel |
| confidence_lower, confidence_upper | float | Bornes IC 95% |
| sentiment_score | float | Sentiment utilisé |
| type | keyword | `actual` ou `forecast` |

## Dashboard Kibana

Visualisations importées automatiquement :

| Visualisation | Description | Index |
|---------------|-------------|-------|
| Évolution des cours | Prix de clôture par symbole sur 90 jours | `stock_analysis` |
| Tableau des actualités | News triées par date avec scores de sentiment | `stock_news` |
| Prédictions SARIMAX | Cours réels + prédictions 30j + bandes de confiance 95% | `stock_predictions` |
| Top/Flop du jour | Classement des symboles par variation journalière (cours, volume) | `stock_analysis` |
| Capitalisation par secteur | Treemap de la capitalisation boursière par secteur et symbole | `stock_analysis` |
| Sentiment moyen par symbole | Bar chart horizontal du score de sentiment moyen par action | `stock_news` |
| Distribution des sentiments | Donut chart positif / négatif / neutre | `stock_news` |

### Exporter le dashboard après modifications

```bash
curl -s -X POST "http://localhost:5601/api/saved_objects/_export" \
  -H "kbn-xsrf: true" \
  -H "Content-Type: application/json" \
  -d '{"type": ["dashboard", "visualization", "lens", "index-pattern", "search"], "includeReferencesDeep": true}' \
  -o kibana/kibana_saved_objects.ndjson
```

## Arrêt

```bash
docker-compose down           # Stopper (données conservées)
docker-compose down -v        # Stopper + supprimer les volumes (perte des données ES)
```

> Avec `-v`, les données Elasticsearch sont perdues. Les dashboards seront réimportés au redémarrage, mais les données doivent être réingérées via le DAG.
