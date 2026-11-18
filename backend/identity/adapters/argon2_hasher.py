"""argon2id with the parameters fixed in ADR 0027."""

from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from argon2.low_level import Type

_HASHER = PasswordHasher(
    time_cost=3,
    memory_cost=65536,
    parallelism=2,
    hash_len=32,
    salt_len=16,
    type=Type.ID,
)


class Argon2Hasher:
    def hash(self, secret: str) -> str:
        return _HASHER.hash(secret)

    def verify(self, secret: str, stored: str) -> bool:
        try:
            return bool(_HASHER.verify(stored, secret))
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            return False

    def needs_rehash(self, stored: str) -> bool:
        return bool(_HASHER.check_needs_rehash(stored))
