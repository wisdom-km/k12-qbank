"""Signed HTTP client for synthetic tests. Login cookie plus CSRF header."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from fastapi.testclient import TestClient

from backend.bootstrap.compose import Loop
from backend.bootstrap.http_app import create_app
from backend.bootstrap.synthetic import ACTOR_TEACHER_ID, SYNTH_SECRET


class SignedClient:
    def __init__(self, client: TestClient, token: str) -> None:
        self._client = client
        self._token = token
        self.app = client.app

    def get(self, url: str, **kwargs: object) -> object:
        return self._client.get(url, **kwargs)  # type: ignore[arg-type]

    def post(self, url: str, **kwargs: object) -> object:
        headers = dict(kwargs.pop("headers", None) or {})  # type: ignore[arg-type]
        headers.setdefault("X-K12-CSRF", self._token)
        return self._client.post(url, headers=headers, **kwargs)  # type: ignore[arg-type]


@contextmanager
def signed_client(loop: Loop | None = None) -> Iterator[SignedClient]:
    with TestClient(create_app(loop, seed=True)) as client:
        response = client.post("/api/login", json={"username": ACTOR_TEACHER_ID, "secret": SYNTH_SECRET})
        if response.status_code != 200:
            raise AssertionError(response.text)
        yield SignedClient(client, response.json()["csrf_token"])
