# Déploiement du générateur de quiz — prototype vers version en ligne

## État actuel

L'application fonctionne en local avec :

- Streamlit
- SQLite (`data/quiz_history.db`)
- import CSV / Excel
- banque de questions
- espace formateur / apprenant
- sessions dirigées
- résultats et exports

Cette V14 ne casse pas le fonctionnement local. Elle prépare seulement le projet pour GitHub, Supabase/PostgreSQL et un futur hébergement.

---

## Lancement local

```powershell
cd "C:\Users\qadir\Desktop\formation\quiz_local_streamlit_v1"

$env:QUIZ_LEARNER_CODE="MONCODE2026"
$env:QUIZ_TRAINER_PASSWORD="MonMotDePasseFort"

.\.venv\Scripts\python.exe -m streamlit run app.py
```

---

## Test Internet rapide sans migration cloud

Pour une formation test, tu peux garder l'application sur ton PC et l'exposer avec un tunnel :

- Cloudflare Tunnel
- ngrok
- Tailscale Funnel

Limites :

- ton PC doit rester allumé
- PowerShell doit rester ouvert
- la base SQLite reste locale
- ce n'est pas une solution SaaS durable

---

## Préparation GitHub

Avant de publier :

1. Vérifier que `.gitignore` exclut :
   - `.venv/`
   - `data/*.db`
   - `.env`
   - `.streamlit/secrets.toml`

2. Ne jamais mettre de vrais mots de passe dans GitHub.

3. Ajouter uniquement :
   - `app.py`
   - `utils/`
   - `requirements.txt`
   - `.gitignore`
   - `.env.example`
   - `.streamlit/secrets.example.toml`
   - `deployment/supabase_schema.sql`
   - `README_DEPLOIEMENT.md`

---

## Préparation Supabase

1. Créer un projet Supabase.
2. Aller dans SQL Editor.
3. Copier-coller le contenu de :

```text
deployment/supabase_schema.sql
```

4. Exécuter le script.

5. Récupérer la connection string PostgreSQL.

Elle sera utilisée plus tard dans :

```text
DATABASE_URL=postgresql://...
```

---

## Hébergement possible

### Option simple

Streamlit Community Cloud :

- dépôt GitHub
- `requirements.txt`
- secrets dans l'interface Streamlit Cloud

### Option plus robuste

Render, Railway ou Fly.io :

- application Streamlit
- variables d'environnement
- base Supabase PostgreSQL

---

## Variables d'environnement à prévoir

```text
QUIZ_LEARNER_CODE
QUIZ_TRAINER_PASSWORD
APP_DATABASE_MODE
SQLITE_DB_PATH
DATABASE_URL
PUBLIC_APP_URL
```

Pour le moment, `APP_DATABASE_MODE=sqlite`.

La migration vers `APP_DATABASE_MODE=postgres` se fera dans une étape suivante.

---

## Étape suivante recommandée

V15 — couche database hybride :

- garder SQLite en local
- ajouter PostgreSQL/Supabase en ligne
- remplacer progressivement les accès directs `sqlite3`
- conserver les mêmes fonctions métier
- tester table par table

Principe : ne pas réécrire l'application, mais remplacer la couche de stockage progressivement.
