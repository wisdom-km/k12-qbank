"""argon2id parameters stay fixed, and a weaker hash asks to be rewritten."""

from __future__ import annotations

import unittest

from argon2 import PasswordHasher
from argon2.low_level import Type

from backend.identity.adapters.argon2_hasher import Argon2Hasher

SECRET = "admin-pass1"


class Argon2HasherTest(unittest.TestCase):
    def test_verify_and_reject(self) -> None:
        hasher = Argon2Hasher()
        stored = hasher.hash(SECRET)
        self.assertTrue(hasher.verify(SECRET, stored))
        self.assertFalse(hasher.verify("wrong-pass1", stored))
        self.assertFalse(hasher.verify(SECRET, "not-a-hash"))
        self.assertFalse(hasher.needs_rehash(stored))

    def test_weaker_parameters_need_rehash(self) -> None:
        other = PasswordHasher(
            time_cost=2,
            memory_cost=65536,
            parallelism=2,
            hash_len=32,
            salt_len=16,
            type=Type.ID,
        )
        stored = other.hash(SECRET)
        hasher = Argon2Hasher()
        self.assertTrue(hasher.needs_rehash(stored))
        self.assertTrue(hasher.verify(SECRET, stored))
