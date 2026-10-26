import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "harness"))
from apprentice import parse_commitments, analyze, gap_score, is_default


def run(angle=90, force="moderate", sentence="I do the step."):
    return [{"step": 1, "angle_deg": angle, "force": force,
             "force_location": "center", "duration_s": 10, "repetitions": 1,
             "size": "unspecified-medium",
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
                         ["angle_deg", "force", "force_location", "duration_s",
                          "repetitions", "size", "stopping_condition"])
        self.assertGreater(gap_score(report[0]), 10)

    def test_divergence_detected(self):
        report = analyze([run(angle=90), run(angle=45)])
        self.assertIn("angle_deg", report[0]["divergences"])
        self.assertNotIn("angle_deg", report[0]["defaults"])

    def test_specified_consistent_step_is_quiet(self):
        specified = [{"step": 1, "angle_deg": 30, "force": "light",
                      "force_location": "edge", "duration_s": 3,
                      "repetitions": 2, "size": "pea-sized",
                      "stopping_condition": "when the seam opens",
                      "in_my_words": "I cut shallow."}]
        report = analyze([specified, specified])
        self.assertEqual(gap_score(report[0]), 0)

    def test_is_default_numeric_tolerance(self):
        self.assertTrue(is_default("angle_deg", 90.0))
        self.assertFalse(is_default("angle_deg", 89.5))


if __name__ == "__main__":
    unittest.main()
