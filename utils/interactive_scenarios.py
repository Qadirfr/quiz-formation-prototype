"""Interactive branching scenarios: small deterministic decision graphs.

One branching scenario is ONE quiz question. Nodes are connected by choice.next.
Answers store only the path; answers and scores are never trusted without
replaying that path against the question definition.
"""
from __future__ import annotations

import re
from typing import Any


MAX_NODES = 12
MAX_STEPS = 12
NODE_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,30}$")


def _nodes(question: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(n.get("id")): n
        for n in (question.get("scenario_nodes") or [])
        if isinstance(n, dict) and isinstance(n.get("id"), str)
    }


def validate_scenario(question: dict[str, Any]) -> list[str]:
    """Check graph integrity, pedagogy, reachability, and bounded termination."""
    errors: list[str] = []
    nodes = question.get("scenario_nodes")
    if not isinstance(nodes, list) or not (2 <= len(nodes) <= MAX_NODES):
        return [f"Un scénario doit comporter entre 2 et {MAX_NODES} étapes."]
    if not all(isinstance(n, dict) for n in nodes):
        return ["Chaque étape doit être un objet structuré."]
    ids = [str(n.get("id") or "").strip() for n in nodes]
    if any(NODE_ID.fullmatch(nid) is None for nid in ids):
        errors.append("Identifiants d'étapes invalides. Utilise S1, S2, S3...")
    if len(set(ids)) != len(ids):
        errors.append("Deux étapes portent le même identifiant.")
    root = str(question.get("scenario_start") or "").strip()
    if root not in ids:
        errors.append("L'étape de départ n'existe pas.")
    edges: dict[str, list[str]] = {nid: [] for nid in ids}
    for node in nodes:
        nid = str(node.get("id") or "")
        if not str(node.get("prompt") or "").strip():
            errors.append(f"Étape {nid} : situation/consigne manquante.")
        choices = node.get("choices")
        if not isinstance(choices, list) or not (2 <= len(choices) <= 4):
            errors.append(f"Étape {nid} : 2 à 4 décisions sont nécessaires.")
            continue
        choice_ids = [str(c.get("id") or "") if isinstance(c, dict) else "" for c in choices]
        if len(set(choice_ids)) != len(choice_ids) or any(not val for val in choice_ids):
            errors.append(f"Étape {nid} : identifiants de décisions absents ou dupliqués.")
        for choice in choices:
            if not isinstance(choice, dict):
                errors.append(f"Étape {nid} : décision mal structurée.")
                continue
            cid = str(choice.get("id") or "")
            if not str(choice.get("label") or "").strip():
                errors.append(f"Étape {nid}/{cid} : texte de décision manquant.")
            if not str(choice.get("consequence") or "").strip():
                errors.append(f"Étape {nid}/{cid} : conséquence pédagogique manquante.")
            target = str(choice.get("next") or "").strip()
            if target == "END":
                pass
            elif target not in ids:
                errors.append(f"Étape {nid}/{cid} : destination '{target}' inconnue.")
            else:
                edges[nid].append(target)
            try:
                score = float(choice["score"])
                if not 0 <= score <= 1:
                    errors.append(f"Étape {nid}/{cid} : score hors de 0 à 1.")
            except (TypeError, ValueError, KeyError):
                errors.append(f"Étape {nid}/{cid} : score numérique 0 à 1 obligatoire.")
    if errors:
        return errors
    visited: set[str] = set()
    active: set[str] = set()

    def walk(nid: str) -> None:
        if nid in active:
            errors.append(f"Cycle détecté vers l'étape {nid}.")
            return
        if nid in visited:
            return
        active.add(nid)
        for destination in edges[nid]:
            walk(destination)
        active.remove(nid)
        visited.add(nid)

    walk(root)
    unreachable = set(ids) - visited
    if unreachable:
        errors.append("Étape(s) inaccessibles depuis le départ : " + ", ".join(sorted(unreachable)))
    if not any(choice.get("next") == "END" for n in nodes for choice in n["choices"]):
        errors.append("Au moins une décision doit terminer le scénario.")
    return list(dict.fromkeys(errors))


def replay_path(question: dict[str, Any], raw_path: Any) -> dict[str, Any]:
    """Replay a learner path; reject forged, truncated or out-of-order answers."""
    nodes = _nodes(question)
    node_id = str(question.get("scenario_start") or "")
    if validate_scenario(question):
        return {"valid": False, "complete": False, "current": None, "history": []}
    if not isinstance(raw_path, list) or len(raw_path) > MAX_STEPS:
        return {"valid": False, "complete": False, "current": None, "history": []}
    history = []
    for step in raw_path:
        if not isinstance(step, dict) or step.get("node_id") != node_id:
            return {"valid": False, "complete": False, "current": None, "history": []}
        node = nodes.get(node_id)
        if not node:
            return {"valid": False, "complete": False, "current": None, "history": []}
        choice = next(
            (c for c in node["choices"] if c["id"] == step.get("choice_id")), None
        )
        if choice is None:
            return {"valid": False, "complete": False, "current": None, "history": []}
        history.append({"node": node, "choice": choice})
        node_id = str(choice["next"])
        if node_id == "END":
            # A terminal answer may not have extra decisions after END.
            if len(history) != len(raw_path):
                return {"valid": False, "complete": False, "current": None, "history": []}
            return {"valid": True, "complete": True, "current": None, "history": history}
    return {"valid": True, "complete": False, "current": node_id, "history": history}


def is_scenario_complete(question: dict[str, Any], answer: Any) -> bool:
    if not isinstance(answer, dict):
        return False
    result = replay_path(question, answer.get("path"))
    return bool(result["valid"] and result["complete"])


def evaluate_scenario(question: dict[str, Any], answer: Any) -> dict[str, Any]:
    result = replay_path(
        question, answer.get("path") if isinstance(answer, dict) else None
    )
    if not result["valid"] or not result["complete"]:
        return {
            "score": 0.0, "is_correct": False, "correct_answer": "",
            "selected_feedback": "Parcours incomplet ou incohérent.",
            "correct_feedback": "Reprends le scénario jusqu'à une conclusion.",
        }
    scores = [float(item["choice"]["score"]) for item in result["history"]]
    score = sum(scores) / len(scores) if scores else 0.0
    rows = []
    for i, item in enumerate(result["history"], start=1):
        node, choice = item["node"], item["choice"]
        rows.append(f"{i}. {node['id']} — {choice['label']}. Conséquence : {choice['consequence']}")
    explanations = [
        f"{item['node']['id']} : {item['choice'].get('rationale') or item['choice']['consequence']}"
        for item in result["history"]
    ]
    if question.get("explanation"):
        explanations.append(str(question["explanation"]))
    if question.get("remediation"):
        explanations.append("Piste de révision : " + str(question["remediation"]))
    return {
        "score": round(score, 5),
        "is_correct": score >= 0.999999,
        "correct_answer": "Barème intégré aux décisions du scénario.",
        "selected_feedback": "\n".join(rows),
        "correct_feedback": "\n".join(explanations),
    }


def render_scenario(question: dict[str, Any], key: str) -> dict[str, Any]:
    """Streamlit cards for one question. The route is isolated per attempt/participant."""
    import streamlit as st

    issues = validate_scenario(question)
    if issues:
        st.error("Scénario non exploitable : " + " / ".join(issues[:3]))
        return {"path": [], "completed": False}
    raw = st.session_state.get(key)
    path = raw if isinstance(raw, list) else []
    progress = replay_path(question, path)
    if not progress["valid"]:
        path = []
        progress = replay_path(question, path)
    st.session_state[key] = path
    st.caption(
        f"Décisions prises : {len(path)} · "
        + ("Parcours terminé" if progress["complete"] else "Choisis une action pour poursuivre")
    )
    for index, past in enumerate(progress["history"], start=1):
        with st.expander(
            f"Décision {index} — {past['choice']['label']}", expanded=False
        ):
            st.markdown(past["node"]["prompt"])
            st.info("Conséquence : " + past["choice"]["consequence"])
    if progress["complete"]:
        st.success("Ton parcours est terminé. Tu peux valider ou recommencer.")
    else:
        node = _nodes(question)[progress["current"]]
        st.markdown(f"#### Étape {len(path) + 1}")
        st.markdown(str(node["prompt"]))
        st.markdown("**Que décides-tu ?**")
        cols = st.columns(min(2, len(node["choices"])))
        for index, choice in enumerate(node["choices"]):
            if cols[index % len(cols)].button(
                f"{choice['id']}. {choice['label']}",
                key=f"{key}_node_{node['id']}_choice_{choice['id']}",
                width="stretch",
            ):
                st.session_state[key] = path + [
                    {"node_id": node["id"], "choice_id": choice["id"]}
                ]
                st.rerun()
    if path and st.button("↺ Recommencer le scénario", key=f"{key}_restart"):
        st.session_state[key] = []
        st.rerun()
    return {"path": path, "completed": progress["complete"]}
