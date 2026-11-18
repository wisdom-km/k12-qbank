"""Write the OpenAPI document. This does not listen on a port."""

from __future__ import annotations

import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def schema_text() -> str:
    """Return the schema only. The boot line stays on the server, not in this document."""
    with redirect_stdout(io.StringIO()):
        from backend.bootstrap.http_app import create_app

        app = create_app(seed=False, openapi=True)
    return json.dumps(app.openapi(), ensure_ascii=False, indent=2) + "\n"


def main() -> int:
    if len(sys.argv) > 1:
        Path(sys.argv[1]).write_text(schema_text(), encoding="utf-8", newline="\n")
    else:
        sys.stdout.write(schema_text())
    return 0


if __name__ == "__main__":
    sys.exit(main())
