from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import requests


QUESTION_TYPE_LABELS = {
    "QCM - une seule bonne reponse": "single_choice",
    "QCM - une seule bonne r?ponse": "single_choice",
    "Vrai / Faux": "true_false",
    "Question courte": "short_answer",
    "Rapprochement d'idees": "matching",
    "Rapprochement d'idees / appariement": "matching",
}


@dataclass
class QuizConfig:
    provider: str
    ollama_base_url: str
    model_name: str
    difficulty: str
    question_types: List[str]
    number_of_questions: int
    audience: str = "apprenants en formation professionnelle"
    assessment_goal: str = ""
    cognitive_focus: str = "Comprehension"


def call_ollama(prompt: str, config: QuizConfig, num_predict: int = 1200) -> str:
    url = config.ollama_base_url.rstrip("/") + "/api/chat"
    payload = {
        "model": config.model_name,
        "stream": False,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Tu es un expert en ingenierie pedagogique et en evaluation. "
                    "Tu dois produire uniquement un JSON valide, sans commentaire hors JSON."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "options": {
            "temperature": 0.15,
            "num_ctx": 2048,
            "num_predict": num_predict,
        },
    }
    response = requests.post(url, json=payload, timeout=300)
    response.raise_for_status()
    return response.json()["message"]["content"]


def analyze_training_content(source_text: str, config: QuizConfig) -> Dict[str, Any]:
    if config.provider == "Ollama local":
        try:
            prompt = build_analysis_prompt(source_text, config)
            content = call_ollama(prompt, config, num_predict=1000)
            analysis = parse_json_from_model(content)
            return validate_analysis_shape(analysis)
        except Exception as exc:
            return {
                "error": str(exc),
                "training_goal": config.assessment_goal or "Analyse indisponible",
                "key_concepts": [],
                "learning_objectives": [],
                "recommended_exercises": [],
                "quality_risks": ["L'analyse Ollama a echoue. Utilise le mode demo ou reduis le texte source."],
            }

    return demo_analyze_training_content(source_text, config)


def orchestrate_quiz_generation(
    source_text: str,
    config: QuizConfig,
    analysis: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if analysis is None or analysis.get("error"):
        analysis = analyze_training_content(source_text, config)

    if config.provider == "Ollama local":
        try:
            return generate_with_ollama(source_text, config, analysis)
        except Exception as exc:
            return {
                "quiz_title": "Erreur de generation Ollama",
                "analysis": analysis,
                "questions": [],
                "error": str(exc),
                "hint": "Verifie que Ollama est lance, que le modele existe, puis reessaie. Reduis aussi le nombre de questions si besoin.",
            }

    return demo_generate_quiz(source_text, config, analysis)


def build_analysis_prompt(source_text: str, config: QuizConfig) -> str:
    schema = {
        "training_goal": "Objectif pedagogique principal",
        "key_concepts": [
            {
                "concept": "Notion importante",
                "definition": "Definition courte",
                "importance": 5,
                "question_angle": "Angle utile pour poser une question",
                "source_excerpt": "Extrait court du support",
            }
        ],
        "learning_objectives": [
            {
                "objective": "Ce que l'apprenant doit savoir faire",
                "cognitive_level": "memorisation | comprehension | application | analyse",
                "evidence": "Ce qui permettra de verifier que l'objectif est atteint",
            }
        ],
        "recommended_exercises": [
            {
                "type": "single_choice | true_false | short_answer | matching",
                "target_concept": "Notion cible",
                "reason": "Pourquoi ce type d'exercice est pertinent",
            }
        ],
        "quality_risks": [
            "Risque de question trop generale, trop facile ou ambigue"
        ],
    }

    return f"""
MISSION
Analyse le support de formation avant toute generation de quiz.

OBJECTIF PEDAGOGIQUE DONNE PAR LE FORMATEUR
{config.assessment_goal or "Non precise. Propose un objectif coherent avec le support."}

PARAMETRES
- Public : {config.audience}
- Niveau : {config.difficulty}
- Niveau cognitif vise : {config.cognitive_focus}
- Types d'exercices envisages : {[QUESTION_TYPE_LABELS.get(q, q) for q in config.question_types]}

TRAVAIL ATTENDU
1. Identifier les notions vraiment importantes.
2. Distinguer les definitions, obligations, risques, controles, exemples ou etapes.
3. Proposer des objectifs pedagogiques evaluables.
4. Recommander les types d'exercices les plus adaptes.
5. Signaler les risques de questions faibles.

REGLES
- Ne te base que sur le contenu source.
- N'invente pas de notion absente.
- Sois selectif : privilegie les notions evaluables.
- Retourne uniquement un JSON valide.

SCHEMA JSON ATTENDU
{json.dumps(schema, ensure_ascii=False, indent=2)}

CONTENU SOURCE
{source_text[:3500]}
""".strip()


def build_generation_prompt(source_text: str, config: QuizConfig, analysis: Dict[str, Any]) -> str:
    question_types = [QUESTION_TYPE_LABELS.get(q, q) for q in config.question_types]

    schema = {
        "quiz_title": "Titre du quiz",
        "analysis_summary": "Resume de l'analyse utilisee",
        "questions": [
            {
                "type": "single_choice | true_false | short_answer | matching",
                "difficulty": config.difficulty,
                "cognitive_level": config.cognitive_focus,
                "competency": "Competence evaluee",
                "concept_evaluated": "Notion evaluee",
                "question": "Consigne claire",
                "options": ["Option A", "Option B", "Option C", "Option D"],
                "pairs": [
                    {"left": "Notion 1", "right": "Definition ou idee associee 1"},
                    {"left": "Notion 2", "right": "Definition ou idee associee 2"},
                ],
                "correct_answer": "Reponse correcte ou correction synthetique",
                "explanation": "Explication courte et pedagogique",
                "source_excerpt": "Court extrait source qui justifie la reponse",
                "quality_score": 85,
                "quality_notes": "Pourquoi la question est pertinente",
            }
        ],
    }

    return f"""
MISSION
Generer un quiz de formation de meilleure qualite a partir d'une analyse pedagogique.

OBJECTIF PEDAGOGIQUE
{config.assessment_goal or analysis.get("training_goal", "")}

ANALYSE PEDAGOGIQUE A UTILISER
{json.dumps(analysis, ensure_ascii=False, indent=2)[:3500]}

PARAMETRES
- Langue : francais.
- Public : {config.audience}.
- Niveau : {config.difficulty}.
- Niveau cognitif vise : {config.cognitive_focus}.
- Nombre d'exercices : {config.number_of_questions}.
- Types acceptes : {question_types}.

REGLES QUALITE OBLIGATOIRES
- Chaque question doit evaluer une notion importante identifiee dans l'analyse.
- Chaque question doit avoir une competence evaluee.
- Chaque question doit contenir un extrait source justificatif.
- Evite les questions de pur copier-coller.
- Evite les questions trop evidentes.
- Evite les formulations vagues du type "Que dit le texte ?".
- Pour les QCM, il faut 4 options et une seule bonne reponse.
- Pour les QCM, les mauvaises reponses doivent etre plausibles.
- Pour les Vrai/Faux, l'explication doit justifier clairement la reponse.
- Pour les questions courtes, donne une reponse attendue precise.
- Pour les rapprochements d'idees, cree 3 a 6 paires de type notion-definition, risque-controle, obligation-exemple ou etape-objectif.
- Donne un quality_score entre 0 et 100.
- quality_score doit etre inferieur a 70 si la question est fragile, ambigue ou mal justifiee.
- Retourne uniquement un JSON valide.

SCHEMA JSON ATTENDU
{json.dumps(schema, ensure_ascii=False, indent=2)}

CONTENU SOURCE
{source_text[:3500]}
""".strip()


def generate_with_ollama(source_text: str, config: QuizConfig, analysis: Dict[str, Any]) -> Dict[str, Any]:
    prompt = build_generation_prompt(source_text, config, analysis)
    content = call_ollama(prompt, config, num_predict=1600)
    quiz = parse_json_from_model(content)
    quiz = validate_quiz_shape(quiz)
    quiz["analysis"] = analysis
    quiz["quality_summary"] = build_quality_summary(quiz)
    return quiz


def parse_json_from_model(content: str) -> Dict[str, Any]:
    cleaned = content.strip()
    cleaned = re.sub(r"^```json\s*", "", cleaned)
    cleaned = re.sub(r"^```\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
        if not match:
            raise ValueError("Le modele n'a pas retourne de JSON exploitable.")
        return json.loads(match.group(0))


def validate_analysis_shape(analysis: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(analysis, dict):
        raise ValueError("L'analyse doit etre un objet JSON.")

    analysis.setdefault("training_goal", "")
    analysis.setdefault("key_concepts", [])
    analysis.setdefault("learning_objectives", [])
    analysis.setdefault("recommended_exercises", [])
    analysis.setdefault("quality_risks", [])

    if not isinstance(analysis["key_concepts"], list):
        analysis["key_concepts"] = []
    if not isinstance(analysis["learning_objectives"], list):
        analysis["learning_objectives"] = []
    if not isinstance(analysis["recommended_exercises"], list):
        analysis["recommended_exercises"] = []
    if not isinstance(analysis["quality_risks"], list):
        analysis["quality_risks"] = []

    return analysis


def validate_quiz_shape(quiz: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(quiz, dict):
        raise ValueError("Le quiz doit etre un objet JSON.")

    quiz.setdefault("quiz_title", "Quiz genere")
    quiz.setdefault("analysis_summary", "")
    quiz.setdefault("questions", [])

    if not isinstance(quiz["questions"], list):
        raise ValueError("Le champ questions doit etre une liste.")

    for question in quiz["questions"]:
        if not isinstance(question, dict):
            continue

        question.setdefault("type", "single_choice")
        question.setdefault("difficulty", "")
        question.setdefault("cognitive_level", "")
        question.setdefault("competency", "")
        question.setdefault("concept_evaluated", "")
        question.setdefault("question", "")
        question.setdefault("options", [])
        question.setdefault("pairs", [])
        question.setdefault("correct_answer", "")
        question.setdefault("explanation", "")
        question.setdefault("source_excerpt", "")
        question.setdefault("quality_score", 0)
        question.setdefault("quality_notes", "")

        if not isinstance(question["options"], list):
            question["options"] = []

        if not isinstance(question["pairs"], list):
            question["pairs"] = []

        cleaned_pairs = []
        for pair in question["pairs"]:
            if isinstance(pair, dict):
                cleaned_pairs.append({
                    "left": str(pair.get("left", "")).strip(),
                    "right": str(pair.get("right", "")).strip(),
                })
        question["pairs"] = [p for p in cleaned_pairs if p["left"] or p["right"]]

        if question.get("type") == "matching" and not question.get("correct_answer"):
            question["correct_answer"] = "Voir les paires de correction."

        heuristic_score, heuristic_notes = evaluate_question_quality(question)
        model_score = parse_score(question.get("quality_score", 0))
        final_score = model_score if model_score else heuristic_score
        final_score = min(final_score, heuristic_score + 15)
        question["quality_score"] = max(0, min(100, int(final_score)))

        if not question.get("quality_notes"):
            question["quality_notes"] = heuristic_notes

    return quiz


def parse_score(value: Any) -> int:
    try:
        return int(float(value))
    except Exception:
        return 0


def evaluate_question_quality(question: Dict[str, Any]) -> tuple[int, str]:
    score = 100
    notes = []

    qtype = question.get("type", "")
    text = str(question.get("question", "")).strip()
    explanation = str(question.get("explanation", "")).strip()
    source_excerpt = str(question.get("source_excerpt", "")).strip()
    competency = str(question.get("competency", "")).strip()
    concept = str(question.get("concept_evaluated", "")).strip()

    if len(text) < 25:
        score -= 15
        notes.append("Question courte ou peu precise.")
    if not explanation or len(explanation) < 40:
        score -= 15
        notes.append("Explication trop courte.")
    if not source_excerpt:
        score -= 20
        notes.append("Extrait source absent.")
    if not competency:
        score -= 10
        notes.append("Competence evaluee absente.")
    if not concept:
        score -= 10
        notes.append("Notion evaluee absente.")

    if qtype == "single_choice":
        options = question.get("options") or []
        if len(options) < 4:
            score -= 20
            notes.append("QCM avec moins de 4 options.")
        if not question.get("correct_answer"):
            score -= 15
            notes.append("Reponse correcte absente.")
    elif qtype == "matching":
        pairs = question.get("pairs") or []
        if len(pairs) < 3:
            score -= 25
            notes.append("Rapprochement avec moins de 3 paires.")
    elif qtype == "short_answer":
        if not question.get("correct_answer"):
            score -= 20
            notes.append("Reponse attendue absente.")
    elif qtype == "true_false":
        if len(question.get("options") or []) < 2:
            score -= 10
            notes.append("Options Vrai/Faux absentes.")

    if not notes:
        notes.append("Question structuree et exploitable.")

    return max(0, min(100, score)), " ".join(notes)


def build_quality_summary(quiz: Dict[str, Any]) -> Dict[str, Any]:
    questions = quiz.get("questions", [])
    scores = [parse_score(q.get("quality_score", 0)) for q in questions if isinstance(q, dict)]
    if not scores:
        return {"average_score": 0, "low_quality_count": 0, "warning": "Aucune question evaluee."}

    average = round(sum(scores) / len(scores), 1)
    low = len([s for s in scores if s < 70])

    warning = ""
    if low:
        warning = f"{low} question(s) sont sous le seuil qualite de 70 et doivent etre relues."
    else:
        warning = "Toutes les questions depassent le seuil qualite de 70."

    return {
        "average_score": average,
        "low_quality_count": low,
        "warning": warning,
    }


def demo_analyze_training_content(source_text: str, config: QuizConfig) -> Dict[str, Any]:
    sentences = split_into_sentences(source_text)
    concepts = []
    for i, sentence in enumerate(sentences[:5], start=1):
        concepts.append({
            "concept": f"Notion {i}",
            "definition": shorten(sentence, 140),
            "importance": max(1, 6 - i),
            "question_angle": "Verifier la comprehension de cette notion.",
            "source_excerpt": sentence,
        })

    return {
        "training_goal": config.assessment_goal or "Verifier la comprehension des notions principales du support.",
        "key_concepts": concepts,
        "learning_objectives": [
            {
                "objective": "Identifier et expliquer les notions principales du support.",
                "cognitive_level": config.cognitive_focus,
                "evidence": "L'apprenant repond correctement aux questions et justifie ses choix.",
            }
        ],
        "recommended_exercises": [
            {
                "type": QUESTION_TYPE_LABELS.get(config.question_types[0], "single_choice") if config.question_types else "single_choice",
                "target_concept": "Notions principales",
                "reason": "Type selectionne par le formateur.",
            }
        ],
        "quality_risks": [
            "Le mode demo ne remplace pas une vraie analyse par le modele."
        ],
    }


def demo_generate_quiz(source_text: str, config: QuizConfig, analysis: Dict[str, Any]) -> Dict[str, Any]:
    sentences = split_into_sentences(source_text)
    if not sentences:
        sentences = ["Ajoute un contenu de formation plus detaille pour generer un quiz."]

    questions = []
    selected_types = config.question_types or ["QCM - une seule bonne reponse"]
    concepts = analysis.get("key_concepts", [])

    for i in range(config.number_of_questions):
        sentence = sentences[i % len(sentences)]
        concept = concepts[i % len(concepts)] if concepts else {}
        qtype_label = selected_types[i % len(selected_types)]
        qtype = QUESTION_TYPE_LABELS.get(qtype_label, "single_choice")
        concept_name = concept.get("concept", f"Notion {i + 1}")

        base = {
            "difficulty": config.difficulty,
            "cognitive_level": config.cognitive_focus,
            "competency": "Comprendre et restituer une notion cle du support.",
            "concept_evaluated": concept_name,
            "source_excerpt": sentence,
        }

        if qtype == "true_false":
            question = {
                **base,
                "type": "true_false",
                "question": f"Vrai ou faux : {sentence}",
                "options": ["Vrai", "Faux"],
                "pairs": [],
                "correct_answer": "Vrai",
                "explanation": "En mode demo, la proposition reprend directement une phrase extraite du contenu source.",
            }
        elif qtype == "short_answer":
            question = {
                **base,
                "type": "short_answer",
                "question": f"Explique brievement la notion suivante : {concept_name}",
                "options": [],
                "pairs": [],
                "correct_answer": sentence,
                "explanation": "La reponse attendue doit reformuler l'idee presente dans l'extrait source.",
            }
        elif qtype == "matching":
            chosen = [sentences[(i + j) % len(sentences)] for j in range(min(4, len(sentences)))]
            pairs = []
            for j, item in enumerate(chosen, start=1):
                pairs.append({
                    "left": f"Idee {j}",
                    "right": shorten(item, 140),
                })
            question = {
                **base,
                "type": "matching",
                "question": "Associe chaque idee avec l'affirmation correspondante.",
                "options": [],
                "pairs": pairs,
                "correct_answer": "Chaque idee doit etre associee a l'affirmation correspondante.",
                "explanation": "En mode demo, les paires sont construites a partir de phrases du contenu source.",
            }
        else:
            question = {
                **base,
                "type": "single_choice",
                "question": f"Quelle affirmation correspond le mieux a la notion suivante : {concept_name} ?",
                "options": [
                    sentence,
                    "Une affirmation plausible mais non justifiee par le support.",
                    "Une affirmation trop generale pour etre correcte.",
                    "Une affirmation contraire au contenu source.",
                ],
                "pairs": [],
                "correct_answer": "A",
                "explanation": "En mode demo, l'option A reprend une phrase issue du contenu source.",
            }

        score, notes = evaluate_question_quality(question)
        question["quality_score"] = score
        question["quality_notes"] = notes
        questions.append(question)

    quiz = {
        "quiz_title": "Quiz genere en mode demo",
        "analysis": analysis,
        "analysis_summary": analysis.get("training_goal", ""),
        "questions": questions,
        "note": "Le mode demo sert a tester l'interface. Pour de vrais quiz, utilise Ollama local.",
    }
    quiz["quality_summary"] = build_quality_summary(quiz)
    return quiz


def split_into_sentences(text: str) -> List[str]:
    parts = re.split(r"(?<=[.!?])\s+", text.replace("\n", " "))
    return [p.strip() for p in parts if len(p.strip()) > 40]


def shorten(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - 3].rstrip() + "..."
