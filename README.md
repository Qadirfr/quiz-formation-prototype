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
