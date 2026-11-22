"""Editable bulk-import models for the two interactive card activities.

The column names intentionally match utils.table_import.read_quiz_table:
one spreadsheet row equals one question, no embedded JSON required.
"""
from __future__ import annotations

import csv
import io
from functools import lru_cache


FIELDS = [
    "quiz_title", "training_scope", "question_set_type", "domain", "subdomain",
    "type", "difficulty", "cognitive_level", "learning_objective",
    "competency", "concept_evaluated", "question",
    *(f"item_{i}" for i in range(1, 7)),
    "correct_order",
    *(field for i in range(1, 7) for field in (f"pair_{i}_left", f"pair_{i}_right")),
    "explanation", "remediation", "source_excerpt",
    "case_id", "context_title", "context_text",
]

EXAMPLE_TITLE = "Ateliers interactifs V24 - exemples a adapter"


def _base(**fields: str) -> dict[str, str]:
    row = {key: "" for key in FIELDS}
    row.update({
        "quiz_title": EXAMPLE_TITLE,
        "question_set_type": "Atelier interactif",
        "difficulty": "Intermediaire",
        "cognitive_level": "Application",
        "source_excerpt": "Exemple pedagogique a adapter au support de formation",
    })
    row.update(fields)
    return row


def _order(*items: str, correct_order: str, **fields: str) -> dict[str, str]:
    row = _base(type="ordering", correct_order=correct_order, **fields)
    for i, text in enumerate(items, 1):
        row[f"item_{i}"] = text
    return row


def _match(*pairs: tuple[str, str], **fields: str) -> dict[str, str]:
    row = _base(type="matching", **fields)
    for i, (left, right) in enumerate(pairs, 1):
        row[f"pair_{i}_left"] = left
        row[f"pair_{i}_right"] = right
    return row


def example_rows() -> list[dict[str, str]]:
    """Six independent, non-confidential trainer workshop examples."""
    return [
        _order(
            "Documenter la conclusion",
            "Definir le point a verifier",
            "Recueillir les pieces utiles",
            "Comparer les pieces aux criteres",
            correct_order="BCDA",
            training_scope="Audit SI",
            domain="Controle interne",
            subdomain="Execution d'un controle",
            learning_objective="Reconstruire la sequence d'un controle documente.",
            competency="Conduire un controle de coherence.",
            concept_evaluated="Etapes du controle",
            question="Remets dans l'ordre les etapes d'un controle de coherence d'un dossier.",
            explanation="Definir le point a verifier, recueillir les preuves, les confronter aux criteres puis documenter la conclusion.",
            remediation="Revoir la demarche de controle : objectif, preuves, comparaison, conclusion.",
        ),
        _match(
            ("Risque", "Evenement susceptible d'empecher l'atteinte d'un objectif"),
            ("Controle", "Mesure concue pour maitriser un risque"),
            ("Preuve", "Element verifiable attestant l'execution d'une action"),
            training_scope="Audit SI",
            domain="Controle interne",
            subdomain="Fondamentaux de l'audit",
            learning_objective="Distinguer risque, controle et preuve.",
            competency="Employer le vocabulaire du controle interne.",
            concept_evaluated="Risque / controle / preuve",
            question="Associe chaque notion de controle interne a sa definition.",
            explanation="Le risque est une incertitude a maitriser, le controle est la mesure mise en place et la preuve permet d'en verifier l'execution.",
            remediation="Revoir les notions et illustrer chacune par un dossier d'audit.",
        ),
        _order(
            "Documenter l'incident et les actions",
            "Qualifier l'alerte et mesurer son impact",
            "Detecter l'alerte",
            "Contenir la situation",
            correct_order="CBDA",
            training_scope="SSI",
            domain="Gestion des incidents",
            subdomain="Traitement initial",
            learning_objective="Reconstituer un enchainement operationnel de traitement.",
            competency="Organiser la reaction a un incident.",
            concept_evaluated="Etapes de gestion d'incident",
            question="Classe les principales actions apres la detection d'une alerte de securite.",
            explanation="L'exercice suit un chemin simplifie : detection, qualification, containment, documentation. En pratique, certaines actions peuvent se chevaucher.",
            remediation="Revoir la procedure d'incident de l'organisation et distinguer priorites immediates et compte rendu.",
        ),
        _match(
            ("Responsable du traitement", "Determine les finalites et les moyens du traitement"),
            ("Sous-traitant", "Traite les donnees pour le compte du responsable"),
            ("DPO", "Conseille et controle le respect des obligations de protection des donnees"),
            training_scope="CDPO",
            domain="RGPD",
            subdomain="Roles et responsabilites",
            learning_objective="Identifier les roles dans un traitement de donnees.",
            competency="Distinguer les acteurs RGPD.",
            concept_evaluated="Roles RGPD",
            question="Associe chaque acteur du traitement de donnees a son role.",
            explanation="Le responsable determine le cadre du traitement, le sous-traitant intervient pour son compte et le DPO apporte conseil et controle.",
            remediation="Revoir les roles RGPD et les illustrer par un traitement courant.",
        ),
        _order(
            "Recenser les usages d'intelligence artificielle",
            "Identifier et apprecier les risques",
            "Definir les mesures de maitrise",
            "Suivre leur mise en oeuvre",
            correct_order="ABCD",
            training_scope="Audit IA",
            domain="Gouvernance IA",
            subdomain="Risques et controles",
            learning_objective="Structurer un exercice simple de maitrise des risques IA.",
            competency="Relier usages, risques et mesures de maitrise.",
            concept_evaluated="Cycle de controle des risques",
            question="Remets dans l'ordre ces quatre activites de gestion des risques IA.",
            explanation="Dans ce cas simplifie, l'inventaire des usages nourrit l'analyse des risques, puis les mesures et leur suivi.",
            remediation="Revoir la chaine usages, risques, mesures, suivi et appliquer a un systeme IA connu.",
        ),
        _match(
            ("Actif", "Information ou ressource ayant une valeur a proteger"),
            ("Responsable d'actif", "Role charge de fixer des regles de gestion de la ressource"),
            ("Classification", "Attribution d'un niveau de sensibilite aux informations"),
            training_scope="SSI",
            domain="Gestion des actifs",
            subdomain="Identification et classification",
            learning_objective="Reconnaitre trois notions de gestion des actifs.",
            competency="Rattacher une notion a sa fonction.",
            concept_evaluated="Inventaire et classification",
            question="Associe les notions de gestion des actifs a leur definition.",
            explanation="L'actif est la ressource, le responsable pilote sa gestion, la classification aide a adapter les protections.",
            remediation="Revoir un exemple d'inventaire d'actifs et ses champs de classification.",
        ),
    ]


def interactive_csv_bytes() -> bytes:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=FIELDS, delimiter=";")
    writer.writeheader()
    writer.writerows(example_rows())
    return output.getvalue().encode("utf-8-sig")


@lru_cache(maxsize=1)
def interactive_xlsx_bytes() -> bytes:
    from openpyxl import Workbook
    from openpyxl.comments import Comment
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.worksheet.datavalidation import DataValidation

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Questions"
    sheet.sheet_view.showGridLines = False
    sheet.append(FIELDS)
    for row in example_rows():
        sheet.append([row[field] for field in FIELDS])

    forest = "06472F"
    sage = "EAF3EC"
    ivory = "FAF9F2"
    blue = "205EAA"
    white = "FFFFFF"
    groups = {
        "type": "ordering ou matching",
        "correct_order": "Pour ordering : sequence des lettres A, B, C... dans l'ordre attendu (ex. BCDA)",
        "question": "Enonce presente a l'apprenant",
        "remediation": "Conseils de revision presentes apres la correction",
        "training_scope": "Formation ou parcours (ex. CDPO, SSI, Audit SI)",
        "domain": "Domaine de formation",
        "subdomain": "Sous-domaine ou theme",
        "quiz_title": "Nom du lot importe (identique pour toutes les lignes d'un lot)",
    }
    for column, field in enumerate(FIELDS, 1):
        cell = sheet.cell(1, column)
        cell.fill = PatternFill("solid", fgColor=forest)
        cell.font = Font(name="Aptos", size=10, color=white, bold=True)
        cell.alignment = Alignment(vertical="center", wrap_text=True)
        cell.comment = Comment(groups.get(field, "Champ du fichier d'import V23"), "Quiz Formation")
        letter = cell.column_letter
        width = 35 if field in {"question", "explanation", "remediation", "source_excerpt", "context_text"} else 24
        if field.startswith("item_") or field.startswith("pair_"):
            width = 34
        if field in {"type", "difficulty", "correct_order"}:
            width = 18
        sheet.column_dimensions[letter].width = width
    sheet.row_dimensions[1].height = 37
    for row_index in range(2, sheet.max_row + 1):
        sheet.row_dimensions[row_index].height = 66
        for cell in sheet[row_index]:
            cell.fill = PatternFill("solid", fgColor=white if row_index % 2 == 0 else sage)
            cell.font = Font(name="Aptos", size=10, color=blue)
            cell.alignment = Alignment(vertical="top", wrap_text=True)
    sheet.freeze_panes = "D2"
    sheet.auto_filter.ref = f"A1:{sheet.cell(1, len(FIELDS)).column_letter}{sheet.max_row}"

    types = DataValidation(type="list", formula1='"ordering,matching"', allow_blank=False)
    types.error = "Choisir ordering ou matching."
    types.errorTitle = "Type de question"
    types.showErrorMessage = True
    sheet.add_data_validation(types)
    type_column = FIELDS.index("type") + 1
    type_letter = sheet.cell(1, type_column).column_letter
    types.add(f"{type_letter}2:{type_letter}2000")

    guide = workbook.create_sheet("Mode d'emploi")
    guide.sheet_view.showGridLines = False
    guide.column_dimensions["A"].width = 30
    guide.column_dimensions["B"].width = 95
    instructions = [
        ("MODELE ATELIERS V24", "Ordonnancement et appariement. Une ligne dans l'onglet Questions = une question."),
        ("1 - Dupliquer", "Dans Questions, duplique une ligne d'exemple ou ajoute une nouvelle ligne a partir de la ligne 8."),
        ("2 - Choisir", "Renseigne type = ordering OU matching. Les autres types sont traites par le modele industriel general."),
        ("3 - Taxonomie", "Renseigne training_scope (formation), domain, subdomain, question_set_type et les objectifs pedagogiques."),
        ("4 - Ordre", "Pour ordering, renseigne item_1, item_2... dans un ordre de saisie quelconque. correct_order contient les LETTRES attendues, par ex. BCDA."),
        ("5 - Appariement", "Pour matching, renseigne pair_1_left, pair_1_right, etc. Chaque association occupe une paire de colonnes."),
        ("6 - Correction", "Renseigne explanation (raisonnement) et remediation (conseils de revision). source_excerpt sert a tracer la source."),
        ("7 - Charger", "Espace formateur > 1. Source > Import industriel > Fichier de questions a importer > Analyser le fichier."),
        ("8 - Verifier", "Consulte le rapport de controle. Previsualise les ateliers sans enregistrer, puis ajoute directement a la banque."),
        ("9 - Utiliser", "Constitue un quiz depuis la banque de questions ou charge les exercices dans Quiz createur."),
        ("Attention", "N'utilise pas de cellules fusionnees ni de lignes de titres au-dessus des noms de colonnes dans Questions."),
        ("Capacite", "Jusqu'a 6 elements ou 6 paires dans ce modele. D'autres lignes/questions peuvent etre ajoutees librement."),
    ]
    for i, (title, description) in enumerate(instructions, 1):
        guide.cell(i, 1, title)
        guide.cell(i, 2, description)
        guide.row_dimensions[i].height = 36 if i > 1 else 46
        for cell in guide[i]:
            cell.alignment = Alignment(vertical="center", wrap_text=True)
            cell.fill = PatternFill("solid", fgColor=forest if i == 1 else (ivory if i % 2 else sage))
            cell.font = Font(name="Aptos", size=12 if i == 1 else 11, bold=cell.column == 1, color=white if i == 1 else forest)
    guide.freeze_panes = "A2"
    stream = io.BytesIO()
    workbook.save(stream)
    return stream.getvalue()
