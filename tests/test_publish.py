"""Tests for the hub publish step and the hub store schema."""
import io
import json
import os
import sqlite3
import sys
import tempfile
import unittest
import urllib.error

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))

import publish


SENT = {}


class FakeResponse:
    def __init__(self, status, payload):
        self.status = status
        self.payload = payload

    def read(self):
        return json.dumps(self.payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def fake_urlopen(req, timeout=None):
    url = req.full_url
    SENT["url"] = url
    SENT["token"] = req.get_header("X-signer-token")
    if url.startswith("https://video.bunnycdn.com/"):
        SENT["vendor_calls"] = SENT.get("vendor_calls", 0) + 1
        if SENT.get("vendor_404"):
            raise urllib.error.HTTPError(url, 404, "Not Found", {},
                                         io.BytesIO(b'{"message":"nope"}'))
        return FakeResponse(200, {"availableResolutions": "720p,480p"})
    if url.endswith("/hub/publish"):
        SENT["payload"] = json.loads(req.data.decode("utf-8"))
        SENT["publishes"] = SENT.get("publishes", 0) + 1
        return FakeResponse(200, {"published": SENT["payload"]["videoId"]})
    if url.endswith("/hub/ignored") and req.get_method() == "GET":
        return FakeResponse(200, SENT.get("remote_ignored", []))
    if url.endswith("/hub/ignored"):
        posted = json.loads(req.data.decode("utf-8"))
        SENT.setdefault("ignored", []).append(posted)
        if SENT.get("refuse_ignored"):
            return FakeResponse(500, {"error": "boom"})
        if SENT.get("misshapen_ignored"):
            # A stale worker that routes unknown paths into the video
            # trio answers 200 with a mint payload instead of a marker.
            return FakeResponse(200, {"videoId": posted.get("videoId"),
                                      "signature": "abc"})
        return FakeResponse(200, {"ignored": posted.get("videoId")})
    if "/hub/ignored/" in url:
        SENT.setdefault("unignored", []).append(url.rsplit("/", 1)[-1])
        return FakeResponse(200, {"deleted": True})
    raise AssertionError("unexpected url " + url)


def fixture_work(parent):
    work = os.path.join(parent, "lesson1")
    os.makedirs(work)
    with open(os.path.join(work, "writeup.md"), "w") as fh:
        fh.write("# Bread\n\nTasty body.\n")
    with open(os.path.join(work, "corrections.json"), "w") as fh:
        json.dump([{"start": "0:42", "quote": "q", "correcting": "c",
                   "segment": "s"}], fh)
    with open(os.path.join(work, "chapters.json"), "w") as fh:
        json.dump([{"start": "0:00", "label": "Intro"}], fh)
    return work


class TestPublish(unittest.TestCase):
    def setUp(self):
        SENT.clear()
        self.real = publish.urllib.request.urlopen
        publish.urllib.request.urlopen = fake_urlopen
        self.env = dict(os.environ)
        os.environ["CLOUD_LIBRARY_ID"] = "L"
        os.environ["CLOUD_LIBRARY_KEY"] = "K"
        os.environ["CLOUD_CDN_HOSTNAME"] = "cdn.example"

    def tearDown(self):
        publish.urllib.request.urlopen = self.real
        os.environ.clear()
        os.environ.update(self.env)

    def run_publish(self, td, extra=()):
        work = fixture_work(td)
        state = os.path.join(td, "cloud_state.json")
        with open(state, "w") as fh:
            json.dump({"vid-1": {"title": "Bread", "workDir": work}}, fh)
        argv = ["publish", "--work", work, "--state", state,
                "--signer", "https://signer.test", "--token", "sekret"]
        publish.main(list(argv[1:]) + list(extra))

    def test_posts_payload_to_hub_publish(self):
        with tempfile.TemporaryDirectory() as td:
            self.run_publish(td)
        self.assertEqual(SENT["url"],
                         "https://signer.test/hub/publish")
        self.assertEqual(SENT["token"], "sekret")
        body = SENT["payload"]
        self.assertEqual(body["videoId"], "vid-1")
        self.assertEqual(body["title"], "Bread")
        self.assertIn("Tasty body", body["writeupMd"])
        self.assertEqual(body["corrections"][0]["quote"], "q")
        self.assertEqual(body["chapters"][0]["label"], "Intro")
        self.assertIn("playlist.m3u8", body["hlsUrl"])
        self.assertIn("play_720p", body["mp4Url"])

    def test_guid_override(self):
        with tempfile.TemporaryDirectory() as td:
            work = fixture_work(td)
            state = os.path.join(td, "cloud_state.json")
            with open(state, "w") as fh:
                json.dump({}, fh)
            publish.main(["--work", work, "--state", state,
                          "--signer", "https://signer.test",
                          "--token", "sekret", "--guid", "vid-9"])
        self.assertEqual(SENT["payload"]["videoId"], "vid-9")

    def test_missing_guid_exits(self):
        with tempfile.TemporaryDirectory() as td:
            work = fixture_work(td)
            state = os.path.join(td, "cloud_state.json")
            with open(state, "w") as fh:
                json.dump({}, fh)
            with self.assertRaises(SystemExit):
                publish.main(["--work", work, "--state", state,
                              "--signer", "https://signer.test",
                              "--token", "sekret"])

    def publish_twice(self, td, between=None, extra=("--if-changed",)):
        work = fixture_work(td)
        state = os.path.join(td, "cloud_state.json")
        with open(state, "w") as fh:
            json.dump({"vid-1": {"title": "Bread", "workDir": work}}, fh)
        argv = ["--work", work, "--state", state, "--signer",
                "https://signer.test", "--token", "sekret"] + list(extra)
        self.assertEqual(publish.main(argv), 0)
        if between:
            between(work)
        self.assertEqual(publish.main(argv), 0)
        return work

    def test_unchanged_session_is_not_republished(self):
        # The cron loop publishes every finished work dir every five
        # minutes: re-posting unchanged sessions resurrected hub
        # deletes made in the apps and churned publishedAt (the hub's
        # newest-first order). --if-changed posts a session once per
        # version of its artifacts.
        with tempfile.TemporaryDirectory() as td:
            work = self.publish_twice(td)
            self.assertEqual(SENT["publishes"], 1)
            self.assertEqual(SENT["vendor_calls"], 1)
            # The marker lives beside the state, never in the work
            # dir (a write there would move the dir-mtime lesson date).
            self.assertTrue(os.path.exists(
                os.path.join(td, "hub_published.json")))
            self.assertNotIn("hub_published.json", os.listdir(work))

    def test_changed_session_republishes(self):
        def rewrite(work):
            with open(os.path.join(work, "writeup.md"), "w") as fh:
                fh.write("# Bread\n\nBetter body.\n")
        with tempfile.TemporaryDirectory() as td:
            self.publish_twice(td, between=rewrite)
        self.assertEqual(SENT["publishes"], 2)
        self.assertIn("Better body", SENT["payload"]["writeupMd"])

    def test_corrected_lesson_date_republishes(self):
        # A lesson date that changes (the cloud dir-name stamp now
        # replaces the processing-date fallback) must reach the hub.
        real = publish.session_meta
        dates = iter(["Nov 01, 2026", "Oct 28, 2026"])
        publish.session_meta = lambda work: (real(work)[0], next(dates), "")
        try:
            with tempfile.TemporaryDirectory() as td:
                self.publish_twice(td)
        finally:
            publish.session_meta = real
        self.assertEqual(SENT["publishes"], 2)
        self.assertEqual(SENT["payload"]["lessonDate"], "Oct 28, 2026")

    def test_plain_publish_always_posts(self):
        # Without --if-changed an operator's manual publish still
        # forces the post.
        with tempfile.TemporaryDirectory() as td:
            self.publish_twice(td, extra=())
        self.assertEqual(SENT["publishes"], 2)

    def test_video_gone_from_stream_is_not_published(self):
        # An app's hub delete removes the hub row AND the Stream
        # video; the work dir stays. A republish would point the hub
        # at a dead video — Stream's 404 skips it (exit 0: not a cron
        # failure), and the marker keeps later runs quiet.
        SENT["vendor_404"] = True
        with tempfile.TemporaryDirectory() as td:
            self.publish_twice(td)
        self.assertNotIn("publishes", SENT)
        self.assertEqual(SENT["vendor_calls"], 1)

    def test_missing_writeup_exits(self):
        with tempfile.TemporaryDirectory() as td:
            work = os.path.join(td, "empty")
            os.makedirs(work)
            state = os.path.join(td, "cloud_state.json")
            with open(state, "w") as fh:
                json.dump({"vid-1": {"workDir": work}}, fh)
            with self.assertRaises(SystemExit):
                publish.main(["--work", work, "--state", state,
                              "--signer", "https://signer.test",
                              "--token", "sekret", "--guid", "vid-1"])


class TestSyncIgnored(unittest.TestCase):
    # The operator's set-asides travel to the hub so the recorders
    # badge them on Record (the sessions list excludes them
    # server-side). Sync converges: ignored entries upserted, stale
    # markers removed.
    def setUp(self):
        SENT.clear()
        self.real = publish.urllib.request.urlopen
        publish.urllib.request.urlopen = fake_urlopen

    def tearDown(self):
        publish.urllib.request.urlopen = self.real

    def run_sync(self, td, state):
        state_path = os.path.join(td, "cloud_state.json")
        with open(state_path, "w") as fh:
            json.dump(state, fh)
        publish.main(["--sync-ignored", "--state", state_path,
                      "--signer", "https://signer.test",
                      "--token", "sekret"])

    def test_posts_only_ignored_entries(self):
        with tempfile.TemporaryDirectory() as td:
            self.run_sync(td, {
                "junk": {"title": "Test", "result": "ignored",
                         "reason": "not a lesson"},
                "good": {"title": "Bread", "result": "done"},
                "bad": {"title": "X", "result": "failed"}})
        posted = SENT.get("ignored", [])
        self.assertEqual(len(posted), 1)
        self.assertEqual(posted[0]["videoId"], "junk")
        self.assertEqual(posted[0]["title"], "Test")
        self.assertEqual(posted[0]["reason"], "not a lesson")
        self.assertEqual(SENT.get("unignored", None), None)

    def test_removes_markers_no_longer_ignored(self):
        with tempfile.TemporaryDirectory() as td:
            SENT["remote_ignored"] = [
                {"videoId": "junk", "title": "T", "reason": "r"},
                {"videoId": "forgiven", "title": "F", "reason": "r"}]
            self.run_sync(td, {"junk": {"title": "T",
                                        "result": "ignored"}})
        self.assertEqual(
            [p["videoId"] for p in SENT.get("ignored", [])], ["junk"])
        self.assertEqual(SENT.get("unignored"), ["forgiven"])

    def test_missing_state_is_a_quiet_noop(self):
        with tempfile.TemporaryDirectory() as td:
            publish.main(["--sync-ignored",
                          "--state", os.path.join(td, "nope.json"),
                          "--signer", "https://signer.test",
                          "--token", "sekret"])
        self.assertNotIn("ignored", SENT)

    def test_corrupt_state_fails_loudly(self):
        with tempfile.TemporaryDirectory() as td:
            state_path = os.path.join(td, "cloud_state.json")
            with open(state_path, "w") as fh:
                fh.write("{nope")
            with self.assertRaises(SystemExit):
                publish.main(["--sync-ignored", "--state", state_path,
                              "--signer", "https://signer.test",
                              "--token", "sekret"])

    def test_wrong_shaped_success_fails_loudly(self):
        # A stale worker answers the marker POST with 200 and a mint
        # payload (unknown paths fall into the video trio). A 200 with
        # the wrong shape must fail like a refusal — never read as a
        # stored marker.
        with tempfile.TemporaryDirectory() as td:
            SENT["misshapen_ignored"] = True
            with self.assertRaises(SystemExit) as ctx:
                self.run_sync(td, {"junk": {"title": "T",
                                            "result": "ignored"}})
        self.assertIn("junk", str(ctx.exception))

    def test_non_list_ignored_answers_loudly(self):
        with tempfile.TemporaryDirectory() as td:
            SENT["remote_ignored"] = {"error": "not a list"}
            with self.assertRaises(SystemExit):
                self.run_sync(td, {"junk": {"title": "T",
                                            "result": "ignored"}})

    def test_refusal_names_the_video(self):
        with tempfile.TemporaryDirectory() as td:
            SENT["refuse_ignored"] = True
            with self.assertRaises(SystemExit) as ctx:
                self.run_sync(td, {"junk": {"title": "T",
                                            "result": "ignored"}})
        self.assertIn("junk", str(ctx.exception))

    def test_needs_signer_and_token(self):
        from unittest import mock
        with tempfile.TemporaryDirectory() as td:
            state_path = os.path.join(td, "cloud_state.json")
            with open(state_path, "w") as fh:
                fh.write("{}")
            env = {k: v for k, v in os.environ.items()
                   if not k.startswith("HUB_")}
            with mock.patch.dict(os.environ, env, clear=True):
                with self.assertRaises(SystemExit):
                    publish.main(["--sync-ignored", "--state", state_path])


class TestHubSchema(unittest.TestCase):
    def test_migration_builds_sessions_table(self):
        mig = os.path.join(ROOT, "app", "cloud-signer", "migrations",
                           "0001_sessions.sql")
        con = sqlite3.connect(":memory:")
        with open(mig) as fh:
            con.executescript(fh.read())
        con.execute(
            "INSERT INTO sessions (video_id, title) VALUES (?, ?)",
            ("v1", "Bread"))
        con.execute(
            "INSERT INTO sessions (video_id, title) VALUES (?, ?) "
            "ON CONFLICT(video_id) DO UPDATE SET title=excluded.title",
            ("v1", "Bread v2"))
        rows = con.execute(
            "SELECT video_id, title FROM sessions").fetchall()
        self.assertEqual(rows, [("v1", "Bread v2")])

    def test_migration_builds_ignored_table(self):
        mig = os.path.join(ROOT, "app", "cloud-signer", "migrations",
                           "0003_ignored.sql")
        con = sqlite3.connect(":memory:")
        with open(mig) as fh:
            con.executescript(fh.read())
        con.execute(
            "INSERT INTO ignored_videos (video_id, title, reason) "
            "VALUES (?, ?, ?)", ("v1", "Test", "r"))
        con.execute(
            "INSERT INTO ignored_videos (video_id, title, reason) "
            "VALUES (?, ?, ?) ON CONFLICT(video_id) DO UPDATE SET "
            "reason=excluded.reason", ("v1", "Test", "r2"))
        rows = con.execute(
            "SELECT video_id, reason FROM ignored_videos").fetchall()
        self.assertEqual(rows, [("v1", "r2")])


if __name__ == "__main__":
    unittest.main()
