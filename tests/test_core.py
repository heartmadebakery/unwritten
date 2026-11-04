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
import draft_writeup as dw
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

    def test_parse_tolerates_brackets_and_fractions(self):
        # The transcript shows [02:08]; a literal finder echoes the
        # brackets. Both that and fractional seconds parse.
        self.assertEqual(rp.parse_ts("[02:08]"), 128)
        self.assertEqual(rp.parse_ts(" 02:08.5 "), 128)
        self.assertEqual(rp.parse_ts("[1:02:08]"), 3728)

    def test_parse_rejects_out_of_range(self):
        # "02:99" silently meant 03:39 before; negatives wrapped the
        # clip to the wrong end of the lesson.
        for bad in ["02:99", "1:99:08", "02:-3", "-1:30", ""]:
            with self.assertRaises(ValueError, msg=bad):
                rp.parse_ts(bad)
        # Long lessons still parse: minutes are unbounded in mm:ss.
        self.assertEqual(rp.parse_ts("75:10"), 4510)

    def test_segment_ends(self):
        text = "[00:04] a\n[02:08] b\n[03:41] c\n"
        self.assertEqual(rp.segment_ends(text), {4: 128, 128: 221, 221: 241})

    def test_segment_ends_dedupes_and_sorts(self):
        # Same-second ASR turns and out-of-order input must not yield
        # zero or negative clip windows.
        text = "[02:08] b\n[00:04] a\n[02:08] b2\n[03:41] c\n"
        self.assertEqual(rp.segment_ends(text), {4: 128, 128: 221, 221: 241})

    def test_correction_end_bisects(self):
        # A finder timestamp that lands mid-segment ends at the next
        # segment start — not at a blind 20-second default.
        # User-ordered 2026-11-01: beats are capped at 60 s, so the
        # two long spans below end at start+60 instead of the far
        # segment boundary (sparse API transcripts yielded 4-minute
        # "moments" that also blew the highlight size limit).
        ends = {4: 128, 128: 221, 221: 241}
        self.assertEqual(rp.correction_end(128, ends), 188)
        self.assertEqual(rp.correction_end(130, ends), 190)
        self.assertEqual(rp.correction_end(0, ends), 4)
        self.assertEqual(rp.correction_end(999, ends), 1019)

    def test_correction_end_caps_sparse_segments(self):
        # The onion-lesson case: a 01:43 correction inside a
        # 4-minute segment cuts a 60 s beat (+2 s padding), not the
        # whole 236 s span.
        ends = rp.segment_ends("[01:43] a\n[05:39] b\n[07:58] c\n")
        self.assertEqual(rp.correction_end(103, ends), 163)
        self.assertEqual(rp.clip_window(103, 163), (101, 165))

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

    def test_every_planted_correction_cuts_a_window(self):
        # The finder's downstream contract, without the LLM: each
        # ground-truth anchor from docs/core-test-2026-10-27.md must
        # parse and resolve to a positive clip window against the
        # real fixture transcript.
        fixture = os.path.join(ROOT, "samples",
                               "lesson_transcript_fixture.md")
        text = open(fixture).read()
        ends = rp.segment_ends(text)
        self.assertGreater(len(ends), 50)
        for stamp in ["02:08", "03:41", "05:38", "07:04", "08:28",
                      "10:12"]:
            start = rp.parse_ts(stamp)
            lo, hi = rp.clip_window(start, rp.correction_end(start, ends))
            self.assertLess(lo, hi, stamp)
            self.assertGreaterEqual(lo, 0, stamp)

    def test_every_fixture_line_parses(self):
        fixture = os.path.join(ROOT, "samples",
                               "lesson_transcript_fixture.md")
        stamped = [ln for ln in open(fixture).read().splitlines()
                   if ln.startswith("[")]
        self.assertGreater(len(stamped), 50)
        for line in stamped:
            rp.parse_ts(line.split("]")[0].strip("["))

    def test_load_hits_rejects_corrupt_file(self):
        with tempfile.TemporaryDirectory() as td:
            bad = os.path.join(td, "corrections.json")
            with open(bad, "w") as fh:
                fh.write("{nope")
            with self.assertRaises(SystemExit):
                rp.load_hits(bad)
            with open(bad, "w") as fh:
                fh.write('{"start": "00:04"}')
            with self.assertRaises(SystemExit):
                rp.load_hits(bad)
            with open(bad, "w") as fh:
                fh.write('[{"start": "00:04"}]')
            self.assertEqual(rp.load_hits(bad), [{"start": "00:04"}])


class TestParseFinderHits(unittest.TestCase):
    def test_clean_array(self):
        hits = fc.parse_hits('[{"start": "02:08", "quote": "q", '
                             '"correcting": "c", "segment": "hands"}]')
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


class TestTranscriptGate(unittest.TestCase):
    def _write(self, td, name, content):
        path = os.path.join(td, name)
        with open(path, "w") as fh:
            fh.write(content)
        return path

    def test_blank_transcript_refused(self):
        # A blank --transcript would let the model invent a lesson
        # from nothing; the transcribers already refuse emptiness,
        # and the bypass must too.
        with tempfile.TemporaryDirectory() as td:
            path = self._write(td, "t.txt", "  \n")
            with self.assertRaises(SystemExit):
                rp.check_transcript_file(path)

    def test_untimestamped_transcript_refused(self):
        # Without [mm:ss] lines there is nothing to anchor clips to.
        with tempfile.TemporaryDirectory() as td:
            path = self._write(td, "t.txt", "just prose, no stamps\n")
            with self.assertRaises(SystemExit):
                rp.check_transcript_file(path)

    def test_missing_transcript_refused(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(SystemExit):
                rp.check_transcript_file(os.path.join(td, "nope.txt"))

    def test_timestamped_transcript_passes(self):
        with tempfile.TemporaryDirectory() as td:
            path = self._write(td, "t.txt", "[00:04] hello\n[02:08] fold\n")
            self.assertEqual(rp.check_transcript_file(path),
                             "[00:04] hello\n[02:08] fold\n")

    def test_muse_preflight_names_the_missing_cli(self):
        # The default keyless path shells out to `muse`; a missing
        # binary must fail with a pointer, not a raw traceback.
        from unittest import mock
        with tempfile.TemporaryDirectory() as td:
            exe = os.path.join(td, "muse")
            with open(exe, "w") as fh:
                fh.write("#!/bin/sh\n")
            with mock.patch.object(dw, "MUSE_BIN", exe):
                self.assertEqual(dw.muse_bin(), exe)
            with mock.patch.object(fc, "MUSE_BIN", exe):
                self.assertEqual(fc.muse_bin(), exe)
        with mock.patch.object(dw, "MUSE_BIN", "/nonexistent/muse"):
            with self.assertRaises(SystemExit):
                dw.muse_bin()
        with mock.patch.object(fc, "MUSE_BIN", "/nonexistent/muse"):
            with self.assertRaises(SystemExit):
                fc.muse_bin()


class TestDraftWriteup(unittest.TestCase):
    # User-ordered 2026-11-02: titles are simple summaries, no "Mentor's" prefix
    # and no " — the write-up" suffix. Updated from "Mentor's Sinigang — the write-up".
    NEW_FORMAT = (
        "# Sinigang\n\n"
        "A sour pork soup, built in one pot in under an hour.\n\n"
        "## What you need\n\n"
        "- pork belly\n- tomatoes\n\n"
        "## Steps\n\n"
        "1. Cut the pork.\n2. Simmer until tender.\n\n"
        "## What Mentor knows\n\n"
        "- Taste before serving.\n"
    )

    def test_validate_accepts_sections_steps_and_title(self):
        self.assertEqual(dw.validate_writeup(self.NEW_FORMAT), "")

    def test_validate_rejects_missing_parts(self):
        self.assertNotEqual(dw.validate_writeup("just prose, no structure"), "")
        self.assertNotEqual(
            dw.validate_writeup("# Title\n\nno steps here\n\n## Steps\n"), "")
        self.assertNotEqual(
            dw.validate_writeup("# Title\n\n1. A step but no sections.\n"), "")

    def test_extract_frames_degrades_without_media(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(dw.extract_frames("/nonexistent/x.mp4", td), [])
            self.assertEqual(dw.extract_frames("", td), [])

    def test_page_parser_reads_new_format(self):
        intro, needs, steps, wisdom = make_page.parse_writeup(self.NEW_FORMAT)
        self.assertEqual(intro, "A sour pork soup, built in one pot in under an hour.")
        self.assertEqual(needs, ["pork belly", "tomatoes"])
        self.assertEqual(steps, ["Cut the pork.", "Simmer until tender."])
        self.assertEqual(wisdom, ["Taste before serving."])

    def test_render_writeup_embeds_step_stills(self):
        # User-ordered 2026-11-04: each write-up step carries its
        # screengrab from the lesson video.
        md = dw.render_writeup(
            {"title": "Soup", "intro": "Intro.",
             "needs": [], "steps": ["Boil.", "Serve."], "knows": []},
            stills=["stills/step-01.jpg", "stills/step-02.jpg"])
        self.assertIn("![Step 1](stills/step-01.jpg)", md)
        self.assertIn("![Step 2](stills/step-02.jpg)", md)
        self.assertEqual(dw.validate_writeup(md), "")
        _, _, steps, _ = make_page.parse_writeup(md)
        self.assertEqual(steps, ["Boil.", "Serve."])

    def test_step_times_spread_across_duration(self):
        times = dw.step_times(90.0, 2)
        self.assertEqual(len(times), 2)
        self.assertLess(times[0], times[1])
        self.assertGreater(times[0], 0)
        self.assertLess(times[1], 90.0)

    def test_extract_step_stills_degrades_without_media(self):
        with tempfile.TemporaryDirectory() as td:
            out = os.path.join(td, "writeup.md")
            self.assertEqual(dw.extract_step_stills("", out, 2), [])
            self.assertEqual(
                dw.extract_step_stills("/nonexistent/x.mp4", out, 2), [])

    def test_attach_stills_skips_missing(self):
        md = "# T\n\n## Steps\n\n1. A.\n2. B.\n"
        out = dw.attach_stills(md, ["stills/step-01.jpg", ""])
        self.assertIn("![Step 1](stills/step-01.jpg)", out)
        self.assertNotIn("Step 2", out)

    def test_parse_step_images_maps_steps(self):
        md = ("# T\n\n## Steps\n\n1. A.\n![Step 1](stills/step-01.jpg)\n"
              "2. B.\n")
        self.assertEqual(dw.parse_step_images(md),
                         {1: "stills/step-01.jpg"})


class TestParseWriteup(unittest.TestCase):
    def test_steps_and_wisdom_split(self):
        md = ("# Mother's Bread — the write-up\n\n"
              "1. Mix the flour.\n2. Knead until it stops fighting you.\n\n"
              "## What Mother knows\n\n- Warm water, like bath water.\n")
        intro, needs, steps, wisdom = make_page.parse_writeup(md)
        self.assertEqual(intro, "")
        self.assertEqual(needs, [])
        self.assertEqual(steps, ["Mix the flour.",
                                 "Knead until it stops fighting you."])
        self.assertEqual(wisdom, ["Warm water, like bath water."])

    def test_page_renders_step_stills(self):
        # User-ordered 2026-11-04: the page shows each step's
        # screengrab beside the step.
        import sys
        from unittest import mock
        with tempfile.TemporaryDirectory() as td:
            os.makedirs(os.path.join(td, "stills"))
            with open(os.path.join(td, "writeup.md"), "w") as fh:
                fh.write("# T\n\nIntro.\n\n## Steps\n\n1. Do it.\n"
                         "![Step 1](stills/step-01.jpg)\n")
            with open(os.path.join(td, "stills", "step-01.jpg"), "wb") as fh:
                fh.write(b"x")
            with open(os.path.join(td, "corrections.json"), "w") as fh:
                fh.write("[]")
            argv = ["make_page.py", "--work", td, "--title", "T"]
            with mock.patch.object(sys, "argv", argv):
                make_page.main()
            with open(os.path.join(td, "page.html")) as fh:
                page = fh.read()
            self.assertIn('src="stills/step-01.jpg"', page)
            self.assertIn('class="still"', page)
            self.assertIn('<a href="stills/step-01.jpg"', page)

    def test_page_renders_audio_clips_and_survives_corrupt_json(self):
        # Audio-only lessons cut correction-NN.m4a; a corrupt
        # corrections.json must not kill the whole page.
        import sys
        from unittest import mock
        with tempfile.TemporaryDirectory() as td:
            os.makedirs(os.path.join(td, "clips"))
            with open(os.path.join(td, "writeup.md"), "w") as fh:
                fh.write("# T — the write-up\n\nIntro line.\n\n"
                         "## Steps\n\n1. Do it.\n")
            with open(os.path.join(td, "corrections.json"), "w") as fh:
                fh.write('[{"start": "00:04", "quote": "q", '
                         '"correcting": "c"}]')
            with open(os.path.join(td, "clips",
                                   "correction-01.m4a"), "wb") as fh:
                fh.write(b"x")
            argv = ["make_page.py", "--work", td, "--title", "T"]
            with mock.patch.object(sys, "argv", argv):
                make_page.main()
            with open(os.path.join(td, "page.html")) as fh:
                page = fh.read()
            self.assertIn("<audio controls", page)
            self.assertIn("correction-01.m4a", page)
            self.assertIn("Intro line.", page)
            # Now corrupt the JSON: the page still renders.
            with open(os.path.join(td, "corrections.json"), "w") as fh:
                fh.write("{nope")
            with mock.patch.object(sys, "argv", argv):
                make_page.main()
            with open(os.path.join(td, "page.html")) as fh:
                page = fh.read()
            self.assertIn("No corrections captured", page)


class TestRootLock(unittest.TestCase):
    def test_second_holder_is_refused_until_released(self):
        # --cloud/--fetch take an exclusive lock on the work root so
        # a manual run can never process videos alongside cron (or
        # another manual run): same-machine races are impossible.
        with tempfile.TemporaryDirectory() as td:
            first = rp.hold_root_lock(td)
            self.assertIsNotNone(first)
            self.assertIsNone(rp.hold_root_lock(td))
            first.close()
            second = rp.hold_root_lock(td)
            self.assertIsNotNone(second)
            second.close()

    def test_main_skips_cloud_when_locked(self):
        from unittest import mock
        with tempfile.TemporaryDirectory() as td:
            held = rp.hold_root_lock(td)
            try:
                with mock.patch.object(sys, "argv",
                                       ["run_pipeline.py", "--cloud", td]), \
                     mock.patch.object(rp, "run_cloud_mode") as mode:
                    with self.assertRaises(SystemExit) as ctx:
                        rp.main()
            finally:
                held.close()
        self.assertEqual(ctx.exception.code, 0)
        mode.assert_not_called()

    def test_main_skips_fetch_when_locked(self):
        from unittest import mock
        with tempfile.TemporaryDirectory() as td:
            held = rp.hold_root_lock(td)
            try:
                with mock.patch.object(sys, "argv",
                                       ["run_pipeline.py", "--fetch", td]), \
                     mock.patch.object(rp, "run_fetch_mode") as mode:
                    with self.assertRaises(SystemExit) as ctx:
                        rp.main()
            finally:
                held.close()
        self.assertEqual(ctx.exception.code, 0)
        mode.assert_not_called()

    def test_main_proceeds_when_free(self):
        from unittest import mock
        with tempfile.TemporaryDirectory() as td:
            with mock.patch.object(sys, "argv",
                                   ["run_pipeline.py", "--cloud", td]), \
                 mock.patch.object(rp, "run_cloud_mode",
                                   return_value=0) as mode:
                with self.assertRaises(SystemExit) as ctx:
                    rp.main()
        self.assertEqual(ctx.exception.code, 0)
        mode.assert_called_once_with(td, max_n=0, retry_failed=False,
                                     state_path="")


class TestSetupSh(unittest.TestCase):
    """setup.sh promises any new machine (Ubuntu/WSL2, macOS) a
    verified tree."""

    @classmethod
    def setUpClass(cls):
        with open(os.path.join(ROOT, "setup.sh")) as fh:
            cls.sh = fh.read()

    def test_ffmpeg_download_matches_the_machine(self):
        # A hard-coded amd64 build cannot run on arm64 Linux (this
        # very host) or macOS: the static build follows uname, and a
        # machine with none names the install instead.
        ff = self.sh.split("if ! command -v ffmpeg", 1)[1].split("\nfi\n", 1)[0]
        self.assertIn("uname -m", ff)
        self.assertIn("arm64", ff)
        self.assertIn("amd64", ff)
        self.assertIn("brew install ffmpeg", ff)
        self.assertIn("exit 1", ff)

    def test_checkpoint_download_lands_atomically(self):
        # An interrupted 375 MB download left a truncated checkpoint
        # that the existence check accepted forever after.
        sam = self.sh.split("# SAM", 1)[1].split("\n\n", 1)[0]
        self.assertIn(".part", sam)
        self.assertIn("curl -fL", sam)
        self.assertIn("mv ", sam)

    def test_scaffolds_env_with_fetch_defaults(self):
        # A fresh clone has no .env — setup.sh must scaffold it with
        # the baked signer so --fetch never silently skips (2026-11-03).
        self.assertIn(".env", self.sh)
        self.assertIn("FETCH_QUEUE_URL", self.sh)
        self.assertIn("CLOUD_PROXY_URL", self.sh)
        self.assertIn("https://unwritten-cloud-signer.heartmade.workers.dev", self.sh)


if __name__ == "__main__":
    unittest.main()
