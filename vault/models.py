"""Model data entri vault (situs, username, password, URL, catatan)."""

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone


def now_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")


#: Default pengaturan MFA buat vault baru / vault lama yang belum punya field ini sama sekali.
DEFAULT_MFA = {"enabled": False, "scope": "all", "totp_secret": None}


@dataclass
class Entry:
    site: str
    username: str
    password: str
    url: str = ""
    notes: str = ""
    # Niat user: entri ini WAJIB MFA buat reveal/copy. Dipakai cuma kalau mfa.scope == "selected"
    # (lihat vault/manager.py) - kalau scope == "all", semua entri ter-gate terlepas dari flag ini.
    mfa_required: bool = False
    # Representasi `password` SAAT INI: True = ciphertext (lapis kedua, lihat crypto/entry_secret.py),
    # False = plaintext biasa. Dikelola VaultManager, bukan diset manual dari UI.
    password_sealed: bool = False
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    created_at: str = field(default_factory=now_str)
    updated_at: str = field(default_factory=now_str)

    @classmethod
    def from_dict(cls, data: dict) -> "Entry":
        return cls(
            id=data.get("id", uuid.uuid4().hex),
            site=data["site"],
            username=data["username"],
            password=data["password"],
            url=data.get("url", ""),
            notes=data.get("notes", ""),
            # Vault lama (sebelum field ini ada) jatuh ke "sekarang"/False - lebih baik daripada crash.
            created_at=data.get("created_at") or now_str(),
            updated_at=data.get("updated_at") or now_str(),
            mfa_required=data.get("mfa_required", False),
            password_sealed=data.get("password_sealed", False),
        )


def dumps(entries: list[Entry], mfa: dict | None = None) -> bytes:
    """Serialize entries + setting MFA jadi plaintext payload (bytes) yang siap dienkripsi
    oleh vault/storage.py."""
    payload = {"entries": [asdict(e) for e in entries], "mfa": mfa or DEFAULT_MFA}
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def loads(payload: bytes) -> tuple[list[Entry], dict]:
    """Deserialize plaintext payload hasil dekripsi vault/storage.py jadi (list Entry, mfa dict).

    Vault lama (sebelum fitur MFA ada) nyimpen payload sebagai LIST polos, bukan dict - kebaca
    balik dengan MFA dianggap nonaktif, sama pola migrasinya kayak storage.py v1->v2."""
    data = json.loads(payload.decode("utf-8"))
    if isinstance(data, list):
        return [Entry.from_dict(item) for item in data], dict(DEFAULT_MFA)
    entries = [Entry.from_dict(item) for item in data.get("entries", [])]
    mfa = {**DEFAULT_MFA, **(data.get("mfa") or {})}
    return entries, mfa


if __name__ == "__main__":
    a = Entry(site="example.com", username="neo", password="hunter2", url="https://example.com", notes="akun demo")
    b = Entry(site="github.com", username="trinity", password="zi0n")

    assert a.id != b.id  # id auto-generate harus unik
    assert a.created_at and a.updated_at  # timestamp auto-stamp pas construct

    payload = dumps([a, b])
    restored_entries, restored_mfa = loads(payload)
    assert restored_entries == [a, b]
    assert restored_mfa == DEFAULT_MFA  # default kalau gak dikasih mfa dict eksplisit

    # Vault kosong harus bisa round-trip.
    empty_entries, empty_mfa = loads(dumps([]))
    assert empty_entries == []
    assert empty_mfa == DEFAULT_MFA

    # Karakter unicode (mis. catatan berbahasa non-ASCII) harus utuh.
    c = Entry(site="unicode.test", username="u", password="p", notes="kunci spesial: éè中文")
    assert loads(dumps([c]))[0] == [c]

    # Vault lama tanpa created_at/updated_at (format sebelum field ini ada) -> gak crash.
    old_format = {"id": "x", "site": "old.com", "username": "u", "password": "p"}
    migrated = Entry.from_dict(old_format)
    assert migrated.created_at and migrated.updated_at
    assert migrated.mfa_required is False and migrated.password_sealed is False

    # Setting MFA ikut round-trip kalau dikasih eksplisit.
    mfa_on = {"enabled": True, "scope": "selected", "totp_secret": "ABCDEFGH"}
    _, restored_mfa_on = loads(dumps([a], mfa_on))
    assert restored_mfa_on == mfa_on

    # Payload vault LAMA (sebelum fitur MFA ada) - list polos, bukan dict - harus tetap kebaca
    # (migrasi otomatis), MFA dianggap nonaktif.
    old_payload = json.dumps([asdict(a)]).encode("utf-8")
    old_entries, old_mfa = loads(old_payload)
    assert old_entries == [a]
    assert old_mfa == DEFAULT_MFA

    print("models.py self-check OK")
