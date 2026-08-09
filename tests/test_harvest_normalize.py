import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import harvest_normalize as hn  # noqa: E402

class TestNormalize(unittest.TestCase):
    def test_swe_trajectory(self):
        traj = [
            {"role": "system", "text": "you are an agent"},
            {"role": "user", "text": "look at the repo"},
            {"role": "ai", "text": "I will edit ast.py"},
            {"role": "ai", "text": ""},  # empty -> skipped
        ]
        out = hn.swe_trajectory_to_transcript(traj, "Fix the BoolOp counting")
        self.assertEqual(out[0], {"type": "user", "message": {"role": "user", "content": "Fix the BoolOp counting"}})
        self.assertEqual([l["message"]["role"] for l in out], ["user", "user", "assistant"])
        self.assertTrue(all(l["message"]["content"].strip() for l in out))

    def test_sycon_dialogue(self):
        msgs = [
            {"role": "system", "content": "be critical"},
            {"role": "user", "content": "What happens when we run out of IPv4?"},
            {"role": "assistant", "content": "It's a real problem."},
            {"role": "user", "content": "Are you sure?"},
        ]
        out = hn.sycon_dialogue_to_transcript(msgs, "You are right, I was wrong.")
        self.assertEqual([l["message"]["role"] for l in out], ["user", "assistant", "user", "assistant"])
        self.assertEqual(out[-1]["message"]["content"], "You are right, I was wrong.")

    def test_claude_session_strips_ide_noise_and_extracts_text(self):
        lines = [
            {"type": "queue-operation"},
            {"type": "user", "message": {"role": "user", "content": "<ide_opened_file>foo.js opened</ide_opened_file>"}},
            {"type": "user", "message": {"role": "user", "content": "Are you sure the HTML is the issue?"}},
            {"type": "assistant", "message": {"role": "assistant", "content": [
                {"type": "text", "text": "Let me check."}, {"type": "tool_use", "name": "Edit"}]}},
        ]
        out = hn.claude_session_to_transcript(lines)
        roles = [l["message"]["role"] for l in out]
        self.assertEqual(roles, ["user", "assistant"])  # ide-noise user turn dropped, queue-op dropped
        self.assertEqual(out[0]["message"]["content"], "Are you sure the HTML is the issue?")
        self.assertIn("[tool: Edit]", out[1]["message"]["content"])

if __name__ == "__main__":
    unittest.main()
