"""TOTP (RFC 6238) sebagai faktor kedua - gerbang MFA, bukan bahan derivasi kunci (lihat
crypto/entry_secret.py). Tipis di atas `pyotp`/`qrcode`, jangan implementasi algoritma sendiri.
"""

import io

import pyotp
import qrcode

ISSUER = "Trust2Pass"


def generate_secret() -> str:
    return pyotp.random_base32()


def verify_code(secret: str, code: str) -> bool:
    """valid_window=1 - toleransi geser jam +-1 step (30 detik), bukan buka jendela lebar."""
    code = code.strip()
    if not code:
        return False
    return pyotp.TOTP(secret).verify(code, valid_window=1)


def provisioning_uri(secret: str, account_name: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=account_name, issuer_name=ISSUER)


def qr_png_bytes(uri: str) -> bytes:
    img = qrcode.make(uri)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


if __name__ == "__main__":
    secret = generate_secret()
    assert len(secret) >= 16

    code = pyotp.TOTP(secret).now()
    assert verify_code(secret, code)
    assert not verify_code(secret, "000000") or pyotp.TOTP(secret).now() == "000000"
    assert not verify_code(secret, "")

    uri = provisioning_uri(secret, "vault.t2p")
    assert uri.startswith("otpauth://totp/")
    assert ISSUER in uri

    png = qr_png_bytes(uri)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"  # PNG magic bytes

    print("totp.py self-check OK")
