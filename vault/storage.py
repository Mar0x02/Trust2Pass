"""Baca/tulis file vault terenkripsi secara atomic (tulis sementara → fsync → rename)."""

import os
import struct
from pathlib import Path

from crypto import cipher

MAGIC = b"T2PV"
FORMAT_VERSION = 2
KDF_ID_ARGON2ID = 1

# `kind` nandain asal file ini - vault biasa, atau hasil fitur Export (lihat vault/manager.py,
# ui/main_window.py _on_import) - plaintext di header, sama kayak salt/parameter KDF, BUKAN
# rahasia dan TIDAK menggantikan otentikasi AEAD (tetep ke-cover AAD, jadi gak bisa di-tamper
# diam-diam buat nyamar jadi "hasil export").
KIND_VAULT = 1
KIND_EXPORT = 2

_PREFIX_FORMAT = ">4sB"  # magic, format_version
_PREFIX_LEN = struct.calcsize(_PREFIX_FORMAT)

# v1 (format lama, sebelum fitur export ada): kdf_id, memory_kib, time_cost, parallelism, salt, nonce
_BODY_FORMAT_V1 = ">BIBB16s12s"
# v2: sama kayak v1, cuma nambah 1 byte `kind` di depan kdf_id.
_BODY_FORMAT_V2 = ">BBIBB16s12s"

HEADER_LEN_V1 = _PREFIX_LEN + struct.calcsize(_BODY_FORMAT_V1)
HEADER_LEN_V2 = _PREFIX_LEN + struct.calcsize(_BODY_FORMAT_V2)

DEFAULT_MEMORY_KIB = 256 * 1024
DEFAULT_TIME_COST = 3
DEFAULT_PARALLELISM = 1


def pack_header(
    salt: bytes, nonce: bytes, memory_kib: int, time_cost: int, parallelism: int, kind: int = KIND_VAULT
) -> bytes:
    prefix = struct.pack(_PREFIX_FORMAT, MAGIC, FORMAT_VERSION)
    body = struct.pack(_BODY_FORMAT_V2, kind, KDF_ID_ARGON2ID, memory_kib, time_cost, parallelism, salt, nonce)
    return prefix + body


def read_header(path) -> dict:
    with open(path, "rb") as f:
        prefix_raw = f.read(_PREFIX_LEN)
        if len(prefix_raw) != _PREFIX_LEN:
            raise ValueError("file vault terlalu pendek / rusak")
        magic, version = struct.unpack(_PREFIX_FORMAT, prefix_raw)
        if magic != MAGIC:
            raise ValueError("bukan file vault Trust2Pass (magic tidak cocok)")

        if version == 1:
            # Vault lama (sebelum fitur export ada) - gak punya byte `kind`, anggap vault biasa.
            # Begitu di-save ulang (edit/tambah entri apa aja), otomatis ke-upgrade ke v2 lewat
            # write_vault (CLAUDE.md: parameter header memang didesain bisa di-upgrade).
            body_len = struct.calcsize(_BODY_FORMAT_V1)
            body_raw = f.read(body_len)
            if len(body_raw) != body_len:
                raise ValueError("file vault terlalu pendek / rusak")
            kdf_id, memory_kib, time_cost, parallelism, salt, nonce = struct.unpack(_BODY_FORMAT_V1, body_raw)
            kind = KIND_VAULT
        elif version == 2:
            body_len = struct.calcsize(_BODY_FORMAT_V2)
            body_raw = f.read(body_len)
            if len(body_raw) != body_len:
                raise ValueError("file vault terlalu pendek / rusak")
            kind, kdf_id, memory_kib, time_cost, parallelism, salt, nonce = struct.unpack(_BODY_FORMAT_V2, body_raw)
        else:
            raise ValueError(f"format_version {version} tidak didukung")

        if kdf_id != KDF_ID_ARGON2ID:
            raise ValueError(f"kdf_id {kdf_id} tidak dikenal")
        return {
            "kind": kind,
            "memory_kib": memory_kib,
            "time_cost": time_cost,
            "parallelism": parallelism,
            "salt": salt,
            "nonce": nonce,
            "header_bytes": prefix_raw + body_raw,
        }


def open_vault(path, key: bytes) -> bytes:
    """Decrypt payload. Kalau header invalid atau auth tag gagal, vault ditolak total - tidak ada baca sebagian."""
    header = read_header(path)
    with open(path, "rb") as f:
        f.seek(len(header["header_bytes"]))
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
    kind: int = KIND_VAULT,
) -> None:
    """Enkripsi lalu tulis vault secara atomic (tulis ke file sementara -> fsync -> rename)."""
    nonce = cipher.generate_nonce()
    header_bytes = pack_header(salt, nonce, memory_kib, time_cost, parallelism, kind)
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
        assert header["kind"] == KIND_VAULT  # default

        # `kind` (dipakai fitur Export) ke-persist & kebaca balik, dan tetep ke-cover AAD.
        export_path = Path(tmpdir) / "export.t2p"
        write_vault(
            export_path, key, plaintext, salt, kdf.MIN_MEMORY_KIB, kdf.MIN_TIME_COST, kdf.MIN_PARALLELISM,
            kind=KIND_EXPORT,
        )
        assert read_header(export_path)["kind"] == KIND_EXPORT
        assert open_vault(export_path, key) == plaintext

        # Vault format LAMA (v1, sebelum field `kind` ada) - harus tetep kebaca (migrasi
        # otomatis), dianggap KIND_VAULT.
        old_nonce = cipher.generate_nonce()
        old_header = struct.pack(
            ">4sBBIBB16s12s", MAGIC, 1, KDF_ID_ARGON2ID,
            kdf.MIN_MEMORY_KIB, kdf.MIN_TIME_COST, kdf.MIN_PARALLELISM, salt, old_nonce,
        )
        old_ciphertext = cipher.encrypt(key, old_nonce, plaintext, old_header)
        old_path = Path(tmpdir) / "old_v1.t2p"
        old_path.write_bytes(old_header + old_ciphertext)
        old_read = read_header(old_path)
        assert old_read["kind"] == KIND_VAULT
        assert open_vault(old_path, key) == plaintext

        # Header di-tamper (ubah salah satu byte-nya) -> harus reject.
        raw = bytearray(vault_path.read_bytes())
        raw[8] ^= 0xFF
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
