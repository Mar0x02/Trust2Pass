"""Enkripsi lapis kedua (per-entri) untuk field password saat MFA gating aktif.

InnerKey diturunkan dari Master Key via HKDF, BUKAN dari kode TOTP - kode TOTP cuma 6 digit
dan berganti tiap 30 detik, jadi gak bisa dipakai sebagai AES key yang stabil (field yang
dienkripsi hari ini harus tetap bisa didekripsi besok). TOTP cuma gerbang (lihat
vault/manager.py reveal_password), bukan bahan kunci.

Catatan jujur: ini mitigasi window-exposure di memori (mis. RAM scraper), bukan root-of-trust
kriptografis baru - penyerang yang sudah punya Master Key + dump vault penuh tetap bisa
dekripsi InnerKey ini sendiri (sama seperti dia bisa dekripsi vault itu sendiri).
"""

import base64

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from crypto import cipher

INNER_KEY_LEN = 32
_INFO_PREFIX = b"trust2pass-entry-secret:"


def derive_inner_key(master_key: bytes, entry_id: str) -> bytes:
    return HKDF(
        algorithm=hashes.SHA256(), length=INNER_KEY_LEN, salt=None,
        info=_INFO_PREFIX + entry_id.encode("utf-8"),
    ).derive(master_key)


def seal(master_key: bytes, entry_id: str, plaintext: str) -> str:
    """Enkripsi password jadi ciphertext base64, siap disimpan di Entry.password."""
    inner_key = derive_inner_key(master_key, entry_id)
    nonce = cipher.generate_nonce()
    ct = cipher.encrypt(inner_key, nonce, plaintext.encode("utf-8"), entry_id.encode("utf-8"))
    return base64.b64encode(nonce + ct).decode("ascii")


def unseal(master_key: bytes, entry_id: str, sealed: str) -> str:
    """Dekripsi balik. Raise InvalidTag kalau ciphertext rusak/di-tamper atau key salah."""
    inner_key = derive_inner_key(master_key, entry_id)
    raw = base64.b64decode(sealed)
    nonce, ct = raw[: cipher.NONCE_LEN], raw[cipher.NONCE_LEN :]
    return cipher.decrypt(inner_key, nonce, ct, entry_id.encode("utf-8")).decode("utf-8")


if __name__ == "__main__":
    import secrets

    from cryptography.exceptions import InvalidTag

    master_key = secrets.token_bytes(32)
    entry_id = "entry-123"

    sealed = seal(master_key, entry_id, "hunter2")
    assert sealed != "hunter2"  # beneran ciphertext, bukan plaintext apa adanya
    assert unseal(master_key, entry_id, sealed) == "hunter2"

    # Dua kali seal password sama -> ciphertext beda (nonce acak tiap kali).
    assert seal(master_key, entry_id, "hunter2") != sealed

    # InnerKey per-entri beda - ciphertext entri A gak bisa didekripsi pakai id entri B.
    try:
        unseal(master_key, "entry-456", sealed)
        raise AssertionError("harusnya reject - AAD (entry_id) gak cocok")
    except InvalidTag:
        pass

    # Master Key salah -> reject.
    try:
        unseal(secrets.token_bytes(32), entry_id, sealed)
        raise AssertionError("harusnya reject - master key salah")
    except InvalidTag:
        pass

    print("entry_secret.py self-check OK")
