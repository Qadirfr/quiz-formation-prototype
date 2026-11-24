# Générateur de quiz local - Streamlit v1

Application locale pour générer des quiz de formation à partir d'un texte, d'un fichier TXT/MD, DOCX ou PDF.

## Installation

```bash
cd quiz_local_streamlit_v1
python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # macOS/Linux
pip install -r requirements.txt
streamlit run app.py
```

## Modes disponibles

### Mode démo sans IA
Fonctionne immédiatement. Il génère des questions simples pour tester l'interface.

### Mode Ollama local
Nécessite Ollama lancé en local :

```bash
ollama serve
ollama pull llama3.1:8b
```

Puis choisir `Ollama local` dans l'application.

## Structure

```text
app.py
requirements.txt
utils/
  file_reader.py
  quiz_agents.py
  export_utils.py
data/
```

## Version v1

Fonctions incluses :

- import de texte ou fichier TXT/MD/DOCX/PDF ;
- choix du nombre de questions ;
- choix du niveau ;
- choix du type de questions ;
- génération via mode démo ou Ollama local ;
- affichage des questions, réponses et explications ;
- export JSON, CSV et Markdown.


## Ateliers interactifs — lots 1 et 2 (tests dans V23)

L'application inclut les cartes d'ordonnancement et d'appariement (lot 1), ainsi que le classement des priorités par cartes, les textes à trous avec étiquettes et les curseurs de répartition de points (lot 2). L'aperçu dans l'espace formateur et l'import Excel/CSV des cinq formats réutilisent la banque actuelle. Les classements et budgets restent soumis à une correction différée. Voir [la notice des ateliers interactifs](docs/ATELIERS_INTERACTIFS_V24.md). La version historique et les données existantes ne sont pas migrées.


## Lot 3 — Scénarios à décisions successives

Deux cas de démonstration sont disponibles dans l'onglet **1. Source** de V23 : incident SSI et assistant RAG pour les réclamations. Le formateur peut créer des parcours par étapes dans **2. Création manuelle**, ou importer un modèle **Excel / CSV** sans cellule JSON. Une ligne contient une décision. Les décisions peuvent conduire à des étapes différentes, avec conséquence, barème et explication. La passation fonctionne en quiz autonome et session dirigée, avec un corrigé différé. Aucun nouveau stockage ni aucune migration ne sont nécessaires.

**Notice détaillée :** [Scénarios à embranchements — lot 3](docs/SCENARIOS_EMBRANCHEMENTS_LOT3.md).
