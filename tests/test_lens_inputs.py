import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
import lens_inputs  # noqa: E402

FLOW = "inputs:\n  transcript: conversation\n"
INLINE = "inputs: { transcript: activity }\n"


def _md(front):
    return "---\nname: x\ntools: Read\n{}---\n\nbody\n".format(front)


def test_declared_view_block_form():
    assert lens_inputs.declared_view(_md(FLOW)) == "conversation"


def test_declared_view_inline_form():
    assert lens_inputs.declared_view(_md(INLINE)) == "activity"


def test_missing_inputs_defaults_to_full():
    assert lens_inputs.declared_view(_md("")) == "full"


def test_unknown_view_falls_back_to_full():
    assert lens_inputs.declared_view(_md("inputs:\n  transcript: bogus\n")) == "full"


def test_requested_views_unions_and_defaults(tmp_path):
    (tmp_path / "a.md").write_text(_md(FLOW), encoding="utf-8")
    (tmp_path / "b.md").write_text(_md(INLINE), encoding="utf-8")
    # 'c' has no file -> full
    assert lens_inputs.requested_views(tmp_path, ["a", "b", "c"]) == {"conversation", "activity", "full"}
