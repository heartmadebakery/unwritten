"""Tests for cloud fetch and run_pipeline --cloud mode.

One full pipeline run per new finished cloud video; credentials come
from CLOUD_* env vars; only status-4 videos unseen in the state file
are processed.
"""
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))

import cloud_fetch as cf
import run_pipeline as rp


def video(guid, status=4, title="Lesson", res="720p"):
    return {"guid": guid, "title": title, "status": status,
            "availableResolutions": res,
            "dateUploaded": "2026-10-28T10:00:00"}


class TestSelectReady(unittest.TestCase):
    def test_only_finished_and_unseen(self):
        vids = [video("new-ok"), video("processing", status=2),
                video("failed", status=5), video("seen")]
        state = {"seen": {"title": "Old", "result": "done"}}
        ready = cf.select_ready(vids, state)
        self.assertEqual([v["guid"] for v in ready], ["new-ok"])

    def test_failed_retried_only_with_flag(self):
        vids = [video("bad")]
        state = {"bad": {"title": "Bad", "result": "failed"}}
        self.assertEqual(cf.select_ready(vids, state), [])
        self.assertEqual(len(cf.select_ready(vids, state, retry_failed=True)), 1)

    def test_done_never_reprocessed(self):
        vids = [video("done")]
        state = {"done": {"title": "Old", "result": "done"}}
        self.assertEqual(
            cf.select_ready(vids, state, retry_failed=True), [])


class TestSanitizeAndUrls(unittest.TestCase):
    def test_sanitize(self):
        self.assertEqual(cf.sanitize("Mother's Bread: lesson #2"),
                         "Mother_s_Bread_lesson_2")
        self.assertEqual(cf.sanitize("  "), "lesson")

    def test_mp4_candidates_highest_first(self):
        urls = cf.mp4_candidates("vz-x.b-cdn.net", "abc", "240p,720p,1080p")
        self.assertEqual(urls, [
            "https://vz-x.b-cdn.net/abc/play_1080p.mp4",
            "https://vz-x.b-cdn.net/abc/play_720p.mp4",
            "https://vz-x.b-cdn.net/abc/play_240p.mp4",
        ])

    def test_mp4_candidates_empty_without_resolutions(self):
        self.assertEqual(cf.mp4_candidates("vz-x.b-cdn.net", "abc", ""), [])
        self.assertEqual(cf.mp4_candidates("vz-x.b-cdn.net", "abc", None), [])

    def test_playlist_url(self):
        self.assertEqual(cf.playlist_url("vz-x.b-cdn.net", "abc"),
                         "https://vz-x.b-cdn.net/abc/playlist.m3u8")


class TestListVideos(unittest.TestCase):
    def test_paginates_with_access_key(self):
        seen = []

        def fake_get(url, headers):
            seen.append((url, headers))
            if "page=1" in url:
                return {"totalItems": 3,
                        "items": [video("a"), video("b")]}
            return {"totalItems": 3, "items": [video("c")]}

        with mock.patch.object(cf, "http_get_json", side_effect=fake_get), \
             mock.patch.object(cf, "PER_PAGE", 2):
            vids = cf.list_videos({"library_id": "7", "api_key": "K",
                                   "cdn": "vz-x.b-cdn.net"})
        self.assertEqual([v["guid"] for v in vids], ["a", "b", "c"])
        for _url, headers in seen:
            self.assertEqual(headers["AccessKey"], "K")
        self.assertIn("/library/7/videos", seen[0][0])


class TestState(unittest.TestCase):
    def test_roundtrip_and_missing(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "state.json")
            self.assertEqual(cf.load_state(path), {})
            cf.save_state(path, {"g": {"title": "T", "result": "done"}})
            self.assertEqual(cf.load_state(path),
                             {"g": {"title": "T", "result": "done"}})

    def test_corrupt_state_fails_loudly(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "state.json")
            with open(path, "w") as fh:
                fh.write("{nope")
            with self.assertRaises(SystemExit):
                cf.load_state(path)


class TestCloudMode(unittest.TestCase):
    def run_mode(self, td, videos, runner_code=0, max_n=0,
                 retry_failed=False, second_run=False):
        env = {"CLOUD_LIBRARY_ID": "7", "CLOUD_LIBRARY_KEY": "K",
               "CLOUD_CDN_HOSTNAME": "vz-x.b-cdn.net"}
        calls = []

        def fake_download(cfg, vid, dest_dir):
            path = os.path.join(dest_dir, vid["guid"] + ".mp4")
            with open(path, "wb") as fh:
                fh.write(b"x" * 16)
            return path

        def fake_run(lesson, work):
            calls.append((lesson, work))
            return runner_code

        with mock.patch.dict(os.environ, env, clear=False), \
             mock.patch.object(cf, "list_videos", return_value=videos), \
             mock.patch.object(cf, "download_video",
                               side_effect=fake_download), \
             mock.patch.object(rp, "_run_one", side_effect=fake_run):
            code = rp.run_cloud_mode(td, max_n=max_n,
                                     retry_failed=retry_failed)
            code2 = None
            if second_run:
                code2 = rp.run_cloud_mode(td, max_n=max_n,
                                          retry_failed=retry_failed)
        return code, code2, calls

    def test_processes_only_new_finished_video(self):
        with tempfile.TemporaryDirectory() as td:
            vids = [video("new", title="Bread"), video("busy", status=2),
                    video("old")]
            # Seed "old" as already processed.
            cf.save_state(os.path.join(td, "cloud_state.json"),
                          {"old": {"title": "Old", "result": "done"}})
            code, code2, calls = self.run_mode(td, vids, second_run=True)
            self.assertEqual(code, 0)
            self.assertEqual(len(calls), 1)
            lesson, work = calls[0]
            self.assertTrue(lesson.endswith(".mp4"))
            self.assertTrue(work.startswith(td))
            state = cf.load_state(os.path.join(td, "cloud_state.json"))
            self.assertEqual(state["new"]["result"], "done")
            self.assertEqual(state["new"]["workDir"], work)
            # Second run picks up nothing new.
            self.assertEqual(code2, 0)

    def test_failed_run_marks_state_and_exits_nonzero(self):
        with tempfile.TemporaryDirectory() as td:
            code, _, calls = self.run_mode(td, [video("v")], runner_code=1)
            self.assertEqual(code, 1)
            self.assertEqual(len(calls), 1)
            state = cf.load_state(os.path.join(td, "cloud_state.json"))
            self.assertEqual(state["v"]["result"], "failed")

    def test_max_caps_videos_per_run(self):
        with tempfile.TemporaryDirectory() as td:
            vids = [video("a"), video("b"), video("c")]
            code, _, calls = self.run_mode(td, vids, max_n=2)
            self.assertEqual(code, 0)
            self.assertEqual(len(calls), 2)


class TestDownloadReferer(unittest.TestCase):
    def test_http_download_sends_referer(self):
        captured = {}

        class Resp:
            def __init__(self): self.left = b"data"
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def read(self, n=-1):
                out, self.left = self.left, b""
                return out

        def fake(req, timeout=None):
            captured.update(dict(req.header_items()))
            return Resp()

        with tempfile.TemporaryDirectory() as td:
            dest = os.path.join(td, "v.mp4")
            with mock.patch("urllib.request.urlopen", fake):
                cf.http_download("https://cdn/x.mp4", dest,
                                 "https://player.mediadelivery.net/embed/1/g")
        self.assertEqual(captured.get("Referer"),
                         "https://player.mediadelivery.net/embed/1/g")

    def test_remux_passes_referer_header(self):
        with mock.patch.object(cf.shutil, "which",
                               return_value="/bin/ffmpeg"), \
                mock.patch("subprocess.run") as run:
            run.return_value = mock.Mock(returncode=0)
            with tempfile.TemporaryDirectory() as td:
                dest = os.path.join(td, "v.mp4")
                with open(dest, "wb") as fh:
                    fh.write(b"x")
                cf.remux_hls("https://cdn/pl.m3u8", dest, "REF")
        cmd = run.call_args[0][0]
        self.assertIn("-headers", cmd)
        self.assertIn("Referer: REF", cmd)

    def test_download_video_uses_player_page(self):
        cfg = {"library_id": "793098", "cdn": "vz-x.b-cdn.net"}
        vid = {"guid": "guid-1234", "title": "t",
               "availableResolutions": "720p"}
        with tempfile.TemporaryDirectory() as td:
            with mock.patch.object(
                    cf, "http_download",
                    return_value=os.path.join(td, "t.mp4")) as dl:
                cf.download_video(cfg, vid, td)
        self.assertEqual(
            dl.call_args[0][2],
            "https://player.mediadelivery.net/embed/793098/guid-1234")


class TestCloudCli(unittest.TestCase):
    def test_single_positional_is_the_work_root(self):
        argv = ["run_pipeline.py", "--cloud", "work/cloud"]
        with mock.patch.object(sys, "argv", argv), \
                mock.patch.object(rp, "run_cloud_mode",
                                  return_value=0) as mode:
            with self.assertRaises(SystemExit) as ctx:
                rp.main()
        self.assertEqual(ctx.exception.code, 0)
        self.assertEqual(mode.call_args[0][0], "work/cloud")

    def test_cloud_rejects_zero_and_two_positionals(self):
        for argv in (["run_pipeline.py", "--cloud"],
                     ["run_pipeline.py", "--cloud", "a", "b"]):
            with mock.patch.object(sys, "argv", argv):
                with self.assertRaises(SystemExit) as ctx:
                    rp.main()
            self.assertNotEqual(ctx.exception.code, 0)


if __name__ == "__main__":
    unittest.main()
