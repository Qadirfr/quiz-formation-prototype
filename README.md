# Quiz Formation

Prototype Streamlit de création et de passation d’évaluations de formation. La version de travail est issue de la branche `diagnostic-performance-v23`, qui contient les développements V22/V23. Les anciens guides numérotés décrivent des étapes antérieures du projet.

## Fonctions présentes

- Espace formateur : import de supports, génération de démonstration ou avec Ollama, création manuelle, import de questions JSON/CSV/Excel et de cas partagés, médias, banque de questions et historique des quiz.
- Évaluations : QCM, vrai/faux, appariement, ordonnancement, questions à trous, auto-positionnement, répartition de points, classement et réponses libres.
- Espace apprenant : entraînement, tentatives, sessions dirigées et consultation des résultats.
- Exports du quiz affiché : JSON, CSV et Markdown.
- Sauvegarde portable des données enregistrées : ZIP accessible au formateur dans l’onglet **7. Export**.
- Base de données : SQLite pour le fonctionnement local, ou PostgreSQL/Supabase selon la configuration.

## Installation et démarrage

Depuis la racine du dépôt, crée un environnement Python et installe les dépendances. Les tests de cette reprise ont été exécutés avec Python 3.12.

```bash
python -m venv .venv
```

Active ensuite l’environnement :

```bash
# Linux, macOS ou Codespaces
source .venv/bin/activate
```

```powershell
# Windows PowerShell
.\.venv\Scripts\Activate.ps1
```

```bash
python -m pip install -r requirements.txt
```

Avant le premier accès formateur, copie `.streamlit/secrets.example.toml` vers `.streamlit/secrets.toml`, puis renseigne **ton propre mot de passe** dans `QUIZ_TRAINER_PASSWORD` et choisis le code apprenant. Ce fichier local est ignoré par Git. Dans un hébergement Streamlit, renseigne les mêmes clés dans les secrets de l’application.

```bash
python -m streamlit run app.py
```

Le mot de passe formateur n’a plus de valeur de démonstration par défaut. S’il est absent, vide ou composé d’espaces, l’accès formateur est désactivé. Le code apprenant historique reste utilisé s’il n’est pas configuré. Configure-le pour ton installation.

### Configuration

Les variables d’environnement non vides sont prioritaires sur les secrets Streamlit. Un fichier `.env` seul n’est **pas chargé automatiquement** par le code actuel. `.env.example` sert de référence pour les variables à définir dans le processus qui lance l’application.

| Clé | Rôle |
| --- | --- |
| `QUIZ_TRAINER_PASSWORD` | Mot de passe obligatoire de l’espace formateur. |
| `QUIZ_LEARNER_CODE` | Code commun de l’espace apprenant. Ce code ne prouve pas l’identité d’une personne. |
| `APP_DATABASE_MODE` | `sqlite` par défaut, ou `postgres`. |
| `SQLITE_DB_PATH` | Chemin de la base locale, par défaut `data/quiz_history.db`. Un chemin relatif est résolu depuis la racine du dépôt. |
| `DATABASE_URL` | Connexion PostgreSQL utilisée lorsque le mode est `postgres`. À conserver dans les secrets ou l’environnement. |

Redémarre l’application après un changement de base ou de connexion. Les initialiseurs et le pool de connexion sont mis en cache. Changer `APP_DATABASE_MODE` ne transfère pas les données existantes d’une base à l’autre. Les scripts historiques de migration sont dans `deployment/` et doivent être examinés avant utilisation.

### Génération

Le **mode démo sans IA** permet de vérifier le parcours sans service externe. Ses questions servent à tester le prototype.

Le mode **Ollama local** nécessite un serveur Ollama accessible depuis la machine qui exécute Streamlit et le modèle choisi dans la barre latérale. Sur un hébergement distant, `localhost` désigne le serveur d’hébergement. Il ne permet pas de joindre automatiquement un serveur Ollama installé sur ton ordinateur.

## Sauvegarde des données enregistrées

1. Connecte-toi comme formateur et enregistre les quiz ou questions encore en cours d’édition.
2. Ouvre **7. Export**, puis **Préparer la sauvegarde ZIP**. Aucune sauvegarde n’est lancée au simple affichage de l’onglet.
3. Vérifie les compteurs et les avertissements affichés.
4. Clique sur **Télécharger la sauvegarde ZIP** et conserve le fichier dans un emplacement adapté aux données des apprenants.

L’archive reste disponible dans la session qui l’a préparée. **Effacer l’archive préparée** ou la déconnexion la retire de cette session. Toute nouvelle tentative supprime d’abord l’ancienne archive, y compris si la préparation échoue. Les modifications effectuées après l’export nécessitent une nouvelle sauvegarde.

### Contenu de l’archive

| Données | Table |
| --- | --- |
| Quiz sauvegardés, avec leurs questions et analyses | `saved_quizzes` |
| Banque de questions, y compris les questions inactives | `question_bank` |
| Apprenants | `learners` |
| Tentatives et scores | `quiz_attempts` |
| Réponses et instantanés des questions | `learner_answers` |
| Sessions de formation | `training_sessions` |
| Participants des sessions | `session_participants` |
| Réponses aux sessions | `session_answers` |
| Journal des migrations de schéma, lorsqu’il existe | `question_schema_migration_log` |

Chaque table présente est exportée intégralement dans `tables/<nom>.json`, sans limite de lignes liée à l’interface. Le fichier `manifest.json` contient la date UTC, le moteur de base, les compteurs, les empreintes SHA-256 et les réserves de l’export. `LIRE_MOI.txt` décrit le format et les précautions de réutilisation.

La lecture des tables utilise un même instantané de la base. SQLite est ouvert en lecture seule. PostgreSQL utilise une transaction `REPEATABLE READ, READ ONLY`. Si des règles de sécurité PostgreSQL filtrent les lignes ou limitent les colonnes accessibles de l’une des tables, l’export est refusé pour éviter de présenter une sauvegarde incomplète.

Les JSON stockés en texte dans SQLite restent intacts. Les colonnes JSON/JSONB PostgreSQL sont exportées en texte JSON produit par le serveur, canonique pour JSONB, afin de conserver la précision des nombres. Le type natif figure dans les métadonnées des colonnes. Les autres valeurs telles que décimales, dates et données binaires ont un encodage explicite documenté dans l’archive.

### Médias et limites

- Les images déjà intégrées dans les données sous forme de `data:` restent intégrées.
- Les fichiers locaux référencés, présents et autorisés dans `assets/`, `media/`, `uploads/`, `data/media/` ou `data/uploads/` sont copiés dans l’archive. Les références d’origine sont conservées.
- Les médias distants ne sont pas téléchargés. Les liens externes, fichiers absents et références non autorisées sont signalés dans le manifeste. Un fichier local devenu illisible pendant la copie provoque l’arrêt de l’export.
- La limite est de **128 Mio avant compression**, pour les données et métadonnées de l’archive. Si elle est dépassée, aucune archive partielle n’est proposée. Il s’agit d’une limite de volume exporté, pas d’un plafond absolu de mémoire du processus.
- Les brouillons non enregistrés, la configuration, les secrets d’hébergement et le code source ne font pas partie de cet export. Les tables inconnues sont signalées et ne sont pas exportées.
- L’archive contient les données personnelles, les réponses, les corrigés et les codes des sessions enregistrées. Elle doit être protégée en conséquence.
- **La restauration automatique n’est pas encore implémentée.** Le ZIP n’est pas compatible avec l’import de quiz. Il ne remplace pas une sauvegarde native du serveur PostgreSQL, notamment pour les séquences, fonctions, droits et politiques de sécurité.

## Vérifications du développement

```bash
python -m pip install pytest
python -m pytest tests
```

Les tests utilisent des bases SQLite temporaires et des identifiants de test. Ils couvrent l’intégrité de l’archive, les médias, les limites, la cohérence pendant une écriture concurrente, ainsi que les parcours Streamlit de connexion et d’export. La partie PostgreSQL de l’export est testée avec un adaptateur simulé. Une validation sur une instance PostgreSQL réelle reste à effectuer.

## Suite du prototype

Le parcours formateur est protégé par un mot de passe commun. L’authentification apprenant actuelle ne suffit pas à garantir l’identité et la confidentialité des résultats pour une ouverture publique. La correction manuelle des réponses rédigées et la restauration contrôlée des sauvegardes restent aussi à finaliser.

Le point de reprise et les critères des prochains lots sont décrits dans [docs/REPRISE_DEVELOPPEMENT.md](docs/REPRISE_DEVELOPPEMENT.md).
