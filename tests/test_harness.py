import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "harness"))
from apprentice import parse_commitments, analyze, gap_score, is_default, strip_wisdom


def run(angle=90, force="moderate", sentence="I do the step."):
    return [{"step": 1, "tool": "unspecified", "angle_deg": angle, "force": force,
             "force_location": "center", "duration_s": 10, "repetitions": 1,
             "size": "unspecified-medium", "amount": "unspecified-amount",
             "temperature": "ambient",
             "stopping_condition": "when the step's motion is complete",
             "in_my_words": sentence}]


class ParseTests(unittest.TestCase):
    def test_plain_json(self):
        steps = parse_commitments(json.dumps({"steps": run()}))
        self.assertEqual(len(steps), 1)

    def test_fenced_json_with_prose(self):
        raw = "Here is my answer:\n```json\n" + json.dumps({"steps": run()}) + "\n```\nDone."
        self.assertEqual(len(parse_commitments(raw)), 1)

    def test_garbage_raises(self):
        with self.assertRaises(ValueError):
            parse_commitments("no json here")


class AnalyzeTests(unittest.TestCase):
    def test_all_default_step_scores_high(self):
        report = analyze([run(), run()])
        self.assertEqual(report[0]["defaults"],
                         ["tool", "angle_deg", "force", "force_location", "duration_s",
                          "repetitions", "size", "amount", "temperature",
                          "stopping_condition"])
        self.assertGreater(gap_score(report[0]), 10)

    def test_divergence_detected(self):
        report = analyze([run(angle=90), run(angle=45)])
        self.assertIn("angle_deg", report[0]["divergences"])
        self.assertNotIn("angle_deg", report[0]["defaults"])

    def test_specified_consistent_step_is_quiet(self):
        specified = [{"step": 1, "tool": "lame", "angle_deg": 30, "force": "light",
                      "force_location": "edge", "duration_s": 3,
                      "repetitions": 2, "size": "pea-sized",
                      "amount": "one spoonful", "temperature": "hot oven",
                      "stopping_condition": "when the seam opens",
                      "in_my_words": "I cut shallow."}]
        report = analyze([specified, specified])
        self.assertEqual(gap_score(report[0]), 0)

    def test_is_default_numeric_tolerance(self):
        self.assertTrue(is_default("angle_deg", 90.0))
        self.assertFalse(is_default("angle_deg", 89.5))

    def test_strip_wisdom(self):
        card = ("# Rosa's Boule — the card\n\n1. Dust the top.\n2. One line.\n\n"
                "## What Rosa knows\n\n- It should tear a little.\n")
        stripped = strip_wisdom(card)
        self.assertIn("1. Dust the top.", stripped)
        self.assertNotIn("What Rosa knows", stripped)
        self.assertNotIn("tear a little", stripped)
        self.assertEqual(strip_wisdom(stripped), stripped)  # no-op without a section

    def test_canon_variants_agree(self):
        # 90 vs "90" vs 90.0 are the same commitment: default, not divergent.
        a, b = run(angle=90), run(angle="90")
        report = analyze([a, b])
        self.assertIn("angle_deg", report[0]["defaults"])
        self.assertNotIn("angle_deg", report[0]["divergences"])

    def test_none_value_is_missing(self):
        a = run(); a[0]["temperature"] = None
        report = analyze([a, run()])
        self.assertIn("temperature", report[0]["missing"])

    def test_minority_step_is_never_fully_specified(self):
        two_steps = run() + [{"step": 2, "tool": "lame", "angle_deg": 30,
                              "force": "light", "force_location": "edge",
                              "duration_s": 3, "repetitions": 2, "size": "pea-sized",
                              "amount": "one spoonful", "temperature": "hot oven",
                              "stopping_condition": "when the seam opens",
                              "in_my_words": "I cut shallow."}]
        report = analyze([two_steps, run()])
        step2 = [s for s in report if s["step"] == 2][0]
        self.assertEqual(step2["n_present"], 1)
        self.assertEqual(len(step2["missing"]), 10)  # unattempted run = all missing
        self.assertGreater(gap_score(step2), 0)

    def test_non_dict_step_raises(self):
        with self.assertRaises(ValueError):
            parse_commitments('{"steps": [1, 2]}')

    def test_second_fence_wins_when_first_is_garbage(self):
        good = json.dumps({"steps": run()})
        raw = "```json\n{not json\n```\nthen:\n```json\n" + good + "\n```"
        self.assertEqual(len(parse_commitments(raw)), 1)

    def test_strip_wisdom_variants(self):
        for heading in ("## What Rosa Knows", "### What rosa knows",
                        "## What the teacher knows"):
            card = "# T\n\n1. One.\n\n" + heading + "\n\n- secret judgment\n"
            stripped = strip_wisdom(card)
            self.assertNotIn("secret judgment", stripped, heading)
            self.assertIn("1. One.", stripped, heading)
        # Wisdom not last: content after the next ## heading survives.
        card = "# T\n\n1. One.\n\n## What Rosa knows\n\n- secret\n\n## Later\n\nkeep me\n"
        stripped = strip_wisdom(card)
        self.assertNotIn("secret", stripped)
        self.assertIn("keep me", stripped)

    def test_contract_matches_instruction_file(self):
        # The "must match exactly" rule, enforced: every DEFAULTS entry
        # appears in the apprentice instruction with its default value,
        # and the example JSON carries all 10 keys.
        path = os.path.join(os.path.dirname(__file__), "..", "prompts",
                            "apprentice_instruction.txt")
        with open(path) as fh:
            text = fh.read()
        from apprentice import DEFAULTS
        import re as _re
        for param, default in DEFAULTS.items():
            self.assertIn("`" + param + "`", text, param)
            pat = r"DEFAULT:\s+`?" + _re.escape(str(default)) + r"`?(?![0-9])"
            self.assertRegex(text, pat, param)
            self.assertIn('"' + param + '"', text, param + " in example JSON")

    def test_missing_key_is_silence_not_specification(self):
        # A run that omits a parameter (e.g. by copying a stale example)
        # must register as missing — never as fully specified.
        incomplete = run()
        del incomplete[0]["temperature"]
        report = analyze([incomplete, run()])
        self.assertIn("temperature", report[0]["missing"])
        # Independent computation (Wonder review): the run that DID
        # commit used the default, so temperature is also at-default —
        # missing and default are separate facts, both reported.
        self.assertIn("temperature", report[0]["defaults"])
        self.assertGreater(gap_score(report[0]), 0)


if __name__ == "__main__":
    unittest.main()
