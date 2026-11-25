"""Static checks for the trial image, compose file, nginx, and env template."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

_AI = (
    "K12_AI_PROVIDER",
    "K12_AI_BASE_URL",
    "K12_AI_MODEL",
    "K12_AI_API_KEY",
    "K12_AI_TIMEOUT_SECONDS",
    "K12_AI_DAILY_LIMIT",
    "K12_AI_REVIEW_THRESHOLD",
)

_SECRET_KEYS = ("PASSWORD", "SECRET", "API_KEY", "PASSPHRASE")


def _text(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


class TrialDeployConfigTest(unittest.TestCase):
    def test_compose_forces_production_and_hides_host_ports(self) -> None:
        text = _text("docker/compose.trial.yml")
        self.assertIn("K12_ENV: production", text)
        self.assertIn('K12_SESSION_SECURE: "1"', text)
        self.assertIn('K12_OPENAPI: "0"', text)
        self.assertNotIn("5432:5432", text)
        self.assertNotIn("8765:8765", text)
        self.assertIsNone(re.search(r"""(?m)^\s+-\s+["']?\d+:(5432|8765)\b""", text))
        self.assertIn('"${K12_HTTPS_PORT:-8443}:443"', text)

    def test_compose_has_no_latest_and_no_hardcoded_secret(self) -> None:
        text = _text("docker/compose.trial.yml")
        self.assertNotIn(":latest", text)
        self.assertNotIn("changeme", text)
        self.assertNotIn("sk-", text)
        self.assertIn("postgres:16-alpine", text)
        self.assertIn("nginx:1.27-alpine", text)
        self.assertIn("POSTGRES_PASSWORD: ${K12_PG_PASSWORD:?}", text)

    def test_compose_lists_r6_ai_variables(self) -> None:
        text = _text("docker/compose.trial.yml")
        for name in _AI:
            self.assertIn(name, text)

    def test_nginx_tls_body_and_forwarded_proto(self) -> None:
        text = _text("docker/nginx.conf")
        self.assertIn("TLSv1.2", text)
        self.assertIn("TLSv1.3", text)
        self.assertIn("client_max_body_size 15m;", text)
        self.assertIn("X-Forwarded-Proto https", text)
        self.assertIn("Strict-Transport-Security", text)
        self.assertIn("proxy_pass http://app:8765;", text)

    def test_dockerfile_fonts_health_and_non_root(self) -> None:
        text = _text("docker/Dockerfile")
        self.assertIn("node:22-alpine", text)
        self.assertIn("python:3.12-slim", text)
        self.assertIn("fonts-noto-cjk", text)
        self.assertIn("NotoSansCJK-Regular.ttc", text)
        self.assertIn("HEALTHCHECK", text)
        self.assertIn("http://127.0.0.1:8765/health", text)
        self.assertIn("USER k12", text)
        self.assertNotIn(":latest", text)

    def test_trial_env_secrets_are_blank(self) -> None:
        text = _text(".env.trial.example")
        self.assertNotIn("changeme", text)
        self.assertNotIn("sk-", text)
        for name in _AI:
            self.assertIn(name, text)
        self.assertIn("K12_INTAKE_RETENTION_DAYS=30", text)
        self.assertIn("K12_CORS_ORIGINS=", text)
        self.assertIn("K12_CERT_DIR=../var/certs", text)
        for line in text.splitlines():
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            if any(part in key for part in _SECRET_KEYS):
                self.assertTrue(value == "" or value.startswith("<"), key)

    def test_env_example_names_the_shipped_variables(self) -> None:
        text = _text(".env.example")
        self.assertIn("K12_CORS_ORIGINS=", text)
        self.assertIn("K12_INTAKE_RETENTION_DAYS=30", text)
        self.assertNotIn("stay unbuilt", text)

    def test_gitignore_ignores_trial_secrets(self) -> None:
        text = _text(".gitignore")
        self.assertIn(".env.trial", text)
        self.assertIn("!.env.trial.example", text)
        self.assertIn("var/certs/", text)
        self.assertIn("var/backups/", text)

    def test_dev_compose_is_still_the_local_database(self) -> None:
        text = _text("docker/compose.yml")
        self.assertIn("5432:5432", text)
        self.assertIn("postgres:16", text)
        self.assertNotIn("nginx", text)

    def test_dockerignore_skips_secrets_and_build_output(self) -> None:
        text = _text(".dockerignore")
        for line in (".git", "var", ".env", "apps/web/node_modules", "apps/web/dist", "__pycache__"):
            self.assertIn(line, text)


if __name__ == "__main__":
    unittest.main()
