"""Tests for cloud fetch and run_pipeline --cloud mode.

One full pipeline run per new finished cloud video; credentials come
from CLOUD_* env vars; only status-4 videos unseen in the state file
are processed.
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

    def test_ignored_never_reprocessed_even_on_retry(self):
        # 'ignored' is an operator decision — this video is not a
        # lesson (e.g. a single-word test clip) and is set aside for
        # good. Unlike 'failed', not even --retry-failed resurrects
        # it; unlike deleting the entry, it never re-downloads.
        vids = [video("junk")]
        state = {"junk": {"title": "J", "result": "ignored",
                        "reason": "not a lesson"}}
        self.assertEqual(cf.select_ready(vids, state), [])
        self.assertEqual(
            cf.select_ready(vids, state, retry_failed=True), [])

    def test_downloaded_means_pipeline_pending(self):
        # 'downloaded' is fetched-but-pipeline-never-finished: it
        # reprocesses (run_cloud_mode skips the re-download — the
        # lesson is on disk — and runs the pipeline). It must never
        # silently drop the lesson.
        vids = [video("dl")]
        state = {"dl": {"title": "T", "lesson": "/x/y.mp4",
                        "result": "downloaded"}}
        self.assertEqual(len(cf.select_ready(vids, state)), 1)


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

    def test_transport_errors_wrapped_as_runtime(self):
        import http.client
        for err in (http.client.RemoteDisconnected("gone"),
                    ConnectionResetError("rst")):
            with mock.patch("urllib.request.urlopen", side_effect=err):
                with self.assertRaises(RuntimeError):
                    cf.http_get_json("https://x/y", {})

    def test_non_json_body_wrapped_as_runtime(self):
        # A 200 with a non-JSON body (edge error page) must surface
        # as RuntimeError like every other transport failure, not a
        # raw traceback mid-run.
        resp = mock.MagicMock()
        resp.read.return_value = b"<html>edge exploded</html>"
        resp.__enter__.return_value = resp
        with mock.patch("urllib.request.urlopen", return_value=resp):
            with self.assertRaises(RuntimeError):
                cf.http_get_json("https://x/y", {})


class TestRunCloudSh(unittest.TestCase):
    def test_failures_are_loud_and_counted(self):
        # The cron wrapper must not swallow step failures: each step
        # logs a greppable FAIL marker, lock contention is logged
        # instead of silent, and any failure exits non-zero for cron.
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(root, "run_cloud.sh")) as fh:
            sh = fh.read()
        for token in ["FAIL=0", "[cloud] FAIL:", "still holds the lock",
                      "exit 1"]:
            self.assertIn(token, sh, token)

    def test_publish_loop_skips_work_without_a_cloud_video(self):
        # Fetch-queue sessions finish in work/cloud/*__* with a
        # writeup.md but map to no Stream video, and publish.py only
        # publishes Stream-backed lessons (it exits 1 without a
        # mapping). The loop must resolve the guid from the state's
        # workDir mapping up front and skip those dirs — otherwise
        # every cron run ends FAIL on finished fetch sessions.
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(root, "run_cloud.sh")) as fh:
            sh = fh.read()
        for token in ["workDir", '[ -n "$GUID" ] || continue',
                      '--guid "$GUID"']:
            self.assertIn(token, sh, token)

    def test_ignored_markers_sync_each_run(self):
        # The operator's set-asides must reach the hub every cycle so
        # the apps badge them on Record (the sessions list excludes
        # them server-side); a sync failure is a loud FAIL like any
        # other step.
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(root, "run_cloud.sh")) as fh:
            sh = fh.read()
        for token in ["--sync-ignored", "ignored sync failed"]:
            self.assertIn(token, sh, token)

    def test_publish_loop_skips_partial_work_dirs(self):
        # A work dir with writeup.md but no corrections.json is a
        # mid-run or crashed run — publishing it would push partial
        # artifacts through the hub upsert (or push them at all on a
        # first publish). The loop must require both files.
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(root, "run_cloud.sh")) as fh:
            sh = fh.read()
        self.assertIn('[ -f "$work/corrections.json" ]', sh)


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

    def test_non_dict_state_fails_loudly(self):
        # Valid JSON that is not an object (e.g. []) is as corrupt as
        # garbage: silently treating it as empty would reprocess
        # every cloud video.
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "state.json")
            with open(path, "w") as fh:
                fh.write("[]")
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

        def fake_dl(url, dest, referer=""):
            with open(dest, "wb") as fh:
                fh.write(b"x" * 8)
            return dest

        with tempfile.TemporaryDirectory() as td:
            with mock.patch.object(
                    cf, "http_download", side_effect=fake_dl) as dl:
                got = cf.download_video(cfg, vid, td)
            self.assertEqual(
                dl.call_args[0][2],
                "https://player.mediadelivery.net/embed/793098/guid-1234")
            self.assertTrue(got.endswith(".mp4"))
            self.assertTrue(os.path.exists(got))

    def test_partial_download_never_lands(self):
        # A failed download must leave neither the lesson file (a
        # truncated lesson would be processed as real) nor its .part.
        cfg = {"library_id": "7", "cdn": "vz-x.b-cdn.net"}
        vid = {"guid": "guid-99", "title": "t",
               "availableResolutions": "720p"}

        def flaky(url, dest, referer=""):
            with open(dest, "wb") as fh:
                fh.write(b"x" * 8)
            raise cf.DownloadError(500, "HTTP 500")

        with tempfile.TemporaryDirectory() as td:
            with mock.patch.object(cf, "http_download",
                                   side_effect=flaky):
                with self.assertRaises(cf.DownloadError):
                    cf.download_video(cfg, vid, td)
            self.assertEqual(os.listdir(td), [])

    def test_failed_rendition_falls_through_cleanly(self):
        # A listed-but-unserved rendition (404) is skipped; the next
        # one lands, with no .part left behind.
        cfg = {"library_id": "7", "cdn": "vz-x.b-cdn.net"}
        vid = {"guid": "guid-99", "title": "t",
               "availableResolutions": "1080p,720p"}
        calls = []

        def fake_dl(url, dest, referer=""):
            calls.append(url)
            if "1080" in url:
                raise cf.DownloadError(404, "HTTP 404")
            with open(dest, "wb") as fh:
                fh.write(b"x" * 8)
            return dest

        with tempfile.TemporaryDirectory() as td:
            with mock.patch.object(cf, "http_download",
                                   side_effect=fake_dl):
                got = cf.download_video(cfg, vid, td)
            self.assertEqual(len(calls), 2)
            self.assertTrue(os.path.exists(got))
            self.assertFalse(got.endswith(".part"))
            self.assertEqual(
                [n for n in os.listdir(td) if n.endswith(".part")], [])

    def test_remux_failure_cleans_part(self):
        cfg = {"library_id": "7", "cdn": "vz-x.b-cdn.net"}
        vid = {"guid": "guid-99", "title": "t",
               "availableResolutions": ""}
        with tempfile.TemporaryDirectory() as td:
            with mock.patch.object(
                    cf, "remux_hls",
                    side_effect=RuntimeError("ffmpeg remux failed")):
                with self.assertRaises(RuntimeError):
                    cf.download_video(cfg, vid, td)
            self.assertEqual(os.listdir(td), [])

    def test_remux_failure_names_token_auth(self):
        # A failed remux (auth-blocked playlist) points at Stream ->
        # Security, wherever the failure surfaces.
        with mock.patch.object(cf.shutil, "which",
                               return_value="/bin/ffmpeg"), \
                mock.patch("subprocess.run") as run:
            run.return_value = mock.Mock(returncode=1,
                                         stderr="403 Forbidden")
            with self.assertRaises(RuntimeError) as ctx:
                cf.remux_hls("https://cdn/pl.m3u8", "/tmp/x.mp4", "REF")
        self.assertIn("token-authenticated", str(ctx.exception))

    def test_missing_ffmpeg_names_only_the_install(self):
        # A missing ffmpeg names the install — never the token-auth
        # hint, which would send the operator to the wrong fix.
        cfg = {"library_id": "7", "cdn": "vz-x.b-cdn.net"}
        vid = {"guid": "guid-99", "title": "t",
               "availableResolutions": ""}
        with tempfile.TemporaryDirectory() as td:
            with mock.patch.object(
                    cf, "remux_hls",
                    side_effect=RuntimeError(
                        "ffmpeg not found on PATH — needed to fetch u")):
                with self.assertRaises(RuntimeError) as ctx:
                    cf.download_video(cfg, vid, td)
        self.assertIn("ffmpeg not found", str(ctx.exception))
        self.assertNotIn("token-authenticated", str(ctx.exception))

    def test_main_marks_failure_and_continues(self):
        # One failing video is recorded as failed; later videos in
        # the same batch still fetch instead of being skipped.
        good = video("good")
        bad = video("bad")
        with tempfile.TemporaryDirectory() as td:
            state_path = os.path.join(td, "cloud_state.json")
            cfg = {"library_id": "7", "api_key": "K",
                   "cdn": "vz-x.b-cdn.net", "proxy": ""}
            with mock.patch.object(sys, "argv",
                                   ["cloud_fetch.py", td]), \
                 mock.patch.object(cf, "load_config",
                                   return_value=cfg), \
                 mock.patch.object(cf, "list_videos",
                                   return_value=[bad, good]), \
                 mock.patch.object(
                       cf, "download_video",
                       side_effect=[RuntimeError("boom"),
                                    os.path.join(td, "good.mp4")]):
                code = cf.main()
            self.assertEqual(code, 1)
            state = cf.load_state(state_path)
            self.assertEqual(state["bad"]["result"], "failed")
            self.assertIn("boom", state["bad"]["error"])
            self.assertEqual(state["good"]["result"], "downloaded")


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


class TestCloudFetchMain(unittest.TestCase):
    def test_bad_max_flag_is_a_clean_error(self):
        # A non-integer --max answers 2 with a message, not a raw
        # ValueError traceback.
        argv = ["cloud_fetch.py", "root", "--max", "abc"]
        with mock.patch.object(sys, "argv", argv):
            self.assertEqual(cf.main(), 2)


class TestStreamUpload(unittest.TestCase):
    # Fetch-queue sessions finish on disk with no Stream copy, so the
    # in-app hub (Stream-backed) can never show them. --fetch uploads
    # each finished lesson after the pipeline: create the video
    # object, PUT the bytes, wait for finished/transcoded.
    CFG = {"library_id": "7", "api_key": "K", "cdn": "vz-x.b-cdn.net",
           "proxy": ""}

    def test_require_upload_config_needs_the_library_key(self):
        with self.assertRaises(SystemExit) as ctx:
            cf.require_upload_config(env={})
        self.assertIn("CLOUD_LIBRARY", str(ctx.exception))
        # Proxy mode lists without the key, but bytes upload direct.
        proxy = {"CLOUD_PROXY_URL": "https://w.example",
                 "CLOUD_LIBRARY_ID": "7",
                 "CLOUD_CDN_HOSTNAME": "vz-x.b-cdn.net"}
        with self.assertRaises(SystemExit) as ctx:
            cf.require_upload_config(env=proxy)
        self.assertIn("CLOUD_LIBRARY_KEY", str(ctx.exception))
        full = dict(proxy, CLOUD_LIBRARY_KEY="K")
        self.assertEqual(cf.require_upload_config(env=full)["api_key"],
                         "K")

    def test_create_video_posts_title_and_returns_guid(self):
        seen = {}

        class Resp:
            def read(self):
                return b'{"guid":"g1"}'
            def __enter__(self):
                return self
            def __exit__(self, *a):
                return False

        def fake_open(req, timeout=None):
            seen["url"] = req.full_url
            seen["data"] = req.data
            seen["headers"] = {k.lower(): v
                               for k, v in req.header_items()}
            return Resp()

        with mock.patch("urllib.request.urlopen", fake_open):
            self.assertEqual(cf.create_video(self.CFG, "My lesson"),
                             "g1")
        self.assertTrue(seen["url"].endswith("/library/7/videos"),
                        seen["url"])
        self.assertEqual(json.loads(seen["data"])["title"], "My lesson")
        self.assertEqual(seen["headers"].get("accesskey"), "K")

    def test_create_video_refusal_is_a_clean_error(self):
        def fake_open(req, timeout=None):
            raise urllib.error.HTTPError(req.full_url, 403, "denied",
                                         {}, io.BytesIO(b"bad key"))

        with mock.patch("urllib.request.urlopen", fake_open):
            with self.assertRaises(RuntimeError) as ctx:
                cf.create_video(self.CFG, "t")
        self.assertIn("403", str(ctx.exception))

    def test_upload_bytes_puts_file_as_octet_stream(self):
        import http.client
        conn = mock.MagicMock()
        resp = mock.MagicMock()
        resp.status = 200
        resp.read.return_value = b'{"success":true}'
        conn.getresponse.return_value = resp
        with tempfile.TemporaryDirectory() as td:
            src = os.path.join(td, "lesson.mp4")
            with open(src, "wb") as fh:
                fh.write(b"v" * 100)
            with mock.patch.object(http.client, "HTTPSConnection",
                                   return_value=conn) as cls:
                cf.upload_bytes(self.CFG, "g1", src)
        self.assertEqual(cls.call_args[0][0], "video.bunnycdn.com")
        conn.putrequest.assert_called_once_with(
            "PUT", "/library/7/videos/g1")
        sent = {c[0][0]: c[0][1]
                for c in conn.putheader.call_args_list}
        self.assertEqual(sent.get("Content-Type"),
                         "application/octet-stream")
        self.assertEqual(sent.get("Content-Length"), "100")
        self.assertEqual(sent.get("AccessKey"), "K")
        conn.send.assert_called_once_with(b"v" * 100)

    def test_upload_bytes_refusal_names_the_video(self):
        import http.client
        conn = mock.MagicMock()
        resp = mock.MagicMock()
        resp.status = 400
        resp.read.return_value = b"nope"
        conn.getresponse.return_value = resp
        with tempfile.TemporaryDirectory() as td:
            src = os.path.join(td, "lesson.mp4")
            with open(src, "wb") as fh:
                fh.write(b"v")
            with mock.patch.object(http.client, "HTTPSConnection",
                                   return_value=conn):
                with self.assertRaises(RuntimeError) as ctx:
                    cf.upload_bytes(self.CFG, "g1", src)
        self.assertIn("g1", str(ctx.exception))
        self.assertIn("400", str(ctx.exception))

    def test_upload_bytes_missing_file_is_a_clean_error(self):
        with self.assertRaises(RuntimeError):
            cf.upload_bytes(self.CFG, "g1", "/nonexistent/lesson.mp4")

    def test_video_status_reads_the_vendor_object(self):
        with mock.patch.object(cf, "http_get_json",
                               return_value={"status": 3}) as get:
            self.assertEqual(cf.video_status(self.CFG, "g1"), 3)
        self.assertIn("g1", get.call_args[0][0])

    def test_await_finished_polls_until_playable(self):
        with mock.patch.object(cf, "video_status",
                               side_effect=[1, 2, 3, 4]) as st:
            self.assertIsNone(
                cf.await_finished(self.CFG, "g1", interval=0))
        self.assertEqual(st.call_count, 4)

    def test_await_finished_transcode_error_fails_loudly(self):
        with mock.patch.object(cf, "video_status", return_value=5):
            with self.assertRaises(RuntimeError) as ctx:
                cf.await_finished(self.CFG, "g1", interval=0)
        self.assertIn("g1", str(ctx.exception))

    def test_await_finished_timeout_names_the_video(self):
        with mock.patch.object(cf, "video_status", return_value=2):
            with self.assertRaises(RuntimeError) as ctx:
                cf.await_finished(self.CFG, "g1", timeout=0,
                                  interval=0)
        self.assertIn("g1", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
