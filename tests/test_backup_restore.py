"""Joint backup and restore using temporary directories and fake database tools."""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKUP = ROOT / "scripts" / "backup_trial.py"
RESTORE = ROOT / "scripts" / "restore_trial.py"
CERT = ROOT / "scripts" / "make_trial_cert.py"
DSN = "postgresql://k12:synth-pw@127.0.0.1:9/k12_trial"
DEV_DSN = "postgresql://k12:synth-pw@127.0.0.1:9/k12"
PHRASE = "synth-passphrase"


def _write_cmd(directory: Path, name: str, script: Path) -> None:
    if os.name == "nt":
        path = directory / f"{name}.cmd"
        path.write_text(f'@echo off\r\n"{sys.executable}" "{script}" %*\r\n', encoding="utf-8")
        return
    path = directory / name
    path.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{script}" "$@"\n', encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


class BackupRestoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="k12-r9-")
        self.root = Path(self._tmp.name)
        self.files = self.root / "files"
        self.out = self.root / "out"
        self.target = self.root / "target"
        self.bin = self.root / "bin"
        self.files.mkdir()
        self.out.mkdir()
        self.target.mkdir()
        self.bin.mkdir()
        nested = self.files / "synth-dir"
        nested.mkdir()
        (nested / "note.txt").write_bytes(b"synth-bytes")
        self.argv_log = self.root / "argv.txt"
        self.psql_sink = self.root / "psql-sink.bin"
        dump_py = self.bin / "dump_tool.py"
        dump_py.write_text(
            "import os, sys\n"
            "from pathlib import Path\n"
            "log = os.environ.get('K12_TEST_ARGV_LOG', '')\n"
            "if log:\n"
            "    Path(log).write_text('\\n'.join(sys.argv), encoding='utf-8')\n"
            "sys.stdout.buffer.write(b'synth-dump-v1\\n')\n",
            encoding="utf-8",
        )
        psql_py = self.bin / "psql_tool.py"
        psql_py.write_text(
            "import os, sys\n"
            "from pathlib import Path\n"
            "sink = os.environ.get('K12_TEST_PSQL_SINK', '')\n"
            "data = sys.stdin.buffer.read()\n"
            "if sink:\n"
            "    Path(sink).write_bytes(data)\n",
            encoding="utf-8",
        )
        _write_cmd(self.bin, "pg_dump", dump_py)
        _write_cmd(self.bin, "psql", psql_py)
        self.openssl = shutil.which("openssl")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _env(self, **extra: str) -> dict[str, str]:
        env = os.environ.copy()
        env["PATH"] = str(self.bin) + os.pathsep + env.get("PATH", "")
        env["K12_PG_DSN"] = DSN
        env["K12_FILE_DIR"] = str(self.files)
        env["K12_TEST_ARGV_LOG"] = str(self.argv_log)
        env["K12_TEST_PSQL_SINK"] = str(self.psql_sink)
        env.pop("K12_BACKUP_PASSPHRASE", None)
        env.update(extra)
        return env

    def _run(self, script: Path, args: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(script), *args],
            cwd=self.root,
            env=env,
            text=True,
            capture_output=True,
            stdin=subprocess.DEVNULL,
            check=False,
        )

    def _backup(self, *args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        return self._run(BACKUP, ["--out-dir", str(self.out), *args], env or self._env())

    def _one_archive(self) -> Path:
        found = [path for path in self.out.iterdir() if path.is_file()]
        self.assertEqual(len(found), 1, [path.name for path in found])
        return found[0]

    def test_joint_backup_writes_dump_files_and_manifest(self) -> None:
        completed = self._backup("--no-encrypt")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertNotIn("synth-pw", completed.stdout)
        self.assertNotIn("synth-pw", completed.stderr)
        archive = self._one_archive()
        logged = self.argv_log.read_text(encoding="utf-8")
        self.assertNotIn("synth-pw", logged)
        with tarfile.open(archive, "r:gz") as packed:
            packed.extractall(self.root / "unpacked", filter="data")
        bundle = self.root / "unpacked"
        self.assertEqual((bundle / "db.sql").read_bytes(), b"synth-dump-v1\n")
        self.assertEqual((bundle / "files" / "synth-dir" / "note.txt").read_bytes(), b"synth-bytes")
        manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["schema_version"], 1)
        self.assertEqual(manifest["file_count"], 1)
        self.assertEqual(manifest["files"][0]["path"], "synth-dir/note.txt")
        self.assertNotIn("synth-pw", json.dumps(manifest))
        import hashlib

        digest = hashlib.sha256(b"synth-bytes").hexdigest()
        self.assertEqual(manifest["files"][0]["sha256"], digest)
        self.assertEqual(manifest["database_sha256"], hashlib.sha256(b"synth-dump-v1\n").hexdigest())

        restored = self._run(
            RESTORE,
            [str(archive)],
            self._env(K12_FILE_DIR=str(self.target)),
        )
        self.assertEqual(restored.returncode, 0, restored.stderr)
        self.assertIn("RESTORED database=k12_trial files=1", restored.stdout)
        self.assertEqual((self.target / "synth-dir" / "note.txt").read_bytes(), b"synth-bytes")
        self.assertEqual(self.psql_sink.read_bytes(), b"synth-dump-v1\n")

    def test_tamper_fails_with_zero_writes(self) -> None:
        completed = self._backup("--no-encrypt")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        archive = self._one_archive()
        unpacked = self.root / "tamper"
        with tarfile.open(archive, "r:gz") as packed:
            packed.extractall(unpacked, filter="data")
        note = unpacked / "files" / "synth-dir" / "note.txt"
        note.write_bytes(b"synth-tampered")
        tampered = self.root / "tampered.tar.gz"
        with tarfile.open(tampered, "w:gz") as packed:
            for path in unpacked.rglob("*"):
                if path.is_file():
                    packed.add(path, arcname=path.relative_to(unpacked).as_posix())
        sentinel = self.target / "keep.txt"
        sentinel.write_text("keep", encoding="utf-8")
        restored = self._run(RESTORE, [str(tampered)], self._env(K12_FILE_DIR=str(self.target)))
        self.assertNotEqual(restored.returncode, 0)
        self.assertIn("hash mismatch", restored.stderr)
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep")
        self.assertFalse((self.target / "synth-dir").exists())
        self.assertFalse(self.psql_sink.exists())

    def test_encrypt_requires_passphrase(self) -> None:
        completed = self._backup()
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("K12_BACKUP_PASSPHRASE", completed.stderr)
        self.assertEqual(list(self.out.iterdir()), [])

    def test_encrypt_round_trip_and_wrong_passphrase(self) -> None:
        if not self.openssl:
            self.skipTest("openssl is not installed")
        wrap = self.bin / "openssl_tool.py"
        wrap.write_text(
            "import os, sys, subprocess\n"
            "from pathlib import Path\n"
            "Path(os.environ['K12_TEST_OPENSSL_ARGV']).write_text('\\n'.join(sys.argv[1:]), encoding='utf-8')\n"
            "raise SystemExit(subprocess.call([os.environ['K12_TEST_OPENSSL_REAL'], *sys.argv[1:]]))\n",
            encoding="utf-8",
        )
        _write_cmd(self.bin, "openssl", wrap)
        argv_file = self.root / "openssl-argv.txt"
        env = self._env(
            K12_BACKUP_PASSPHRASE=PHRASE,
            K12_TEST_OPENSSL_ARGV=str(argv_file),
            K12_TEST_OPENSSL_REAL=self.openssl,
        )
        completed = self._backup(env=env)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        archive = self._one_archive()
        self.assertTrue(archive.name.endswith(".tar.gz.enc"))
        self.assertNotIn(PHRASE, completed.stdout)
        self.assertNotIn(PHRASE, completed.stderr)
        logged = argv_file.read_text(encoding="utf-8")
        self.assertIn("env:K12_BACKUP_PASSPHRASE", logged)
        self.assertNotIn(PHRASE, logged)
        verified = self._run(RESTORE, [str(archive), "--verify-only"], env)
        self.assertEqual(verified.returncode, 0, verified.stderr)
        self.assertIn("VERIFIED files=1", verified.stdout)
        self.assertFalse(self.psql_sink.exists())
        self.assertEqual(list(self.target.iterdir()), [])
        wrong = self._run(
            RESTORE,
            [str(archive), "--verify-only"],
            self._env(
                K12_BACKUP_PASSPHRASE="synth-wrong",
                K12_TEST_OPENSSL_ARGV=str(argv_file),
                K12_TEST_OPENSSL_REAL=self.openssl,
            ),
        )
        self.assertNotEqual(wrong.returncode, 0)
        self.assertFalse(self.psql_sink.exists())

    def test_restore_refuses_database_k12(self) -> None:
        completed = self._backup("--no-encrypt")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        archive = self._one_archive()
        sentinel = self.target / "keep.txt"
        sentinel.write_text("keep", encoding="utf-8")
        restored = self._run(
            RESTORE,
            [str(archive)],
            self._env(K12_PG_DSN=DEV_DSN, K12_FILE_DIR=str(self.target)),
        )
        self.assertNotEqual(restored.returncode, 0)
        self.assertIn("database k12", restored.stderr)
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep")
        self.assertFalse(self.psql_sink.exists())

    def test_make_trial_cert_refuses_tracked_directory(self) -> None:
        out = ROOT / "docker" / "r9-cert-should-not-exist"
        completed = self._run(
            CERT,
            ["--hosts", "localhost,127.0.0.1", "--out-dir", str(out)],
            self._env(),
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("refusing", completed.stderr)
        self.assertFalse(out.exists())
        if not self.openssl:
            return
        generated = self.root / "certs"
        made = self._run(
            CERT,
            ["--hosts", "localhost,127.0.0.1", "--out-dir", str(generated)],
            self._env(),
        )
        self.assertEqual(made.returncode, 0, made.stderr)
        self.assertNotIn("PRIVATE KEY", made.stdout)
        self.assertNotIn("PRIVATE KEY", made.stderr)
        self.assertTrue((generated / "server.crt").is_file())
        self.assertTrue((generated / "server.key").is_file())
        kept = self._run(
            CERT,
            ["--hosts", "localhost", "--out-dir", str(generated)],
            self._env(),
        )
        self.assertEqual(kept.returncode, 0, kept.stderr)
        self.assertIn("already exists", kept.stdout)


if __name__ == "__main__":
    unittest.main()
