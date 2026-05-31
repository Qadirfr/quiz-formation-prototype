# V16 — Sessions dirigées sur Supabase

## Objectif

Cette V16 rend hybrides les modules :

```text
utils/learner_db.py
utils/session_db.py
```

Quand :

```powershell
$env:APP_DATABASE_MODE="sqlite"
```

l'application continue à utiliser la base locale SQLite.

Quand :

```powershell
$env:APP_DATABASE_MODE="postgres"
$env:DATABASE_URL="postgresql://..."
```

les apprenants, sessions dirigées, participants et réponses de session sont stockés dans Supabase.

## Ce qui est migré

- learners
- quiz_attempts
- learner_answers
- training_sessions
- session_participants
- session_answers

## Ce qui reste encore local pour l'instant

- saved_quizzes
- question_bank

Donc, pendant cette étape, tu peux créer une session depuis un quiz local, mais la session et les réponses seront stockées dans Supabase.

## Test recommandé

1. Lancer l'application en mode postgres.
2. Créer une session côté formateur.
3. Rejoindre la session côté apprenant.
4. Répondre à une question.
5. Vérifier dans Supabase :
   - learners
   - training_sessions
   - session_participants
   - session_answers

## Migration optionnelle des anciennes sessions locales

```powershell
$env:APP_DATABASE_MODE="postgres"
$env:DATABASE_URL="postgresql://..."
.\.venv\Scripts\python.exe deployment\migrate_sqlite_to_postgres_sessions.py
```
