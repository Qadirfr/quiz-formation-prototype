"""Lot 3 regression: real branching, graph integrity, importing, and scoring."""
from __future__ import annotations

import copy
import io

import pytest

from utils.interactive_scenarios import (
    evaluate_scenario, is_scenario_complete, replay_path, validate_scenario,
)
from utils.scenario_templates import (
    example_rows, rows_to_scenario_quiz, scenario_csv_bytes, scenario_xlsx_bytes,
)
from utils.table_import import read_quiz_table, validate_imported_quiz


class Uploaded(io.BytesIO):
    def __init__(self, name, payload):
        super().__init__(payload)
        self.name = name


def examples():
    return rows_to_scenario_quiz(example_rows(), filename="cas.xlsx")["questions"]


def test_two_distinct_scenarios_with_real_branches():
    questions = examples()
    assert len(questions) == 2
    assert questions[0]["scenario_start"] == "S1"
    assert len(questions[0]["scenario_nodes"]) == 3
    assert [choice["next"] for choice in questions[0]["scenario_nodes"][0]["choices"]] == ["S2", "S3"]
    assert [choice["next"] for choice in questions[1]["scenario_nodes"][0]["choices"]] == ["S2", "S3"]
    for question in questions:
        assert validate_scenario(question) == []
        assert question["type"] == "branching_scenario"


def test_paths_do_not_converge_accidentally_and_show_different_outcomes():
    q = examples()[0]
    good = [{"node_id": "S1", "choice_id": "A"}, {"node_id": "S2", "choice_id": "A"}]
    recovery = [{"node_id": "S1", "choice_id": "B"}, {"node_id": "S3", "choice_id": "A"}]
    a = replay_path(q, good)
    b = replay_path(q, recovery)
    assert a["valid"] and a["complete"] and b["valid"] and b["complete"]
    assert a["history"][0]["choice"]["next"] == "S2"
    assert b["history"][0]["choice"]["next"] == "S3"
    assert "éléments probants" in a["history"][1]["choice"]["consequence"]
    assert "corrigée" in b["history"][1]["choice"]["consequence"]
    assert evaluate_scenario(q, {"path": good})["score"] == 1.0
    assert evaluate_scenario(q, {"path": recovery})["score"] == 0.45


def test_incomplete_invalid_and_forged_answers_do_not_score():
    q = examples()[0]
    for raw in (
        [],
        [{"node_id": "S1", "choice_id": "A"}],
        [{"node_id": "S1", "choice_id": "Z"}],
        [{"node_id": "S2", "choice_id": "A"}],
        [{"node_id": "S1", "choice_id": "A"}, {"node_id": "S3", "choice_id": "A"}],
        [{"node_id": "S1", "choice_id": "A"}, {"node_id": "S2", "choice_id": "A"},
         {"node_id": "S3", "choice_id": "A"}],
    ):
        assert not is_scenario_complete(q, {"path": raw})
        assert evaluate_scenario(q, {"path": raw})["score"] == 0


def test_score_reveals_explanations_only_in_evaluation():
    q = examples()[0]
    path = [{"node_id": "S1", "choice_id": "B"}, {"node_id": "S3", "choice_id": "B"}]
    feedback = evaluate_scenario(q, {"path": path})
    assert feedback["is_correct"] is False
    assert feedback["score"] == 0.1
    assert "Conséquence" in feedback["selected_feedback"]
    assert "procédure" in feedback["correct_feedback"]


def test_cycle_unknown_step_unreachable_and_non_numeric_score_rejected():
    base = examples()[0]
    variants = []
    for mutate in (
        lambda q: q["scenario_nodes"][2]["choices"][0].update({"next": "S1"}),
        lambda q: q["scenario_nodes"][0]["choices"][0].update({"next": "S999"}),
        lambda q: q["scenario_nodes"][0]["choices"][1].update({"next": "S2"}),
        lambda q: q["scenario_nodes"][0]["choices"][0].update({"score": "invalid"}),
    ):
        q = copy.deepcopy(base)
        mutate(q)
        variants.append(q)
    for q in variants:
        assert validate_scenario(q)
        assert not is_scenario_complete(q, {"path": []})


@pytest.mark.parametrize(
    ("filename", "payload"),
    [
        ("modele_scenarios_embranchements.csv", scenario_csv_bytes),
        ("modele_scenarios_embranchements.xlsx", scenario_xlsx_bytes),
    ],
)
def test_import_scenarios_from_standard_files(filename, payload):
    quiz = read_quiz_table(Uploaded(filename, payload()))
    assert len(quiz["questions"]) == 2
    report = validate_imported_quiz(quiz)
    assert report["valid"], report["errors"]
    assert [q["domain"] for q in quiz["questions"]] == ["Gestion des incidents", "Gouvernance IA"]
    assert [q["type"] for q in quiz["questions"]] == ["branching_scenario"] * 2
    assert all(q.get("remediation") for q in quiz["questions"])


def test_scenario_excel_import_selects_correct_tab_when_guide_active():
    from openpyxl import load_workbook
    wb = load_workbook(io.BytesIO(scenario_xlsx_bytes()))
    wb.active = wb.sheetnames.index("Mode d'emploi")
    payload = io.BytesIO()
    wb.save(payload)
    quiz = read_quiz_table(Uploaded("cases.xlsx", payload.getvalue()))
    assert len(quiz["questions"]) == 2
    assert validate_imported_quiz(quiz)["valid"]


def test_invalid_graph_import_is_blocked_before_bank_write():
    rows = copy.deepcopy(example_rows())
    rows[0]["next_node"] = "S99"
    quiz = rows_to_scenario_quiz(rows)
    report = validate_imported_quiz(quiz)
    assert not report["valid"]
    assert any("S99" in message for message in report["errors"])


def test_no_json_cells_and_all_rows_have_scenario_ids():
    rows = example_rows()
    assert len(rows) == 12
    assert all(row.get("scenario_id") and row.get("node_id") and row.get("choice_id") for row in rows)
    assert all(not key.endswith("_json") for key in rows[0])
