"""Visual quiz questions: click an image, then evaluate a percentage-based zone.

One image hotspot question has one learner click. All coordinates and
rectangle sizes are percentages, independent of displayed image resolution.
No schema migration: media and hotspot_zones live in the existing JSON field.
"""
from __future__ import annotations

import base64
import binascii
from io import BytesIO
from typing import Any

MAX_ZONES = 6


def _source(question: dict[str, Any]) -> str:
    media = question.get("media") or {}
    if not isinstance(media, dict):
        return ""
    return str(media.get("url") or "").strip()


def valid_source(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    source = value.strip().lower()
    return source.startswith(("https://", "http://", "data:image/png;base64,",
                              "data:image/jpeg;base64,", "data:image/webp;base64,"))


def validate_hotspot(question: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    if not valid_source(_source(question)):
        issues.append("Une image URL (HTTP/HTTPS) ou téléversée (PNG/JPEG/WEBP) est nécessaire.")
    zones = question.get("hotspot_zones")
    if not isinstance(zones, list) or not (1 <= len(zones) <= MAX_ZONES):
        issues.append(f"Définis entre 1 et {MAX_ZONES} zones sur l'image.")
        return issues
    ids = set()
    rectangles = []
    good = 0
    for index, zone in enumerate(zones, start=1):
        label = f"Zone {index}"
        if not isinstance(zone, dict):
            issues.append(f"{label} : données invalides.")
            continue
        name = str(zone.get("id") or "").strip()
        if not name or name in ids:
            issues.append(f"{label} : identifiant manquant ou en double.")
        ids.add(name)
        if not str(zone.get("label") or "").strip():
            issues.append(f"{label} : libellé manquant.")
        if not str(zone.get("feedback") or "").strip():
            issues.append(f"{label} : explication pédagogique manquante.")
        if not isinstance(zone.get("correct"), bool):
            issues.append(f"{label} : correct doit être vrai ou faux.")
        elif zone["correct"]:
            good += 1
        coords = []
        for field in ("x", "y", "w", "h"):
            try:
                value = float(zone[field])
            except (TypeError, ValueError, KeyError):
                issues.append(f"{label} : {field} doit être numérique.")
                break
            if not 0 <= value <= 100 or (field in {"w", "h"} and value <= 0):
                issues.append(f"{label} : {field} doit être dans les limites de l'image.")
            coords.append(value)
        if len(coords) == 4:
            x, y, w, h = coords
            if x + w > 100 or y + h > 100:
                issues.append(f"{label} : le rectangle déborde de l'image.")
            else:
                rectangles.append((label, x, y, x + w, y + h))
    if good == 0:
        issues.append("Au moins une zone doit être considérée comme correcte.")
    for index, (name, x1, y1, x2, y2) in enumerate(rectangles):
        for other, ox1, oy1, ox2, oy2 in rectangles[index + 1:]:
            if x1 < ox2 and ox1 < x2 and y1 < oy2 and oy1 < y2:
                issues.append(f"Les zones {name} et {other} se chevauchent.")
    return issues


def normalize_click(event: Any) -> dict[str, float] | None:
    """Convert the browser component event to invariant percentages."""
    if not isinstance(event, dict):
        return None
    try:
        x, y = float(event["x"]), float(event["y"])
        width, height = float(event["width"]), float(event["height"])
    except (KeyError, TypeError, ValueError):
        return None
    if width <= 0 or height <= 0 or not (0 <= x <= width and 0 <= y <= height):
        return None
    return {"x": round(100 * x / width, 4), "y": round(100 * y / height, 4)}


def hit_zone(question: dict[str, Any], point: Any) -> dict[str, Any] | None:
    if not isinstance(point, dict):
        return None
    try:
        x, y = float(point["x"]), float(point["y"])
    except (KeyError, TypeError, ValueError):
        return None
    for zone in question.get("hotspot_zones") or []:
        try:
            zx, zy, w, h = (float(zone[field]) for field in ("x", "y", "w", "h"))
        except (TypeError, ValueError, KeyError):
            continue
        if zx <= x <= zx + w and zy <= y <= zy + h:
            return zone
    return None


def is_hotspot_complete(question: dict[str, Any], answer: Any) -> bool:
    if not isinstance(answer, dict):
        return False
    point = answer.get("point")
    if not isinstance(point, dict):
        return False
    try:
        x, y = float(point["x"]), float(point["y"])
    except (KeyError, TypeError, ValueError):
        return False
    return 0 <= x <= 100 and 0 <= y <= 100


def evaluate_hotspot(question: dict[str, Any], answer: Any) -> dict[str, Any]:
    if validate_hotspot(question) or not is_hotspot_complete(question, answer):
        return {
            "score": 0.0, "is_correct": False, "correct_answer": "",
            "selected_feedback": "Position non renseignée ou question visuelle invalide.",
            "correct_feedback": "Contrôle de la définition des zones nécessaire.",
        }
    point = answer["point"]
    selected = hit_zone(question, point)
    correct = bool(selected and selected.get("correct"))
    target = [zone for zone in question["hotspot_zones"] if zone.get("correct")]
    selected_feedback = (
        f"Tu as indiqué : {selected['label']}. {selected['feedback']}"
        if selected else
        "Le clic se situe en dehors des zones définies. Repère les éléments significatifs."
    )
    explanations = [
        "Zone(s) attendue(s) : " + ", ".join(str(zone["label"]) for zone in target)
    ]
    if question.get("explanation"):
        explanations.append(str(question["explanation"]))
    if question.get("remediation"):
        explanations.append("Piste de révision : " + str(question["remediation"]))
    return {
        "score": 1.0 if correct else 0.0,
        "is_correct": correct,
        "correct_answer": [str(zone["id"]) for zone in target],
        "selected_feedback": selected_feedback,
        "correct_feedback": "\n".join(explanations),
    }


def image_for_component(source: str) -> Any:
    """Return a URL or a Pillow image. The component cannot read data: URIs."""
    if source.startswith(("http://", "https://")):
        return source
    if source.startswith("data:image/") and ";base64," in source:
        encoded = source.split(";base64,", 1)[1]
        try:
            raw = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise ValueError("Image téléversée invalide.") from exc
        if len(raw) > 2 * 1024 * 1024:
            raise ValueError("Image trop volumineuse pour la question visuelle.")
        from PIL import Image, ImageOps
        try:
            image = Image.open(BytesIO(raw))
            image = ImageOps.exif_transpose(image)
            image.load()
            if image.width * image.height > 18_000_000:
                raise ValueError("Image trop grande : utilise une image plus légère.")
            return image.convert("RGB")
        except (OSError, ValueError) as exc:
            raise ValueError("Le fichier image ne peut pas être affiché.") from exc
    raise ValueError("Source d'image non prise en charge pour les zones cliquables.")


def click_image(source: str, widget_key: str) -> Any:
    from streamlit_image_coordinates import streamlit_image_coordinates
    return streamlit_image_coordinates(
        image_for_component(source),
        width="stretch",
        key=widget_key,
        cursor="crosshair",
    )


def render_hotspot(question: dict[str, Any], state_key: str) -> dict[str, Any]:
    """Learner-facing click; hides zone locations and correction until submit."""
    import streamlit as st
    errors = validate_hotspot(question)
    if errors:
        st.error("Question visuelle invalide : " + " / ".join(errors[:3]))
        return {}
    st.caption("Clique directement sur l'élément de l'image que tu veux désigner.")
    event = click_image(_source(question), f"{state_key}_image")
    previous_event = st.session_state.get(f"{state_key}_last_event")
    if isinstance(event, dict):
        token = (event.get("unix_time"), event.get("x"), event.get("y"))
        if token != previous_event:
            point = normalize_click(event)
            if point is not None:
                st.session_state[state_key] = {"point": point}
                st.session_state[f"{state_key}_last_event"] = token
    selected = st.session_state.get(state_key)
    if is_hotspot_complete(question, selected):
        point = selected["point"]
        st.caption(f"Position enregistrée : {point['x']:.1f} % horizontal, {point['y']:.1f} % vertical.")
    else:
        st.info("Clique sur l'image pour sélectionner une position.")
    with st.expander("Alternative : renseigner une position sans cliquer sur l'image"):
        col1, col2 = st.columns(2)
        x = col1.number_input("Position horizontale (%)", 0.0, 100.0, 50.0, 1.0, key=f"{state_key}_manual_x")
        y = col2.number_input("Position verticale (%)", 0.0, 100.0, 50.0, 1.0, key=f"{state_key}_manual_y")
        if st.button("Choisir cette position", key=f"{state_key}_manual_set"):
            st.session_state[state_key] = {"point": {"x": float(x), "y": float(y)}}
            st.rerun()
    if is_hotspot_complete(question, selected) and st.button(
        "Effacer ma position", key=f"{state_key}_reset"
    ):
        st.session_state.pop(state_key, None)
        st.rerun()
    return st.session_state.get(state_key) or {}


def render_hotspot_editor(source: str) -> dict[str, Any]:
    """Manual authoring: click the image to position a rectangular zone."""
    import streamlit as st
    st.caption(
        "Choisis une zone puis clique sur l'image pour placer son centre. "
        "Tu peux ajuster la position et la taille en pourcentage."
    )
    n = int(st.number_input(
        "Nombre de zones cliquables", min_value=1, max_value=MAX_ZONES,
        value=3, step=1, key="manual_hotspot_count"
    ))
    active = st.selectbox(
        "Zone à positionner sur l'image", [f"Z{i}" for i in range(1, n + 1)],
        key="manual_hotspot_active",
    )
    if valid_source(source):
        event = click_image(source, "manual_hotspot_picker")
        if isinstance(event, dict):
            token = (event.get("unix_time"), event.get("x"), event.get("y"), active)
            if token != st.session_state.get("manual_hotspot_last_picker"):
                point = normalize_click(event)
                if point:
                    w = float(st.session_state.get(f"manual_hotspot_{active}_w", 20.0))
                    h = float(st.session_state.get(f"manual_hotspot_{active}_h", 20.0))
                    st.session_state[f"manual_hotspot_{active}_x"] = max(
                        0.0, min(100.0 - w, point["x"] - w / 2)
                    )
                    st.session_state[f"manual_hotspot_{active}_y"] = max(
                        0.0, min(100.0 - h, point["y"] - h / 2)
                    )
                    st.session_state["manual_hotspot_last_picker"] = token
    else:
        st.info("Ajoute une URL d'image ou téléverse un PNG/JPEG pour placer les zones.")

    zones = []
    for i in range(1, n + 1):
        zone_id = f"Z{i}"
        with st.expander(f"{zone_id} — Définir le rectangle et la correction", expanded=zone_id == active):
            label = st.text_input(
                f"Nom de la zone {zone_id}", value=f"Élément {i}",
                key=f"manual_hotspot_{zone_id}_label"
            )
            c1, c2 = st.columns(2)
            x = c1.number_input(
                f"{zone_id} — début horizontal (%)", 0.0, 100.0, 10.0 if i == 1 else 40.0 if i == 2 else 70.0,
                1.0, key=f"manual_hotspot_{zone_id}_x"
            )
            y = c2.number_input(
                f"{zone_id} — début vertical (%)", 0.0, 100.0, 32.0,
                1.0, key=f"manual_hotspot_{zone_id}_y"
            )
            c3, c4 = st.columns(2)
            w = c3.number_input(
                f"{zone_id} — largeur (%)", 1.0, 100.0, 20.0,
                1.0, key=f"manual_hotspot_{zone_id}_w"
            )
            h = c4.number_input(
                f"{zone_id} — hauteur (%)", 1.0, 100.0, 30.0,
                1.0, key=f"manual_hotspot_{zone_id}_h"
            )
            correct = st.checkbox(
                f"{zone_id} — Cette zone est une réponse correcte",
                value=i == 2, key=f"manual_hotspot_{zone_id}_correct",
            )
            feedback = st.text_area(
                f"{zone_id} — Explication pour ce choix",
                value="Choix à analyser selon les faits présentés.",
                height=75,
                key=f"manual_hotspot_{zone_id}_feedback",
            )
            zones.append({
                "id": zone_id, "label": label, "x": x, "y": y,
                "w": w, "h": h, "correct": correct, "feedback": feedback,
            })
    st.caption(
        "Les rectangles ne doivent pas se chevaucher et rester dans l'image. "
        "Un clic situé hors des rectangles est considéré comme une erreur."
    )
    return {"hotspot_zones": zones}
