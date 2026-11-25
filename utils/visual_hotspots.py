"""Lot 4: visual analysis questions with percentage-based, click-selectable zones.

A single question stores media as it already does in V23 and an array of
hotspots. Click positions are expressed in percentages, not pixels, so image
resizing does not change the grading. No database/schema changes are needed.
"""
from __future__ import annotations

import base64
from functools import lru_cache
from io import BytesIO
import math
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont, ImageOps


MAX_IMAGE_BYTES = 2 * 1024 * 1024
MAX_IMAGE_PIXELS = 6_000_000
MAX_HOTSPOTS = 12
MAX_TARGETS = 6
DEMO_URLS = {"demo:network", "demo:gdpr"}


def image_url(question: dict[str, Any]) -> str:
    raw = question.get("media") or question.get("image_url") or ""
    if isinstance(raw, list):
        raw = raw[0] if raw else ""
    if isinstance(raw, dict):
        return str(raw.get("url") or raw.get("source") or raw.get("path") or "")
    return str(raw or "")


def valid_image_reference(url: str) -> bool:
    if not url:
        return False
    if url in DEMO_URLS:
        return True
    if url.startswith("https://") and len(url) <= 2048:
        return True
    if url.startswith("data:image/"):
        prefix = url.partition(",")[0].lower()
        if not prefix.endswith(";base64") or not prefix.startswith(
            ("data:image/png;", "data:image/jpeg;", "data:image/webp;")
        ):
            return False
        return len(url) < 3 * 1024 * 1024
    if url.startswith("assets/") and ".." not in url:
        return Path(url).suffix.lower() in {".png", ".jpeg", ".jpg", ".webp"}
    return False


def _open_bytes(raw: bytes) -> Image.Image:
    if not raw or len(raw) > MAX_IMAGE_BYTES:
        raise ValueError("Image trop volumineuse : 2 Mo maximum.")
    try:
        image = Image.open(BytesIO(raw))
        if image.width * image.height > MAX_IMAGE_PIXELS:
            raise ValueError("Image trop grande : 6 millions de pixels maximum.")
        image = ImageOps.exif_transpose(image)
        image.load()
        image = image.convert("RGB")
        image.thumbnail((1100, 850))
        return image
    except (OSError, SyntaxError) as exc:
        raise ValueError("Image non lisible. Utilise PNG, JPEG ou WEBP.") from exc


@lru_cache(maxsize=4)
def _demo_image(which: str) -> Image.Image:
    """Original diagrams; no source images, secrets or user records."""
    img = Image.new("RGB", (900, 500), "#f5f8f5")
    dr = ImageDraw.Draw(img)
    forest, sage, red = "#14563e", "#dcece4", "#c95b52"
    ink, gray = "#172b27", "#576660"
    font = ImageFont.load_default()
    if which == "demo:network":
        dr.text((32, 20), "EXERCICE - ARCHITECTURE SI", fill=forest, font=font)
        boxes = [
            ((30, 75, 245, 220), "INTERNET", "Entrees publiques"),
            ((342, 75, 560, 220), "APPLICATION", "Acces utilisateur"),
            ((657, 75, 870, 220), "DONNEES", "Base clients"),
            ((342, 300, 560, 450), "SAUVEGARDE", "Restaurations"),
        ]
        for rect, name, desc in boxes:
            dr.rounded_rectangle(rect, radius=18, fill=sage, outline=forest, width=3)
            dr.text((rect[0] + 22, rect[1] + 38), name, fill=ink, font=font)
            dr.text((rect[0] + 22, rect[1] + 70), desc, fill=gray, font=font)
        dr.line((245, 145, 342, 145), fill=forest, width=7)
        dr.line((560, 145, 657, 145), fill=red, width=8)
        dr.line((455, 220, 455, 300), fill=red, width=8)
        dr.text((580, 118), "Lien direct", fill=red, font=font)
        dr.text((474, 263), "Non teste", fill=red, font=font)
    else:
        dr.text((32, 20), "EXERCICE - PARCOURS DE DONNEES PERSONNELLES", fill=forest, font=font)
        boxes = [
            ((30, 80, 255, 235), "COLLECTE", "Formulaire client"),
            ((337, 80, 562, 235), "TRAITEMENT", "Dossier de gestion"),
            ((645, 80, 870, 235), "EXPORT", "Fichier non protege"),
            ((337, 305, 562, 457), "ARCHIVAGE", "Conservation 20 ans"),
        ]
        for rect, name, desc in boxes:
            dr.rounded_rectangle(rect, radius=18, fill=sage, outline=forest, width=3)
            dr.text((rect[0] + 20, rect[1] + 40), name, fill=ink, font=font)
            dr.text((rect[0] + 20, rect[1] + 74), desc, fill=gray, font=font)
        dr.line((255, 158, 337, 158), fill=forest, width=7)
        dr.line((562, 158, 645, 158), fill=red, width=8)
        dr.line((447, 235, 447, 305), fill=red, width=8)
        dr.text((580, 131), "Sans chiffrement", fill=red, font=font)
        dr.text((467, 272), "Duree a revoir", fill=red, font=font)
    return img


def load_visual_image(url: str) -> str | Image.Image:
    """Remote images remain in the browser. Never fetch an arbitrary URL server-side."""
    if not valid_image_reference(url):
        raise ValueError("Illustration manquante ou format non autorisé.")
    if url in DEMO_URLS:
        return _demo_image(url).copy()
    if url.startswith("https://"):
        return url
    if url.startswith("data:image/"):
        try:
            data = base64.b64decode(url.partition(",")[2], validate=True)
        except (ValueError, Exception) as exc:
            raise ValueError("Illustration encodée invalide.") from exc
        return _open_bytes(data)
    path = Path(url)
    if not path.is_file():
        raise ValueError("Illustration locale introuvable.")
    return _open_bytes(path.read_bytes())


def validate_visual_question(question: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    url = image_url(question)
    if not valid_image_reference(url):
        errors.append("Image requise : téléverse une image ou indique une URL HTTPS.")
    zones = question.get("hotspots")
    if not isinstance(zones, list) or not (1 <= len(zones) <= MAX_HOTSPOTS):
        return errors + [f"Il faut de 1 à {MAX_HOTSPOTS} zones définies."]
    ids: set[str] = set()
    targets = 0
    for idx, zone in enumerate(zones, 1):
        if not isinstance(zone, dict):
            errors.append(f"Zone {idx} : définition invalide.")
            continue
        zid = str(zone.get("id") or "").strip()
        if not zid or zid in ids:
            errors.append(f"Zone {idx} : identifiant absent ou dupliqué.")
        ids.add(zid)
        if not str(zone.get("label") or "").strip():
            errors.append(f"Zone {idx} : libellé absent.")
        if not isinstance(zone.get("is_target"), bool):
            errors.append(f"Zone {idx} : is_target doit être vrai ou faux.")
        elif zone["is_target"]:
            targets += 1
            if not str(zone.get("feedback") or "").strip():
                errors.append(f"Zone {idx} : explication pédagogique manquante.")
        try:
            x, y, radius = (
                float(zone["x_pct"]), float(zone["y_pct"]), float(zone["radius_pct"])
            )
            if not (0 <= x <= 100 and 0 <= y <= 100 and 2 <= radius <= 25):
                errors.append(f"Zone {idx} : coordonnées 0–100 et rayon 2–25 % attendus.")
            if any(not math.isfinite(v) for v in (x, y, radius)):
                errors.append(f"Zone {idx} : valeurs non finies.")
        except (ValueError, TypeError, KeyError):
            errors.append(f"Zone {idx} : coordonnées ou rayon incorrects.")
    if not 1 <= targets <= MAX_TARGETS:
        errors.append(f"De 1 à {MAX_TARGETS} zones à repérer sont nécessaires.")
    return errors


def click_to_percentage(event: Any) -> dict[str, float] | None:
    if not isinstance(event, dict):
        return None
    try:
        x, y = float(event["x"]), float(event["y"])
        width, height = float(event["width"]), float(event["height"])
        if not all(math.isfinite(v) for v in (x, y, width, height)):
            return None
        if not (width > 0 and height > 0 and 0 <= x <= width and 0 <= y <= height):
            return None
        return {"x": round(100 * x / width, 2), "y": round(100 * y / height, 2)}
    except (TypeError, ValueError, KeyError):
        return None


def _distance(point: dict[str, Any], zone: dict[str, Any]) -> float:
    return math.hypot(
        float(point["x"]) - float(zone["x_pct"]),
        float(point["y"]) - float(zone["y_pct"]),
    )


def hit_zone(point: dict[str, Any], zones: list[dict[str, Any]]) -> dict[str, Any] | None:
    matches = [
        z for z in zones if _distance(point, z) <= float(z["radius_pct"])
    ]
    return min(matches, key=lambda z: _distance(point, z)) if matches else None


def visual_complete(question: dict[str, Any], answer: Any) -> bool:
    return (
        isinstance(answer, dict)
        and validate_visual_question(question) == []
        and isinstance(answer.get("points"), list)
        and len(answer["points"]) == sum(bool(z["is_target"]) for z in question["hotspots"])
        and all(_valid_point(p) for p in answer["points"])
    )


def _valid_point(p: Any) -> bool:
    if not isinstance(p, dict):
        return False
    try:
        x, y = float(p["x"]), float(p["y"])
        return all(math.isfinite(v) for v in (x, y)) and 0 <= x <= 100 and 0 <= y <= 100
    except (TypeError, ValueError, KeyError):
        return False


def evaluate_visual(question: dict[str, Any], answer: Any) -> dict[str, Any]:
    targets = [z for z in question.get("hotspots") or [] if z.get("is_target")]
    if not visual_complete(question, answer):
        return {
            "score": 0.0, "is_correct": False,
            "correct_answer": "", "selected_feedback": "Réponse visuelle incomplète ou invalide.",
            "correct_feedback": "Repère toutes les zones demandées avant de valider.",
        }
    found: set[str] = set()
    for point in answer["points"]:
        matching = hit_zone(point, question["hotspots"])
        if matching and matching.get("is_target"):
            found.add(str(matching["id"]))
    correct = len(found)
    required = len(targets)
    score = correct / required if required else 0.0
    lines = [
        f"{z['label']} — {z.get('feedback') or 'Zone attendue.'}"
        for z in targets
    ]
    if question.get("explanation"):
        lines.append(str(question["explanation"]))
    if question.get("remediation"):
        lines.append("Révision : " + str(question["remediation"]))
    return {
        "score": round(score, 5), "is_correct": correct == required,
        "correct_answer": "Zones : " + ", ".join(str(z["label"]) for z in targets),
        "selected_feedback": f"{correct} zone(s) correctement repérée(s) sur {required}.",
        "correct_feedback": "\n".join(lines),
    }


def annotate_image(source: Image.Image, points: list[dict[str, Any]], *,
                   hotspots: list[dict[str, Any]] | None = None) -> Image.Image:
    """Draw only learner selections until correction is explicitly requested."""
    image = source.copy().convert("RGB")
    draw = ImageDraw.Draw(image)
    width, height = image.size
    for index, point in enumerate(points, start=1):
        x = int(float(point["x"]) * width / 100)
        y = int(float(point["y"]) * height / 100)
        rad = max(12, round(min(width, height) * 0.023))
        draw.ellipse((x-rad, y-rad, x+rad, y+rad), fill="#246d9e", outline="white", width=3)
        draw.text((x-4, y-6), str(index), fill="white")
    if hotspots:
        for hotspot in hotspots:
            if not hotspot.get("is_target"):
                continue
            x = int(float(hotspot["x_pct"]) * width / 100)
            y = int(float(hotspot["y_pct"]) * height / 100)
            radx = int(float(hotspot["radius_pct"]) * width / 100)
            rady = int(float(hotspot["radius_pct"]) * height / 100)
            draw.ellipse((x-radx, y-rady, x+radx, y+rady), outline="#16834d", width=5)
    return image


def render_visual(question: dict[str, Any], key: str) -> dict[str, Any]:
    """Render responsive image and collect target-count clicks without giving away answers."""
    import streamlit as st
    from streamlit_image_coordinates import streamlit_image_coordinates

    issues = validate_visual_question(question)
    if issues:
        st.warning("Exercice visuel incomplet : " + " / ".join(issues[:3]))
        return {"points": []}
    try:
        source = load_visual_image(image_url(question))
    except ValueError as exc:
        st.error(f"Impossible d'afficher l'illustration : {exc}")
        return {"points": []}
    count = sum(bool(z["is_target"]) for z in question["hotspots"])
    raw = st.session_state.get(key)
    points = [p for p in raw if _valid_point(p)] if isinstance(raw, list) else []
    points = points[:count]
    st.session_state[key] = points
    st.caption(f"Clique sur {count} zone(s) de l'image. Les réponses ne sont révélées qu'après validation.")
    st.progress(len(points)/count, text=f"{len(points)}/{count} zones sélectionnées")
    shown = annotate_image(source, points) if isinstance(source, Image.Image) else source
    event = streamlit_image_coordinates(
        shown, key=f"{key}_image", width="stretch", cursor="crosshair",
    )
    event_id = event.get("unix_time") if isinstance(event, dict) else None
    point = click_to_percentage(event)
    if (
        point and event_id is not None
        and event_id != st.session_state.get(f"{key}_last_click")
    ):
        st.session_state[f"{key}_last_click"] = event_id
        if len(points) < count:
            st.session_state[key] = points + [point]
            st.rerun()
    if points:
        st.caption(
            "Tes repères : "
            + " · ".join(
                f"{i}. ({p['x']:.0f} %, {p['y']:.0f} %)" for i, p in enumerate(points, 1)
            )
        )
        col1, col2 = st.columns(2)
        if col1.button("↶ Retirer le dernier repère", key=f"{key}_undo"):
            st.session_state[key] = points[:-1]
            st.rerun()
        if col2.button("↺ Recommencer", key=f"{key}_reset"):
            st.session_state[key] = []
            st.rerun()
    if len(points) >= count:
        st.success("Tous les repères sont placés. Tu peux valider tes choix.")
    return {"points": points}


def render_visual_correction(question: dict[str, Any], answer: dict[str, Any]) -> None:
    """Reveal target regions only after validation."""
    import streamlit as st
    src = load_visual_image(image_url(question))
    if isinstance(src, Image.Image):
        st.image(
            annotate_image(src, answer.get("points") or [], hotspots=question["hotspots"]),
            caption="Cercles verts : zones attendues. Points bleus : tes sélections.",
            width="stretch",
        )
    else:
        st.caption("Zones de correction (positions relatives à l'image) :")
        for zone in question["hotspots"]:
            if zone["is_target"]:
                st.write(f"{zone['label']} : x={zone['x_pct']} %, y={zone['y_pct']} %.")


def render_hotspot_editor(source_url: str, key: str) -> list[dict[str, Any]]:
    """Author a hotspot by clicking the existing media; no JSON for the trainer."""
    import streamlit as st
    from streamlit_image_coordinates import streamlit_image_coordinates

    raw = st.session_state.get(key)
    zones = list(raw) if isinstance(raw, list) else []
    st.caption(
        "Clique sur l'image pour positionner une zone. Renseigne son libellé, "
        "l'explication et son rayon, puis ajoute-la. Les zones recherchées "
        "restent invisibles aux apprenants avant la correction."
    )
    try:
        source = load_visual_image(source_url)
    except ValueError as exc:
        st.warning(str(exc))
        return zones
    preview = annotate_image(
        source, [],
        hotspots=zones
    ) if isinstance(source, Image.Image) else source
    event = streamlit_image_coordinates(
        preview, key=f"{key}_picker", width="stretch", cursor="crosshair",
    )
    clicked = click_to_percentage(event)
    st.caption(
        f"Point choisi : x={clicked['x']:.1f} %, y={clicked['y']:.1f} %"
        if clicked else "Clique sur une zone de l'image pour la définir."
    )
    target = st.checkbox(
        "Zone à repérer (sinon zone leurre)",
        value=True, key=f"{key}_target",
    )
    label = st.text_input("Libellé de la zone", key=f"{key}_label")
    feedback = st.text_area("Explication / constat associé à cette zone", key=f"{key}_feedback")
    radius = st.slider(
        "Tolérance de clic / rayon de la zone (%)", 2, 25, 9, key=f"{key}_radius"
    )
    if st.button(
        "Ajouter cette zone",
        key=f"{key}_add",
        disabled=clicked is None or not label.strip() or len(zones) >= MAX_HOTSPOTS,
    ):
        zones.append({
            "id": f"Z{len(zones)+1}", "label": label.strip(),
            "x_pct": clicked["x"], "y_pct": clicked["y"],
            "radius_pct": radius, "is_target": target, "feedback": feedback.strip(),
        })
        st.session_state[key] = zones
        st.rerun()
    for index, zone in enumerate(zones):
        a, b = st.columns([5, 1])
        a.write(
            f"**{zone['id']}** · {zone['label']} · "
            f"({zone['x_pct']:.0f} %, {zone['y_pct']:.0f} %) · rayon {zone['radius_pct']} % "
            f"· {'à repérer' if zone['is_target'] else 'leurre'}"
        )
        if b.button("×", key=f"{key}_remove_{index}"):
            new_zones = [z for n, z in enumerate(zones) if n != index]
            for i, z in enumerate(new_zones, 1):
                z["id"] = f"Z{i}"
            st.session_state[key] = new_zones
            st.rerun()
    return zones
