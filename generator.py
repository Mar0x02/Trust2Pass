"""Password generator berbasis modul `secrets`."""

import secrets
import string

DEFAULT_LENGTH = 16
MIN_LENGTH = 12
ALPHABET = string.ascii_letters + string.digits + string.punctuation


def generate_password(length: int = DEFAULT_LENGTH) -> str:
    if length < MIN_LENGTH:
        raise ValueError(f"panjang password minimal {MIN_LENGTH} karakter")
    return "".join(secrets.choice(ALPHABET) for _ in range(length))


if __name__ == "__main__":
    pw = generate_password()
    assert len(pw) == DEFAULT_LENGTH
    assert all(c in ALPHABET for c in pw)

    pw_long = generate_password(24)
    assert len(pw_long) == 24

    # Dua pemanggilan harus beda (secrets, bukan random predictable) - praktis selalu benar.
    assert generate_password() != generate_password()

    try:
        generate_password(8)
        raise AssertionError("harusnya reject panjang di bawah minimum")
    except ValueError:
        pass

    print("generator.py self-check OK")
