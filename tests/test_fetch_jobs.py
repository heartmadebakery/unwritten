"""Tests for URL fetch jobs (pipeline/fetch_jobs.py) and --fetch mode.

The apps queue video URLs the browser cannot download itself
(YouTube/watch pages) at the signer; the pipeline claims them one at
a time, downloads each (yt-dlp or direct), and runs it like a
session. Terminal states mirror the cloud fetcher: failed stays
failed until --retry-failed reclaims it.
"""
import io
import json
import os
import sys
import tempfile
import unittest
import urllib.error
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))

import cloud_fetch as cf
import fetch_jobs as fj
import run_pipeline as rp


def resp_json(payload, status=200):
    body = json.dumps(payload).encode("utf-8")
    resp = mock.MagicMock()
    resp.read.return_value = body
    resp.__enter__.return_value = resp
    resp.status = status
    return resp


def http_error(url, code, body="err"):
    return urllib.error.HTTPError(url, code, "msg", {}, io.BytesIO(body.encode()))


class TestClassifyUrl(unittest.TestCase):
    def test_watch_pages_go_to_ytdlp(self):
        for url in ("https://www.youtube.com/watch?v=abc123",
                    "https://youtu.be/abc123",
                    "https://youtube.com/shorts/abc123",
                    "https://music.youtube.com/watch?v=abc123",
                    "https://vimeo.com/123456",
                    "https://example.com/lessons/bread"):
            self.assertEqual(fj.classify_url(url), "page", url)

    def test_media_files_download_direct(self):
        for url in ("https://cdn/x/play_720p.mp4",
                    "https://cdn/x/v.webm?token=abc",
                    "https://cdn/x/V.MOV",
                    "https://cdn/x/a.MP3#frag"):
            self.assertEqual(fj.classify_url(url), "direct", url)

    def test_direct_ext_falls_back_to_mp4(self):
        self.assertEqual(fj.direct_ext("https://cdn/x/v.mp4"), "mp4")
        self.assertEqual(fj.direct_ext("https://cdn/x/v.webm?t=1"), "webm")
        self.assertEqual(fj.direct_ext("https://cdn/x/v"), "mp4")


class TestLoadConfig(unittest.TestCase):
    def test_missing_queue_url_exits_loudly(self):
        with self.assertRaises(SystemExit) as ctx:
            fj.load_config(env={})
        self.assertIn("FETCH_QUEUE_URL", str(ctx.exception))

    def test_proxy_url_is_the_fallback(self):
        cfg = fj.load_config(env={"CLOUD_PROXY_URL": "https://w.example/"})
        self.assertEqual(cfg["queue"], "https://w.example")

    def test_env_token_beats_the_pool_file(self):
        cfg = fj.load_config(env={"FETCH_QUEUE_URL": "https://w.example",
                                  "FETCH_QUEUE_TOKEN": "envtok"})
        self.assertEqual(cfg["token"], "envtok")


class TestQueueClient(unittest.TestCase):
    def setUp(self):
        self.cfg = {"queue": "https://w.example", "token": "t"}

    def test_claim_url_and_empty_queue(self):
        seen = {}

        def fake_open(req, timeout=30):
            seen["url"] = req.full_url
            seen["token"] = req.headers.get("X-signer-token")
            return resp_json({"job": None})

        with mock.patch.object(fj.urllib.request, "urlopen", fake_open):
            self.assertIsNone(fj.claim_job(self.cfg))
        self.assertIn("/fetch/jobs?claim=1&by=pipeline", seen["url"])
        self.assertEqual(seen["token"], "t")

    def test_claim_passes_include_failed(self):
        seen = {}

        def fake_open(req, timeout=30):
            seen["url"] = req.full_url
            return resp_json({"job": None})

        with mock.patch.object(fj.urllib.request, "urlopen", fake_open):
            fj.claim_job(self.cfg, include_failed=True)
        self.assertIn("includeFailed=1", seen["url"])

    def test_finish_posts_done_and_failed(self):
        seen = []

        def fake_open(req, timeout=30):
            seen.append((req.full_url, req.data and json.loads(req.data)))
            return resp_json({"ok": True})

        with mock.patch.object(fj.urllib.request, "urlopen", fake_open):
            fj.finish_job(self.cfg, "job_1", True, session="w/1")
            fj.finish_job(self.cfg, "job_2", False, error="boom")
        self.assertEqual(seen[0][0], "https://w.example/fetch/jobs/job_1/done")
        self.assertEqual(seen[0][1], {"session": "w/1"})
        self.assertEqual(seen[1][0], "https://w.example/fetch/jobs/job_2/failed")
        self.assertEqual(seen[1][1], {"error": "boom"})

    def test_401_names_the_token_fix(self):
        def fake_open(req, timeout=30):
            raise http_error(req.full_url, 401, "unauthorized")

        with mock.patch.object(fj.urllib.request, "urlopen", fake_open):
            with self.assertRaises(fj.QueueError) as ctx:
                fj.claim_job(self.cfg)
        self.assertIn("token", str(ctx.exception))

    def test_unreachable_names_the_url_fix(self):
        def fake_open(req, timeout=30):
            raise urllib.error.URLError("boom")

        with mock.patch.object(fj.urllib.request, "urlopen", fake_open):
            with self.assertRaises(fj.QueueError) as ctx:
                fj.claim_job(self.cfg)
        self.assertIn("FETCH_QUEUE_URL", str(ctx.exception))

    def test_non_json_success_raises_queue_error(self):
        # A 200 with a non-JSON body (edge error page) must surface
        # as QueueError, not a raw traceback mid-run.
        resp = mock.MagicMock()
        resp.read.return_value = b"<html>edge exploded</html>"
        resp.__enter__.return_value = resp

        def fake_open(req, timeout=30):
            return resp

        with mock.patch.object(fj.urllib.request, "urlopen", fake_open):
            with self.assertRaises(fj.QueueError) as ctx:
                fj.claim_job(self.cfg)
        self.assertIn("not JSON", str(ctx.exception))


class TestNaming(unittest.TestCase):
    def test_media_name_matches_the_filename_contract(self):
        name = fj.media_name("mp4")
        self.assertTrue(name.startswith("unwritten_lesson_"), name)
        self.assertTrue(name.endswith(".mp4"), name)

    def test_job_slug_is_safe_and_short(self):
        slug = fj.job_slug("Bread: lesson #1!", "job_0123456789abcdef")
        self.assertEqual(slug, "Bread_lesson_1__89abcdef", slug)

    def test_session_dir_names_the_job(self):
        self.assertEqual(fj.session_dir_name("job_0123456789abcdef"),
                         "fetch_89abcdef")
        self.assertEqual(fj.session_dir_name(""), "fetch_job")

    def test_existing_media_skips_redownload(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(fj.existing_media(td), "")
            dest = os.path.join(td, "unwritten_lesson_x.mp4")
            with open(dest, "wb") as fh:
                fh.write(b"data")
            self.assertEqual(fj.existing_media(td), dest)

    def test_existing_media_never_resumes_a_part_sidecar(self):
        # A killed run (cron timeout, reboot) skips download_direct's
        # cleanup and leaves "unwritten_lesson_x.mp4.part" behind. The
        # retry must download again, never process the truncated
        # sidecar as the lesson.
        with tempfile.TemporaryDirectory() as td:
            with open(os.path.join(td, "unwritten_lesson_x.mp4.part"),
                      "wb") as fh:
                fh.write(b"half")
            self.assertEqual(fj.existing_media(td), "")

    def test_failed_direct_leaves_no_lesson_file(self):
        # Mirror of the cloud path's .part discipline: an interrupted
        # direct download must leave neither the lesson file (a
        # truncated lesson would be processed as real on retry) nor
        # its sidecar.
        def flaky(url, dest, referer=""):
            with open(dest, "wb") as fh:
                fh.write(b"x" * 8)
            raise fj.cloud_fetch.DownloadError(-1, "request failed")

        with tempfile.TemporaryDirectory() as td:
            dest = os.path.join(td, "unwritten_lesson_x.mp4")
            with mock.patch.object(fj.cloud_fetch, "http_download",
                                   side_effect=flaky):
                with self.assertRaises(fj.cloud_fetch.DownloadError):
                    fj.download_direct("https://cdn/x/v.mp4", dest)
            self.assertEqual(os.listdir(td), [])

    def test_direct_download_lands_atomically(self):
        # A successful direct download lands at the lesson path with
        # no sidecar left behind.
        def fake_dl(url, dest, referer=""):
            with open(dest, "wb") as fh:
                fh.write(b"x" * 8)
            return dest

        with tempfile.TemporaryDirectory() as td:
            dest = os.path.join(td, "unwritten_lesson_x.mp4")
            with mock.patch.object(fj.cloud_fetch, "http_download",
                                   side_effect=fake_dl):
                got = fj.download_direct("https://cdn/x/v.mp4", dest)
            self.assertEqual(got, dest)
            self.assertTrue(os.path.exists(dest))
            self.assertEqual(
                [n for n in os.listdir(td) if n.endswith(".part")], [])

    def test_source_round_trip(self):
        with tempfile.TemporaryDirectory() as td:
            job = {"id": "job_1", "url": "https://x/y.mp4"}
            fj.write_source(td, job, "Bread", os.path.join(td, "m.mp4"))
            self.assertEqual(fj.read_source_title(td), "Bread")
            src = json.load(open(os.path.join(td, "source.json")))
            self.assertEqual(src["url"], "https://x/y.mp4")
            self.assertEqual(src["job_id"], "job_1")
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(fj.read_source_title(td), "")


class TestUploadGuid(unittest.TestCase):
    def test_round_trip_and_missing(self):
        # The Stream video id is written once, right after create, so
        # a retry reuses it instead of minting a duplicate video.
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(fj.read_upload_guid(td), "")
            fj.write_upload_guid(td, "vid-1")
            self.assertEqual(fj.read_upload_guid(td), "vid-1")
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(fj.read_upload_guid(td), "")


class TestYtdlp(unittest.TestCase):
    def test_missing_binary_names_the_install(self):
        with mock.patch.object(fj.shutil, "which", return_value=None), \
             mock.patch("importlib.util.find_spec", return_value=None):
            with self.assertRaises(fj.QueueError) as ctx:
                fj.ytdlp_download("https://youtube.com/watch?v=x", "/tmp")
        self.assertIn("yt-dlp", str(ctx.exception))

    def test_module_fallback_without_path_binary(self):
        # Cron has no venv bin on PATH: the running interpreter's
        # yt-dlp module is the fallback.
        seen = {}

        def fake_run(cmd, capture_output, text, timeout):
            seen["cmd"] = cmd
            return mock.Mock(returncode=0, stderr="")

        with mock.patch.object(fj.shutil, "which", return_value=None), \
             mock.patch.object(fj.subprocess, "run", fake_run):
            with tempfile.TemporaryDirectory() as td:
                with open(os.path.join(td, "video.mp4"), "wb") as fh:
                    fh.write(b"data")
                out = fj.ytdlp_download("https://youtube.com/watch?v=x",
                                        td)
        self.assertEqual(seen["cmd"][:3],
                         [sys.executable, "-m", "yt_dlp"])
        self.assertTrue(out.endswith(".mp4"))

    def test_download_command_and_rename(self):
        with tempfile.TemporaryDirectory() as td:
            seen = {}

            def fake_run(cmd, capture_output, text, timeout):
                seen["cmd"] = cmd
                with open(os.path.join(td, "video.mp4"), "wb") as fh:
                    fh.write(b"data")
                return mock.Mock(returncode=0, stderr="")

            with mock.patch.object(fj.shutil, "which", return_value="/bin/yt-dlp"), \
                 mock.patch.object(fj.subprocess, "run", fake_run):
                out = fj.ytdlp_download("https://youtube.com/watch?v=x", td)
            self.assertIn("--no-playlist", seen["cmd"])
            self.assertIn("--merge-output-format", seen["cmd"])
            self.assertTrue(os.path.basename(out).startswith("unwritten_lesson_"))
            self.assertTrue(out.endswith(".mp4"))
            self.assertFalse(os.path.exists(os.path.join(td, "video.mp4")))

    def test_download_ignores_leftover_partials(self):
        # A partial from an earlier, killed attempt can outweigh the
        # finished file; the lesson must be the finished media file,
        # never "video.webm.part".
        with tempfile.TemporaryDirectory() as td:
            with open(os.path.join(td, "video.webm.part"), "wb") as fh:
                fh.write(b"x" * 4096)

            def fake_run(cmd, capture_output, text, timeout):
                with open(os.path.join(td, "video.mp4"), "wb") as fh:
                    fh.write(b"data")
                return mock.Mock(returncode=0, stderr="")

            with mock.patch.object(fj.shutil, "which", return_value="/bin/yt-dlp"), \
                 mock.patch.object(fj.subprocess, "run", fake_run):
                out = fj.ytdlp_download("https://youtube.com/watch?v=x", td)
            self.assertTrue(out.endswith(".mp4"), out)

    def test_failed_download_raises_with_tail(self):
        def fake_run(cmd, capture_output, text, timeout):
            return mock.Mock(returncode=1, stderr="line1\nbang")

        with mock.patch.object(fj.shutil, "which", return_value="/bin/yt-dlp"), \
             mock.patch.object(fj.subprocess, "run", fake_run):
            with self.assertRaises(fj.QueueError) as ctx:
                fj.ytdlp_download("https://youtube.com/watch?v=x", "/tmp")
        self.assertIn("bang", str(ctx.exception))

    def test_title_is_best_effort(self):
        with mock.patch.object(fj.shutil, "which", return_value=None), \
             mock.patch("importlib.util.find_spec", return_value=None):
            self.assertEqual(fj.ytdlp_title("https://x"), "")


class TestFetchCli(unittest.TestCase):
    def test_single_positional_is_the_work_root(self):
        # A temp root, never the live work/cloud: the cron run holds
        # that root's lock every five minutes, and a held lock skips
        # the mode this test asserts on.
        with tempfile.TemporaryDirectory() as td:
            root = os.path.join(td, "cloud")
            argv = ["run_pipeline.py", "--fetch", root]
            with mock.patch.object(sys, "argv", argv), \
                    mock.patch.object(rp, "run_fetch_mode",
                                      return_value=0) as mode:
                with self.assertRaises(SystemExit) as ctx:
                    rp.main()
        self.assertEqual(ctx.exception.code, 0)
        self.assertEqual(mode.call_args[0][0], root)

    def test_fetch_rejects_zero_and_two_positionals(self):
        for argv in (["run_pipeline.py", "--fetch"],
                    ["run_pipeline.py", "--fetch", "a", "b"]):
            with mock.patch.object(sys, "argv", argv):
                with self.assertRaises(SystemExit) as ctx:
                    rp.main()
            self.assertNotEqual(ctx.exception.code, 0)

    def test_bad_max_flag_is_a_clean_error(self):
        # A non-integer --max answers 2 with a message, not a raw
        # ValueError traceback.
        argv = ["fetch_jobs.py", "root", "--max", "abc"]
        with mock.patch.object(sys, "argv", argv):
            self.assertEqual(fj.main(), 2)


UPLOAD_CFG = {"library_id": "7", "api_key": "K", "cdn": "vz-x.b-cdn.net",
                "proxy": ""}


class TestFetchMode(unittest.TestCase):
    def test_empty_queue_is_quiet_success(self):
        with tempfile.TemporaryDirectory() as td:
            with mock.patch.object(fj, "load_config",
                                   return_value={"queue": "q", "token": ""}), \
                 mock.patch.object(cf, "require_upload_config",
                                   return_value=UPLOAD_CFG), \
                 mock.patch.object(fj, "claim_job", return_value=None) as claim:
                code = rp.run_fetch_mode(td)
        self.assertEqual(code, 0)
        claim.assert_called_once()

    def test_one_job_runs_the_pipeline_and_finishes(self):
        job = {"id": "job_1", "url": "https://cdn/x/v.mp4"}
        with tempfile.TemporaryDirectory() as td:
            lesson = os.path.join(td, "fetch_job", "m.mp4")
            with mock.patch.object(fj, "load_config",
                                   return_value={"queue": "q", "token": ""}), \
                 mock.patch.object(cf, "require_upload_config",
                                   return_value=UPLOAD_CFG), \
                 mock.patch.object(fj, "claim_job",
                                   side_effect=[job, None]), \
                 mock.patch.object(fj, "download_direct",
                                   return_value=lesson) as dl, \
                 mock.patch.object(cf, "create_video",
                                   return_value="vid-9") as mk, \
                 mock.patch.object(cf, "upload_bytes") as up, \
                 mock.patch.object(cf, "await_finished") as wait, \
                 mock.patch.object(fj, "finish_job") as fin, \
                 mock.patch.object(rp, "_run_one", return_value=0) as one:
                code = rp.run_fetch_mode(td)
            state = cf.load_state(os.path.join(td, "cloud_state.json"))
        self.assertEqual(code, 0)
        dl.assert_called_once()
        one.assert_called_once()
        fin.assert_called_with({"queue": "q", "token": ""}, "job_1", True,
                               session=mock.ANY, error="")
        # The finished lesson is uploaded to Stream and recorded in
        # the cloud state, so --cloud skips it and the publish loop
        # picks it up for the hub.
        mk.assert_called_once()
        up.assert_called_once()
        self.assertEqual(up.call_args[0][1], "vid-9")
        self.assertEqual(up.call_args[0][2], lesson)
        wait.assert_called_once()
        self.assertEqual(state["vid-9"]["result"], "done")
        self.assertEqual(state["vid-9"]["workDir"], one.call_args[0][1])

    def test_download_failure_marks_failed(self):
        job = {"id": "job_1", "url": "https://cdn/x/v.mp4"}
        with tempfile.TemporaryDirectory() as td:
            with mock.patch.object(fj, "load_config",
                                   return_value={"queue": "q", "token": ""}), \
                 mock.patch.object(cf, "require_upload_config",
                                   return_value=UPLOAD_CFG), \
                 mock.patch.object(fj, "claim_job",
                                   side_effect=[job, None]), \
                 mock.patch.object(fj, "download_direct",
                                   side_effect=RuntimeError("boom")), \
                 mock.patch.object(fj, "finish_job") as fin, \
                 mock.patch.object(rp, "_run_one") as one:
                code = rp.run_fetch_mode(td)
        self.assertEqual(code, 1)
        one.assert_not_called()
        self.assertEqual(fin.call_args[0][:3], ({"queue": "q", "token": ""}, "job_1", False))
        self.assertIn("boom", fin.call_args[1]["error"])

    def test_upload_failure_marks_failed(self):
        # A lesson the pipeline finished but Stream refused stays
        # failed (never silently hub-less): the bytes and the retry
        # carry the same video id.
        job = {"id": "job_1", "url": "https://cdn/x/v.mp4"}
        with tempfile.TemporaryDirectory() as td:
            lesson = os.path.join(td, "fetch_job", "m.mp4")
            with mock.patch.object(fj, "load_config",
                                   return_value={"queue": "q", "token": ""}), \
                 mock.patch.object(cf, "require_upload_config",
                                   return_value=UPLOAD_CFG), \
                 mock.patch.object(fj, "claim_job",
                                   side_effect=[job, None]), \
                 mock.patch.object(fj, "download_direct",
                                   return_value=lesson), \
                 mock.patch.object(cf, "create_video",
                                   return_value="vid-9"), \
                 mock.patch.object(cf, "upload_bytes",
                                   side_effect=RuntimeError("boom")), \
                 mock.patch.object(cf, "await_finished") as wait, \
                 mock.patch.object(fj, "finish_job") as fin, \
                 mock.patch.object(rp, "_run_one", return_value=0):
                code = rp.run_fetch_mode(td)
            state = cf.load_state(os.path.join(td, "cloud_state.json"))
        self.assertEqual(code, 1)
        wait.assert_not_called()
        self.assertEqual(fin.call_args[0][:3], ({"queue": "q", "token": ""}, "job_1", False))
        self.assertIn("boom", fin.call_args[1]["error"])
        self.assertNotIn("vid-9", state)

    def test_missing_upload_creds_exits_before_claim(self):
        # Without the library key no fetch job could reach the hub,
        # so the run fails fast instead of claiming work it cannot
        # finish visibly.
        with tempfile.TemporaryDirectory() as td:
            with mock.patch.object(fj, "load_config",
                                   return_value={"queue": "q", "token": ""}), \
                 mock.patch.object(cf, "require_upload_config",
                                   side_effect=SystemExit("Missing x")), \
                 mock.patch.object(fj, "claim_job") as claim:
                with self.assertRaises(SystemExit):
                    rp.run_fetch_mode(td)
        claim.assert_not_called()

    def test_retry_reuses_the_stored_video_id(self):
        # A retry (re-download skipped, pipeline rerun) uploads under
        # the video id stored by the first attempt — never a second
        # Stream object for the same lesson.
        job = {"id": "job_9", "url": "https://cdn/x/v.mp4"}
        with tempfile.TemporaryDirectory() as td:
            session = os.path.join(td, "fetch_job_9")
            os.makedirs(session)
            with open(os.path.join(session, "unwritten_lesson_x.mp4"),
                      "wb") as fh:
                fh.write(b"data")
            fj.write_upload_guid(session, "vid-old")
            with mock.patch.object(fj, "load_config",
                                   return_value={"queue": "q", "token": ""}), \
                 mock.patch.object(cf, "require_upload_config",
                                   return_value=UPLOAD_CFG), \
                 mock.patch.object(fj, "claim_job",
                                   side_effect=[job, None]), \
                 mock.patch.object(fj, "download_direct") as dl, \
                 mock.patch.object(cf, "create_video") as mk, \
                 mock.patch.object(cf, "upload_bytes") as up, \
                 mock.patch.object(cf, "await_finished"), \
                 mock.patch.object(fj, "finish_job") as fin, \
                 mock.patch.object(rp, "_run_one", return_value=0):
                code = rp.run_fetch_mode(td)
        self.assertEqual(code, 0)
        dl.assert_not_called()
        mk.assert_not_called()
        self.assertEqual(up.call_args[0][1], "vid-old")
        self.assertEqual(fin.call_args[0][:3], ({"queue": "q", "token": ""}, "job_9", True))

    def test_retry_failed_never_loops_on_one_bad_job(self):
        # --retry-failed reclaims failed jobs, and a job that fails
        # again is failed again — so the queue hands the same job
        # straight back. The run must process each job once, put the
        # re-handed one back as failed (a dangling claim would come
        # back after two hours even without --retry-failed), and end.
        job = {"id": "job_1", "url": "https://cdn/x/v.mp4"}
        with tempfile.TemporaryDirectory() as td:
            with mock.patch.object(fj, "load_config",
                                   return_value={"queue": "q", "token": ""}), \
                 mock.patch.object(cf, "require_upload_config",
                                   return_value=UPLOAD_CFG), \
                 mock.patch.object(fj, "claim_job",
                                   side_effect=[job, job, job, None]) as claim, \
                 mock.patch.object(fj, "download_direct",
                                   side_effect=RuntimeError("boom")) as dl, \
                 mock.patch.object(fj, "finish_job") as fin, \
                 mock.patch.object(rp, "_run_one") as one:
                code = rp.run_fetch_mode(td, retry_failed=True)
        self.assertEqual(code, 1)
        self.assertEqual(dl.call_count, 1)
        self.assertEqual(claim.call_count, 2)
        one.assert_not_called()
        self.assertEqual(fin.call_count, 2)
        for call in fin.call_args_list:
            self.assertEqual(call[0][1:3], ("job_1", False))
            self.assertIn("boom", call[1]["error"])

    def test_download_only_retry_failed_never_loops(self):
        # fetch_jobs.py main() claims the same way, so the same guard.
        job = {"id": "job_1", "url": "https://cdn/x/v.mp4"}
        with tempfile.TemporaryDirectory() as td:
            with mock.patch.object(sys, "argv",
                                   ["fetch_jobs.py", td, "--retry-failed"]), \
                 mock.patch.object(fj, "load_config",
                                   return_value={"queue": "q", "token": ""}), \
                 mock.patch.object(fj, "claim_job",
                                   side_effect=[job, job, job, None]) as claim, \
                 mock.patch.object(fj, "download_direct",
                                   side_effect=RuntimeError("boom")) as dl, \
                 mock.patch.object(fj, "finish_job") as fin:
                self.assertEqual(fj.main(), 1)
        self.assertEqual(dl.call_count, 1)
        self.assertEqual(claim.call_count, 2)
        self.assertEqual(fin.call_count, 2)
        self.assertIn("boom", fin.call_args[1]["error"])

    def test_download_only_needs_no_library_key(self):
        # fetch_jobs.py main() downloads without running the pipeline
        # and without uploading: no library key required.
        with tempfile.TemporaryDirectory() as td:
            env = {k: v for k, v in os.environ.items()
                   if not k.startswith("CLOUD_")}
            with mock.patch.object(sys, "argv",
                                   ["fetch_jobs.py", td]), \
                 mock.patch.object(fj, "load_config",
                                   return_value={"queue": "q", "token": ""}), \
                 mock.patch.object(fj, "claim_job", return_value=None), \
                 mock.patch.dict(os.environ, env, clear=True):
                self.assertEqual(fj.main(), 0)


if __name__ == "__main__":
    unittest.main()
