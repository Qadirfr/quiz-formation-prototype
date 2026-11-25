"""Lot 4 image hotspot exercises: geometry, correction and click handling."""
import base64
import io
import sys

import pytest
from PIL import Image

from utils.visual_hotspots import (
    annotate_image, click_to_percentage, evaluate_visual, hit_zone, image_url,
    load_visual_image, render_hotspot_editor, render_visual,
    valid_image_reference, validate_visual_question, visual_complete,
)
from utils.visual_templates import example_rows, rows_to_visual_quiz


def samples():
    return rows_to_visual_quiz(example_rows())["questions"]


def test_two_examples_with_expected_zone_count():
    a, b = samples()
    assert a["type"] == b["type"] == "image_hotspots"
    assert len(a["hotspots"]) == len(b["hotspots"]) == 3
    assert sum(z["is_target"] for z in a["hotspots"]) == 2
    assert validate_visual_question(a) == []
    assert validate_visual_question(b) == []


def test_click_coordinates_are_normalized_across_desktop_and_mobile():
    large = click_to_percentage({"x": 600, "y": 120, "width": 900, "height": 400})
    small = click_to_percentage({"x": 200, "y": 60, "width": 300, "height": 200})
    assert large == {"x": 66.67, "y": 30.0}
    assert small == {"x": 66.67, "y": 30.0}
    for data in (
        {"x": -2, "y": 1, "width": 500, "height": 300},
        {"x": 600, "y": 5, "width": 500, "height": 300},
        {"x": 10, "y": 5, "width": 0, "height": 300},
        {"x": float("nan"), "y": 5, "width": 500, "height": 300},
        {"x": "not a coordinate", "y": 5, "width": 500, "height": 300},
    ):
        assert click_to_percentage(data) is None


def test_scoring_unique_targets_and_partial_credit():
    q = samples()[0]
    good = {"points": [{"x": 67.5, "y": 29}, {"x": 50.5, "y": 53}]}
    assert visual_complete(q, good)
    assert evaluate_visual(q, good)["score"] == 1
    assert evaluate_visual(q, good)["is_correct"] is True
    one_wrong = {"points": [{"x": 67.5, "y": 29}, {"x": 15, "y": 29}]}
    assert evaluate_visual(q, one_wrong)["score"] == 0.5
    assert evaluate_visual(q, one_wrong)["is_correct"] is False
    duplicate = {"points": [{"x": 67.5, "y": 29}, {"x": 67.5, "y": 29}]}
    assert evaluate_visual(q, duplicate)["score"] == 0.5
    assert hit_zone({"x": 15, "y": 29}, q["hotspots"])["is_target"] is False


def test_invalid_and_incomplete_image_answers_are_refused():
    q = samples()[0]
    for answer in (
        {}, None, {"points": []}, {"points": [{"x": 67, "y": 29}]},
        {"points": [{"x": -500, "y": 29}, {"x": 50, "y": 53}]},
        {"points": [{"x": 67, "y": 29}, {"x": 500, "y": 53}]},
        {"points": [{"x": 67, "y": 29}, {"x": float("nan"), "y": 53}]},
    ):
        assert not visual_complete(q, answer)
        assert evaluate_visual(q, answer)["score"] == 0


def test_reject_invalid_hotspot_and_uncontrolled_media():
    q = samples()[0]
    q["hotspots"][0]["radius_pct"] = 37
    assert validate_visual_question(q)
    q = samples()[0]
    q["hotspots"][0]["feedback"] = ""
    assert any("explication" in x for x in validate_visual_question(q))
    q = samples()[0]
    q["media"]["url"] = "http://127.0.0.1/private.png"
    assert any("Image" in x for x in validate_visual_question(q))
    assert not valid_image_reference("file:///etc/passwd")
    assert not valid_image_reference("../../secrets/secret.png")
    assert not valid_image_reference("javascript:alert(1)")


def test_demo_diagrams_load_as_real_images_and_marks_do_not_leak():
    q = samples()[0]
    source = load_visual_image(image_url(q))
    assert isinstance(source, Image.Image)
    assert source.size == (900, 500)
    unmarked = annotate_image(source, [])
    marked = annotate_image(source, [], hotspots=q["hotspots"])
    assert unmarked.size == marked.size
    assert list(unmarked.getdata()) != list(marked.getdata())


def test_can_open_uploaded_data_uri():
    image = Image.new("RGB", (120, 80), "#eeeeff")
    stream = io.BytesIO()
    image.save(stream, "PNG")
    uri = "data:image/png;base64," + base64.b64encode(stream.getvalue()).decode("ascii")
    assert valid_image_reference(uri)
    assert load_visual_image(uri).size == (120, 80)


class Rerun(Exception):
    pass


class FakeStreamlit:
    def __init__(self):
        self.session_state = {}
        self.clicked = ""
        self.messages = []

    def caption(self, *args, **kwargs):
        self.messages.append(args)

    def progress(self, *args, **kwargs):
        self.messages.append(args)

    def columns(self, cols):
        return [self] * cols

    def button(self, label, key, **kwargs):
        return key == self.clicked and not kwargs.get("disabled", False)

    def success(self, *args, **kwargs):
        self.messages.append(args)

    def write(self, *args, **kwargs):
        self.messages.append(args)

    def text_input(self, *args, **kwargs):
        return "Sauvegarde"

    def text_area(self, *args, **kwargs):
        return "Explication du constat"

    def slider(self, *args, **kwargs):
        return 10

    def checkbox(self, *args, **kwargs):
        return True

    def rerun(self):
        raise Rerun()


def test_visual_widget_receives_clicks_once_and_can_undo(monkeypatch):
    fake = FakeStreamlit()
    monkeypatch.setitem(sys.modules, "streamlit", fake)
    import types
    click = {"x": 90, "y": 50, "width": 900, "height": 500, "unix_time": 111}
    component = types.SimpleNamespace(streamlit_image_coordinates=lambda *a, **k: click)
    monkeypatch.setitem(sys.modules, "streamlit_image_coordinates", component)
    question = samples()[0]
    with pytest.raises(Rerun):
        render_visual(question, "vis")
    assert fake.session_state["vis"] == [{"x": 10, "y": 10}]
    assert render_visual(question, "vis") == {"points": [{"x": 10, "y": 10}]}
    click.update({"x": 500, "y": 250, "unix_time": 222})
    with pytest.raises(Rerun):
        render_visual(question, "vis")
    assert len(fake.session_state["vis"]) == 2
    fake.clicked = "vis_undo"
    with pytest.raises(Rerun):
        render_visual(question, "vis")
    assert len(fake.session_state["vis"]) == 1


def test_trainer_can_mark_zone_with_mouse_click(monkeypatch):
    import types
    fake = FakeStreamlit()
    monkeypatch.setitem(sys.modules, "streamlit", fake)
    component = types.SimpleNamespace(
        streamlit_image_coordinates=lambda *a, **k: {
            "x": 450, "y": 250, "width": 900, "height": 500, "unix_time": 777,
        }
    )
    monkeypatch.setitem(sys.modules, "streamlit_image_coordinates", component)
    fake.clicked = "edit_add"
    with pytest.raises(Rerun):
        render_hotspot_editor("demo:network", "edit")
    zones = fake.session_state["edit"]
    assert zones[0]["x_pct"] == 50
    assert zones[0]["y_pct"] == 50
    assert zones[0]["label"] == "Sauvegarde"
    assert zones[0]["is_target"] is True
