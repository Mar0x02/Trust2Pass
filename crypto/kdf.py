"""Derivasi Master Key dari password via Argon2id (RFC 9106)."""

import secrets

from argon2.low_level import Type, hash_secret_raw

KEY_LEN = 32
SALT_LEN = 16

# Baseline minimum OWASP - jangan pernah di bawah ini.
MIN_MEMORY_KIB = 19 * 1024
MIN_TIME_COST = 2
MIN_PARALLELISM = 1


def generate_salt() -> bytes:
    return secrets.token_bytes(SALT_LEN)


def derive_key(password: bytes, salt: bytes, memory_kib: int, time_cost: int, parallelism: int) -> bytes:
    """Derive 32-byte Master Key. Password masuk langsung ke Argon2id, tanpa pre-hash."""
    if len(salt) != SALT_LEN:
        raise ValueError(f"salt harus {SALT_LEN} byte, dapat {len(salt)}")
    if memory_kib < MIN_MEMORY_KIB or time_cost < MIN_TIME_COST or parallelism < MIN_PARALLELISM:
        raise ValueError("parameter Argon2id di bawah baseline minimum OWASP")
    return hash_secret_raw(
        secret=password,
        salt=salt,
        time_cost=time_cost,
        memory_cost=memory_kib,
        parallelism=parallelism,
        hash_len=KEY_LEN,
        type=Type.ID,
    )


if __name__ == "__main__":
    salt = generate_salt()
    assert len(salt) == SALT_LEN

    key = derive_key(b"correct horse battery staple", salt, MIN_MEMORY_KIB, MIN_TIME_COST, MIN_PARALLELISM)
    assert len(key) == KEY_LEN

    # Deterministik: password+salt+params sama -> key sama.
    assert key == derive_key(b"correct horse battery staple", salt, MIN_MEMORY_KIB, MIN_TIME_COST, MIN_PARALLELISM)

    # Salt beda -> key beda.
    assert key != derive_key(b"correct horse battery staple", generate_salt(), MIN_MEMORY_KIB, MIN_TIME_COST, MIN_PARALLELISM)

    # Password beda -> key beda.
    assert key != derive_key(b"wrong password", salt, MIN_MEMORY_KIB, MIN_TIME_COST, MIN_PARALLELISM)

    # Parameter di bawah baseline harus ditolak.
    try:
        derive_key(b"x", salt, MIN_MEMORY_KIB - 1, MIN_TIME_COST, MIN_PARALLELISM)
        raise AssertionError("harusnya reject memory_kib di bawah baseline")
    except ValueError:
        pass

    print("kdf.py self-check OK")
