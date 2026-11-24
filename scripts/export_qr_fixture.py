"""Write the synth QR matrix used by the browser tests.

Run this script to refresh apps/web/tests/fixtures/qr_synth.json.
Do not edit that file by hand.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.practice.domain.qr_code import encode_qr, qr_payload  # noqa: E402

PAYLOAD = qr_payload("a" * 32, 1)
OUT = ROOT / "apps" / "web" / "tests" / "fixtures" / "qr_synth.json"


def main() -> int:
    modules = encode_qr(PAYLOAD)
    body = {
        "payload": PAYLOAD,
        "modules": [[int(cell) for cell in row] for row in modules],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(body, separators=(",", ":")) + "\n", encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
