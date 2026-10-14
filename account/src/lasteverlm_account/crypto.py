"""Voucher codes at rest: AES-GCM under a key that lives only in the environment
(VOUCHER_KEY), so a database leak alone does not yield spendable credit (context/credits.md).
"""

from __future__ import annotations

import base64
import binascii
import secrets

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

KEY_BYTES = 32
NONCE_BYTES = 12


class VoucherKeyError(ValueError):
    """VOUCHER_KEY is missing or not 32 base64-encoded bytes."""


def load_key(encoded: str | None) -> bytes:
    """Standard base64 with padding (``openssl rand -base64 32``); the urlsafe alphabet is
    accepted too. Exactly 32 bytes, anything else refuses to start."""
    raw = (encoded or "").strip()
    if not raw:
        raise VoucherKeyError("VOUCHER_KEY is required: 32 random bytes, base64-encoded")
    try:
        key = base64.b64decode(raw, validate=True)
    except (binascii.Error, ValueError):
        try:
            key = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))
        except (binascii.Error, ValueError) as exc:
            raise VoucherKeyError("VOUCHER_KEY is not base64") from exc
    if len(key) != KEY_BYTES:
        raise VoucherKeyError(f"VOUCHER_KEY must decode to {KEY_BYTES} bytes, got {len(key)}")
    return key


class VoucherCipher:
    def __init__(self, key: bytes) -> None:
        self._aead = AESGCM(key)

    def encrypt(self, code: str) -> str:
        nonce = secrets.token_bytes(NONCE_BYTES)
        sealed = self._aead.encrypt(nonce, code.encode(), None)
        return base64.b64encode(nonce + sealed).decode()

    def decrypt(self, token: str) -> str | None:
        """The code, or None when the token is not ours (another key, a damaged row)."""
        try:
            blob = base64.b64decode(token, validate=True)
            return self._aead.decrypt(blob[:NONCE_BYTES], blob[NONCE_BYTES:], None).decode()
        except (InvalidTag, ValueError, binascii.Error):
            return None
