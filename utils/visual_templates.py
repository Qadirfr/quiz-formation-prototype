"""Bulk XLSX/CSV template for visually identifying anomalies or components.

One row = a clickable region. Each visual_id groups a small number of
regions into one question. Image URL uses the existing V23 media mechanism.
"""
from __future__ import annotations

import csv
from collections import OrderedDict
from functools import lru_cache
from io import BytesIO, StringIO
from pathlib import Path
from typing import Any


FIELDS = [
    "quiz_title", "visual_id", "training_scope", "question_set_type",
    "domain", "subdomain", "difficulty", "learning_objective",
    "question", "image_url", "media_caption", "media_alt_text",
    "zone_id", "zone_label", "x_pct", "y_pct", "radius_pct",
    "is_target", "zone_feedback",
    "explanation", "remediation", "source_excerpt",
]


def _row(**data: str) -> dict[str, str]:
    row = {field: "" for field in FIELDS}
    row.update({"quiz_title": "Lot 4 — Analyse visuelle",
                "question_set_type": "Repérage sur image",
                "difficulty": "Intermédiaire"})
    row.update(data)
    return row


def example_rows() -> list[dict[str, str]]:
    samples = [
        dict(visual_id="VIS-SSI-01", training_scope="SSI",
             domain="Architecture SSI", subdomain="Réseau et sauvegardes",
             question="Repère deux points de vigilance sur cette architecture SI.",
             learning_objective="Localiser des risques sur un schéma d'architecture.",
             image_url="demo:network",
             media_caption="Schéma fictif simplifié d'un système d'information",
             media_alt_text="Internet, application, données et sauvegarde reliés par des flux.",
             explanation="Les flux et la stratégie de restauration doivent être vérifiés au regard des risques.",
             remediation="Revoir la segmentation, les flux autorisés, les sauvegardes et tests de restauration.",
             source_excerpt="Exemple pédagogique construit pour le lot 4"),
        dict(visual_id="VIS-RGPD-01", training_scope="CDPO",
             domain="RGPD", subdomain="Flux et conservation",
             question="Clique sur les deux traitements qui présentent un risque de protection des données.",
             learning_objective="Identifier des risques de transmission et de conservation.",
             image_url="demo:gdpr",
             media_caption="Schéma fictif d'un parcours de données personnelles",
             media_alt_text="Collecte, traitement, export et archivage des données.",
             explanation="Les mesures de protection et durées de conservation doivent être adaptées aux risques.",
             remediation="Revoir sécurité du traitement, limitation de conservation et minimisation.",
             source_excerpt="Exemple pédagogique construit pour le lot 4"),
    ]
    zones = [
        (0, "Z1", "Échange application → base", 67.5, 29, 9, True,
         "Un accès direct aux données nécessite de vérifier segmentation, habilitations et flux."),
        (0, "Z2", "Sauvegarde non testée", 50.5, 53, 9, True,
         "Une sauvegarde doit s'accompagner de tests de restauration documentés."),
        (0, "Z3", "Formulaire public", 15, 29, 8, False,
         "Une exposition Internet n'est pas automatiquement un écart si les protections sont adaptées."),
        (1, "Z1", "Export non protégé", 67.5, 32, 9, True,
         "La transmission d'un fichier sensible sans protection adaptée crée un risque de divulgation."),
        (1, "Z2", "Durée de conservation excessive", 50.5, 54, 9, True,
         "La conservation doit être justifiée et limitée à une durée nécessaire."),
        (1, "Z3", "Collecte d'informations", 15, 31, 8, False,
         "La collecte n'est pas un écart en soi ; il faut examiner la base légale et la minimisation."),
    ]
    result = []
    for sample_idx, zid, label, x, y, radius, target, feedback in zones:
        result.append(_row(**samples[sample_idx], zone_id=zid, zone_label=label,
                           x_pct=str(x), y_pct=str(y), radius_pct=str(radius),
                           is_target="true" if target else "false",
                           zone_feedback=feedback))
    return result


def _yes_no(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    token = str(value or "").strip().casefold()
    if token in {"true", "vrai", "oui", "yes", "1"}:
        return True
    if token in {"false", "faux", "non", "no", "0"}:
        return False
    return None


def rows_to_visual_quiz(rows: list[dict[str, Any]],
                        filename: str = "analyse_visuelle.xlsx") -> dict[str, Any]:
    if not rows:
        raise ValueError("Le fichier ne contient aucune zone visuelle.")
    groups: OrderedDict[str, list[dict[str, Any]]] = OrderedDict()
    for line_no, row in enumerate(rows, 2):
        visual_id = str(row.get("visual_id") or "").strip()
        if not visual_id:
            raise ValueError(f"Ligne {line_no} : visual_id est obligatoire.")
        groups.setdefault(visual_id, []).append(row)
    questions = []
    for vid, group in groups.items():
        first = group[0]
        nodes = []
        for row in group:
            if str(row.get("image_url") or "") != str(first.get("image_url") or ""):
                raise ValueError(f"Exercice {vid} : les lignes ne portent pas la même image.")
            if str(row.get("question") or "") != str(first.get("question") or ""):
                raise ValueError(f"Exercice {vid} : consignes contradictoires.")
            def num(field: str) -> float | str:
                raw = str(row.get(field) or "").strip().replace(",", ".")
                try:
                    return float(raw)
                except (TypeError, ValueError):
                    return raw
            nodes.append({
                "id": str(row.get("zone_id") or "").strip(),
                "label": str(row.get("zone_label") or "").strip(),
                "x_pct": num("x_pct"), "y_pct": num("y_pct"),
                "radius_pct": num("radius_pct"),
                "is_target": _yes_no(row.get("is_target")),
                "feedback": str(row.get("zone_feedback") or "").strip(),
            })
        questions.append({
            "type": "image_hotspots", "schema_version": 2,
            "schema_type_locked": True, "schema_type_source": "visual_import",
            "training_scope": first.get("training_scope") or "",
            "question_set_type": first.get("question_set_type") or "Repérage sur image",
            "case_id": vid,
            "domain": first.get("domain") or "Non classé",
            "subdomain": first.get("subdomain") or "",
            "difficulty": first.get("difficulty") or "Intermédiaire",
            "learning_objective": first.get("learning_objective") or "",
            "question": first.get("question") or "",
            "media": {
                "type": "image",
                "url": first.get("image_url") or "",
                "caption": first.get("media_caption") or "",
                "alt_text": first.get("media_alt_text") or "",
            },
            "hotspots": nodes,
            "explanation": first.get("explanation") or "",
            "remediation": first.get("remediation") or "",
            "source_excerpt": first.get("source_excerpt") or "",
            "quality_score": 90,
        })
    return {
        "quiz_title": str(rows[0].get("quiz_title") or "") or f"Analyse visuelle — {Path(filename).stem}",
        "questions": questions,
        "analysis_summary": "Questions de repérage sur images importées par zones.",
        "quality_summary": {"average_score": 90, "low_quality_count": 0,
                            "warning": "Analyse visuelle structurée depuis les zones importées."},
    }


def visual_csv_bytes() -> bytes:
    output = StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=FIELDS, delimiter=";")
    writer.writeheader()
    writer.writerows(example_rows())
    return output.getvalue().encode("utf-8-sig")


@lru_cache(maxsize=1)
def visual_xlsx_bytes() -> bytes:
    from openpyxl import Workbook
    from openpyxl.comments import Comment
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.worksheet.datavalidation import DataValidation
    wb = Workbook()
    ws = wb.active
    ws.title = "Zones"
    ws.sheet_view.showGridLines = False
    ws.append(FIELDS)
    for row in example_rows():
        ws.append([row[k] for k in FIELDS])
    explanations = {
        "visual_id": "Identifiant commun aux zones appartenant à la même question",
        "image_url": "URL HTTPS accessible, ou demo:network / demo:gdpr pour les exemples",
        "zone_id": "Z1, Z2, Z3... Identifiant unique par question",
        "zone_label": "Libellé de la zone à repérer ou du leurre",
        "x_pct": "Centre horizontal en pourcentage de 0 à 100, mesuré depuis la gauche",
        "y_pct": "Centre vertical en pourcentage de 0 à 100, mesuré depuis le haut",
        "radius_pct": "Tolérance de clic en pourcentage (2 à 25)",
        "is_target": "true pour une anomalie à trouver, false pour un distracteur",
        "zone_feedback": "Explication pédagogique liée à cette zone",
    }
    green, pale = "06472F", "EAF3EC"
    for j, field in enumerate(FIELDS, 1):
        cell = ws.cell(1, j)
        cell.fill = PatternFill("solid", fgColor=green)
        cell.font = Font(color="FFFFFF", bold=True)
        cell.alignment = Alignment(wrap_text=True, vertical="center")
        cell.comment = Comment(explanations.get(field, "Conserver le nom de cette colonne"),
                               "Quiz Formation")
        ws.column_dimensions[cell.column_letter].width = (
            55 if field in {"question", "zone_feedback", "explanation", "remediation"} else 26
        )
    ws.row_dimensions[1].height = 42
    for i in range(2, ws.max_row+1):
        ws.row_dimensions[i].height = 85
        for cell in ws[i]:
            cell.fill = PatternFill("solid", fgColor="FFFFFF" if i % 2 == 0 else pale)
            cell.font = Font(color="205EAA", size=10)
            cell.alignment = Alignment(wrap_text=True, vertical="top")
    ws.freeze_panes = "M2"
    ws.auto_filter.ref = f"A1:{ws.cell(1,len(FIELDS)).column_letter}{ws.max_row}"
    target = DataValidation(type="list", formula1='"true,false"', allow_blank=False)
    target.showErrorMessage = True
    ws.add_data_validation(target)
    target.add(f"R2:R2000")

    guide = wb.create_sheet("Mode d'emploi")
    guide.sheet_view.showGridLines = False
    guide.column_dimensions["A"].width = 31
    guide.column_dimensions["B"].width = 99
    steps = [
        ("LOT 4 — ANALYSE VISUELLE", "Une ligne de l'onglet Zones correspond à une zone cliquable. Un visual_id regroupe toutes les zones d'une question."),
        ("Choisir l'image", "Utilise un lien HTTPS accessible par les apprenants. Les deux valeurs demo:network et demo:gdpr montrent les schémas fictifs intégrés."),
        ("Fichiers personnels", "Pour une image privée, utilise l'espace formateur > 2. Création manuelle > Téléverser une image. Le fichier est alors enregistré dans le quiz existant."),
        ("Coordonnées", "x_pct et y_pct en pourcentage : 0 est le bord gauche ou haut, 100 est le bord droit ou bas."),
        ("Rayon", "radius_pct = tolérance en pourcentage sur l'image ; ex. 9. L'éditeur visuel permet de placer les zones sans calculer les coordonnées."),
        ("Bonnes zones", "is_target = true pour les anomalies attendues, false pour une zone trompeuse (facultative). Prévois de 1 à 6 bonnes zones."),
        ("Explications", "zone_feedback décrit le point de vigilance. explanation et remediation donnent la synthèse et les pistes de révision."),
        ("Importer", "V23 > espace formateur > 1. Source > Import industriel > Analyser le fichier. Puis prévisualiser sans enregistrer."),
        ("Validation", "Vérifie le rapport, puis ajoute les exercices à la banque. Corrigé visible seulement après validation apprenant."),
        ("Respecter les colonnes", "Ne change pas les noms de colonnes. Pas de cellules fusionnées ni de titre au-dessus des en-têtes."),
    ]
    for n, (title, desc) in enumerate(steps, 1):
        guide.cell(n, 1, title)
        guide.cell(n, 2, desc)
        guide.row_dimensions[n].height = 48
        for cell in guide[n]:
            cell.alignment = Alignment(wrap_text=True, vertical="center")
            cell.fill = PatternFill("solid", fgColor=green if n == 1 else
                                    ("FFFFFF" if n % 2 else pale))
            cell.font = Font(bold=cell.column == 1, color="FFFFFF" if n == 1 else green)
    guide.freeze_panes = "A2"
    output = BytesIO()
    wb.save(output)
    return output.getvalue()
