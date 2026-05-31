from pathlib import Path

required = [
    "app.py",
    "requirements.txt",
    ".gitignore",
    ".env.example",
    ".streamlit/secrets.example.toml",
    "deployment/supabase_schema.sql",
    "README_DEPLOIEMENT.md",
]

missing = []
for item in required:
    if not Path(item).exists():
        missing.append(item)

if missing:
    print("Fichiers manquants :")
    for item in missing:
        print(f"- {item}")
else:
    print("Préparation cloud OK : tous les fichiers attendus sont présents.")

if Path("data/quiz_history.db").exists():
    print("Note : data/quiz_history.db doit rester local et ne doit pas être envoyé sur GitHub.")
