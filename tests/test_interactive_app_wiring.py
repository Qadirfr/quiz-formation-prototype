"""Structural checks for the two independent learner paths (no Streamlit runtime)."""

from pathlib import Path
import ast


def test_both_quiz_paths_use_card_renderers_and_separate_state():
    source = (Path(__file__).resolve().parents[1] / "app.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    functions = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
    for function_name, expected_state_marker in (
        ("render_test_question", "attempt_{attempt_id"),
        ("render_session_question", "session_{session_id}_participant_"),
    ):
        function = functions[function_name]
        calls = [
            node.func.id
            for node in ast.walk(function)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        ]
        assert calls.count("render_ordering_cards") == 1
        assert calls.count("render_matching_cards") == 1
        assert expected_state_marker in ast.get_source_segment(source, function)


def test_live_containers_are_used_outside_forms():
    source = (Path(__file__).resolve().parents[1] / "app.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    functions = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
    assert "has_interactive_card_activity" in functions
    assert "interactive_quiz" in source
    assert "interactive_session" in source
    assert "st.container() if interactive_quiz else st.form" in source
