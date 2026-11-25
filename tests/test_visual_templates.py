"""Verify Lot 4 XLSX/CSV import and persistence without altering Supabase."""
import io

import pytest

from utils.visual_templates import (
    FIELDS, example_rows, rows_to_visual_quiz,
    visual_csv_bytes, visual_xlsx_bytes,
)
from utils.table_import import read_quiz_table, validate_imported_quiz


class Upload(io.BytesIO):
    def __init__(self, name, data):
        super().__init__(data)
        self.name = name


@pytest.mark.parametrize("name,producer", [
    ("zones.csv", visual_csv_bytes), ("zones.xlsx", visual_xlsx_bytes),
])
def test_visual_template_roundtrip(name, producer):
    quiz = read_quiz_table(Upload(name, producer()))
    assert len(quiz["questions"]) == 2
    report = validate_imported_quiz(quiz)
    assert report["valid"], report["errors"]
    assert [q["type"] for q in quiz["questions"]] == ["image_hotspots"] * 2
    assert [q["domain"] for q in quiz["questions"]] == ["Architecture SSI", "RGPD"]
    assert all(len(q["hotspots"]) == 3 for q in quiz["questions"])
    assert quiz["questions"][0]["media"]["url"] == "demo:network"
    assert quiz["questions"][1]["media"]["url"] == "demo:gdpr"


def test_template_columns_are_unique_and_json_free():
    assert len(FIELDS) == len(set(FIELDS))
    assert FIELDS[0] == "quiz_title"
    assert "zone_feedback" in FIELDS
    assert not any(field.endswith("_json") for field in FIELDS)


def test_xlsx_import_selects_zones_when_guide_is_active():
    from openpyxl import load_workbook
    wb = load_workbook(io.BytesIO(visual_xlsx_bytes()))
    wb.active = wb.sheetnames.index("Mode d'emploi")
    stream = io.BytesIO()
    wb.save(stream)
    quiz = read_quiz_table(Upload("visual_changed.xlsx", stream.getvalue()))
    assert len(quiz["questions"]) == 2
    assert validate_imported_quiz(quiz)["valid"]


def test_invalid_coordinate_target_and_image_rejected():
    row = dict(example_rows()[0])
    row["x_pct"] = "120"
    quiz = rows_to_visual_quiz([row])
    assert not validate_imported_quiz(quiz)["valid"]

    row = dict(example_rows()[0])
    row["is_target"] = "incorrect"
    quiz = rows_to_visual_quiz([row])
    assert not validate_imported_quiz(quiz)["valid"]

    row = dict(example_rows()[0])
    row["image_url"] = "http://localhost/admin"
    quiz = rows_to_visual_quiz([row])
    assert not validate_imported_quiz(quiz)["valid"]


def test_visual_id_cannot_mix_unrelated_images_and_prompts():
    rows = example_rows()
    rows[1]["image_url"] = "demo:gdpr"
    with pytest.raises(ValueError, match="même image"):
        rows_to_visual_quiz(rows)
    rows = example_rows()
    rows[1]["question"] = "Another unrelated question"
    with pytest.raises(ValueError, match="consignes contradictoires"):
        rows_to_visual_quiz(rows)


def test_100_visual_questions_in_a_single_import():
    source = example_rows()[:3]
    rows = []
    for number in range(100):
        for raw in source:
            row = dict(raw)
            row["visual_id"] = f"VIS-{number:03d}"
            row["question"] += f" (exemple {number})"
            rows.append(row)
    quiz = rows_to_visual_quiz(rows)
    report = validate_imported_quiz(quiz)
    assert report["valid"], report["errors"]
    assert len(quiz["questions"]) == 100


def test_maintains_original_bank_roundtrip(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_DATABASE_MODE", "sqlite")
    monkeypatch.setenv("SQLITE_DB_PATH", str(tmp_path / "hotspots.sqlite"))
    from utils.question_bank import (
        init_question_bank_db, add_quiz_to_bank,
        get_question_bank_stats, select_random_questions_scoped,
    )
    init_question_bank_db.cache_clear()
    quiz = read_quiz_table(Upload("zones.xlsx", visual_xlsx_bytes()))
    assert validate_imported_quiz(quiz)["valid"]
    result = add_quiz_to_bank(quiz)
    assert result["added"] == 2, result
    assert get_question_bank_stats()["total"] == 2
    saved = select_random_questions_scoped(limit=15)
    assert len(saved) == 2
    assert all(item["type"] == "image_hotspots" for item in saved)
    assert all(len(item["hotspots"]) == 3 for item in saved)
    second = add_quiz_to_bank(quiz)
    assert second["added"] == 0 and second["ignored"] == 2
