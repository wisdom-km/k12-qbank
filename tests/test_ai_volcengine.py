"""The Ark adapter speaks to a local server. This file does not open the public network."""

from __future__ import annotations

import json
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

import httpx

from backend.ai.adapters.volcengine_model import VolcengineModel
from backend.ai.domain.model import ModelFault
from backend.ai.domain.records import JudgeAsk, TranscribeAsk

PROBE = "probe-key"
MODEL_ID = "model-probe"


class _Ark(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        self.server.bodies.append(raw)  # type: ignore[attr-defined]
        self.server.auth.append(self.headers.get("Authorization", ""))  # type: ignore[attr-defined]
        mode = self.server.mode  # type: ignore[attr-defined]
        if mode == "slow":
            time.sleep(1.5)
        if mode == "auth":
            self.send_response(401)
            self.end_headers()
            return
        if mode == "missing-model":
            self.send_response(404)
            self.end_headers()
            return
        if mode == "invalid":
            content = "nope"
        else:
            content = json.dumps(self.server.reply, ensure_ascii=False)  # type: ignore[attr-defined]
        payload = json.dumps(
            {
                "choices": [{"message": {"content": content}}],
                "usage": {"prompt_tokens": 3, "completion_tokens": 1},
            }
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        try:
            self.wfile.write(payload)
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
            return

    def log_message(self, format: str, *args: object) -> None:
        return


class VolcengineAdapterTest(unittest.TestCase):
    def test_request_uses_data_url_disabled_thinking_and_json(self) -> None:
        server = _listen()
        try:
            server.reply = {  # type: ignore[attr-defined]
                "seen_external_id": None,
                "seen_page_no": 1,
                "items": [{"order_no": 1, "transcription": "2", "unreadable": False, "confidence": 0.8}],
            }
            model = VolcengineModel(_url(server), MODEL_ID, PROBE, 5)
            result = model.transcribe(b"\xff\xd8\xff\xd9", (TranscribeAsk(1, "solution", ()),))
            body = json.loads(server.bodies[0])  # type: ignore[attr-defined]
        finally:
            _stop(server)
        self.assertEqual(result.items[0].transcription, "2")
        self.assertEqual(result.input_tokens, 3)
        self.assertEqual(result.output_tokens, 1)
        self.assertEqual(body["model"], MODEL_ID)
        self.assertEqual(body["thinking"], {"type": "disabled"})
        self.assertEqual(body["response_format"], {"type": "json_object"})
        content = body["messages"][0]["content"]
        self.assertEqual(content[0]["type"], "text")
        self.assertIn("JSON", content[0]["text"])
        self.assertTrue(content[1]["image_url"]["url"].startswith("data:image/jpeg;base64,"))
        self.assertEqual(server.auth[0], "Bearer " + PROBE)  # type: ignore[attr-defined]
        self.assertNotIn(PROBE, server.bodies[0].decode("utf-8"))  # type: ignore[attr-defined]

    def test_judge_request_has_no_image(self) -> None:
        server = _listen()
        try:
            server.reply = {  # type: ignore[attr-defined]
                "items": [{"order_no": 2, "verdict": "partial", "reason": "步骤对了"}],
            }
            model = VolcengineModel(_url(server), MODEL_ID, PROBE, 5)
            result = model.judge(
                (JudgeAsk(2, "solution", "stem-hidden", "2", "ans-hidden"),)
            )
            body = json.loads(server.bodies[0])  # type: ignore[attr-defined]
        finally:
            _stop(server)
        self.assertEqual(result.items[0].verdict, "partial")
        self.assertIsInstance(body["messages"][0]["content"], str)
        self.assertNotIn("image_url", server.bodies[0].decode("utf-8"))  # type: ignore[attr-defined]
        self.assertNotIn(PROBE, str(result))

    def test_auth_timeout_invalid_and_unknown_model(self) -> None:
        refused = _listen()
        refused.mode = "auth"  # type: ignore[attr-defined]
        try:
            model = VolcengineModel(_url(refused), MODEL_ID, PROBE, 2)
            with self.assertRaises(ModelFault) as caught:
                model.transcribe(b"\xff\xd8\xff\xd9", (TranscribeAsk(1, "solution", ()),))
        finally:
            _stop(refused)
        self.assertEqual(caught.exception.code, "auth_failed")
        self.assertNotIn(PROBE, str(caught.exception))

        slow = _listen()
        slow.mode = "slow"  # type: ignore[attr-defined]
        slow.reply = {"items": []}  # type: ignore[attr-defined]
        try:
            model = VolcengineModel(_url(slow), MODEL_ID, PROBE, 0.3)
            with self.assertRaises(ModelFault) as timed:
                model.transcribe(b"\xff\xd8\xff\xd9", (TranscribeAsk(1, "solution", ()),))
        finally:
            _stop(slow)
        self.assertEqual(timed.exception.code, "timeout")

        invalid = _listen()
        invalid.mode = "invalid"  # type: ignore[attr-defined]
        try:
            model = VolcengineModel(_url(invalid), MODEL_ID, PROBE, 2)
            with self.assertRaises(ModelFault) as bad:
                model.judge((JudgeAsk(1, "solution", "stem", "2", "2"),))
        finally:
            _stop(invalid)
        self.assertEqual(bad.exception.code, "model_output_invalid")

        missing = _listen()
        missing.mode = "missing-model"  # type: ignore[attr-defined]
        try:
            model = VolcengineModel(_url(missing), MODEL_ID, PROBE, 2)
            with self.assertRaises(ModelFault) as absent:
                model.judge((JudgeAsk(1, "solution", "stem", "2", "2"),))
        finally:
            _stop(missing)
        self.assertEqual(absent.exception.code, "model_not_found")

        offline = VolcengineModel("http://127.0.0.1:9/v1", MODEL_ID, PROBE, 0.5)
        with mock.patch(
            "backend.ai.adapters.volcengine_model.httpx.post",
            side_effect=httpx.ConnectError("refused"),
        ):
            with self.assertRaises(ModelFault) as down:
                offline.judge((JudgeAsk(1, "solution", "stem", "2", "2"),))
        self.assertEqual(down.exception.code, "network")
        self.assertNotIn(PROBE, str(down.exception))


def _listen() -> ThreadingHTTPServer:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Ark)
    server.bodies = []  # type: ignore[attr-defined]
    server.auth = []  # type: ignore[attr-defined]
    server.mode = "ok"  # type: ignore[attr-defined]
    server.reply = {"items": []}  # type: ignore[attr-defined]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    server.thread = thread  # type: ignore[attr-defined]
    thread.start()
    return server


def _stop(server: ThreadingHTTPServer) -> None:
    server.shutdown()
    server.thread.join(2)  # type: ignore[attr-defined]
    server.server_close()


def _url(server: ThreadingHTTPServer) -> str:
    return "http://127.0.0.1:" + str(server.server_address[1]) + "/v1"
