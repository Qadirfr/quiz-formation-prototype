"""One-row-per-question Excel/CSV templates for image clickable-zone quizzes."""
from __future__ import annotations

import csv
import io
from functools import lru_cache


HEADERS = [
    "quiz_title", "training_scope", "question_set_type", "domain", "subdomain",
    "difficulty", "learning_objective", "type", "question",
    "media_type", "media_url", "media_caption", "explanation",
    "remediation", "source_excerpt",
    *(name for i in range(1, 7) for name in (
        f"zone_{i}_label", f"zone_{i}_x", f"zone_{i}_y",
        f"zone_{i}_w", f"zone_{i}_h", f"zone_{i}_correct",
        f"zone_{i}_feedback",
    )),
]
BASE_URL = (
    "https://raw.githubusercontent.com/Qadirfr/quiz-formation-prototype/"
    "diagnostic-performance-v23/assets/"
)


def _row(**fields: str) -> dict[str, str]:
    row = {key: "" for key in HEADERS}
    row.update({
        "quiz_title": "Lot 4 — Repérage visuel sur image",
        "question_set_type": "Atelier interactif",
        "difficulty": "Intermédiaire",
        "type": "image_hotspot",
        "media_type": "image",
        "source_excerpt": "Capture fictive créée pour l'exercice pédagogique",
    })
    row.update(fields)
    return row


def example_rows() -> list[dict[str, str]]:
    return [
        _row(
            training_scope="SSI", domain="Contrôles SSI",
            subdomain="Gestion des comptes privilégiés",
            learning_objective="Repérer une anomalie à investiguer dans un tableau de bord SSI",
            question="Dans ce tableau de bord, clique sur l'indicateur qui révèle une anomalie de gestion des habilitations.",
            media_url=BASE_URL + "demo_hotspot_ssi.svg",
            media_caption="Tableau de bord SSI fictif",
            zone_1_label="MFA utilisateurs", zone_1_x="5", zone_1_y="34",
            zone_1_w="28", zone_1_h="35", zone_1_correct="false",
            zone_1_feedback="Le MFA est largement déployé. Cet indicateur n'est pas l'écart recherché.",
            zone_2_label="Comptes privilégiés inactifs encore habilités",
            zone_2_x="35", zone_2_y="34", zone_2_w="29", zone_2_h="35",
            zone_2_correct="true",
            zone_2_feedback="Douze comptes inactifs restent habilités. Il faut examiner leur désactivation et la revue des accès.",
            zone_3_label="Sauvegardes",
            zone_3_x="67", zone_3_y="34", zone_3_w="28", zone_3_h="35",
            zone_3_correct="false",
            zone_3_feedback="L'indicateur de sauvegarde est déclaré satisfaisant. Vérifier les tests peut rester pertinent mais ce n'est pas l'anomalie affichée.",
            explanation="L'inactivité des comptes privilégiés ne justifie pas leur maintien indéfini. Une analyse des habilitations est nécessaire.",
            remediation="Revoir le cycle de vie des identités, les revues d'accès et la suppression des comptes inutiles.",
        ),
        _row(
            training_scope="CDPO", domain="RGPD",
            subdomain="Registre des traitements",
            learning_objective="Identifier une information obligatoire absente du registre",
            question="Clique sur la rubrique incomplète de ce registre des traitements.",
            media_url=BASE_URL + "demo_hotspot_rgpd.svg",
            media_caption="Registre fictif de gestion des réclamations",
            zone_1_label="Finalité", zone_1_x="5", zone_1_y="35",
            zone_1_w="28", zone_1_h="36", zone_1_correct="false",
            zone_1_feedback="La finalité est renseignée. Elle reste à apprécier mais n'est pas absente.",
            zone_2_label="Base légale non renseignée", zone_2_x="35",
            zone_2_y="35", zone_2_w="29", zone_2_h="36",
            zone_2_correct="true",
            zone_2_feedback="La base légale manque. Elle doit être déterminée et documentée dans le registre.",
            zone_3_label="Durée de conservation", zone_3_x="67",
            zone_3_y="35", zone_3_w="28", zone_3_h="36",
            zone_3_correct="false",
            zone_3_feedback="Une durée de conservation est déjà indiquée dans l'extrait.",
            explanation="Le registre doit décrire les traitements et les bases légales doivent être identifiées dans la documentation de conformité.",
            remediation="Vérifier les finalités, bases légales et durées de conservation, ainsi que la cohérence avec les notices d'information.",
        ),
    ]


def hotspot_csv_bytes() -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=HEADERS, delimiter=";")
    writer.writeheader()
    writer.writerows(example_rows())
    return buffer.getvalue().encode("utf-8-sig")


@lru_cache(maxsize=1)
def hotspot_xlsx_bytes() -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment, PatternFill
    from openpyxl.comments import Comment
    from openpyxl.worksheet.datavalidation import DataValidation

    wb = Workbook()
    ws = wb.active
    ws.title = "Questions"
    ws.sheet_view.showGridLines = False
    ws.append(HEADERS)
    for row in example_rows():
        ws.append([row.get(field, "") for field in HEADERS])
    for j, name in enumerate(HEADERS, start=1):
        cell = ws.cell(1, j)
        cell.fill = PatternFill("solid", fgColor="174A35")
        cell.font = Font(color="FFFFFF", bold=True)
        cell.alignment = Alignment(wrap_text=True)
        ws.column_dimensions[cell.column_letter].width = (
            50 if "feedback" in name or name in {"question", "explanation", "remediation"}
            else 22 if name not in {"media_url"} else 76
        )
        if name.endswith(("_x", "_y", "_w", "_h")):
            cell.comment = Comment(
                "Valeur de 0 à 100 en pourcentage de l'image. "
                "x/y = coin supérieur gauche, w/h = largeur et hauteur.", "Quiz Formation"
            )
    ws.row_dimensions[1].height = 38
    for row_index in range(2, ws.max_row + 1):
        ws.row_dimensions[row_index].height = 76
        for cell in ws[row_index]:
            cell.alignment = Alignment(wrap_text=True, vertical="top")
            cell.fill = PatternFill(
                "solid", fgColor="F0F7F2" if row_index % 2 else "FFFFFF"
            )
    ws.freeze_panes = "I2"
    ws.auto_filter.ref = ws.dimensions
    status = DataValidation(type="list", formula1='"true,false"')
    ws.add_data_validation(status)
    for i in range(1, 7):
        col = ws.cell(1, HEADERS.index(f"zone_{i}_correct") + 1).column_letter
        status.add(f"{col}2:{col}2000")
    guide = wb.create_sheet("Mode d'emploi")
    guide.sheet_view.showGridLines = False
    guide.column_dimensions["A"].width = 32
    guide.column_dimensions["B"].width = 105
    instructions = [
        ("LOT 4 — ZONES CLIQUABLES", "Une ligne par question. Le fichier contient deux exemples que tu peux remplacer."),
        ("Type", "Conserver type = image_hotspot. Les autres types de la banque restent inchangés."),
        ("Image", "media_url : URL HTTP/HTTPS de l'image. Pour une image privée, téléverse-la plutôt dans Création manuelle."),
        ("Coordonnées", "x et y sont les pourcentages du coin haut gauche. w et h sont la largeur et la hauteur en pourcentage."),
        ("Zones", "zone_1 à zone_6 : label, x, y, w, h, correct, feedback."),
        ("Correction", "Au moins une zone doit être correcte. Les zones ne doivent pas se chevaucher."),
        ("Clic apprenant", "Un clic sur l'image, puis validation. Le score est automatique et la correction s'affiche après validation."),
        ("Révision", "explanation explique l'objectif ; remediation propose une reprise de la notion."),
        ("Importer", "Espace formateur > 1. Source > Import industriel > Analyser le fichier."),
        ("Prévisualiser", "Tester comme apprenti avant l'ajout à la banque de questions."),
        ("Attention", "Les exemples pointent vers les deux images de démonstration de la branche V23."),
    ]
    for i, (name, desc) in enumerate(instructions, start=1):
        guide.cell(i, 1, name)
        guide.cell(i, 2, desc)
        guide.row_dimensions[i].height = 44
        for cell in guide[i]:
            cell.alignment = Alignment(wrap_text=True, vertical="center")
            cell.fill = PatternFill("solid", fgColor="174A35" if i == 1 else
                                    "F0F7F2" if i % 2 == 0 else "FFFFFF")
            cell.font = Font(bold=cell.column == 1, color="FFFFFF" if i == 1 else "174A35")
    guide.freeze_panes = "A2"
    output = io.BytesIO()
    wb.save(output)
    return output.getvalue()
