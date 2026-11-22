"""The V24 xlsx/csv models must work with the existing V23 industrial importer."""
from __future__ import annotations

import io

import pytest

from utils.interactive_templates import (
    FIELDS,
    example_rows,
    interactive_csv_bytes,
    interactive_xlsx_bytes,
)
from utils.table_import import read_quiz_table, rows_to_quiz, validate_imported_quiz


class _UploadedFile(io.BytesIO):
    def __init__(self, name, data):
        super().__init__(data)
        self.name = name


@pytest.mark.parametrize(
    ("filename", "data_factory"),
    [
        ("modele_cartes.csv", interactive_csv_bytes),
        ("modele_cartes.xlsx", interactive_xlsx_bytes),
    ],
)
def test_template_roundtrips_to_six_valid_questions(filename, data_factory):
    quiz = read_quiz_table(_UploadedFile(filename, data_factory()))
    report = validate_imported_quiz(quiz)
    assert report["valid"], report["errors"]
    assert len(quiz["questions"]) == 6
    assert [q["type"] for q in quiz["questions"]] == [
        "ordering", "matching", "ordering", "matching", "ordering", "matching"
    ]
    assert quiz["questions"][0]["correct_order"] == list("BCDA")
    assert len(quiz["questions"][1]["pairs"]) == 3
    assert quiz["questions"][3]["training_scope"] == "CDPO"
    assert quiz["questions"][3]["domain"] == "RGPD"
    assert quiz["questions"][0]["subdomain"] == "Execution d'un controle"
    assert all(q.get("remediation") for q in quiz["questions"])
    assert all(q.get("explanation") for q in quiz["questions"])


def test_header_order_and_all_columns_are_unique():
    assert FIELDS[0] == "quiz_title"
    assert FIELDS[-1] == "context_text"
    assert len(FIELDS) == len(set(FIELDS))
    assert "pair_6_right" in FIELDS
    assert "item_6" in FIELDS


def test_template_roundtrip_preserves_many_questions():
    base = example_rows()
    # Bulk scale without a database: every row has its own unique question text.
    rows = []
    for index in range(100):
        row = dict(base[index % len(base)])
        row["question"] += f" [variante {index}]"
        rows.append(row)
    quiz = rows_to_quiz(rows, filename="bulk.xlsx")
    report = validate_imported_quiz(quiz)
    assert report["valid"], report["errors"]
    assert report["question_count"] == 100


def test_incomplete_order_is_rejected_before_bank_import():
    row = dict(example_rows()[0])
    row["correct_order"] = "BCB"
    report = validate_imported_quiz(rows_to_quiz([row]))
    assert not report["valid"]
    assert any("correct_order" in msg for msg in report["errors"])


def test_missing_right_matching_pair_is_rejected_before_bank_import():
    row = dict(example_rows()[1])
    row["pair_2_right"] = ""
    report = validate_imported_quiz(rows_to_quiz([row]))
    assert not report["valid"]
    assert any("gauche et a droite" in msg for msg in report["errors"])


def test_duplicate_right_matching_pair_is_rejected_before_bank_import():
    row = dict(example_rows()[1])
    row["pair_2_right"] = row["pair_1_right"]
    report = validate_imported_quiz(rows_to_quiz([row]))
    assert not report["valid"]
    assert any("termes de droite" in msg for msg in report["errors"])


def test_example_rows_have_no_hidden_json_fields():
    assert all(set(row) == set(FIELDS) for row in example_rows())
    assert all(not field.endswith("_json") for field in FIELDS)


def test_excel_import_prefers_questions_when_guide_was_last_active():
    from openpyxl import load_workbook

    workbook = load_workbook(io.BytesIO(interactive_xlsx_bytes()))
    workbook.active = workbook.sheetnames.index("Mode d'emploi")
    stream = io.BytesIO()
    workbook.save(stream)
    quiz = read_quiz_table(_UploadedFile("modified_active_sheet.xlsx", stream.getvalue()))
    assert len(quiz["questions"]) == 6
    assert validate_imported_quiz(quiz)["valid"]
