"""Admin gate. Teachers do not run admin use cases."""

from __future__ import annotations

from backend.kernel.result import Err


def admin_only(actor: object | None) -> Err | None:
    if actor is None or getattr(actor, "role", "") != "admin":
        return Err("permission_denied", "permission_denied")
    return None


def signed_in(actor: object | None) -> Err | None:
    if actor is None or getattr(actor, "role", "") not in {"admin", "teacher"}:
        return Err("permission_denied", "permission_denied")
    return None
