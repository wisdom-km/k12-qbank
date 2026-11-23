"""Whether a newly issued paper prints a QR code. Rendering reads the stored flag."""

from __future__ import annotations

import os


def paper_qr_enabled() -> bool:
    """Only the exact value off turns the code off. Empty and anything else stay on."""
    return os.environ.get("K12_PAPER_QR", "on").strip() != "off"
