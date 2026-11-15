"""Model data entri vault (situs, username, password, URL, catatan)."""

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone


def now_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")


@dataclass
class Entry:
    site: str
    username: str
    password: str
    url: str = ""
    notes: str = ""
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
            # Vault lama (sebelum field ini ada) jatuh ke "sekarang" - lebih baik daripada crash.
            created_at=data.get("created_at") or now_str(),
            updated_at=data.get("updated_at") or now_str(),
        )


def dumps(entries: list[Entry]) -> bytes:
    """Serialize entries jadi plaintext payload (bytes) yang siap dienkripsi oleh vault/storage.py."""
    return json.dumps([asdict(e) for e in entries], ensure_ascii=False).encode("utf-8")


def loads(payload: bytes) -> list[Entry]:
    """Deserialize plaintext payload hasil dekripsi vault/storage.py jadi list Entry."""
    data = json.loads(payload.decode("utf-8"))
    return [Entry.from_dict(item) for item in data]


if __name__ == "__main__":
    a = Entry(site="example.com", username="neo", password="hunter2", url="https://example.com", notes="akun demo")
    b = Entry(site="github.com", username="trinity", password="zi0n")

    assert a.id != b.id  # id auto-generate harus unik
    assert a.created_at and a.updated_at  # timestamp auto-stamp pas construct

    payload = dumps([a, b])
    restored = loads(payload)
    assert restored == [a, b]

    # Vault kosong harus bisa round-trip.
    assert loads(dumps([])) == []

    # Karakter unicode (mis. catatan berbahasa non-ASCII) harus utuh.
    c = Entry(site="unicode.test", username="u", password="p", notes="kunci spesial: éè中文")
    assert loads(dumps([c])) == [c]

    # Vault lama tanpa created_at/updated_at (format sebelum field ini ada) -> gak crash.
    old_format = {"id": "x", "site": "old.com", "username": "u", "password": "p"}
    migrated = Entry.from_dict(old_format)
    assert migrated.created_at and migrated.updated_at

    print("models.py self-check OK")
