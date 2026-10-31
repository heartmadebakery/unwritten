"""Terminology contract: the product calls its storage "Cloud" (not the
vendor's name), itself "Unwritten Craft" on every platform (never the
retired "Unwritten Recorder"), and the lesson-giver a generic mentor —
no "teacher", no she/her anywhere in live code, copy, prompts, samples,
or tests.

Dated history is exempt: CHANGELOG.md and the dated docs logs record
the past, so they keep their original wording. Vendor endpoints
(video.bunnycdn.com, bunny.net docs/account links) and one-generation
legacy storage keys are the only allowed "bunny" mentions, and the
legacy keys must sit on lines marked legacy."""
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

LIVE_DIRS = ["app", "pipeline", "harness", "prompts", "samples", "tests"]
LIVE_FILES = ["README.md",
              os.path.join("docs", "DEVICES.md"),
              os.path.join("docs", "PIPELINE.md"),
              os.path.join("docs", "android-app-worklog.md")]
SCAN_EXTS = (".py", ".md", ".txt", ".js", ".java", ".xml", ".html",
             ".webmanifest", ".toml",
             ".swift", ".cpp", ".h", ".mm", ".plist", ".pbxproj",
             ".xcscheme")
SKIP_DIRS = {"__pycache__", "build-manual", "build", "models", "icons"}

BANNED_MENTOR = re.compile(r"\b(teachers?|she|her|hers|herself)\b",
                           re.IGNORECASE)
VENDOR_BUNNY = re.compile(r"bunny", re.IGNORECASE)
VENDOR_LINE = re.compile(r"bunnycdn\.com|bunny\.net")
LEGACY_LINE = re.compile(r"legacy", re.IGNORECASE)


SELF = os.path.basename(__file__)


def live_text_files():
    # The harness itself is exempt: it must name the banned tokens to
    # forbid them.
    paths = [os.path.join(ROOT, f) for f in LIVE_FILES]
    for d in LIVE_DIRS:
        for base, dirs, files in os.walk(os.path.join(ROOT, d)):
            dirs[:] = [x for x in dirs if x not in SKIP_DIRS]
            for f in files:
                if f.endswith(SCAN_EXTS) and f != SELF:
                    paths.append(os.path.join(base, f))
    return sorted(paths)


class TerminologyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.files = live_text_files()
        assert cls.files, "no live files found to scan"

    def test_no_teacher_or_gendered_pronouns(self):
        bad = []
        for path in self.files:
            with open(path, encoding="utf-8", errors="replace") as fh:
                for i, line in enumerate(fh, 1):
                    m = BANNED_MENTOR.search(line)
                    if m:
                        bad.append("%s:%d:%s" % (
                            os.path.relpath(path, ROOT), i, m.group(0)))
        self.assertEqual(bad, [], "banned mentor terms:\n" + "\n".join(bad))

    def test_no_bunny_product_naming(self):
        bad = []
        for path in self.files:
            with open(path, encoding="utf-8", errors="replace") as fh:
                for i, line in enumerate(fh, 1):
                    if VENDOR_BUNNY.search(line) and not VENDOR_LINE.search(line) \
                            and not LEGACY_LINE.search(line):
                        bad.append("%s:%d: %s" % (
                            os.path.relpath(path, ROOT), i, line.strip()[:80]))
        self.assertEqual(bad, [], "bunny product naming:\n" + "\n".join(bad))

    def test_no_unwritten_recorder_product_naming(self):
        # The product is one app called Unwritten Craft on all three
        # platforms; the retired "Unwritten Recorder" product name must
        # not survive in live code, copy, or docs. Internal identifiers
        # without the space (UnwrittenRecorderApp, the app/recorder and
        # recorder/ paths) are untouched and do not match.
        bad = []
        for path in self.files:
            with open(path, encoding="utf-8", errors="replace") as fh:
                for i, line in enumerate(fh, 1):
                    if "Unwritten Recorder" in line:
                        bad.append("%s:%d: %s" % (
                            os.path.relpath(path, ROOT), i, line.strip()[:80]))
        self.assertEqual(bad, [],
                         "retired product naming:\n" + "\n".join(bad))


if __name__ == "__main__":
    unittest.main()
