"""Baca/tulis file vault terenkripsi secara atomic (tulis sementara → fsync → rename)."""

import os
import struct
from pathlib import Path

from crypto import cipher

MAGIC = b"T2PV"
FORMAT_VERSION = 1
KDF_ID_ARGON2ID = 1

# magic, format_version, kdf_id, memory_kib, time_cost, parallelism, salt, nonce
HEADER_FORMAT = ">4sBBIBB16s12s"
HEADER_LEN = struct.calcsize(HEADER_FORMAT)

DEFAULT_MEMORY_KIB = 256 * 1024
DEFAULT_TIME_COST = 3
DEFAULT_PARALLELISM = 1


def pack_header(salt: bytes, nonce: bytes, memory_kib: int, time_cost: int, parallelism: int) -> bytes:
    return struct.pack(HEADER_FORMAT, MAGIC, FORMAT_VERSION, KDF_ID_ARGON2ID, memory_kib, time_cost, parallelism, salt, nonce)


def read_header(path) -> dict:
    with open(path, "rb") as f:
        raw = f.read(HEADER_LEN)
    if len(raw) != HEADER_LEN:
        raise ValueError("file vault terlalu pendek / rusak")
    magic, version, kdf_id, memory_kib, time_cost, parallelism, salt, nonce = struct.unpack(HEADER_FORMAT, raw)
    if magic != MAGIC:
        raise ValueError("bukan file vault Trust2Pass (magic tidak cocok)")
    if version != FORMAT_VERSION:
        raise ValueError(f"format_version {version} tidak didukung")
    if kdf_id != KDF_ID_ARGON2ID:
        raise ValueError(f"kdf_id {kdf_id} tidak dikenal")
    return {
        "memory_kib": memory_kib,
        "time_cost": time_cost,
        "parallelism": parallelism,
        "salt": salt,
        "nonce": nonce,
        "header_bytes": raw,
    }


def open_vault(path, key: bytes) -> bytes:
    """Decrypt payload. Kalau header invalid atau auth tag gagal, vault ditolak total - tidak ada baca sebagian."""
    header = read_header(path)
    with open(path, "rb") as f:
        f.seek(HEADER_LEN)
        ciphertext = f.read()
    return cipher.decrypt(key, header["nonce"], ciphertext, header["header_bytes"])


def write_vault(
    path,
    key: bytes,
    plaintext: bytes,
    salt: bytes,
    memory_kib: int = DEFAULT_MEMORY_KIB,
    time_cost: int = DEFAULT_TIME_COST,
    parallelism: int = DEFAULT_PARALLELISM,
) -> None:
    """Enkripsi lalu tulis vault secara atomic (tulis ke file sementara -> fsync -> rename)."""
    nonce = cipher.generate_nonce()
    header_bytes = pack_header(salt, nonce, memory_kib, time_cost, parallelism)
    ciphertext = cipher.encrypt(key, nonce, plaintext, header_bytes)

    path = Path(path)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with open(tmp_path, "wb") as f:
        f.write(header_bytes)
        f.write(ciphertext)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_path, path)


if __name__ == "__main__":
    import secrets
    import tempfile

    from crypto import kdf

    password = b"correct horse battery staple"
    plaintext = b'[{"site": "example.com", "username": "neo", "password": "hunter2"}]'
    salt = kdf.generate_salt()
    key = kdf.derive_key(password, salt, kdf.MIN_MEMORY_KIB, kdf.MIN_TIME_COST, kdf.MIN_PARALLELISM)

    with tempfile.TemporaryDirectory() as tmpdir:
        vault_path = Path(tmpdir) / "test.t2p"

        write_vault(vault_path, key, plaintext, salt, kdf.MIN_MEMORY_KIB, kdf.MIN_TIME_COST, kdf.MIN_PARALLELISM)
        assert open_vault(vault_path, key) == plaintext

        header = read_header(vault_path)
        assert header["salt"] == salt
        assert header["memory_kib"] == kdf.MIN_MEMORY_KIB

        # Header di-tamper (mis. downgrade memory_kib) -> harus reject.
        raw = bytearray(vault_path.read_bytes())
        raw[8] ^= 0xFF  # salah satu byte field memory_kib -> ubah nilainya
        tampered_path = Path(tmpdir) / "tampered.t2p"
        tampered_path.write_bytes(bytes(raw))
        try:
            open_vault(tampered_path, key)
            raise AssertionError("harusnya reject header yang di-tamper")
        except Exception as e:
            assert "Tag" in type(e).__name__ or "InvalidTag" in str(type(e))

        # Ciphertext di-tamper -> harus reject.
        raw2 = bytearray(vault_path.read_bytes())
        raw2[-1] ^= 0xFF
        tampered_path2 = Path(tmpdir) / "tampered2.t2p"
        tampered_path2.write_bytes(bytes(raw2))
        try:
            open_vault(tampered_path2, key)
            raise AssertionError("harusnya reject ciphertext yang di-tamper")
        except Exception as e:
            assert "Tag" in type(e).__name__

        # Key salah -> reject.
        try:
            open_vault(vault_path, secrets.token_bytes(32))
            raise AssertionError("harusnya reject key yang salah")
        except Exception as e:
            assert "Tag" in type(e).__name__

        # Bukan file vault sama sekali -> reject dengan pesan jelas, bukan exception kriptik.
        junk_path = Path(tmpdir) / "junk.t2p"
        junk_path.write_bytes(b"not a vault file at all")
        try:
            read_header(junk_path)
            raise AssertionError("harusnya reject file yang bukan vault")
        except ValueError:
            pass

    print("storage.py self-check OK")
