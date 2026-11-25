"""Vault manager: jembatan sesi antara crypto/storage dan UI.

Pegang Master Key di memori selama sesi (bytearray, di-zeroize saat lock()).
Tiap operasi CRUD langsung autosave ke disk - tidak ada state "belum tersimpan"
yang bisa hilang kalau app crash/ditutup paksa.

MFA (lihat crypto/totp.py, crypto/entry_secret.py): kalau aktif, field password entri yang
ter-gate TETAP ciphertext bahkan setelah vault unlock (Entry.password_sealed) - gak pernah ada
plaintext yang nongkrong lama di `self.entries`. reveal_password() cuma buka plaintext-nya
sesaat, dipanggil UI pas mau copy/show, balik ter-"kunci" lagi karena memang gak pernah
dimutasi ke plaintext di tempat pertama (one-shot decrypt, bukan decrypt-lalu-re-encrypt).
"""

import time
from dataclasses import replace
from pathlib import Path

from crypto import entry_secret, kdf, totp
from crypto.memory import zeroize
from vault import models, storage

MFA_MAX_ATTEMPTS = 5
MFA_LOCKOUT_SECONDS = 30


class InvalidMfaCode(Exception):
    """Kode TOTP yang dimasukin salah/kedaluwarsa."""


class MfaLockedOut(Exception):
    """Kena cooldown gara-gara kode salah berturut-turut (lihat MFA_MAX_ATTEMPTS)."""

    def __init__(self, retry_after: float) -> None:
        super().__init__(f"terlalu banyak kode salah, coba lagi dalam {retry_after:.0f} detik")
        self.retry_after = retry_after


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
        self.mfa_enabled = False
        self.mfa_scope = "all"
        self._totp_secret: str | None = None
        self._mfa_fail_count = 0
        self._mfa_lockout_until = 0.0

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
        self.entries, mfa = models.loads(plaintext)
        self.mfa_enabled = mfa["enabled"]
        self.mfa_scope = mfa["scope"]
        self._totp_secret = mfa["totp_secret"]
        self._mfa_fail_count = 0
        self._mfa_lockout_until = 0.0

    def lock(self) -> None:
        """Zeroize Master Key dan lupain entri plaintext dari memori (best-effort, lihat crypto/memory.py)."""
        if self._key is not None:
            zeroize(self._key)
            self._key = None
        self.entries = []
        self._salt = None
        self.mfa_enabled = False
        self.mfa_scope = "all"
        self._totp_secret = None
        self._mfa_fail_count = 0
        self._mfa_lockout_until = 0.0

    def _save(self) -> None:
        if self._key is None or self.path is None:
            raise RuntimeError("vault belum unlocked/dibuat")
        mfa = {"enabled": self.mfa_enabled, "scope": self.mfa_scope, "totp_secret": self._totp_secret}
        storage.write_vault(
            self.path, self._key, models.dumps(self.entries, mfa), self._salt,
            self._memory_kib, self._time_cost, self._parallelism, self._kind,
        )

    def entry_should_be_gated(self, entry: models.Entry) -> bool:
        """Niat kebijakan MFA saat ini buat entri ini (dipakai internal buat nentuin seal/unseal
        pas CRUD/setting berubah). Buat UI, cek state AKTUAL-nya lewat `entry.password_sealed`."""
        return self.mfa_enabled and (self.mfa_scope == "all" or entry.mfa_required)

    def _seal_for_storage(self, entry: models.Entry) -> models.Entry:
        """entry WAJIB datang dengan password PLAINTEXT (dari EntryDialog/import) - seal kalau
        seharusnya ter-gate sesuai setting MFA saat ini, biar `self.entries` gak pernah nyimpen
        plaintext buat entri yang digate."""
        if self.entry_should_be_gated(entry):
            sealed = entry_secret.seal(self._key, entry.id, entry.password)
            return replace(entry, password=sealed, password_sealed=True)
        return replace(entry, password_sealed=False)

    def add_entry(self, entry: models.Entry) -> None:
        self.entries.append(self._seal_for_storage(entry))
        self._save()

    def add_entries(self, entries: list[models.Entry]) -> None:
        """Dipakai Import/Export (main_window.py) - satu kali tulis ke disk buat banyak entri
        sekaligus, bukan _save() berkali-kali kayak manggil add_entry() di loop."""
        self.entries.extend(self._seal_for_storage(e) for e in entries)
        self._save()

    def update_entry(self, entry_id: str, **changes) -> None:
        """Kalau `password` ikut di `changes`, nilainya WAJIB plaintext (dialog edit sudah
        reveal dulu lewat reveal_password() kalau entrinya ter-gate - lihat ui/main_window.py),
        jadi di sini aman langsung dievaluasi ulang seal/unseal-nya."""
        changes.setdefault("updated_at", models.now_str())
        for i, e in enumerate(self.entries):
            if e.id == entry_id:
                merged = replace(e, **changes)
                self.entries[i] = self._seal_for_storage(merged) if "password" in changes else merged
                self._save()
                return
        raise KeyError(f"entry id {entry_id} tidak ditemukan")

    def delete_entry(self, entry_id: str) -> None:
        before = len(self.entries)
        self.entries = [e for e in self.entries if e.id != entry_id]
        if len(self.entries) == before:
            raise KeyError(f"entry id {entry_id} tidak ditemukan")
        self._save()

    def _find_entry(self, entry_id: str) -> models.Entry:
        for e in self.entries:
            if e.id == entry_id:
                return e
        raise KeyError(f"entry id {entry_id} tidak ditemukan")

    def _require_valid_mfa(self, code: str) -> None:
        """Gerbang TOTP generik - dipakai reveal_password() dan tiap aksi yang MELEMAHKAN
        proteksi MFA (disable_mfa, set_mfa_scope). Rate-limit sederhana (bukan kripto, cuma
        app-logic) biar kode 6 digit gak gampang di-brute-force lokal."""
        now = time.monotonic()
        if now < self._mfa_lockout_until:
            raise MfaLockedOut(self._mfa_lockout_until - now)
        if not self._totp_secret or not totp.verify_code(self._totp_secret, code):
            self._mfa_fail_count += 1
            if self._mfa_fail_count >= MFA_MAX_ATTEMPTS:
                self._mfa_lockout_until = now + MFA_LOCKOUT_SECONDS
                self._mfa_fail_count = 0
            raise InvalidMfaCode("kode TOTP salah atau kedaluwarsa")
        self._mfa_fail_count = 0

    def reveal_password(self, entry_id: str, code: str) -> str:
        """Dekripsi plaintext password SESAAT buat copy/show di UI. Gak pernah nulis balik
        plaintext ke `self.entries` - begitu nilai ini dipakai (copy ke clipboard / ditampilin),
        entri itu tetap ciphertext di memori seperti semula, gak ada langkah "re-lock" manual
        yang perlu dilakukan."""
        entry = self._find_entry(entry_id)
        if not entry.password_sealed:
            return entry.password
        self._require_valid_mfa(code)
        return entry_secret.unseal(self._key, entry.id, entry.password)

    def _reseal_all(self) -> None:
        """Evaluasi ulang seal/unseal semua entri sesuai mfa_enabled/mfa_scope SAAT INI, lalu
        simpan sekali. Dipanggil tiap setting MFA global berubah (enable/disable/ganti scope)."""
        new_entries = []
        for e in self.entries:
            should = self.entry_should_be_gated(e)
            if should and not e.password_sealed:
                sealed = entry_secret.seal(self._key, e.id, e.password)
                e = replace(e, password=sealed, password_sealed=True)
            elif not should and e.password_sealed:
                plain = entry_secret.unseal(self._key, e.id, e.password)
                e = replace(e, password=plain, password_sealed=False)
            new_entries.append(e)
        self.entries = new_entries
        self._save()

    def enable_mfa(self, secret: str, scope: str, confirm_code: str) -> None:
        """Aktifin MFA. `confirm_code` membuktikan user udah bener nyalin secret-nya ke app
        authenticator (roundtrip check) - mencegah lockout gara-gara typo pas enrollment."""
        if scope not in ("all", "selected"):
            raise ValueError(f"scope tidak dikenal: {scope}")
        if not totp.verify_code(secret, confirm_code):
            raise InvalidMfaCode("kode konfirmasi salah - pastikan secret sudah benar dimasukkan ke app authenticator")
        self.mfa_enabled = True
        self.mfa_scope = scope
        self._totp_secret = secret
        self._mfa_fail_count = 0
        self._mfa_lockout_until = 0.0
        self._reseal_all()

    def disable_mfa(self, code: str) -> None:
        """Matiin MFA total - butuh kode TOTP valid dulu (melemahkan proteksi, bukan menguatkan,
        jadi harus dibuktikan user masih pegang second factor-nya) sebelum semua entri ter-gate
        di-unseal balik ke plaintext."""
        self._require_valid_mfa(code)
        self.mfa_enabled = False
        self._totp_secret = None
        self._reseal_all()

    def set_mfa_scope(self, scope: str, code: str) -> None:
        """Ganti scope "all"/"selected" - juga butuh kode TOTP valid (bisa melemahkan proteksi
        buat entri yang gak ditandai mfa_required)."""
        if scope not in ("all", "selected"):
            raise ValueError(f"scope tidak dikenal: {scope}")
        self._require_valid_mfa(code)
        self.mfa_scope = scope
        self._reseal_all()


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

    # --- MFA ---
    import pyotp

    with tempfile.TemporaryDirectory() as tmp:
        vault_path = Path(tmp) / "mfa_test.t2p"
        vm = VaultManager()
        vm.create(vault_path, b"correct horse battery staple", MIN_MEMORY_KIB, MIN_TIME_COST, MIN_PARALLELISM)
        assert not vm.mfa_enabled and vm.mfa_scope == "all"  # default vault baru

        entry_a = models.Entry(site="a.com", username="a", password="pw-a")
        vm.add_entry(entry_a)
        assert not vm.entries[0].password_sealed  # belum ada MFA - plaintext biasa

        secret = totp.generate_secret()
        wrong_confirm = "000000" if pyotp.TOTP(secret).now() != "000000" else "111111"
        try:
            vm.enable_mfa(secret, "all", wrong_confirm)
            raise AssertionError("harusnya reject confirm_code yang salah")
        except InvalidMfaCode:
            pass
        assert not vm.mfa_enabled  # gagal enroll -> state gak berubah

        vm.enable_mfa(secret, "all", pyotp.TOTP(secret).now())
        assert vm.mfa_enabled and vm.mfa_scope == "all"
        assert vm.entries[0].password_sealed  # scope "all" -> entri yang udah ada ikut di-seal
        assert vm.entries[0].password != "pw-a"  # representasi di memori BUKAN plaintext lagi

        # Entri baru setelah MFA aktif (scope "all") otomatis ter-seal juga.
        vm.add_entry(models.Entry(site="b.com", username="b", password="pw-b"))
        entry_b_id = vm.entries[1].id
        assert vm.entries[1].password_sealed

        # Kode salah -> ditolak, plaintext gak kebuka.
        try:
            vm.reveal_password(entry_a.id, "999999")
            raise AssertionError("harusnya reject kode TOTP salah")
        except InvalidMfaCode:
            pass

        # Kode benar -> plaintext balik sesaat, TANPA mengubah representasi `self.entries`
        # (masih ciphertext - inilah yang bikin "lock lagi" gak perlu langkah eksplisit).
        code = pyotp.TOTP(secret).now()
        assert vm.reveal_password(entry_a.id, code) == "pw-a"
        assert vm.entries[0].password_sealed and vm.entries[0].password != "pw-a"

        # Rate limit: 5 kode salah berturut-turut -> entri ke-6 (walau kodenya BENAR) kena lockout.
        vm._mfa_fail_count = 0
        vm._mfa_lockout_until = 0.0
        for _ in range(MFA_MAX_ATTEMPTS):
            try:
                vm.reveal_password(entry_a.id, "999999")
            except InvalidMfaCode:
                pass
        try:
            vm.reveal_password(entry_a.id, pyotp.TOTP(secret).now())
            raise AssertionError("harusnya kena lockout")
        except MfaLockedOut:
            pass
        vm._mfa_lockout_until = 0.0  # reset manual - testnya gak mau nunggu cooldown beneran

        # Ganti scope ke "selected" - entri tanpa mfa_required balik plaintext (melemahkan,
        # makanya butuh kode valid); entri B ditandai mfa_required lewat edit flow (reveal dulu,
        # baru update_entry dengan plaintext - cara yang sama kayak UI).
        plain_b = vm.reveal_password(entry_b_id, pyotp.TOTP(secret).now())
        vm.update_entry(entry_b_id, password=plain_b, mfa_required=True)
        vm.set_mfa_scope("selected", pyotp.TOTP(secret).now())
        assert vm.mfa_scope == "selected"
        assert not vm._find_entry(entry_a.id).password_sealed  # gak ditandai -> ungated
        assert vm._find_entry(entry_a.id).password == "pw-a"
        assert vm._find_entry(entry_b_id).password_sealed  # ditandai mfa_required -> tetep gated

        try:
            vm.set_mfa_scope("not-a-scope", pyotp.TOTP(secret).now())
            raise AssertionError("harusnya reject scope yang gak dikenal")
        except ValueError:
            pass

        # Matiin MFA butuh kode valid, lalu semua entri balik plaintext.
        try:
            vm.disable_mfa("000000" if pyotp.TOTP(secret).now() != "000000" else "111111")
            raise AssertionError("harusnya reject kode salah pas disable")
        except InvalidMfaCode:
            pass
        vm.disable_mfa(pyotp.TOTP(secret).now())
        assert not vm.mfa_enabled
        assert vm._totp_secret is None
        assert all(not e.password_sealed for e in vm.entries)
        assert vm._find_entry(entry_b_id).password == plain_b

        vm.lock()
        assert vm._totp_secret is None and not vm.mfa_enabled  # lock() juga reset state MFA

    print("manager.py self-check OK")
