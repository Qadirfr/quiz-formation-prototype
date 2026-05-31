# V18 — Banque de questions et quiz sauvegardés sur Supabase

## Ce qui est migré

Cette V18 rend hybrides :

```text
utils/database.py
utils/question_bank.py
```

Quand `APP_DATABASE_MODE=postgres`, les quiz sauvegardés et la banque de questions sont lus/écrits dans Supabase.

Quand `APP_DATABASE_MODE=sqlite`, le fonctionnement local reste disponible.

## Tables concernées

```text
saved_quizzes
question_bank
```

## Migration des données existantes

Après installation, en mode postgres :

```powershell
$env:APP_DATABASE_MODE="postgres"
$env:DATABASE_URL="postgresql://..."

.\.venv\Scripts\python.exe deployment\migrate_sqlite_to_postgres_quizzes_bank.py
```

## Vérification

```powershell
.\.venv\Scripts\python.exe deployment\check_quizzes_bank_counts.py
```

Résultat attendu :

```text
Mode base : postgres
Quiz sauvegardés : ...
Questions banque : 239
```

## Après V18

L'application peut lire la banque de questions depuis Supabase. Cela prépare :

- session autonome
- entraînement autonome
- accès cloud sans dépendre de la base SQLite locale
