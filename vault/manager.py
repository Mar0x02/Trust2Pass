"""Vault manager: jembatan sesi antara crypto/storage dan UI.

Pegang Master Key di memori selama sesi (bytearray, di-zeroize saat lock()).
Tiap operasi CRUD langsung autosave ke disk - tidak ada state "belum tersimpan"
yang bisa hilang kalau app crash/ditutup paksa.
"""

from dataclasses import replace
from pathlib import Path

from crypto import kdf
from crypto.memory import zeroize
from vault import models, storage


class VaultManager:
    def __init__(self) -> None:
        self.path: Path | None = None
        self.entries: list[models.Entry] = []
        self._key: bytearray | None = None
        self._salt: bytes | None = None
        self._memory_kib = storage.DEFAULT_MEMORY_KIB
        self._time_cost = storage.DEFAULT_TIME_COST
        self._parallelism = storage.DEFAULT_PARALLELISM
        self._kind = storage.KIND_VAULT

    @property
    def is_unlocked(self) -> bool:
        return self._key is not None

    @property
    def kind(self) -> int:
        """`storage.KIND_VAULT` (biasa) atau `storage.KIND_EXPORT` (hasil fitur Export) - dibaca
        dari header file, bukan dari password, jadi gak butuh unlock dulu buat tau (lihat
        `storage.read_header` yang dipanggil fitur Import SEBELUM minta password)."""
        return self._kind

    def create(
        self,
        path,
        password: bytes,
        memory_kib: int = storage.DEFAULT_MEMORY_KIB,
        time_cost: int = storage.DEFAULT_TIME_COST,
        parallelism: int = storage.DEFAULT_PARALLELISM,
        kind: int = storage.KIND_VAULT,
    ) -> None:
        """Buat vault baru kosong di `path` (overwrite kalau sudah ada)."""
        self.path = Path(path)
        self._salt = kdf.generate_salt()
        self._memory_kib, self._time_cost, self._parallelism = memory_kib, time_cost, parallelism
        self._kind = kind
        self._key = bytearray(kdf.derive_key(password, self._salt, memory_kib, time_cost, parallelism))
        self.entries = []
        self._save()

    def unlock(self, path, password: bytes) -> None:
        """Buka vault yang sudah ada. Raise (InvalidTag/ValueError) kalau password salah / vault rusak."""
        path = Path(path)
        header = storage.read_header(path)
        key = kdf.derive_key(password, header["salt"], header["memory_kib"], header["time_cost"], header["parallelism"])
        plaintext = storage.open_vault(path, key)  # reject total kalau tag invalid

        self.path = path
        self._salt = header["salt"]
        self._memory_kib = header["memory_kib"]
        self._time_cost = header["time_cost"]
        self._parallelism = header["parallelism"]
        self._kind = header["kind"]
        self._key = bytearray(key)
        self.entries = models.loads(plaintext)

    def lock(self) -> None:
        """Zeroize Master Key dan lupain entri plaintext dari memori (best-effort, lihat crypto/memory.py)."""
        if self._key is not None:
            zeroize(self._key)
            self._key = None
        self.entries = []
        self._salt = None

    def _save(self) -> None:
        if self._key is None or self.path is None:
            raise RuntimeError("vault belum unlocked/dibuat")
        storage.write_vault(
            self.path, self._key, models.dumps(self.entries), self._salt,
            self._memory_kib, self._time_cost, self._parallelism, self._kind,
        )

    def add_entry(self, entry: models.Entry) -> None:
        self.entries.append(entry)
        self._save()

    def add_entries(self, entries: list[models.Entry]) -> None:
        """Dipakai Import/Export (main_window.py) - satu kali tulis ke disk buat banyak entri
        sekaligus, bukan _save() berkali-kali kayak manggil add_entry() di loop."""
        self.entries.extend(entries)
        self._save()

    def update_entry(self, entry_id: str, **changes) -> None:
        changes.setdefault("updated_at", models.now_str())
        for i, e in enumerate(self.entries):
            if e.id == entry_id:
                self.entries[i] = replace(e, **changes)
                self._save()
                return
        raise KeyError(f"entry id {entry_id} tidak ditemukan")

    def delete_entry(self, entry_id: str) -> None:
        before = len(self.entries)
        self.entries = [e for e in self.entries if e.id != entry_id]
        if len(self.entries) == before:
            raise KeyError(f"entry id {entry_id} tidak ditemukan")
        self._save()


if __name__ == "__main__":
    import tempfile

    from cryptography.exceptions import InvalidTag

    from crypto.kdf import MIN_MEMORY_KIB, MIN_PARALLELISM, MIN_TIME_COST

    with tempfile.TemporaryDirectory() as tmp:
        vault_path = Path(tmp) / "manager_test.t2p"
        password = b"correct horse battery staple"

        vm = VaultManager()
        vm.create(vault_path, password, MIN_MEMORY_KIB, MIN_TIME_COST, MIN_PARALLELISM)
        assert vm.is_unlocked
        assert vm.entries == []
        assert vm.kind == storage.KIND_VAULT  # default

        # kind=KIND_EXPORT (fitur Export) - ke-persist & kebaca balik dari disk.
        export_path = Path(tmp) / "export_test.t2p"
        vm_export = VaultManager()
        vm_export.create(export_path, b"password export beda", MIN_MEMORY_KIB, MIN_TIME_COST, MIN_PARALLELISM, kind=storage.KIND_EXPORT)
        assert vm_export.kind == storage.KIND_EXPORT
        vm_export.lock()
        vm_export2 = VaultManager()
        vm_export2.unlock(export_path, b"password export beda")
        assert vm_export2.kind == storage.KIND_EXPORT
        vm_export2.lock()

        vm.add_entry(models.Entry(site="github.com", username="Mar0x02", password="s3cr3t!"))
        vm.add_entry(models.Entry(site="example.com", username="neo", password="hunter2"))
        assert len(vm.entries) == 2

        target_id = vm.entries[0].id
        original_created_at = vm.entries[0].created_at
        vm.update_entry(target_id, password="new-password")
        assert vm.entries[0].password == "new-password"
        assert vm.entries[0].created_at == original_created_at  # created_at tidak berubah saat edit
        assert vm.entries[0].updated_at  # updated_at di-refresh otomatis

        vm.delete_entry(vm.entries[1].id)
        assert len(vm.entries) == 1

        vm.lock()
        assert not vm.is_unlocked
        assert vm.entries == []

        # Re-unlock dari disk - perubahan (update + delete) harus ke-persist.
        vm2 = VaultManager()
        vm2.unlock(vault_path, password)
        assert len(vm2.entries) == 1
        assert vm2.entries[0].id == target_id
        assert vm2.entries[0].password == "new-password"

        # add_entries (dipake Import/Export) - satu kali save buat banyak entri.
        vm2.add_entries([
            models.Entry(site="a.com", username="a", password="pa"),
            models.Entry(site="b.com", username="b", password="pb"),
        ])
        assert len(vm2.entries) == 3
        vm4 = VaultManager()
        vm4.unlock(vault_path, password)
        assert len(vm4.entries) == 3  # ke-persist ke disk
        vm4.lock()

        # Password salah -> reject.
        vm3 = VaultManager()
        try:
            vm3.unlock(vault_path, b"wrong password")
            raise AssertionError("harusnya reject password yang salah")
        except InvalidTag:
            pass
        assert not vm3.is_unlocked

        # Operasi CRUD setelah lock harus ditolak (state bersih, bukan silently corrupt).
        try:
            vm2.lock()
            vm2.add_entry(models.Entry(site="x", username="x", password="x"))
            raise AssertionError("harusnya RuntimeError karena vault sudah locked")
        except RuntimeError:
            pass

    print("manager.py self-check OK")
