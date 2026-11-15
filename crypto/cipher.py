"""Enkripsi/dekripsi vault dengan AES-256-GCM (AEAD).

Nonce 12 byte unik per operasi enkripsi; header vault di-bind sebagai AAD.
"""

import secrets

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

KEY_LEN = 32
NONCE_LEN = 12


def generate_nonce() -> bytes:
    return secrets.token_bytes(NONCE_LEN)


def encrypt(key: bytes, nonce: bytes, plaintext: bytes, aad: bytes) -> bytes:
    """Return ciphertext+tag. `aad` (header vault) ikut diautentikasi tapi tidak dienkripsi."""
    if len(key) != KEY_LEN:
        raise ValueError(f"key harus {KEY_LEN} byte, dapat {len(key)}")
    if len(nonce) != NONCE_LEN:
        raise ValueError(f"nonce harus {NONCE_LEN} byte, dapat {len(nonce)}")
    return AESGCM(key).encrypt(nonce, plaintext, aad)


def decrypt(key: bytes, nonce: bytes, ciphertext: bytes, aad: bytes) -> bytes:
    """Raise InvalidTag kalau ciphertext/aad dimanipulasi atau key salah - vault harus ditolak, bukan dibaca sebagian."""
    if len(key) != KEY_LEN:
        raise ValueError(f"key harus {KEY_LEN} byte, dapat {len(key)}")
    if len(nonce) != NONCE_LEN:
        raise ValueError(f"nonce harus {NONCE_LEN} byte, dapat {len(nonce)}")
    return AESGCM(key).decrypt(nonce, ciphertext, aad)


if __name__ == "__main__":
    key = secrets.token_bytes(KEY_LEN)
    nonce = generate_nonce()
    header = b"T2PV\x01header-stuff"
    plaintext = b'[{"site": "example.com", "password": "hunter2"}]'

    ct = encrypt(key, nonce, plaintext, header)
    assert decrypt(key, nonce, ct, header) == plaintext

    # Ciphertext di-tamper -> harus reject, bukan baca sebagian.
    tampered = bytearray(ct)
    tampered[0] ^= 0xFF
    try:
        decrypt(key, nonce, bytes(tampered), header)
        raise AssertionError("harusnya reject ciphertext yang di-tamper")
    except InvalidTag:
        pass

    # Header (AAD) di-tamper -> harus reject juga (downgrade parameter KDF, dsb).
    try:
        decrypt(key, nonce, ct, header + b"x")
        raise AssertionError("harusnya reject AAD yang di-tamper")
    except InvalidTag:
        pass

    # Key salah -> reject.
    try:
        decrypt(secrets.token_bytes(KEY_LEN), nonce, ct, header)
        raise AssertionError("harusnya reject key yang salah")
    except InvalidTag:
        pass

    # Dua nonce berbeda untuk key yang sama -> ciphertext beda (sanity check generate_nonce).
    assert generate_nonce() != generate_nonce()

    print("cipher.py self-check OK")
