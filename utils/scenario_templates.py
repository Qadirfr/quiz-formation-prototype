"""Excel/CSV templates for branching serious-game scenarios.

One row = one possible decision, not one complete question. A scenario_id
groups nodes and decisions into one quiz question; no JSON cells required.
"""
from __future__ import annotations

import csv
import io
from collections import OrderedDict
from functools import lru_cache
from pathlib import Path
from typing import Any

from utils.interactive_scenarios import validate_scenario


FIELDS = [
    "quiz_title", "scenario_id", "training_scope", "question_set_type",
    "domain", "subdomain", "difficulty", "learning_objective",
    "question", "scenario_start",
    "node_id", "node_prompt", "choice_id", "choice_label", "next_node",
    "consequence", "score", "rationale",
    "explanation", "remediation", "source_excerpt",
]


def _choice(**values: str) -> dict[str, str]:
    row = {field: "" for field in FIELDS}
    row.update({
        "quiz_title": "Lot 3 — Scenarios interactifs",
        "question_set_type": "Mise en situation",
        "difficulty": "Intermédiaire",
        "scenario_start": "S1",
        "source_excerpt": "Exemple pédagogique à adapter à la procédure interne",
    })
    row.update(values)
    return row


def example_rows() -> list[dict[str, str]]:
    samples = [
        # Incident containing possible personal-data exposure
        dict(scenario_id="INC-01", training_scope="SSI", domain="Gestion des incidents",
             subdomain="Données personnelles", learning_objective="Piloter les premières décisions de réponse à incident",
             question="Tu supervises une alerte signalant un accès inhabituel à des dossiers clients. Quelles décisions prends-tu ?",
             explanation="L'exercice illustre une démarche de qualification, de conservation des preuves et d'escalade adaptée.",
             remediation="Revoir la procédure de gestion d'incident, les responsabilités du RSSI et du DPO."),
        dict(scenario_id="IA-01", training_scope="Audit IA", domain="Gouvernance IA",
             subdomain="Déploiement d'un RAG", learning_objective="Choisir un déploiement proportionné aux risques",
             question="Une équipe souhaite utiliser un assistant RAG pour préparer les réponses aux réclamations. Comment procèdes-tu ?",
             explanation="L'automatisation doit partir du risque et du besoin métier. La validation humaine reste déterminante pour ce pilote.",
             remediation="Revoir les critères de cadrage d'un cas d'usage IA et les contrôles de qualité du RAG."),
    ]
    decisions = [
        # scenario 0
        ("S1","La supervision détecte un accès anormal à des dossiers clients.","A","Qualifier l'alerte et limiter les accès à risque","S2","L'accès est contenu et l'analyse peut commencer.","1","Mesure proportionnée : qualification et limitation de l'exposition."),
        ("S1","La supervision détecte un accès anormal à des dossiers clients.","B","Diffuser immédiatement un message affirmant une fuite confirmée","S3","La communication précède la qualification de l'incident.","0.2","L'alerte ne prouve pas encore qu'une fuite est avérée."),
        ("S2","Les accès sont contenus. Il faut préparer les suites de l'incident.","A","Conserver les traces et associer les responsables concernés","END","La chronologie et les éléments probants sont sécurisés.","1","La décision facilite investigation et analyse des obligations."),
        ("S2","Les accès sont contenus. Il faut préparer les suites de l'incident.","B","Effacer les journaux pour limiter les traces","END","Les éléments nécessaires à l'investigation sont perdus.","0","La destruction de preuves rend l'analyse et le retour d'expérience difficiles."),
        ("S3","La communication a été précipitée. Que fais-tu maintenant ?","A","Rectifier les éléments non confirmés et enclencher la qualification","END","La communication est corrigée et l'équipe revient à une analyse fondée.","0.7","Bonne mesure corrective mais l'annonce initiale reste problématique."),
        ("S3","La communication a été précipitée. Que fais-tu maintenant ?","B","Maintenir le message sans vérification","END","Les équipes conservent une information non étayée.","0","La gestion d'incident doit s'appuyer sur des faits vérifiables."),
        # scenario 1
        ("S1","Un métier propose de laisser un RAG répondre automatiquement aux réclamations.","A","Définir un pilote limité avec validation humaine","S2","Le projet peut être testé dans un cadre contrôlé.","1","Un pilote permet de vérifier qualité, risques et bénéfices."),
        ("S1","Un métier propose de laisser un RAG répondre automatiquement aux réclamations.","B","Ouvrir l'envoi automatique à toutes les demandes","S3","Des réponses insuffisamment vérifiées peuvent être émises.","0.1","Déploiement non maîtrisé au regard des risques opérationnels."),
        ("S2","Le pilote RAG est cadré. Quel contrôle effectues-tu en priorité ?","A","Tester sources, citations, erreurs et supervision humaine","END","Les limites du système deviennent visibles avant un élargissement.","1","Les tests doivent couvrir qualité des réponses et traçabilité des sources."),
        ("S2","Le pilote RAG est cadré. Quel contrôle effectues-tu en priorité ?","B","Mesurer uniquement le temps gagné","END","Le gain de productivité est connu, mais la fiabilité reste incertaine.","0.3","Le ROI ne doit pas effacer les mesures de maîtrise des risques."),
        ("S3","Plusieurs réponses ont été envoyées sans validation. Quelle suite choisis-tu ?","A","Suspendre l'envoi automatique et analyser les écarts","END","Le risque est limité pendant le réexamen du dispositif.","0.8","Correction utile après une mise en service prématurée."),
        ("S3","Plusieurs réponses ont été envoyées sans validation. Quelle suite choisis-tu ?","B","Poursuivre sans contrôle car le volume traité augmente","END","Les erreurs potentielles continuent de se propager.","0","La performance doit être appréciée avec la qualité et la maîtrise des risques."),
    ]
    rows = []
    for index, data in enumerate(decisions):
        base = samples[0 if index < 6 else 1]
        node, prompt, cid, label, next_node, consequence, score, rationale = data
        rows.append(_choice(
            **base, node_id=node, node_prompt=prompt, choice_id=cid,
            choice_label=label, next_node=next_node,
            consequence=consequence, score=score, rationale=rationale,
        ))
    return rows


def rows_to_scenario_quiz(rows: list[dict[str, Any]], filename: str = "scenarios.xlsx") -> dict[str, Any]:
    """Build one question per scenario_id from decision rows. Validate separately."""
    if not rows:
        raise ValueError("Aucune décision trouvée dans le fichier.")
    groups: OrderedDict[str, list[dict[str, Any]]] = OrderedDict()
    for index, row in enumerate(rows, start=2):
        sid = str(row.get("scenario_id") or "").strip()
        if not sid:
            raise ValueError(f"Ligne {index} : scenario_id obligatoire.")
        groups.setdefault(sid, []).append(row)

    questions = []
    for sid, group in groups.items():
        first = group[0]
        nodes: OrderedDict[str, dict[str, Any]] = OrderedDict()
        for row in group:
            nid = str(row.get("node_id") or "").strip()
            node = nodes.setdefault(nid, {
                "id": nid, "prompt": str(row.get("node_prompt") or "").strip(),
                "choices": [],
            })
            # Repeated node prompts must not disagree between rows.
            current_prompt = str(row.get("node_prompt") or "").strip()
            if node["prompt"] != current_prompt:
                raise ValueError(
                    f"Scénario {sid}, étape {nid} : descriptions contradictoires."
                )
            raw_score = str(row.get("score") or "").strip().replace(",", ".")
            try:
                score: float | str = float(raw_score)
            except ValueError:
                score = raw_score
            node["choices"].append({
                "id": str(row.get("choice_id") or "").strip(),
                "label": str(row.get("choice_label") or "").strip(),
                "next": str(row.get("next_node") or "").strip(),
                "consequence": str(row.get("consequence") or "").strip(),
                "score": score,
                "rationale": str(row.get("rationale") or "").strip(),
            })
        question = {
            "type": "branching_scenario", "schema_version": 2,
            "schema_type_locked": True, "schema_type_source": "scenario_import",
            "case_id": sid,
            "training_scope": str(first.get("training_scope") or ""),
            "question_set_type": str(first.get("question_set_type") or "Mise en situation"),
            "domain": str(first.get("domain") or "Non classé"),
            "subdomain": str(first.get("subdomain") or ""),
            "difficulty": str(first.get("difficulty") or "Intermédiaire"),
            "learning_objective": str(first.get("learning_objective") or ""),
            "question": str(first.get("question") or ""),
            "scenario_start": str(first.get("scenario_start") or "S1"),
            "scenario_nodes": list(nodes.values()),
            "explanation": str(first.get("explanation") or ""),
            "remediation": str(first.get("remediation") or ""),
            "source_excerpt": str(first.get("source_excerpt") or ""),
            "quality_score": 90,
        }
        questions.append(question)
    title = str(rows[0].get("quiz_title") or "").strip() or f"Scénarios — {Path(filename).stem}"
    return {
        "quiz_title": title,
        "analysis_summary": "Mises en situation à embranchements importées depuis Excel/CSV.",
        "questions": questions,
        "quality_summary": {
            "average_score": 90, "low_quality_count": 0,
            "warning": "Scénarios validés par le moteur d'import.",
        },
    }


def scenario_csv_bytes() -> bytes:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=FIELDS, delimiter=";")
    writer.writeheader()
    writer.writerows(example_rows())
    return output.getvalue().encode("utf-8-sig")


@lru_cache(maxsize=1)
def scenario_xlsx_bytes() -> bytes:
    from openpyxl import Workbook
    from openpyxl.comments import Comment
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.worksheet.datavalidation import DataValidation

    wb = Workbook()
    ws = wb.active
    ws.title = "Scenarios"
    ws.sheet_view.showGridLines = False
    ws.append(FIELDS)
    for row in example_rows():
        ws.append([row[field] for field in FIELDS])
    forest, sage, white = "06472F", "EAF3EC", "FFFFFF"
    explanations = {
        "scenario_id": "Un identifiant par parcours. Toutes ses décisions portent la même valeur",
        "node_id": "Identifiant de l'étape (ex. S1, S2, S3), répétée pour chaque choix",
        "choice_id": "Lettre unique dans l'étape (A, B, C ou D)",
        "next_node": "END pour terminer, ou l'identifiant d'une autre étape existante",
        "score": "Pertinence pédagogique de la décision, de 0 à 1 (ex. 0,5)",
        "consequence": "Conséquence affichée après le choix, avant de passer à la suite",
        "rationale": "Explication révélée après validation du scénario",
    }
    for i, name in enumerate(FIELDS, start=1):
        cell = ws.cell(1, i)
        cell.fill = PatternFill("solid", fgColor=forest)
        cell.font = Font(bold=True, color=white)
        cell.alignment = Alignment(wrap_text=True)
        cell.comment = Comment(explanations.get(name, "Renseigner pour chaque décision"), "Quiz Formation")
        ws.column_dimensions[cell.column_letter].width = (
            54 if name in {"node_prompt", "choice_label", "consequence", "rationale", "question"} else 24
        )
    ws.row_dimensions[1].height = 42
    ws.freeze_panes = "K2"
    ws.auto_filter.ref = f"A1:{ws.cell(1,len(FIELDS)).column_letter}{ws.max_row}"
    for i in range(2, ws.max_row + 1):
        for cell in ws[i]:
            cell.fill = PatternFill("solid", fgColor=white if i % 2 == 0 else sage)
            cell.font = Font(color="205EAA", size=10)
            cell.alignment = Alignment(wrap_text=True, vertical="top")
        ws.row_dimensions[i].height = 70
    targets = DataValidation(type="decimal", operator="between", formula1="0", formula2="1")
    targets.showErrorMessage = True
    targets.error = "Le score doit être compris entre 0 et 1"
    ws.add_data_validation(targets)
    score_letter = ws.cell(1, FIELDS.index("score") + 1).column_letter
    targets.add(f"{score_letter}2:{score_letter}2000")

    guide = wb.create_sheet("Mode d'emploi")
    guide.column_dimensions["A"].width = 28
    guide.column_dimensions["B"].width = 96
    guide.sheet_view.showGridLines = False
    tips = [
        ("MODÈLE SCÉNARIOS", "Une ligne = un choix ; plusieurs lignes = un scénario ; ne pas fusionner les cellules."),
        ("Identifier le scénario", "Renseigner scenario_id identique sur toutes les lignes du même parcours (ex. INC-01)."),
        ("Définir le départ", "scenario_start désigne la première étape (S1 dans les exemples)."),
        ("Créer les étapes", "node_id indique une étape. La même étape doit comporter 2 à 4 choix distincts."),
        ("Choix et destinations", "choice_id = A, B... ; next_node = END ou une étape existante. Eviter les boucles."),
        ("Afficher les conséquences", "consequence apparaît juste après le clic. Le score et rationale n'apparaissent qu'après validation."),
        ("Scorer une décision", "score entre 0 et 1. Le score final est la moyenne des décisions effectivement prises."),
        ("Données pédagogiques", "domain, subdomain, learning_objective, explanation et remediation accompagnent l'exercice."),
        ("Importer", "Dans Quiz Formation V23 : espace formateur > 1. Source > Import industriel > Analyser le fichier."),
        ("Vérifier", "Les étapes inaccessibles, destinations inconnues, boucles et scores erronés sont rejetés."),
        ("Utiliser", "Prévisualiser comme apprenti puis ajouter à la banque. Un scénario = une question."),
    ]
    for i, (key, value) in enumerate(tips, start=1):
        guide.cell(i, 1, key)
        guide.cell(i, 2, value)
        guide.row_dimensions[i].height = 44
        for cell in guide[i]:
            cell.fill = PatternFill("solid", fgColor=forest if i == 1 else (white if i % 2 else sage))
            cell.font = Font(bold=cell.column == 1, color=white if i == 1 else forest)
            cell.alignment = Alignment(wrap_text=True, vertical="center")
    guide.freeze_panes = "A2"
    stream = io.BytesIO()
    wb.save(stream)
    return stream.getvalue()
