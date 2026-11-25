"""Write a trial self-signed certificate. The private key is never printed.

Existing server.crt and server.key are kept unless --force is passed.
The output directory cannot be a tracked project directory.
"""

from __future__ import annotations

import argparse
import ipaddress
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.trial_bundle import with_openssl_conf  # noqa: E402

_ALLOWED = {"var"}


def _refused(out: Path) -> str | None:
    try:
        relative = out.resolve().relative_to(ROOT.resolve())
    except ValueError:
        return None
    if not relative.parts or relative.parts[0] not in _ALLOWED:
        return relative.parts[0] if relative.parts else "repository root"
    return None


def _san(host: str) -> str:
    try:
        ipaddress.ip_address(host)
    except ValueError:
        if not host or any(char in host for char in " /\\$\"'`"):
            raise RuntimeError("bad_host")
        return f"DNS:{host}"
    return f"IP:{host}"


def _openssl() -> str | None:
    return shutil.which("openssl")


def _docker_hint(out: Path, san: str) -> str:
    return (
        "openssl was not found. Install it, or rerun with --via-docker. "
        "Example: docker run --rm -v "
        f'"{out.resolve()}:/certs" -w /certs alpine:3.20 '
        "sh -c \"apk add --no-cache openssl >/dev/null && "
        "openssl req -x509 -newkey rsa:2048 -sha256 -days 825 -nodes "
        "-keyout server.key -out server.crt -subj /CN=k12-trial "
        f"-addext subjectAltName={san}\""
    )


def _run_local(out: Path, san: str) -> int:
    program = _openssl()
    if not program:
        print(_docker_hint(out, san), file=sys.stderr)
        return 2
    completed = subprocess.run(
        [
            program,
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-sha256",
            "-days",
            "825",
            "-nodes",
            "-keyout",
            str(out / "server.key"),
            "-out",
            str(out / "server.crt"),
            "-subj",
            "/CN=k12-trial",
            "-addext",
            f"subjectAltName={san}",
        ],
        capture_output=True,
        check=False,
        env=with_openssl_conf(os.environ.copy()),
    )
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace")
        if "PRIVATE KEY" in detail:
            detail = "openssl_failed"
        print(detail.strip() or "openssl_failed", file=sys.stderr)
        return 1
    return 0


def _run_docker(out: Path, san: str) -> int:
    if not shutil.which("docker"):
        print("docker was not found", file=sys.stderr)
        return 2
    script = (
        "apk add --no-cache openssl >/dev/null && "
        "openssl req -x509 -newkey rsa:2048 -sha256 -days 825 -nodes "
        "-keyout server.key -out server.crt -subj /CN=k12-trial "
        f"-addext subjectAltName={san}"
    )
    completed = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{out.resolve()}:/certs",
            "-w",
            "/certs",
            "alpine:3.20",
            "sh",
            "-c",
            script,
        ],
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        print("docker openssl failed", file=sys.stderr)
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create the trial self-signed certificate.")
    parser.add_argument("--hosts", required=True, help="Comma-separated DNS names and IP addresses")
    parser.add_argument("--out-dir", default="var/certs")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--via-docker", action="store_true")
    args = parser.parse_args(argv)
    out = Path(args.out_dir)
    refused = _refused(out)
    if refused is not None:
        print(f"refusing to write a certificate under {refused}", file=sys.stderr)
        return 2
    hosts = [part.strip() for part in args.hosts.split(",") if part.strip()]
    if not hosts:
        print("--hosts is required", file=sys.stderr)
        return 2
    try:
        san = ",".join(_san(host) for host in hosts)
    except RuntimeError:
        print("--hosts has an invalid name", file=sys.stderr)
        return 2
    out.mkdir(parents=True, exist_ok=True)
    key = out / "server.key"
    crt = out / "server.crt"
    if key.exists() or crt.exists():
        if not args.force:
            print("certificate already exists; pass --force to replace")
            return 0
        key.unlink(missing_ok=True)
        crt.unlink(missing_ok=True)
    code = _run_docker(out, san) if args.via_docker else _run_local(out, san)
    if code != 0:
        key.unlink(missing_ok=True)
        crt.unlink(missing_ok=True)
        return code
    print(f"certificate written to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
