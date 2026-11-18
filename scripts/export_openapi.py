"""Write the OpenAPI document. This does not listen on a port."""

from __future__ import annotations

import io
import json
import os
import sys
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_PATH = ROOT / "apps" / "web" / "src" / "api.openapi.json"


def schema_text() -> str:
    """Return the schema only. The boot line stays on the server, not in this document."""
    previous = os.environ.get("K12_OPENAPI")
    os.environ["K12_OPENAPI"] = "1"
    try:
        with redirect_stdout(io.StringIO()):
            from backend.bootstrap.http_app import create_app

            app = create_app(seed=False, openapi=True)
    finally:
        if previous is None:
            os.environ.pop("K12_OPENAPI", None)
        else:
            os.environ["K12_OPENAPI"] = previous
    return json.dumps(app.openapi(), ensure_ascii=False, indent=2) + "\n"


def main() -> int:
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PATH
    target.write_text(schema_text(), encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
