# V15 — Couche base de données hybride

## Objectif

Cette V15 prépare le passage :

```text
local → SQLite
cloud → PostgreSQL / Supabase
```

Elle ne remplace pas encore toute l'application par PostgreSQL. Elle ajoute une couche de connexion testable, sans casser le prototype local.

## Fichiers ajoutés

```text
utils/db_runtime.py
deployment/test_database_connection.py
deployment/apply_supabase_schema.py
deployment/export_sqlite_snapshot.py
README_V15_DATABASE.md
```

## Test local SQLite

```powershell
cd "C:\Users\qadir\Desktop\formation\quiz_local_streamlit_v1"

$env:APP_DATABASE_MODE="sqlite"
$env:SQLITE_DB_PATH="data/quiz_history.db"

.\.venv\Scripts\python.exe deployment\test_database_connection.py
```

Résultat attendu :

```text
OK
mode: sqlite
tables: [...]
```

## Export de sauvegarde SQLite

Avant toute migration cloud, exporte un snapshot JSON :

```powershell
.\.venv\Scripts\python.exe deployment\export_sqlite_snapshot.py
```

Le fichier sera créé dans :

```text
deployment/snapshots/
```

## Test Supabase/PostgreSQL

Quand ton projet Supabase sera créé :

```powershell
$env:APP_DATABASE_MODE="postgres"
$env:DATABASE_URL="postgresql://..."

.\.venv\Scripts\python.exe deployment\test_database_connection.py
```

## Créer les tables Supabase

Après avoir défini `DATABASE_URL` :

```powershell
$env:APP_DATABASE_MODE="postgres"
$env:DATABASE_URL="postgresql://..."

.\.venv\Scripts\python.exe deployment\apply_supabase_schema.py
```

## Prochaine étape après V15

V16 pourra commencer à remplacer progressivement les accès directs SQLite par cette couche hybride.

Ordre conseillé :

1. `question_bank` — faible risque
2. `learners` — risque modéré
3. `training_sessions` — important pour le live
4. `quiz_attempts` / `learner_answers` — important pour les résultats
5. `saved_quizzes` — bibliothèque de quiz

Principe : une table à la fois, avec test à chaque étape.
