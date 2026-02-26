# Documentation Technique — Yahoo Finance Data Lake

## Table des matières

1. [Vue d'ensemble](#1-vue-densemble)
2. [Architecture générale](#2-architecture-générale)
3. [Infrastructure Docker](#3-infrastructure-docker)
4. [Configuration centralisée](#4-configuration-centralisée)
5. [Phase 1 — Ingestion des données](#5-phase-1--ingestion-des-données)
6. [Phase 2 — Formatage JSON → Parquet](#6-phase-2--formatage-json--parquet)
7. [Phase 3 — Combinaison et enrichissement](#7-phase-3--combinaison-et-enrichissement)
8. [Phase 4 — Prédiction SARIMAX](#8-phase-4--prédiction-sarimax)
9. [Phase 5 — Indexation Elasticsearch](#9-phase-5--indexation-elasticsearch)
10. [Orchestration Airflow](#10-orchestration-airflow)
11. [Visualisation Kibana](#11-visualisation-kibana)
12. [Structure du Data Lake](#12-structure-du-data-lake)
13. [Schémas des index Elasticsearch](#13-schémas-des-index-elasticsearch)
14. [Compatibilité cross-platform](#14-compatibilité-cross-platform)
15. [Commandes utiles](#15-commandes-utiles)

---

## 1. Vue d'ensemble

Ce projet implémente un **Data Lake complet** pour l'analyse financière de 10 actions majeures du marché américain. Le pipeline ETL ingère quotidiennement des données boursières et des actualités financières, les transforme via Apache Spark, génère des prédictions SARIMAX avec intégration du sentiment de marché, et indexe le tout dans Elasticsearch pour une visualisation en temps réel via Kibana.

**Symboles suivis :**

| Symbole | Entreprise | Secteur |
|---------|-----------|---------|
| AAPL | Apple | Technology |
| GOOGL | Google | Technology |
| MSFT | Microsoft | Technology |
| AMZN | Amazon | Consumer Cyclical |
| META | Meta Platforms | Technology |
| TSLA | Tesla | Consumer Cyclical |
| NVDA | Nvidia | Technology |
| JPM | JPMorgan Chase | Financial Services |
| V | Visa | Financial Services |
| WMT | Walmart | Consumer Defensive |

---

## 2. Architecture générale

Le pipeline se décompose en 5 phases séquentielles orchestrées par Airflow :

```
┌──────────────────┐     ┌──────────────────┐
│  Yahoo Finance   │     │   Finnhub API    │
│  (yfinance)      │     │   + VADER NLP    │
└────────┬─────────┘     └────────┬─────────┘
         │                        │
         ▼                        ▼
┌─────────────────────────────────────────────┐
│            Raw Layer (JSON)                  │
│  data/raw/yahoo_finance/  data/raw/news/    │
│  Partitionné par date : YYYY-MM-DD/         │
└────────────────────┬────────────────────────┘
                     │ Spark (format_to_parquet.py)
                     ▼
┌─────────────────────────────────────────────┐
│          Formatted Layer (Parquet)           │
│  stocks.parquet  company_info.parquet       │
│  news.parquet                                │
└────────────────────┬────────────────────────┘
                     │ Spark (combine_sources.py)
                     ▼
┌─────────────────────────────────────────────┐
│            Usage Layer (Parquet)             │
│  enriched_stocks.parquet                     │
│  arima_predictions.parquet                   │
└────────────────────┬────────────────────────┘
                     │ to_elasticsearch.py
                     ▼
┌─────────────────────────────────────────────┐
│           Elasticsearch (3 index)           │
│  stock_analysis  stock_news  stock_predictions│
└────────────────────┬────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────┐
│          Kibana (7 visualisations)          │
└─────────────────────────────────────────────┘
```

**Stack technique :**

| Composant | Technologie | Version | Rôle |
|-----------|------------|---------|------|
| Orchestration | Apache Airflow | 2.7.3 | Planification et exécution du DAG |
| Processing | Apache Spark | 3.5.0 | Transformation distribuée JSON → Parquet |
| Stockage métadonnées | PostgreSQL | 15 | Backend Airflow |
| Indexation | Elasticsearch | 8.11.0 | Moteur de recherche et agrégation |
| Visualisation | Kibana | 8.11.0 | Dashboards interactifs |
| Conteneurisation | Docker Compose | — | Orchestration des 6 services |
| Langage | Python | 3.10 | Scripts ETL, ML, ingestion |

---

## 3. Infrastructure Docker

### 3.1 Services

Le fichier `docker-compose.yml` définit 6 services interconnectés via le réseau `bigdata-network` (bridge) :

#### Airflow (`airflow`)
- **Image** : `apache/airflow:2.7.3-python3.10` (custom via `Dockerfile.airflow`)
- **Port** : `8080` (interface web)
- **Executor** : `LocalExecutor` (adapté au mono-nœud)
- **Base de données** : PostgreSQL pour les métadonnées
- **Identifiants** : `admin` / `admin`
- **Initialisation** :
  1. Crée l'arborescence du Data Lake (`mkdir -p`)
  2. Applique les permissions (`chmod -R 777`)
  3. Exécute `airflow db migrate`
  4. Crée l'utilisateur admin
  5. Lance l'import Kibana en arrière-plan (après 30s de délai)
  6. Démarre le webserver et le scheduler en parallèle

#### PostgreSQL (`postgres`)
- **Image** : `postgres:15`
- **Port** : `5432`
- **Healthcheck** : `pg_isready -U airflow` toutes les 5 secondes
- **Volume** : `postgres-data` (persistant)
- Airflow attend que le healthcheck passe avant de démarrer (`condition: service_healthy`)

#### Spark Master (`spark-master`)
- **Image** : `apache/spark:3.5.0`
- **Ports** : `7077` (master), `8081` (UI web)
- **User** : `root` (`user: "0"`) pour la compatibilité cross-platform
- **Initialisation** : `umask 000` + création des répertoires + `chmod -R 777`

#### Spark Worker (`spark-worker`)
- **Image** : `apache/spark:3.5.0`
- **Mémoire** : 2 Go (`SPARK_WORKER_MEMORY=2g`)
- **Work directory** : `/tmp/spark-worker` (évite les conflits sur les bind mounts)
- **User** : `root` (`user: "0"`)
- **Dépendance** : attend spark-master

#### Elasticsearch (`elasticsearch`)
- **Image** : `docker.elastic.co/elasticsearch/elasticsearch:8.11.0`
- **Port** : `9200`
- **Configuration** : single-node, sécurité désactivée, heap 512 Mo
- **Volume** : `elasticsearch-data` (persistant)

#### Kibana (`kibana`)
- **Image** : `docker.elastic.co/kibana/kibana:8.11.0`
- **Port** : `5601`
- **Dépendance** : attend Elasticsearch

### 3.2 Volumes

| Volume | Type | Partagé entre | Contenu |
|--------|------|---------------|---------|
| `airflow_data` | Docker nommé | airflow, spark-master, spark-worker | Data Lake (raw, formatted, usage) |
| `postgres-data` | Docker nommé | postgres | Métadonnées Airflow |
| `elasticsearch-data` | Docker nommé | elasticsearch | Index ES |

L'utilisation d'un **volume Docker nommé** (`airflow_data`) au lieu d'un bind mount (`./data`) résout les problèmes de permissions sur Windows/WSL2.

### 3.3 Dockerfile.airflow

Le Dockerfile customise l'image Airflow avec :

1. **OpenJDK 11** — requis par PySpark pour la JVM
2. **Détection d'architecture** — lien symbolique dynamique pour ARM64 (Apple Silicon) ou AMD64 (Intel/Windows)
3. **Dépendances Python** :
   - `yfinance`, `pandas`, `pyarrow` — ingestion et manipulation
   - `pyspark==3.5.0` — client Spark
   - `elasticsearch` — client ES
   - `vaderSentiment` — analyse de sentiment NLP
   - `statsmodels` — modèle SARIMAX
   - `loguru` — logging structuré
   - `apache-airflow-providers-apache-spark==4.7.1` — intégration Airflow-Spark

### 3.4 Réseau

Tous les services communiquent via le réseau Docker `bigdata-network` (driver bridge). Les noms de service (`spark-master`, `elasticsearch`, `kibana`, etc.) servent de DNS interne.

---

## 4. Configuration centralisée

Fichier : `config/settings.py`

Toute la configuration du projet est centralisée dans ce module :

```python
# Chemins du Data Lake (3 couches)
DATA_LAKE_PATH = Path(os.getenv("DATA_LAKE_PATH", PROJECT_ROOT / "data"))
RAW_PATH       = DATA_LAKE_PATH / "raw"
FORMATTED_PATH = DATA_LAKE_PATH / "formatted"
USAGE_PATH     = DATA_LAKE_PATH / "usage"

# 10 symboles boursiers suivis
STOCK_SYMBOLS = ["AAPL", "GOOGL", "MSFT", "AMZN", "META",
                 "TSLA", "NVDA", "JPM", "V", "WMT"]

# 3 index Elasticsearch
ELASTICSEARCH_INDEX             = "stock_analysis"
ELASTICSEARCH_NEWS_INDEX        = "stock_news"
ELASTICSEARCH_PREDICTIONS_INDEX = "stock_predictions"

# Spark
SPARK_APP_NAME   = "YahooFinanceDataLake"
SPARK_MASTER_URL = os.getenv("SPARK_MASTER_URL", "local[*]")
```

**Variables d'environnement** (`.env`) :

| Variable | Valeur par défaut | Description |
|----------|-------------------|-------------|
| `FINNHUB_API_KEY` | — | Clé API Finnhub (obligatoire) |
| `ELASTICSEARCH_HOST` | `elasticsearch` | Hostname ES |
| `ELASTICSEARCH_PORT` | `9200` | Port ES |
| `SPARK_MASTER_URL` | `local[*]` | URL du master Spark |
| `DATA_LAKE_PATH` | `./data` | Racine du Data Lake |

---

## 5. Phase 1 — Ingestion des données

### 5.1 Ingestion des cours boursiers

**Script** : `scripts/ingestion/yahoo_stocks.py`
**Opérateur Airflow** : `PythonOperator` (task `ingest_stocks`)
**API** : Yahoo Finance via la librairie `yfinance`
**Durée** : ~30 secondes

#### Données récupérées

**Cours historiques** (`fetch_stock_data`) :
- Période : **5 ans** de données historiques (~1 260 jours de trading par symbole)
- Champs : `symbol`, `date`, `open`, `high`, `low`, `close`, `volume`, `fetched_at`
- Volume : ~12 600 enregistrements au total

**Informations entreprise** (`fetch_company_info`) :
- Champs : `symbol`, `name`, `sector`, `industry`, `country`, `market_cap`, `currency`, `fetched_at`
- Volume : 10 enregistrements (1 par symbole)

#### Stockage

Les données sont sauvegardées en JSON dans la couche Raw, partitionnées par date :
```
data/raw/yahoo_finance/stocks/2026-02-26/stocks.json
data/raw/yahoo_finance/company_info/2026-02-26/company_info.json
```

### 5.2 Ingestion des actualités financières

**Script** : `scripts/ingestion/finnhub_news.py`
**Opérateur Airflow** : `PythonOperator` (task `ingest_news`)
**API** : Finnhub (`https://finnhub.io/api/v1/company-news`)
**Durée** : ~3 minutes

#### Fonctionnement

1. **Découpage temporel** : la fonction `generate_month_ranges()` génère 12 plages mensuelles pour couvrir un an d'historique
2. **Appels API** : 10 symboles × 12 mois = 120 appels
3. **Rate limiting** : pause de 1.1 seconde entre chaque appel (limite free tier : 60 appels/min)
4. **Dédoublonnage** : les articles sont identifiés par leur `id` Finnhub — les doublons cross-mois sont éliminés via un `set`

#### Analyse de sentiment VADER

Chaque article est analysé par le modèle **VADER** (Valence Aware Dictionary and sEntiment Reasoner) :

```python
def analyze_sentiment(text: str) -> dict:
    scores = sentiment_analyzer.polarity_scores(text)
    compound = scores["compound"]  # Score composite [-1.0, +1.0]

    if compound >= 0.05:   label = "positive"
    elif compound <= -0.05: label = "negative"
    else:                   label = "neutral"
```

- **Entrée** : concaténation du titre et du résumé de l'article
- **Score** : `compound` VADER, arrondi à 4 décimales
- **Seuils** : `≥ 0.05` positif, `≤ -0.05` négatif, entre les deux neutre

#### Champs produits

`id`, `symbol`, `title`, `summary`, `pub_date` (UTC ISO), `provider`, `url`, `category`, `image`, `sentiment_score`, `sentiment_label`, `fetched_at`

#### Stockage

```
data/raw/news/financial_news/2026-02-26/news.json
```

Volume : ~21 000 articles uniques par exécution.

### 5.3 Parallélisme

Les tâches `ingest_stocks` et `ingest_news` s'exécutent **en parallèle** car elles sont indépendantes (sources différentes, pas de dépendance de données).

---

## 6. Phase 2 — Formatage JSON → Parquet

**Script** : `scripts/formatting/format_to_parquet.py`
**Opérateur Airflow** : `BashOperator` via `spark-submit`
**Commande** : `spark-submit --master spark://spark-master:7077 --deploy-mode client`
**Durée** : ~1 minute

### 6.1 Configuration Spark

```python
SparkSession.builder
    .appName("YahooFinanceDataLake")
    .config("spark.sql.legacy.timeParserPolicy", "LEGACY")
    .config("spark.hadoop.mapreduce.fileoutputcommitter.algorithm.version", "2")
    .config("spark.hadoop.fs.permissions.umask-mode", "000")
    .getOrCreate()
```

- `LEGACY` : parsing de dates flexible (formats hétérogènes)
- `algorithm.version=2` : commit des fichiers Parquet sans `rename` atomique cross-directory (compatibilité WSL2)
- `umask-mode=000` : fichiers créés en world-writable

### 6.2 Formatage des cours (`format_stocks`)

- **Entrée** : `data/raw/yahoo_finance/stocks/*/stocks.json` (glob multi-dates)
- **Normalisation** :
  - `open`, `high`, `low`, `close` → `DoubleType`
  - `volume` → `LongType`
  - `fetched_at` → `fetched_at_utc` (conversion UTC)
- **Sortie** : `data/formatted/yahoo_finance/stocks/stocks.parquet` (Snappy)

### 6.3 Formatage des infos entreprise (`format_company_info`)

- **Entrée** : `data/raw/yahoo_finance/company_info/*/company_info.json`
- **Normalisation** :
  - `market_cap` → `LongType`
  - `fetched_at` → `fetched_at_utc`
- **Sortie** : `data/formatted/yahoo_finance/company_info/company_info.parquet`

### 6.4 Formatage des actualités (`format_news`)

- **Entrée** : `data/raw/news/financial_news/*/news.json`
- **Normalisation** :
  - `pub_date` → `pub_date_utc` (conversion UTC)
  - `fetched_at` → `fetched_at_utc`
- **Filtrage** : suppression des articles antérieurs à 2020
- **Sortie** : `data/formatted/news/financial_news/news.parquet`

### 6.5 Stratégie d'écriture

Pour éviter les données dupliquées et les erreurs de permissions cross-platform :

1. `safe_rmtree(path)` supprime le répertoire de sortie existant (échoue bruyamment si impossible)
2. `df.write.mode("append").parquet(path)` écrit dans un répertoire vide

Cette approche remplace `mode("overwrite")` qui effectuait un `rename` interne échouant sur les bind mounts Windows/WSL2.

---

## 7. Phase 3 — Combinaison et enrichissement

**Script** : `scripts/combination/combine_sources.py`
**Opérateur Airflow** : `BashOperator` via `spark-submit`
**Durée** : ~1 minute

### 7.1 Jointures

```
stocks_df ──LEFT JOIN──► company_df (on: symbol)
     │
     └──LEFT JOIN──► news_agg (on: symbol)
```

1. **Agrégation des news** : par symbole → `news_count` (nombre d'articles), `latest_news_date` (date du plus récent)
2. **Jointure stocks + company_info** : enrichit chaque ligne de cours avec `name`, `sector`, `industry`, `market_cap`
3. **Jointure avec news** : ajoute les métriques d'actualités agrégées

### 7.2 Métriques dérivées

```python
daily_range     = high - low                           # Amplitude journalière
daily_change_pct = ((close - open) / open) * 100       # Variation en %
```

### 7.3 Schéma final

| Colonne | Type | Description |
|---------|------|-------------|
| `symbol` | string | Ticker boursier |
| `name` | string | Nom de l'entreprise |
| `sector` | string | Secteur d'activité |
| `industry` | string | Industrie |
| `date` | timestamp | Date de trading |
| `open` | double | Prix d'ouverture |
| `high` | double | Plus haut |
| `low` | double | Plus bas |
| `close` | double | Prix de clôture |
| `volume` | long | Volume échangé |
| `market_cap` | long | Capitalisation boursière |
| `daily_range` | double | Amplitude (high - low) |
| `daily_change_pct` | double | Variation % (close - open) / open |
| `news_count` | long | Nombre d'articles |
| `latest_news_date` | timestamp | Date du dernier article |
| `fetched_at_utc` | timestamp | Date d'ingestion |

**Sortie** : `data/usage/stock_analysis/enriched_stocks.parquet`
**Volume** : ~12 800 enregistrements

---

## 8. Phase 4 — Prédiction SARIMAX

**Script** : `scripts/prediction/arima_forecast.py`
**Opérateur Airflow** : `PythonOperator` (task `predict_arima`)
**Durée** : ~30 secondes

### 8.1 Modèle mathématique

Le modèle **SARIMAX** (Seasonal AutoRegressive Integrated Moving Average with eXogenous variables) combine :

- **Composante ARIMA** : tendance et autocorrélation
- **Composante saisonnière** : cycle hebdomadaire (5 jours de trading)
- **Variable exogène** : score de sentiment agrégé quotidien

**Formule** :

```
φ(B) Φ(Bˢ) (1-B)^d (1-Bˢ)^D y_t = θ(B) Θ(Bˢ) ε_t + β·x_t
```

où `x_t` est le sentiment moyen du jour t.

### 8.2 Hyperparamètres

| Paramètre | Valeur | Justification |
|-----------|--------|---------------|
| Ordre ARIMA `(p,d,q)` | `(2, 1, 2)` | 2 termes AR, 1 différenciation, 2 termes MA |
| Ordre saisonnier `(P,D,Q,s)` | `(1, 1, 1, 5)` | Cycle hebdomadaire de 5 jours ouvrés |
| Période d'entraînement | 252 jours | ~1 an de trading |
| Horizon de prédiction | 30 jours | 30 jours ouvrés (~6 semaines) |
| Intervalle de confiance | 95% | α = 0.05 |
| Itérations max | 200 | Convergence de l'optimiseur |

### 8.3 Intégration du sentiment

1. **Construction du sentiment quotidien** (`build_daily_sentiment`) :
   - Filtre les articles par symbole
   - Moyenne du `sentiment_score` par date
   - Retourne une `pd.Series` indexée par date

2. **Alignement avec les cours** :
   - Le sentiment est réindexé sur les dates de trading
   - Les jours sans article reçoivent un score neutre de `0.0`

3. **Projection future** :
   - La moyenne du sentiment des 30 derniers jours est utilisée comme constante pour les 30 jours de prédiction

### 8.4 Sortie

Chaque symbole produit :
- **90 jours de données réelles** (`type: "actual"`) — pour la continuité visuelle sur le dashboard
- **30 jours de prédiction** (`type: "forecast"`) — avec bornes de confiance

| Colonne | Type | Description |
|---------|------|-------------|
| `symbol` | string | Ticker |
| `date` | timestamp | Date |
| `predicted_close` | float | Prix prédit (ou réel pour type=actual) |
| `confidence_lower` | float | Borne inférieure IC 95% |
| `confidence_upper` | float | Borne supérieure IC 95% |
| `sentiment_score` | float | Score de sentiment utilisé |
| `type` | string | `actual` ou `forecast` |

**Sortie** : `data/usage/predictions/arima_predictions.parquet`
**Volume** : ~1 200 enregistrements (10 symboles × 120 lignes)

---

## 9. Phase 5 — Indexation Elasticsearch

**Script** : `scripts/indexing/to_elasticsearch.py`
**Opérateur Airflow** : `PythonOperator` (task `index_data`)
**Durée** : ~1 minute

### 9.1 Client Elasticsearch

```python
Elasticsearch(
    hosts=["http://elasticsearch:9200"],
    request_timeout=30
)
```

Connexion validée par `es.ping()` avant toute opération.

### 9.2 Index `stock_analysis`

- **Source** : `enriched_stocks.parquet`
- **Comportement** : index créé une fois, documents mis à jour par upsert
- **ID document** : `{symbol}_{date}` (garantit l'idempotence)
- **Volume** : ~12 800 documents
- Conversion des colonnes datetime en ISO 8601 (`%Y-%m-%dT%H:%M:%SZ`)

### 9.3 Index `stock_news`

- **Source** : `news.parquet` (couche formatted)
- **Comportement** : index créé une fois, documents dédoublonnés par ID
- **ID document** : UUID Finnhub (ou `{symbol}_{pub_date_utc}` en fallback)
- **Volume** : ~21 000 documents
- Les champs `title` et `summary` ont des sous-champs `.keyword` pour les agrégations

### 9.4 Index `stock_predictions`

- **Source** : `arima_predictions.parquet`
- **Comportement** : **recréé intégralement** à chaque exécution (`delete` + `create`)
- **ID document** : `{symbol}_{date}`
- **Volume** : ~1 200 documents
- Justification : les prédictions changent à chaque run, l'index doit refléter les dernières valeurs

### 9.5 Bulk indexing

L'indexation utilise l'API `bulk` d'Elasticsearch via la librairie Python :

```python
success, errors = bulk(es, generate_actions(df, index), raise_on_error=False)
```

- Les valeurs `NaT`/`NaN` sont converties en `None` avant sérialisation JSON
- Les erreurs sont loguées (5 premières) mais ne bloquent pas l'exécution

---

## 10. Orchestration Airflow

**Fichier** : `airflow/dags/yahoo_finance_pipeline.py`

### 10.1 Configuration du DAG

| Paramètre | Valeur |
|-----------|--------|
| `dag_id` | `yahoo_finance_pipeline` |
| `schedule_interval` | `@daily` (minuit UTC) |
| `start_date` | 2024-01-01 |
| `catchup` | `False` |
| `retries` | 1 |
| `retry_delay` | 5 minutes |

### 10.2 Graphe des tâches

```
start (EmptyOperator)
  ├── ingest_stocks (PythonOperator)      ~30s
  ├── ingest_news (PythonOperator)        ~3min
  └───────────┬───────────────────────────┘
              ▼
      format_data (BashOperator)          ~1min
          spark-submit → format_to_parquet.py
              ▼
      combine_data (BashOperator)         ~1min
          spark-submit → combine_sources.py
              ▼
      predict_arima (PythonOperator)      ~30s
              ▼
      index_data (PythonOperator)         ~1min
              ▼
         end (EmptyOperator)
```

### 10.3 Types d'opérateurs

- **`PythonOperator`** : ingestion (yfinance, Finnhub), prédiction (statsmodels), indexation (elasticsearch-py) — pas besoin de la JVM
- **`BashOperator`** : formatage et combinaison via `spark-submit` — exécuté sur le cluster Spark (driver en mode `client` dans le conteneur Airflow)
- **`EmptyOperator`** : marqueurs de début/fin pour la lisibilité du graphe

### 10.4 Durée totale

Pipeline complet : **~6-7 minutes** (dominé par `ingest_news` à ~3 min dû au rate limiting Finnhub).

---

## 11. Visualisation Kibana

### 11.1 Import automatique

Le script `scripts/init_kibana.sh` est lancé en arrière-plan 30 secondes après le démarrage d'Airflow :

1. Attend que Kibana soit disponible (polling `/api/status` pendant 120s max)
2. Importe `kibana/kibana_saved_objects.ndjson` via l'API REST (`POST /api/saved_objects/_import?overwrite=true`)

Le fichier NDJSON est versionné dans Git, garantissant la reproductibilité des dashboards.

### 11.2 Visualisations du dashboard

| # | Visualisation | Type | Index | Description |
|---|--------------|------|-------|-------------|
| 1 | Evolution des cours | Line chart | `stock_analysis` | Prix de clôture par symbole sur 90 jours |
| 2 | Tableau des actualités | Data table | `stock_news` | News triées par date avec scores et labels de sentiment |
| 3 | Prédictions SARIMAX | Line chart | `stock_predictions` | Cours réels + prédictions 30j + bandes de confiance 95% |
| 4 | Top/Flop du jour | Data table | `stock_analysis` | Classement des symboles par variation journalière |
| 5 | Capitalisation par secteur | Treemap | `stock_analysis` | Répartition de la capitalisation boursière par secteur et symbole |
| 6 | Sentiment moyen par symbole | Bar chart horizontal | `stock_news` | Score de sentiment moyen des 10 actions |
| 7 | Distribution des sentiments | Donut chart | `stock_news` | Répartition positive / négative / neutre des articles |

### 11.3 Index patterns

3 index patterns configurés dans Kibana :

| Index pattern | Time field | Usage |
|--------------|------------|-------|
| `stock_analysis` | `date` | Cours boursiers enrichis |
| `stock_predictions` | `date` | Prédictions SARIMAX |
| `stock_news` | `pub_date` | Actualités avec sentiment |

### 11.4 Export manuel

```bash
curl -s -X POST "http://localhost:5601/api/saved_objects/_export" \
  -H "kbn-xsrf: true" \
  -H "Content-Type: application/json" \
  -d '{"type":["dashboard","visualization","lens","index-pattern","search"],"includeReferencesDeep":true}' \
  -o kibana/kibana_saved_objects.ndjson
```

---

## 12. Structure du Data Lake

Architecture en 3 couches (Médaillon) :

### Couche Raw (Bronze)

```
data/raw/
├── yahoo_finance/
│   ├── stocks/
│   │   └── YYYY-MM-DD/stocks.json          ← OHLCV 5 ans
│   └── company_info/
│       └── YYYY-MM-DD/company_info.json     ← Métadonnées entreprise
└── news/
    └── financial_news/
        └── YYYY-MM-DD/news.json             ← Articles + sentiment VADER
```

- **Format** : JSON brut
- **Partitionnement** : par date d'ingestion
- **Taille** : ~77 Mo
- **Rétention** : cumulative (chaque run ajoute une partition)

### Couche Formatted (Silver)

```
data/formatted/
├── yahoo_finance/
│   ├── stocks/stocks.parquet                ← Cours normalisés
│   └── company_info/company_info.parquet    ← Infos entreprise normalisées
└── news/
    └── financial_news/news.parquet          ← News normalisées (≥ 2020)
```

- **Format** : Apache Parquet (compression Snappy)
- **Normalisation** : types castés, timestamps UTC, filtrage dates invalides
- **Taille** : ~23 Mo (compression ~3x vs JSON)

### Couche Usage (Gold)

```
data/usage/
├── stock_analysis/enriched_stocks.parquet   ← Jointure stocks + company + news
└── predictions/arima_predictions.parquet    ← Prédictions SARIMAX
```

- **Format** : Apache Parquet
- **Enrichissement** : métriques dérivées, jointures multi-sources
- **Taille** : ~5 Mo

### Volumétrie totale

| Couche | Format | Taille | Enregistrements |
|--------|--------|--------|-----------------|
| Raw | JSON | ~77 Mo | ~33 600 |
| Formatted | Parquet | ~23 Mo | ~33 600 |
| Usage | Parquet | ~5 Mo | ~14 000 |
| **Total** | — | **~105 Mo** | **~81 200** |

---

## 13. Schémas des index Elasticsearch

### Index `stock_analysis`

```json
{
  "mappings": {
    "properties": {
      "symbol":           { "type": "keyword" },
      "name":             { "type": "text" },
      "sector":           { "type": "keyword" },
      "industry":         { "type": "keyword" },
      "date":             { "type": "date" },
      "open":             { "type": "float" },
      "high":             { "type": "float" },
      "low":              { "type": "float" },
      "close":            { "type": "float" },
      "volume":           { "type": "long" },
      "market_cap":       { "type": "long" },
      "daily_range":      { "type": "float" },
      "daily_change_pct": { "type": "float" },
      "news_count":       { "type": "integer" },
      "latest_news_date": { "type": "date" },
      "fetched_at_utc":   { "type": "date" }
    }
  }
}
```

### Index `stock_news`

```json
{
  "mappings": {
    "properties": {
      "symbol":           { "type": "keyword" },
      "title":            { "type": "text", "fields": { "keyword": { "type": "keyword", "ignore_above": 512 } } },
      "summary":          { "type": "text", "fields": { "keyword": { "type": "keyword", "ignore_above": 1024 } } },
      "provider":         { "type": "keyword" },
      "category":         { "type": "keyword" },
      "url":              { "type": "keyword" },
      "image":            { "type": "keyword" },
      "sentiment_score":  { "type": "float" },
      "sentiment_label":  { "type": "keyword" },
      "pub_date_utc":     { "type": "date" },
      "fetched_at_utc":   { "type": "date" }
    }
  }
}
```

### Index `stock_predictions`

```json
{
  "mappings": {
    "properties": {
      "symbol":           { "type": "keyword" },
      "date":             { "type": "date" },
      "predicted_close":  { "type": "float" },
      "confidence_lower": { "type": "float" },
      "confidence_upper": { "type": "float" },
      "sentiment_score":  { "type": "float" },
      "type":             { "type": "keyword" }
    }
  }
}
```

---

## 14. Compatibilité cross-platform

Le projet fonctionne sur **macOS**, **Linux** et **Windows/WSL2** grâce aux adaptations suivantes :

| Problème | Cause | Solution |
|----------|-------|----------|
| Spark worker ne peut pas créer de répertoires | Bind mounts WSL2 en lecture seule pour les processus non-root | `user: "0"` sur spark-master et spark-worker |
| `Failed to rename` lors de l'écriture Parquet | Le filesystem 9p/grpcfuse de WSL2 ne supporte pas les `rename` cross-directory | `fileoutputcommitter.algorithm.version=2` + `safe_rmtree()` + `mode("append")` |
| Fichiers créés avec permissions restrictives | L'umask par défaut empêche l'écriture par d'autres processus | `umask 000` dans les commandes Spark + `fs.permissions.umask-mode=000` |
| `chmod` ineffectif sur bind mounts Windows | NTFS ne supporte pas les permissions POSIX | Volume Docker nommé `airflow_data` au lieu de bind mount `./data` |
| Java introuvable selon l'architecture CPU | ARM64 (Apple Silicon) vs AMD64 (Intel) | Détection dynamique dans le Dockerfile : `dpkg --print-architecture` |

---

## 15. Commandes utiles

### Démarrage

```bash
# Configurer la clé API Finnhub
cp .env.example .env
# Editer .env et ajouter FINNHUB_API_KEY=...

# Lancer tous les services
docker-compose up --build -d

# Vérifier les services
docker-compose ps
```

### Interfaces web

| Service | URL |
|---------|-----|
| Airflow | http://localhost:8080 (admin/admin) |
| Spark Master UI | http://localhost:8081 |
| Elasticsearch | http://localhost:9200 |
| Kibana | http://localhost:5601 |

### Gestion du pipeline

```bash
# Déclencher le DAG manuellement (via l'UI Airflow ou CLI)
docker-compose exec airflow airflow dags trigger yahoo_finance_pipeline

# Voir les logs d'une tâche
docker-compose exec airflow airflow tasks logs yahoo_finance_pipeline format_data
```

### Export du dashboard Kibana

```bash
curl -s -X POST "http://localhost:5601/api/saved_objects/_export" \
  -H "kbn-xsrf: true" \
  -H "Content-Type: application/json" \
  -d '{"type":["dashboard","visualization","lens","index-pattern","search"],"includeReferencesDeep":true}' \
  -o kibana/kibana_saved_objects.ndjson
```

### Arrêt

```bash
# Arrêter les services (données préservées dans les volumes)
docker-compose down

# Arrêter et supprimer les volumes (reset complet)
docker-compose down -v
```
