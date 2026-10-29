"""Tests for the simplified core pipeline (Oct 27, 2026): ingest by
extension, the lesson pick, timestamp helpers, correction rendering,
and the write-up parser used by the optional page generator."""
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))

import ingest as ingest_mod
import run_pipeline as rp
import find_corrections as fc
import make_page


class TestIngest(unittest.TestCase):
    def test_classify_by_extension_only(self):
        self.assertEqual(ingest_mod.classify("/x/IMG_4021.MP4"), "media")
        self.assertEqual(ingest_mod.classify("/x/voice memo.m4a"), "media")
        self.assertEqual(ingest_mod.classify("/x/unwritten_teach_1.webm"), "media")
        self.assertEqual(ingest_mod.classify("/x/photo.jpg"), "photos")
        self.assertEqual(ingest_mod.classify("/x/notes.txt"), "unknown")

    def test_pick_lesson_is_largest(self):
        with tempfile.TemporaryDirectory() as td:
            small = os.path.join(td, "clip.mp4")
            big = os.path.join(td, "lesson.mp4")
            with open(small, "wb") as fh:
                fh.write(b"x" * 10)
            with open(big, "wb") as fh:
                fh.write(b"x" * 100)
            picked, note = ingest_mod.pick_lesson([small, big])
            self.assertEqual(picked, big)
            self.assertIn("largest", note)

    def test_pick_lesson_single_and_none(self):
        self.assertEqual(ingest_mod.pick_lesson(["/x/a.mp4"]), ("/x/a.mp4", ""))
        self.assertEqual(ingest_mod.pick_lesson([]), (None, ""))


class TestTimestamps(unittest.TestCase):
    def test_parse_and_fmt_roundtrip(self):
        self.assertEqual(rp.parse_ts("02:08"), 128)
        self.assertEqual(rp.parse_ts("1:02:08"), 3728)
        self.assertEqual(rp.fmt_ts(128), "02:08")
        with self.assertRaises(ValueError):
            rp.parse_ts("soon")

    def test_segment_ends(self):
        text = "[00:04] a\n[02:08] b\n[03:41] c\n"
        self.assertEqual(rp.segment_ends(text), {4: 128, 128: 221, 221: 241})

    def test_clip_window_pads_and_clamps(self):
        self.assertEqual(rp.clip_window(128, 140), (126, 142))
        self.assertEqual(rp.clip_window(1, 5), (0, 7))
        self.assertEqual(rp.clip_window(60, None), (58, 80))


class TestRenderCorrections(unittest.TestCase):
    def test_render_includes_quote_anchor_and_clip(self):
        hits = [{"start": "02:08", "quote": "No — fold, don't push.",
                 "correcting": "pressing down"}]
        md = rp.render_corrections_md(hits, {1: "correction-01.mp4"})
        self.assertIn("02:08", md)
        self.assertIn("fold, don't push", md)
        self.assertIn("clips/correction-01.mp4", md)

    def test_render_empty(self):
        self.assertIn("No corrections found", rp.render_corrections_md([], {}))


class TestParseFinderHits(unittest.TestCase):
    def test_clean_array(self):
        hits = fc.parse_hits('[{"start": "02:08", "quote": "q", "correcting": "c"}]')
        self.assertEqual(hits[0]["start"], "02:08")

    def test_fenced_array(self):
        self.assertEqual(fc.parse_hits('```json\n[]\n```'), [])

    def test_doubled_empty_array(self):
        # Observed live (Oct 29): the finder means "no corrections"
        # but emits the empty array twice; take the first, don't crash.
        self.assertEqual(fc.parse_hits('[][]'), [])

    def test_rejects_non_array(self):
        with self.assertRaises(SystemExit):
            fc.parse_hits('{"start": "02:08"}')

    def test_rejects_garbage(self):
        with self.assertRaises(SystemExit):
            fc.parse_hits('no corrections here, just prose')


class TestParseWriteup(unittest.TestCase):
    def test_steps_and_wisdom_split(self):
        md = ("# Mother's Bread — the write-up\n\n"
              "1. Mix the flour.\n2. Knead until it stops fighting you.\n\n"
              "## What Mother knows\n\n- Warm water, like bath water.\n")
        steps, wisdom = make_page.parse_writeup(md)
        self.assertEqual(steps, ["Mix the flour.",
                                 "Knead until it stops fighting you."])
        self.assertEqual(wisdom, ["Warm water, like bath water."])


if __name__ == "__main__":
    unittest.main()
