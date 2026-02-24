# Yahoo Finance Data Lake

Projet Big Data : architecture complète de collecte, transformation, prédiction et visualisation de données financières.

## Description

Ce projet implémente un Data Lake pour l'analyse boursière avec :
- Ingestion de données Yahoo Finance (cours, volumes, infos entreprises) - **5 ans d'historique**
- Collecte d'actualités financières via **Finnhub API** (12 mois d'historique)
- **Analyse de sentiment** automatique avec VADER
- Transformation et enrichissement avec Apache Spark
- **Prédiction des cours** avec SARIMAX + sentiment des actualités comme variable exogène
- Indexation dans Elasticsearch
- Visualisation via dashboards Kibana (avec import automatique)

**Symboles suivis** : AAPL, GOOGL, MSFT, AMZN, META, TSLA, NVDA, JPM, V, WMT

## Architecture

```
┌─────────────────┐
│  Yahoo Finance  │──┐
│  (yfinance)     │  │
└─────────────────┘  │     ┌─────────┐     ┌─────────────┐     ┌─────────┐     ┌───────────────┐     ┌───────────────┐
                     ├────►│   RAW   │────►│  FORMATTED  │────►│  USAGE  │────►│  PREDICTION   │────►│ Elasticsearch │
┌─────────────────┐  │     │  (JSON) │     │  (Parquet)  │     │(Parquet)│     │   (SARIMAX    │     │    Kibana     │
│  Finnhub API    │──┘     └─────────┘     └─────────────┘     └─────────┘     │ + Sentiment)  │     └───────────────┘
│  (news + VADER) │              │               │                  │           └───────┬───────┘
└─────────────────┘         Partitionné     Normalisé UTC      Jointures              │
                            par date        Types validés      Métriques        Croisement cours
                                            + Sentiment                       + sentiment des news
                                                                             Bandes de confiance 95%
```

## Prérequis

- Docker & Docker Compose
- Python 3.10+
- Poetry (optionnel, pour exécution locale)

## Structure du projet

```
YahooFinance/
├── config/
│   └── settings.py             # Configuration centralisée
├── data/
│   ├── raw/                    # Données brutes (JSON partitionné par date)
│   │   ├── yahoo_finance/
│   │   └── news/
│   ├── formatted/              # Données normalisées (Parquet)
│   └── usage/
│       ├── stock_analysis/     # Données enrichies finales
│       └── predictions/        # Prédictions Holt-Winters (Parquet)
├── scripts/
│   ├── ingestion/              # Collecte des données
│   │   ├── yahoo_stocks.py     # Stocks + Company Info
│   │   └── finnhub_news.py     # Actualités Finnhub + sentiment VADER
│   ├── formatting/             # Transformation Spark (JSON → Parquet)
│   │   └── format_to_parquet.py
│   ├── combination/            # Jointure des sources
│   │   └── combine_sources.py
│   ├── prediction/             # Machine Learning
│   │   └── arima_forecast.py   # Prédictions SARIMAX + sentiment
│   ├── indexing/               # Indexation Elasticsearch
│   │   └── to_elasticsearch.py
│   ├── init_kibana.sh          # Import auto des dashboards
│   └── kibana_export.py        # Export/Import des dashboards
├── kibana/
│   └── kibana_saved_objects.ndjson  # Dashboards exportés
├── airflow/dags/               # Orchestration du pipeline
│   └── yahoo_finance_pipeline.py
├── docker-compose.yml
└── Dockerfile.airflow          # Image Airflow avec Java/Spark/statsmodels
```

## Stack technique

| Composant | Technologie | Version |
|-----------|-------------|---------|
| Orchestration | Apache Airflow | 2.7.3 |
| Transformation | Apache Spark | 3.5.0 |
| Prédiction | statsmodels (SARIMAX) | - |
| Indexation | Elasticsearch | 8.11.0 |
| Visualisation | Kibana | 8.11.0 |
| Base métadonnées | PostgreSQL | 15 |
| Runtime Java | OpenJDK | 11 |
| Analyse sentiment | VADER | 3.3.2 |
| API News | Finnhub | - |

> Airflow utilise une image Docker custom (`Dockerfile.airflow`) avec Java, PySpark et statsmodels pour exécuter les jobs Spark et les prédictions.

## Installation

```bash
# 1. Cloner le projet
git clone <repository>
cd YahooFinance

# 2. Configurer la clé API Finnhub
cp .env.example .env
# Éditer .env et ajouter votre clé Finnhub (gratuite sur https://finnhub.io/)
# FINNHUB_API_KEY=votre_cle_ici

# 3. Construire l'image Airflow (avec Java pour Spark)
docker-compose build

# 4. Démarrer les services Docker
docker-compose up -d

# 5. Vérifier que les services sont up
docker-compose ps
```

> **Note** : Les dashboards Kibana sont automatiquement importés au démarrage via `init_kibana.sh`.

> **Note** : L'installation locale via Poetry (`poetry install`) est optionnelle, pour le développement uniquement.

> **Note** : La connexion Spark est configurée directement dans le DAG, aucune connexion Airflow n'est requise.

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
start → [ingest_stocks, ingest_news] → format_data → combine_data → predict_arima → index_data → end
              (parallèle)                (Spark)       (Spark)      (Holt-Winters)     (ES)
```

| Task | Opérateur | Description |
|------|-----------|-------------|
| `ingest_stocks` | PythonOperator | Collecte cours + infos entreprises (5 ans d'historique) |
| `ingest_news` | PythonOperator | Collecte 12 mois de news via Finnhub (~3 min, 120 appels API) |
| `format_data` | BashOperator | Conversion JSON → Parquet (spark-submit) |
| `combine_data` | BashOperator | Jointure stocks + company info + news agrégées (spark-submit) |
| `predict_arima` | PythonOperator | Prédictions SARIMAX + sentiment des news sur 30 jours |
| `index_data` | PythonOperator | Indexation dans Elasticsearch (3 index) |

### Exécution

1. Accéder à Airflow : http://localhost:8080 (admin/admin)
2. Activer le DAG `yahoo_finance_pipeline`
3. Déclencher manuellement avec "Trigger DAG" ou attendre l'exécution planifiée (@daily)

> **Indexation incrémentale** : Le pipeline ajoute les nouvelles données sans supprimer l'historique. Les documents sont mis à jour via leur identifiant unique (`symbol_date` pour les stocks, `uuid` pour les news).

## Prédiction des cours (Machine Learning)

Le projet intègre une phase de prédiction des cours financiers utilisant **SARIMAX** avec le **sentiment des actualités** comme variable exogène. Le modèle croise ainsi l'analyse de séries temporelles avec le NLP (sentiment analysis) pour produire des prédictions plus contextualisées.

### Modèle utilisé

**SARIMAX** (Seasonal AutoRegressive Integrated Moving Average with eXogenous variables) via `statsmodels.tsa.statespace.sarimax.SARIMAX` :
- **Ordre ARIMA** : (2, 1, 2) — composantes auto-régressives et moyenne mobile
- **Saisonnalité** : (1, 1, 1, 5) — cycle hebdomadaire de 5 jours ouvrés
- **Variable exogène** : score de sentiment agrégé quotidien par symbole (issu de VADER)
- **Entraînement** : sur les 252 derniers jours de trading (~1 an)
- **Horizon** : 30 jours ouvrés de prédiction

### Fonctionnement

1. Les actualités financières sont agrégées par jour et par symbole pour obtenir un **score de sentiment moyen quotidien**
2. Pour chaque symbole, le modèle SARIMAX est entraîné sur la série temporelle du prix de clôture (`close`) avec le sentiment comme variable exogène
3. Pour les jours futurs, le **sentiment moyen des 30 derniers jours** est utilisé comme hypothèse de projection
4. Les **bandes de confiance à 95%** sont calculées automatiquement par SARIMAX
5. Les 90 derniers jours de données réelles sont inclus pour assurer la continuité visuelle sur le dashboard

### Impact du sentiment

Le sentiment des news influence directement les prédictions :
- Un sentiment **positif** (ex: AMZN ~0.41) ajuste les prédictions à la hausse
- Un sentiment **négatif** ou **neutre** (ex: TSLA ~0.10) produit des prédictions plus conservatrices
- Les jours sans actualités reçoivent un sentiment neutre (0.0)

### Sortie

Le script produit un fichier `data/usage/predictions/arima_predictions.parquet` contenant :

| Champ | Description |
|-------|-------------|
| `symbol` | Symbole boursier |
| `date` | Date de la valeur |
| `predicted_close` | Cours prédit (ou réel pour les données historiques) |
| `confidence_lower` | Borne inférieure de l'intervalle de confiance (95%) |
| `confidence_upper` | Borne supérieure de l'intervalle de confiance (95%) |
| `sentiment_score` | Score de sentiment utilisé pour la prédiction |
| `type` | `actual` (données réelles) ou `forecast` (prédiction) |

## Ingestion des données

### Yahoo Finance (cours boursiers)

Le script `scripts/ingestion/yahoo_stocks.py` récupère via la librairie `yfinance` :
- **Historique des cours** : open, high, low, close, volume sur 5 ans
- **Informations entreprise** : nom, secteur, industrie, capitalisation boursière

Les données sont sauvegardées en JSON, partitionnées par date dans `data/raw/yahoo_finance/`.

### Finnhub (actualités financières)

Le script `scripts/ingestion/finnhub_news.py` récupère les articles via l'API Finnhub :

| Paramètre | Valeur |
|-----------|--------|
| Période | 12 mois |
| Symboles | 10 |
| Appels API | 120 (10 × 12) |
| Rate limit | 60 appels/min (free tier) |
| Durée totale | ~3 minutes |
| Volume | ~21 000 articles |

> L'ingestion utilise un délai de 1.1 seconde entre chaque appel pour respecter le rate limit de Finnhub.

## Transformation Spark

### Formatting (`scripts/formatting/format_to_parquet.py`)

Conversion des données brutes JSON en Parquet avec :
- Normalisation des types (float, long, date)
- Conversion des timestamps en UTC
- Partitionnement optimisé pour Spark

### Combination (`scripts/combination/combine_sources.py`)

Jointure des sources de données :
1. **Stocks ⨝ Company Info** (sur `symbol`) : enrichit les cours avec les infos entreprise
2. **Résultat ⨝ News agrégées** (sur `symbol`) : ajoute le nombre d'articles et la date de la dernière news

Métriques dérivées calculées :
- `daily_range` = high - low (amplitude journalière)
- `daily_change_pct` = ((close - open) / open) × 100 (variation en %)

## Analyse de sentiment

Le projet utilise **VADER** (Valence Aware Dictionary and sEntiment Reasoner) pour analyser automatiquement le sentiment des actualités financières.

### Comment ça fonctionne

1. Lors de l'ingestion, chaque article (title + summary) est analysé
2. VADER retourne un score `compound` entre -1.0 et 1.0
3. Le score est classifié en label :
   - `positive` : score >= 0.05
   - `negative` : score <= -0.05
   - `neutral` : entre -0.05 et 0.05

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
| summary | text | Résumé de l'article |
| provider | keyword | Éditeur (Yahoo, Reuters, etc.) |
| category | keyword | Catégorie (company, market, etc.) |
| pub_date_utc | date | Date de publication |
| url | keyword | URL de l'article |
| sentiment_score | float | Score de sentiment (-1.0 à 1.0) |
| sentiment_label | keyword | Label (positive, negative, neutral) |

### Index `stock_predictions` (prédictions ML)

| Champ | Type | Description |
|-------|------|-------------|
| symbol | keyword | Symbole boursier |
| date | date | Date de la valeur |
| predicted_close | float | Cours prédit ou réel |
| confidence_lower | float | Borne inférieure (IC 95%) |
| confidence_upper | float | Borne supérieure (IC 95%) |
| sentiment_score | float | Score de sentiment utilisé pour la prédiction |
| type | keyword | `actual` ou `forecast` |

## Visualisation Kibana

Les dashboards sont **automatiquement importés** au démarrage du projet via `scripts/init_kibana.sh`. Aucune configuration manuelle n'est requise.

### Dashboard principal : "Cours des actions US sur 90 jours"

Le dashboard contient les visualisations suivantes :

1. **Évolution des cours** : Line chart montrant le prix de clôture par symbole sur les 90 derniers jours (index `stock_analysis`)
2. **Tableau des actualités** : Dernières news avec titre, résumé, score de sentiment et label (index `stock_news`)
3. **Cours réels + Prédictions SARIMAX** : Graphique combiné montrant :
   - Les 90 derniers jours de cours réels (lignes solides)
   - Les 30 jours de prédictions (lignes continues)
   - Les bandes de confiance à 95% (zones area)

### Export/Import des dashboards

Les dashboards sont sauvegardés dans `kibana/kibana_saved_objects.ndjson` et importés automatiquement au démarrage.

Pour exporter vos modifications :
```bash
curl -s -X POST "http://localhost:5601/api/saved_objects/_export" \
  -H "kbn-xsrf: true" \
  -H "Content-Type: application/json" \
  -d '{"type": ["dashboard", "visualization", "lens", "index-pattern", "search"], "includeReferencesDeep": true}' \
  -o kibana/kibana_saved_objects.ndjson
```

## Pipeline manuel (optionnel)

Pour exécuter les étapes individuellement en local :

```bash
# 1. Ingestion (collecte des données Yahoo Finance)
poetry run ingest-stocks    # Stocks + Company Info (5 ans d'historique)
poetry run ingest-news      # Actualités financières

# 2. Transformation (JSON → Parquet avec Spark)
poetry run format-data

# 3. Combinaison (jointure + métriques dérivées)
poetry run combine-data

# 4. Prédiction (Holt-Winters)
python scripts/prediction/arima_forecast.py

# 5. Indexation (Elasticsearch)
poetry run index-data
```

## Arrêt

```bash
docker-compose down           # Stopper les services (données conservées)
docker-compose down -v        # Stopper + supprimer les volumes (perte des données)
```

> **Attention** : `docker-compose down -v` supprime les volumes Elasticsearch. Les dashboards seront réimportés automatiquement au prochain démarrage, mais les données devront être réingérées via le DAG Airflow.
