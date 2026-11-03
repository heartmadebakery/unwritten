"""Tests for the Meta Model API integration: SAM wire parsing, the
API client shapes (stubbed HTTP — no key, no network), highlight
rendering, and the write-up video/fallback routing."""
import io
import json
import os
import struct
import sys
import tempfile
import unittest
import zlib
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))

import highlight as hl
import meta_api
from meta_api import MetaApiError
import draft_writeup as dw
import run_pipeline as rp
import schemas as schemas_mod
import transcribe as transcribe_mod
import find_corrections as fc

# Verbatim wire fixtures from the SAM "reading segmentation output" doc.
VIDEO_LINE = (
    "<0f>0<|box;x1=211;y1=228;x2=270;y2=254;w=320;h=334|>"
    "<|mask;x=0;y=0;data=27,60,~!!!!M!0c[0o91w?q1!pIH4pPRVp2B3'7`e.ioeAf6-k/#Xd8%dX9x(|>,"
    "1<|box;x1=155;y1=228;x2=202;y2=254;w=320;h=334|>"
    "<|mask;x=0;y=0;data=27,48,~!!!!J!0c[q=Pj_zs=*4C4(/./x#:/`S_GnD`=o3?X{emCgO$y@|>"
)
CONF_LINE = (
    "<0f>1<|box;x1=444;y1=625;x2=679;y2=850;w=1800;h=1200;c=0.9609375|>"
    "<|mask;x=0;y=0;c=0.9609375;data=226,236,!...|>"
)


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self.payload


def stub_urlopen(captured, payload):
    def fake(req, timeout=None):
        captured.append(req)
        return FakeResponse(payload)
    return fake


class TestParseSegmentation(unittest.TestCase):
    def test_video_line_two_records(self):
        frames = meta_api.parse_segmentation(VIDEO_LINE)
        self.assertEqual(len(frames), 1)
        self.assertEqual(frames[0]["frame"], 0)
        recs = frames[0]["records"]
        self.assertEqual([r["id"] for r in recs], [0, 1])
        self.assertEqual(recs[0]["box"]["x1"], 211)
        self.assertEqual(recs[0]["box"]["h"], 334)
        self.assertIsNone(recs[0]["box"]["c"])
        self.assertEqual(recs[0]["mask"]["h"], 27)  # height-first
        self.assertEqual(recs[0]["mask"]["w"], 60)
        self.assertEqual(recs[0]["mask"]["enc"], "~")
        self.assertTrue(recs[0]["mask"]["payload"])

    def test_confidence_fields(self):
        recs = meta_api.parse_segmentation(CONF_LINE)[0]["records"]
        self.assertAlmostEqual(recs[0]["box"]["c"], 0.9609375)
        self.assertAlmostEqual(recs[0]["mask"]["c"], 0.9609375)
        self.assertEqual(recs[0]["mask"]["enc"], "!")

    def test_empty_and_malformed(self):
        self.assertEqual(meta_api.parse_segmentation(""), [])
        self.assertEqual(meta_api.parse_segmentation("not a wire line\n"), [])
        # A bad line never kills the good ones around it.
        frames = meta_api.parse_segmentation("garbage\n" + VIDEO_LINE + "\n")
        self.assertEqual(len(frames), 1)

    def test_sparse_ids_and_skipped_frames(self):
        line2 = VIDEO_LINE.replace("<0f>0<|", "<2f>0<|", 1)
        line2 = line2.split(",1<|")[0]  # object 1 left the frame
        frames = meta_api.parse_segmentation(VIDEO_LINE + "\n" + line2)
        self.assertEqual([f["frame"] for f in frames], [0, 2])
        tracks = meta_api.tracks(frames)
        self.assertEqual(sorted(tracks), [0, 1])
        self.assertEqual(tracks[0]["frames"], [0, 2])
        self.assertEqual(tracks[1]["frames"], [0])
        self.assertEqual(len(tracks[0]["boxes"]), 2)


class TestMaskDecodeHandoff(unittest.TestCase):
    def test_doc_payload_decodes_to_binary_raster(self):
        try:
            from meta_sam_parser import (SegmentationMask,
                                         decode_mask_to_raster)
        except ImportError:
            self.skipTest("meta_sam_parser not installed")
        rec = meta_api.parse_segmentation(VIDEO_LINE)[0]["records"][0]
        mask = rec["mask"]
        raster = decode_mask_to_raster(SegmentationMask(
            encoding="lossless", payload=mask["enc"] + mask["payload"],
            width=mask["w"], height=mask["h"]))
        self.assertEqual(len(raster), mask["w"] * mask["h"])
        self.assertTrue(set(raster) <= {0, 1})


class FakeHttpResp:
    def __init__(self, status, payload):
        self.status = status
        self.payload = payload

    def read(self):
        return self.payload


def stub_conn(captured, status, payload):
    class Conn:
        def __init__(self, host, port=None, timeout=None):
            captured["host"] = host

        def putrequest(self, method, path):
            captured["req"] = (method, path)

        def putheader(self, key, value):
            captured.setdefault("headers", {})[key] = value

        def endheaders(self):
            pass

        def send(self, data):
            captured.setdefault("body", []).append(bytes(data))

        def getresponse(self):
            return FakeHttpResp(status, payload)

        def close(self):
            pass

    return Conn


class TestClientShapes(unittest.TestCase):
    def test_upload_streams_multipart_with_purpose(self):
        captured = {}
        payload = json.dumps({"id": "file-abc123"}).encode()
        with tempfile.NamedTemporaryFile(suffix=".mp4") as fh:
            fh.write(b"fakevideo")
            fh.flush()
            with mock.patch.dict(os.environ, {"MODEL_API_KEY": "k"}), \
                    mock.patch("http.client.HTTPSConnection",
                               stub_conn(captured, 200, payload)):
                file_id = meta_api.upload_file(fh.name)
        self.assertEqual(file_id, "file-abc123")
        self.assertEqual(captured["req"], ("POST", "/v1/files"))
        headers = captured["headers"]
        self.assertEqual(headers["Authorization"], "Bearer k")
        self.assertIn("multipart/form-data", headers["Content-Type"])
        body = b"".join(captured["body"])
        self.assertEqual(int(headers["Content-Length"]), len(body))
        self.assertIn(b'name="purpose"', body)
        self.assertIn(b"user_data", body)
        self.assertIn(b".mp4", body)
        self.assertIn(b"fakevideo", body)

    def test_upload_rejects_bad_id(self):
        payload = json.dumps({"id": "nope"}).encode()
        with tempfile.NamedTemporaryFile(suffix=".mp4") as fh:
            fh.write(b"x")
            fh.flush()
            with mock.patch.dict(os.environ, {"MODEL_API_KEY": "k"}), \
                    mock.patch("http.client.HTTPSConnection",
                               stub_conn({}, 200, payload)):
                with self.assertRaises(MetaApiError):
                    meta_api.upload_file(fh.name)

    def test_upload_rejects_http_error_status(self):
        with tempfile.NamedTemporaryFile(suffix=".mp4") as fh:
            fh.write(b"x")
            fh.flush()
            with mock.patch.dict(os.environ, {"MODEL_API_KEY": "k"}), \
                    mock.patch("http.client.HTTPSConnection",
                               stub_conn({}, 401, b"no")):
                with self.assertRaises(MetaApiError) as ctx:
                    meta_api.upload_file(fh.name)
        self.assertEqual(ctx.exception.status, 401)

    def test_responses_body_shape(self):
        captured = []
        payload = json.dumps({"output": [{"type": "message", "content": [
            {"type": "output_text", "text": "hello"}]}]}).encode()
        with mock.patch("urllib.request.urlopen",
                         stub_urlopen(captured, payload)):
            text = meta_api.ask_video({"file_id": "file-9"}, "Describe.",
                                      "k", timeout=5)
        self.assertEqual(text, "hello")
        sent = json.loads(captured[0].data.decode())
        self.assertEqual(sent["model"], "muse-spark-1.3")
        content = sent["input"][0]["content"]
        self.assertEqual(content[1],
                         {"type": "input_video", "file_id": "file-9"})

    def test_responses_retries_429_then_success(self):
        import urllib.error
        good = json.dumps({"output": []}).encode()
        calls = []

        def flaky(req, timeout=None):
            calls.append(req)
            if len(calls) < 3:
                raise urllib.error.HTTPError(
                    req.full_url, 429, "slow", {}, io.BytesIO(b"{}"))
            return FakeResponse(good)

        with mock.patch("urllib.request.urlopen", flaky), \
                mock.patch("time.sleep") as sl:
            resp = meta_api.responses_create(
                "m", [{"type": "input_text", "text": "hi"}], "k")
        self.assertEqual(resp, {"output": []})
        self.assertEqual(len(calls), 3)
        sl.assert_called()

    def test_responses_persistent_500_raises(self):
        import urllib.error
        calls = []

        def failing(req, timeout=None):
            calls.append(req)
            raise urllib.error.HTTPError(
                req.full_url, 500, "bad", {}, io.BytesIO(b"{}"))

        with mock.patch("urllib.request.urlopen", failing), \
                mock.patch("time.sleep"):
            with self.assertRaises(MetaApiError):
                meta_api.responses_create("m", [], "k")
        self.assertEqual(len(calls), 2)  # once, plus the one retry

    def test_tls_and_http_errors_wrapped(self):
        import http.client
        import ssl
        errors = [ssl.SSLError("tls boom"),
                  http.client.RemoteDisconnected("gone"),
                  ConnectionResetError("rst")]
        for err in errors:
            with mock.patch("urllib.request.urlopen", side_effect=err):
                with self.assertRaises(MetaApiError):
                    meta_api.responses_create("m", [], "k")

    def test_output_text_walker(self):
        resp = {"output": [
            {"content": [{"type": "output_text", "text": "a"},
                         {"type": "other", "text": "IGNORED"}]},
            {"content": [{"type": "output_text", "text": "b"}]}]}
        self.assertEqual(meta_api.output_text(resp), "ab")
        self.assertEqual(meta_api.output_text({"unexpected": 1}), "")
        self.assertEqual(meta_api.output_text(None), "")

    def test_key_and_phrase_guards(self):
        with self.assertRaises(MetaApiError):
            meta_api.ask_video({"file_id": "file-9"}, "x", "")
        with self.assertRaises(MetaApiError):
            meta_api.segment_video_lines("file-9", "  ", "k")
        self.assertFalse(meta_api.delete_file("file-9"))

    def test_zero_matches_is_empty_text(self):
        payload = json.dumps({"output": [{"type": "message",
                                          "content": []}]}).encode()
        with mock.patch("urllib.request.urlopen",
                         stub_urlopen([], payload)):
            self.assertEqual(
                meta_api.segment_video_lines("file-9", "hands", "k"), "")


class TestCaching(unittest.TestCase):
    def test_cache_key_sent(self):
        captured = []
        payload = json.dumps({"output": [], "usage": {"input_tokens": 10,
                             "input_tokens_details": {"cached_tokens": 4}}
                              }).encode()
        with mock.patch("urllib.request.urlopen",
                         stub_urlopen(captured, payload)):
            meta_api.responses_create("m", [{"type": "input_text",
                                             "text": "hi"}], "k",
                                      cache_key="unwritten-test")
        sent = json.loads(captured[0].data.decode())
        self.assertEqual(sent["prompt_cache_key"], "unwritten-test")

    def test_cached_tokens_walker(self):
        resp = {"usage": {"input_tokens": 1847, "input_tokens_details":
                          {"cached_tokens": 1792}}}
        self.assertEqual(meta_api.cached_tokens(resp), (1792, 1847))
        self.assertEqual(meta_api.cached_tokens({}), (0, 0))
        self.assertEqual(meta_api.cached_tokens(None), (0, 0))


class TestChapters(unittest.TestCase):
    def test_parse_chapters(self):
        out = rp.parse_chapters('[{"start": "00:00", "label": "Prep veg"},'
                                ' {"start": "04:12", "label": "Simmer"}]')
        self.assertEqual(out, [{"start": "00:00", "label": "Prep veg"},
                               {"start": "04:12", "label": "Simmer"}])
        with self.assertRaises(ValueError):
            rp.parse_chapters("not json")
        with self.assertRaises(ValueError):
            rp.parse_chapters('[{"start": "xx", "label": "Bad"}]')

    def test_no_key_no_chapters(self):
        env = dict(os.environ)
        env.pop("MODEL_API_KEY", None)
        with mock.patch.dict(os.environ, env, clear=True):
            work = lambda *p: os.path.join("w", *p)
            self.assertEqual(rp.try_chapters(work, "lesson.mp4"), "")
            self.assertEqual(rp.try_chapters(work, ""), "")


class TestHighlightRender(unittest.TestCase):
    def test_clamp_box(self):
        self.assertEqual(hl.clamp_box((2, 2, 6, 6), 8, 8), (2, 2, 6, 6))
        self.assertEqual(hl.clamp_box((-5, -5, 99, 99), 8, 8), (0, 0, 8, 8))
        self.assertIsNone(hl.clamp_box((9, 9, 12, 12), 8, 8))
        self.assertIsNone(hl.clamp_box((4, 4, 4, 6), 8, 8))

    def test_spotlight_pixels(self):
        pixels = hl.spotlight_frame(10, 9, [(1, 1, 9, 8)])

        def px(x, y):
            off = (y * 10 + x) * 4
            return bytes(pixels[off:off + 4])

        self.assertEqual(px(0, 0), bytes((0, 0, 0, hl.DIM_ALPHA)))
        self.assertEqual(px(5, 4), bytes((0, 0, 0, 0)))  # clear inside
        edge = bytes((hl.EDGE_RGB[0], hl.EDGE_RGB[1], hl.EDGE_RGB[2], 255))
        self.assertEqual(px(1, 1), edge)  # amber border
        self.assertEqual(len(pixels), 10 * 9 * 4)

    def test_boxes_hold_across_gaps(self):
        parsed = meta_api.parse_segmentation(VIDEO_LINE)
        boxes = hl.boxes_for_frame(parsed, 7)  # past the only line
        self.assertEqual(len(boxes), 2)
        self.assertEqual(hl.boxes_for_frame([], 0), [])

    def test_boxes_hold_before_first_track(self):
        # A share-safe redaction must never render a bare face for
        # want of an earlier box: frames before the first tracked
        # frame hold that frame's boxes.
        parsed = [{"frame": 5, "records": [
            {"id": 0, "box": {"x1": 1, "y1": 2, "x2": 3, "y2": 4}}]}]
        self.assertEqual(hl.boxes_for_frame(parsed, 0), [(1, 2, 3, 4)])
        self.assertEqual(hl.boxes_for_frame(parsed, 7), [(1, 2, 3, 4)])

    def test_mux_uses_compatible_pix_fmt_and_cleans_partial(self):
        with tempfile.TemporaryDirectory() as td:
            out = os.path.join(td, "h.mp4")
            with open(out, "wb") as fh:
                fh.write(b"partial")
            with mock.patch("subprocess.run") as run:
                run.return_value = mock.Mock(returncode=1, stderr="boom")
                self.assertFalse(
                    hl.mux_highlight("c.mp4", "ov_%05d.png", 30.0, out))
            cmd = run.call_args[0][0]
            self.assertIn("yuv420p", cmd)
            self.assertFalse(os.path.exists(out))

    def test_probe_falls_back_to_frame_count(self):
        out = ("width=640\nheight=480\navg_frame_rate=0/0\n"
               "r_frame_rate=30/1\nduration=N/A\nnb_frames=90\n")
        with mock.patch("subprocess.run") as run:
            run.return_value = mock.Mock(stdout=out)
            self.assertEqual(hl.probe_clip("x.mp4"), (640, 480, 30.0, 90))
        run.assert_called_once()  # no decode pass needed

    def test_probe_decode_counts_when_nothing_listed(self):
        out1 = "width=640\nheight=480\navg_frame_rate=0/0\n"
        with mock.patch("subprocess.run") as run:
            run.side_effect = [mock.Mock(stdout=out1),
                               mock.Mock(stdout="45\n")]
            self.assertEqual(hl.probe_clip("x.mp4"), (640, 480, 30.0, 45))
        cmd = run.call_args_list[1][0][0]
        self.assertIn("-count_frames", cmd)

    def test_png_round_trip(self):
        pixels = bytes(range(4 * 3 * 4))
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "t.png")
            hl.write_png_rgba(path, 4, 3, pixels)
            with open(path, "rb") as fh:
                data = fh.read()
        self.assertTrue(data.startswith(b"\x89PNG\r\n\x1a\n"))
        width, height, depth, color = struct.unpack(">IIBB", data[16:26])
        self.assertEqual((width, height, depth, color), (4, 3, 8, 6))
        idat = b""
        pos = 8
        while pos < len(data):
            (length,) = struct.unpack(">I", data[pos:pos + 4])
            tag = data[pos + 4:pos + 8]
            if tag == b"IDAT":
                idat += data[pos + 8:pos + 8 + length]
            pos += 12 + length
        rows = zlib.decompress(idat)
        self.assertEqual(len(rows), 3 * (1 + 4 * 4))
        self.assertEqual(rows[1:1 + 4 * 4], pixels[0:4 * 4])

    def test_render_overlays_count(self):
        parsed = meta_api.parse_segmentation(VIDEO_LINE)
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(hl.render_overlays(parsed, 8, 6, 3, td), 3)
            self.assertEqual(len([f for f in os.listdir(td)
                                  if f.endswith(".png")]), 3)

    def test_save_tracks_shape(self):
        parsed = meta_api.parse_segmentation(VIDEO_LINE)
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "segments-01.json")
            hl.save_tracks(path, "hands", parsed)
            with open(path) as fh:
                saved = json.load(fh)
        self.assertEqual(saved["concept"], "hands")
        self.assertEqual(saved["frames"][0]["frame"], 0)


class TestHighlightStage(unittest.TestCase):
    def test_no_key_means_no_highlight(self):
        env = dict(os.environ)
        env.pop("MODEL_API_KEY", None)
        with mock.patch.dict(os.environ, env, clear=True):
            work = lambda *p: os.path.join("w", *p)
            self.assertEqual(rp.try_highlight(work, "c.mp4", "hands", 1), "")
            self.assertEqual(rp.try_highlight(work, "c.mp4", "", 1), "")

    def test_render_lists_highlight(self):
        hits = [{"start": "02:08", "quote": "q", "correcting": "c"}]
        md = rp.render_corrections_md(hits, {1: "correction-01.mp4"},
                                      {1: "highlight-01.mp4"})
        self.assertIn("Clip: `clips/correction-01.mp4`", md)
        self.assertIn("Highlight: `clips/highlight-01.mp4`", md)

    def test_render_without_highlights_unchanged(self):
        hits = [{"start": "02:08", "quote": "q", "correcting": "c"}]
        md = rp.render_corrections_md(hits, {1: "correction-01.mp4"})
        self.assertNotIn("Highlight:", md)


class TestAsrClient(unittest.TestCase):
    TURNS_RESP = {"sessionId": "s", "transcript": "Hi. Bye.",
                  "audioDurationMs": 8240,
                  "turns": [
                      {"turnId": 1, "startMs": 1520, "endMs": 4640,
                       "transcript": "Hi.", "speaker": "A"},
                      {"turnId": 2, "startMs": 5900, "endMs": 8240,
                       "transcript": "Bye.", "speaker": "B"}]}

    def test_request_shape(self):
        captured = []
        payload = json.dumps(self.TURNS_RESP).encode()
        with tempfile.NamedTemporaryFile(suffix=".wav") as fh:
            fh.write(b"RIFFfake")
            fh.flush()
            with mock.patch("urllib.request.urlopen",
                             stub_urlopen(captured, payload)):
                segs = meta_api.asr_transcribe(fh.name, "k")
        self.assertEqual(
            segs,
            [{"start": 1.52, "end": 4.64, "text": "Hi.", "speaker": "A"},
             {"start": 5.9, "end": 8.24, "text": "Bye.", "speaker": "B"}])
        req = captured[0]
        self.assertIn("/v1/asr/transcribe", req.full_url)
        body = req.data.decode("ascii", "replace")
        self.assertIn('"mode": "DIARIZATION"', body)
        self.assertIn('"model": "muse-voice-transcribe-1.0"', body)
        self.assertIn('"audioEncoding": "WAV"', body)
        self.assertIn(b"RIFFfake", req.data)

    def test_empty_transcript_refuses(self):
        payload = json.dumps({"sessionId": "s", "transcript": "",
                              "audioDurationMs": 1000, "turns": []}).encode()
        with tempfile.NamedTemporaryFile(suffix=".wav") as fh:
            fh.write(b"x")
            fh.flush()
            with mock.patch("urllib.request.urlopen",
                             stub_urlopen([], payload)):
                with self.assertRaises(MetaApiError):
                    meta_api.asr_transcribe(fh.name, "k")

    def test_retry_then_success(self):
        import urllib.error
        good = json.dumps(self.TURNS_RESP).encode()
        calls = []

        def flaky(req, timeout=None):
            calls.append(req)
            if len(calls) < 3:
                raise urllib.error.HTTPError(
                    req.full_url, 429, "slow down", {}, io.BytesIO(b"{}"))
            return FakeResponse(good)

        with tempfile.NamedTemporaryFile(suffix=".wav") as fh:
            fh.write(b"x")
            fh.flush()
            with mock.patch("urllib.request.urlopen", flaky), \
                    mock.patch("time.sleep") as sl:
                segs = meta_api.asr_transcribe(fh.name, "k")
        self.assertEqual(len(segs), 2)
        self.assertEqual(len(calls), 3)
        sl.assert_called()

    def test_persistent_500_raises(self):
        import urllib.error

        def failing(req, timeout=None):
            raise urllib.error.HTTPError(
                req.full_url, 500, "bad", {}, io.BytesIO(b"{}"))

        with tempfile.NamedTemporaryFile(suffix=".wav") as fh:
            fh.write(b"x")
            fh.flush()
            with mock.patch("urllib.request.urlopen", failing), \
                    mock.patch("time.sleep"):
                with self.assertRaises(MetaApiError):
                    meta_api.asr_transcribe(fh.name, "k")

    def test_error_carries_status(self):
        import urllib.error

        def failing(req, timeout=None):
            raise urllib.error.HTTPError(
                req.full_url, 403, "no", {}, io.BytesIO(b"{}"))

        with tempfile.NamedTemporaryFile(suffix=".wav") as fh:
            fh.write(b"x")
            fh.flush()
            with mock.patch("urllib.request.urlopen", failing):
                with self.assertRaises(MetaApiError) as ctx:
                    meta_api.asr_transcribe(fh.name, "k")
        self.assertEqual(ctx.exception.status, 403)

    def test_chunk_plan(self):
        self.assertEqual(transcribe_mod.chunk_plan(300), [(0, 300)])
        self.assertEqual(transcribe_mod.chunk_plan(600), [(0, 600)])
        self.assertEqual(transcribe_mod.chunk_plan(601),
                         [(0, 600), (600, 1)])
        self.assertEqual(transcribe_mod.chunk_plan(1500),
                         [(0, 600), (600, 600), (1200, 300)])


class TestTranscribeRouting(unittest.TestCase):
    def test_api_default_with_key(self):
        segs = [{"start": 0, "end": 1, "text": "x"}]
        with mock.patch.dict(os.environ, {"MODEL_API_KEY": "k"}), \
                mock.patch.object(transcribe_mod, "transcribe_api",
                                  return_value=segs) as api, \
                mock.patch.object(transcribe_mod, "transcribe_local") as loc:
            self.assertEqual(transcribe_mod.transcribe("m.mp4"), segs)
        api.assert_called_once()
        loc.assert_not_called()

    def test_local_when_no_key(self):
        env = dict(os.environ)
        env.pop("MODEL_API_KEY", None)
        segs = [{"start": 0, "end": 1, "text": "x"}]
        with mock.patch.dict(os.environ, env, clear=True), \
                mock.patch.object(transcribe_mod, "transcribe_api") as api, \
                mock.patch.object(transcribe_mod, "transcribe_local",
                                  return_value=segs):
            self.assertEqual(transcribe_mod.transcribe("m.mp4"), segs)
        api.assert_not_called()

    def test_local_forced_by_env(self):
        segs = [{"start": 0, "end": 1, "text": "x"}]
        with mock.patch.dict(os.environ, {"MODEL_API_KEY": "k",
                                           "UNWRITTEN_TRANSCRIBE": "local"}), \
                mock.patch.object(transcribe_mod, "transcribe_api") as api, \
                mock.patch.object(transcribe_mod, "transcribe_local",
                                  return_value=segs):
            transcribe_mod.transcribe("m.mp4")
        api.assert_not_called()

    def test_api_forced_without_key_fails_loudly(self):
        env = dict(os.environ)
        env.pop("MODEL_API_KEY", None)
        env["UNWRITTEN_TRANSCRIBE"] = "api"
        with mock.patch.dict(os.environ, env, clear=True):
            with self.assertRaises(MetaApiError):
                transcribe_mod.transcribe("m.mp4")

    def test_unknown_mode_is_a_usage_error(self):
        with mock.patch.dict(os.environ, {"MODEL_API_KEY": "k",
                                           "UNWRITTEN_TRANSCRIBE": "lcoal"}):
            with self.assertRaises(ValueError):
                transcribe_mod.transcribe("m.mp4")


class TestAsrBias(unittest.TestCase):
    def _capture(self, **kw):
        captured = []
        payload = json.dumps(TestAsrClient.TURNS_RESP).encode()
        with tempfile.NamedTemporaryFile(suffix=".wav") as fh:
            fh.write(b"x")
            fh.flush()
            with mock.patch("urllib.request.urlopen",
                             stub_urlopen(captured, payload)):
                meta_api.asr_transcribe(fh.name, "k", **kw)
        return captured[0].data.decode("ascii", "replace")

    def test_bias_fields_included(self):
        body = self._capture(keywords=["sinigang", "patis"],
                             languages=["English", "Tagalog"])
        self.assertIn('"keywords": ["sinigang", "patis"]', body)
        self.assertIn('"languageBias": ["English", "Tagalog"]', body)

    def test_bias_omitted_by_default(self):
        body = self._capture()
        self.assertNotIn("keywords", body)
        self.assertNotIn("languageBias", body)

    def test_csv_env_parsing(self):
        with mock.patch.dict(os.environ, {
                "UNWRITTEN_ASR_KEYWORDS": "sinigang, patis,,",
                "UNWRITTEN_ASR_LANGUAGES": "English, Tagalog"}):
            self.assertEqual(transcribe_mod._csv_env("UNWRITTEN_ASR_KEYWORDS"),
                             ["sinigang", "patis"])
            self.assertEqual(
                transcribe_mod._csv_env("UNWRITTEN_ASR_LANGUAGES"),
                ["English", "Tagalog"])


class TestRedaction(unittest.TestCase):
    def test_solid_frame_covers_face(self):
        pixels = hl.solid_frame(20, 10, [(5, 2, 11, 6)])

        def px(x, y):
            off = (y * 20 + x) * 4
            return bytes(pixels[off:off + 4])

        cover = bytes((hl.FACE_RGB[0], hl.FACE_RGB[1], hl.FACE_RGB[2], 255))
        self.assertEqual(px(8, 4), cover)          # inside the cover
        self.assertEqual(px(4, 2), cover)          # padding margin
        self.assertEqual(px(0, 0), bytes(4))       # untouched corner
        self.assertEqual(px(19, 9), bytes(4))

    def test_redact_no_key_no_file(self):
        env = dict(os.environ)
        env.pop("MODEL_API_KEY", None)
        with mock.patch.dict(os.environ, env, clear=True):
            work = lambda *p: os.path.join("w", *p)
            self.assertEqual(rp.try_redact(work, "c.mp4", 1), "")

    def test_render_lists_share_safe(self):
        hits = [{"start": "02:08", "quote": "q", "correcting": "c"}]
        md = rp.render_corrections_md(hits, {1: "correction-01.mp4"}, {},
                                      {1: "redacted-01.mp4"})
        self.assertIn("Share-safe: `clips/redacted-01.mp4`", md)

    def test_pad_clamps_to_frame(self):
        self.assertEqual(hl._pad((0, 0, 10, 10), 20, 20), (0, 0, 11, 11))
        self.assertEqual(hl._pad((18, 18, 20, 20), 20, 20), (17, 17, 20, 20))


class TestPoster(unittest.TestCase):
    def test_pick_ts(self):
        self.assertEqual(rp.pick_poster_ts("07:41"), 461)
        self.assertEqual(rp.pick_poster_ts("the moment is at 1:02:03."),
                         3723)
        self.assertIsNone(rp.pick_poster_ts("no timestamp here"))
        self.assertIsNone(rp.pick_poster_ts(""))

    def test_missing_lesson_no_poster(self):
        work = lambda *p: os.path.join("w", *p)
        self.assertEqual(rp.try_poster(work, "/nonexistent.mp4"), "")
        self.assertEqual(rp.try_poster(work, ""), "")

    @unittest.skipUnless(__import__("shutil").which("ffmpeg"), "needs ffmpeg")
    def test_poster_past_the_end_falls_back_to_the_midpoint(self):
        # A model answer past the end of the video grabbed no frame
        # and left the session poster-less; the midpoint fallback
        # covers that too.
        import subprocess
        with tempfile.TemporaryDirectory() as td:
            lesson = os.path.join(td, "lesson.mp4")
            subprocess.run(
                ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
                 "testsrc=duration=4:size=64x48:rate=10", "-pix_fmt",
                 "yuv420p", lesson], check=True, capture_output=True,
                timeout=120)
            work = lambda *p: os.path.join(td, *p)
            with mock.patch.object(rp.meta_api, "api_key",
                                   return_value="k"), \
                 mock.patch.object(rp.meta_api, "upload_file",
                                   return_value="file-1"), \
                 mock.patch.object(rp.meta_api, "delete_file"), \
                 mock.patch.object(rp.meta_api, "ask_video",
                                   return_value="59:00"):
                self.assertEqual(rp.try_poster(work, lesson), "poster.jpg")
            self.assertGreater(os.path.getsize(work("poster.jpg")), 0)


class TestSchemas(unittest.TestCase):
    def test_validate_ok_and_missing(self):
        schema = {"type": "object", "required": ["a"],
                  "properties": {"a": {"type": "string", "minLength": 1},
                                 "b": {"type": "array",
                                       "items": {"type": "string"}}}}
        schemas_mod.validate({"a": "x", "b": ["y"]}, schema)
        with self.assertRaises(schemas_mod.SchemaError):
            schemas_mod.validate({"b": []}, schema)
        with self.assertRaises(schemas_mod.SchemaError):
            schemas_mod.validate({"a": "x", "b": [3]}, schema)
        with self.assertRaises(schemas_mod.SchemaError):
            schemas_mod.validate({"a": "  "}, schema)

    def test_parse_draft(self):
        raw = '{"title": "T", "intro": "", "needs": [], "steps": ["Do."], "knows": []}'
        self.assertEqual(dw.parse_draft("```json\n" + raw + "\n```")["title"], "T")
        with self.assertRaises(ValueError):
            dw.parse_draft("just prose")
        with self.assertRaises(ValueError):
            dw.parse_draft('{"title": "T"}')

    def test_render_writeup_shape(self):
        md = dw.render_writeup({"title": "Mentor's Soup", "intro": "Intro.",
                                "needs": ["water"], "steps": ["Boil."],
                                "knows": []})
        self.assertEqual(
            md, "# Mentor's Soup — the write-up\n\nIntro.\n\n"
                "## What you need\n\n- water\n\n## Steps\n\n1. Boil.\n")
        self.assertEqual(dw.validate_writeup(md), "")
        self.assertNotIn("## What the mentor knows", md)

    def test_finder_rejects_malformed_item(self):
        with self.assertRaises(SystemExit):
            fc.parse_hits('[{"start": "02:08"}]')


class TestDraftRouting(unittest.TestCase):
    GOOD_JSON = json.dumps({"title": "Mentor's Soup", "intro": "Intro.",
                            "needs": ["water"], "steps": ["Boil."],
                            "knows": []})
    GOOD_MD = ("# Mentor's Soup — the write-up\n\nIntro.\n\n"
               "## What you need\n\n- water\n\n## Steps\n\n1. Boil.\n")

    def test_video_path_used_with_key_and_mp4(self):
        with tempfile.NamedTemporaryFile(suffix=".mp4") as fh:
            with mock.patch.dict(os.environ, {"MODEL_API_KEY": "k"}), \
                    mock.patch.object(dw, "draft_video",
                                      return_value=self.GOOD_JSON) as dv, \
                    mock.patch.object(dw, "draft_frames") as df:
                self.assertEqual(dw.draft("t", fh.name), self.GOOD_MD)
        dv.assert_called_once()
        df.assert_not_called()

    def test_api_failure_falls_back_to_frames(self):
        with tempfile.NamedTemporaryFile(suffix=".mp4") as fh:
            with mock.patch.dict(os.environ, {"MODEL_API_KEY": "k"}), \
                    mock.patch.object(dw, "draft_video",
                                      side_effect=MetaApiError("down")), \
                    mock.patch.object(dw, "draft_frames",
                                      return_value=self.GOOD_JSON) as df:
                self.assertEqual(dw.draft("t", fh.name), self.GOOD_MD)
        df.assert_called_once()

    def test_no_key_goes_straight_to_frames(self):
        env = dict(os.environ)
        env.pop("MODEL_API_KEY", None)
        with tempfile.NamedTemporaryFile(suffix=".mp4") as fh:
            with mock.patch.dict(os.environ, env, clear=True), \
                    mock.patch.object(dw, "draft_video") as dv, \
                    mock.patch.object(dw, "draft_frames",
                                      return_value=self.GOOD_JSON):
                dw.draft("t", fh.name)
        dv.assert_not_called()

    def test_ensure_mp4(self):
        with tempfile.TemporaryDirectory() as td:
            mp4 = os.path.join(td, "a.mp4")
            with open(mp4, "wb") as fh:
                fh.write(b"x")
            self.assertEqual(dw.ensure_mp4(mp4, td), mp4)
            self.assertEqual(dw.ensure_mp4(os.path.join(td, "no.mp4"), td),
                             "")
            webm = os.path.join(td, "b.webm")  # empty: remux must fail
            with open(webm, "wb") as fh:
                fh.write(b"")
            self.assertEqual(dw.ensure_mp4(webm, td), "")

    @unittest.skipUnless(__import__("shutil").which("ffmpeg"), "needs ffmpeg")
    def test_ensure_mp4_converts_a_vp8_web_take(self):
        # The web recorder takes VP8/Opus WebM, which the MP4 muxer
        # refuses to stream-copy ("Could not find tag for codec vp8"):
        # every raw web take fell back to still frames. A refused
        # remux now transcodes instead.
        import subprocess
        with tempfile.TemporaryDirectory() as td:
            webm = os.path.join(td, "take.webm")
            subprocess.run(
                ["ffmpeg", "-y", "-v", "error",
                 "-f", "lavfi", "-i", "testsrc=duration=2:size=160x120:rate=10",
                 "-f", "lavfi", "-i", "sine=duration=2",
                 "-c:v", "libvpx", "-c:a", "libopus", webm],
                check=True, capture_output=True, timeout=120)
            out = dw.ensure_mp4(webm, td)
            self.assertTrue(out.endswith(".mp4"), out)
            self.assertGreater(os.path.getsize(out), 0)

    def test_finder_prompt_names_segment(self):
        with open(os.path.join(ROOT, "prompts", "correction_finder.md")) as fh:
            prompt = fh.read()
        self.assertIn('"segment"', prompt)


if __name__ == "__main__":
    unittest.main()
