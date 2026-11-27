"""Shared helpers for the trial backup and restore scripts.

The passphrase is never placed on a command line and never printed.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path
from urllib.parse import unquote, urlsplit


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def database_name(dsn: str) -> str:
    name = urlsplit(dsn).path.lstrip("/").split("/")[0]
    return unquote(name)


def is_dev_database(name: str) -> bool:
    return name.casefold() == "k12"


def split_dsn(dsn: str) -> dict[str, str]:
    parts = urlsplit(dsn)
    if parts.scheme not in {"postgresql", "postgres"}:
        raise RuntimeError("dsn_scheme")
    name = database_name(dsn)
    if not name:
        raise RuntimeError("dsn_name")
    return {
        "user": unquote(parts.username or ""),
        "password": unquote(parts.password or ""),
        "host": parts.hostname or "",
        "port": str(parts.port or 5432),
        "name": name,
    }


def pg_env(base: dict[str, str], fields: dict[str, str]) -> dict[str, str]:
    env = dict(base)
    env["PGHOST"] = fields["host"]
    env["PGPORT"] = fields["port"]
    env["PGUSER"] = fields["user"]
    env["PGDATABASE"] = fields["name"]
    if fields["password"]:
        env["PGPASSWORD"] = fields["password"]
    return env


def which(name: str) -> str:
    """Find name on PATH. Skip the current directory so a local script cannot shadow it."""
    suffixes = [""]
    if os.name == "nt":
        suffixes = os.environ.get("PATHEXT", ".COM;.EXE;.BAT;.CMD").split(";")
    for directory in os.environ.get("PATH", "").split(os.pathsep):
        if not directory:
            continue
        folder = Path(directory)
        for suffix in suffixes:
            candidate = folder / f"{name}{suffix}"
            if candidate.is_file():
                return str(candidate)
    raise RuntimeError(f"{name}_missing")


def with_openssl_conf(env: dict[str, str]) -> dict[str, str]:
    if env.get("OPENSSL_CONF"):
        return env
    try:
        program = which("openssl")
    except RuntimeError:
        return env
    candidate = Path(program).resolve().parent.parent / "ssl" / "openssl.cnf"
    if not candidate.is_file():
        return env
    copied = dict(env)
    copied["OPENSSL_CONF"] = str(candidate)
    return copied


def run(
    argv: list[str],
    env: dict[str, str],
    input_bytes: bytes | None = None,
) -> subprocess.CompletedProcess[bytes]:
    program = argv[0]
    if os.name == "nt" and program.lower().endswith((".cmd", ".bat")):
        argv = ["cmd.exe", "/d", "/c", subprocess.list2cmdline(argv)]
    return subprocess.run(
        argv,
        env=env,
        input=input_bytes,
        capture_output=True,
        check=False,
    )


def redact(text: str, secrets: list[str]) -> str:
    cleaned = text
    for secret in secrets:
        if secret:
            cleaned = cleaned.replace(secret, "[redacted]")
    return cleaned


def passphrase() -> str:
    return os.environ.get("K12_BACKUP_PASSPHRASE", "")


def openssl_convert(source: Path, dest: Path, *, decrypt: bool) -> None:
    """AES-256-CBC with PBKDF2. The passphrase stays in the child environment."""
    secret = passphrase()
    if not secret:
        raise RuntimeError("passphrase_missing")
    argv = [
        which("openssl"),
        "enc",
        "-aes-256-cbc",
        "-pbkdf2",
        "-salt",
        "-pass",
        "env:K12_BACKUP_PASSPHRASE",
        "-in",
        str(source),
        "-out",
        str(dest),
    ]
    if decrypt:
        argv.insert(2, "-d")
    child = with_openssl_conf(dict(os.environ))
    child["K12_BACKUP_PASSPHRASE"] = secret
    completed = run(argv, child)
    if completed.returncode != 0 or (decrypt and not dest.is_file()):
        detail = redact(completed.stderr.decode("utf-8", errors="replace"), [secret])
        dest.unlink(missing_ok=True)
        raise RuntimeError(detail.strip() or "openssl_failed")
    if decrypt and not dest.read_bytes().startswith(b"\x1f\x8b"):
        dest.unlink(missing_ok=True)
        raise RuntimeError("decrypt_failed")


def safe_relative(value: str) -> Path:
    if not value or value.startswith(("/", "\\")) or ":" in value:
        raise RuntimeError("unsafe_path")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise RuntimeError("unsafe_path")
    return path
