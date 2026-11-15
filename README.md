<div align="center">

<img src="assets/icon-rounded.png" alt="Trust2Pass icon" width="140"/>

# Trust2Pass

**Credential manager lokal-first** — proyek belajar cybersecurity dengan fokus penerapan **CIA Triad** (Confidentiality, Integrity, Availability) dalam desain kriptografi nyata.

![status](https://img.shields.io/badge/status-skeleton%20%2F%20MVP-orange)
![python](https://img.shields.io/badge/python-3.11%2B-blue)
![platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-informational)

</div>

---

## Tentang

Trust2Pass adalah credential manager untuk penggunaan pribadi: satu vault terenkripsi, tersimpan lokal, tanpa server pusat. Tujuannya bukan mengejar fitur sebanyak mungkin, tapi memahami dan menerapkan dengan benar bagaimana sebuah aplikasi menyimpan rahasia secara aman — mulai dari derivasi kunci, enkripsi, sampai manajemen memori.

> ⚠️ **Status: skeleton / under development (Fase 1 MVP).** Belum untuk dipakai menyimpan password asli.

## Fitur Inti (MVP)
- 🔐 Master password untuk membuka vault.
- 📋 CRUD entri kredensial: situs, username, password, URL, catatan.
- 🎲 Password generator berbasis modul `secrets`.
- ⏱️ Auto-lock otomatis setelah idle.

## Desain Keamanan

| Aspek | Penerapan |
|---|---|
| **Confidentiality** | Argon2id (`argon2-cffi`) men-derive Master Key dari password — password tidak pernah dipakai langsung sebagai kunci enkripsi. |
| **Confidentiality** | AES-256-GCM (`cryptography`), AEAD — sekali jalan dapat kerahasiaan *dan* integritas. |
| **Integrity** | Header vault (magic, versi, parameter KDF, salt) di-*bind* sebagai AAD, jadi tidak bisa dimanipulasi tanpa ketahuan. |
| **Integrity** | Penulisan vault atomic (tulis sementara → fsync → rename) — tahan crash di tengah proses simpan. |
| **Availability** | Akses offline penuh, satu device, satu vault. |
| **Trade-off sadar** | Fase 1 murni *zero-knowledge*: tanpa recovery key. Lupa master password = data hilang — ini keputusan desain, bukan bug. |

## Stack
Python + PySide6 — desktop native, cross-platform (Windows / macOS / Linux).

## Struktur Proyek
```
main.py          entry point
generator.py     password generator
crypto/          KDF (Argon2id), cipher (AES-256-GCM), zeroize memori
vault/           model entri & storage vault terenkripsi
ui/              dialog unlock & window utama
assets/          icon app (source, .ico, .icns, varian PNG)
```

## Menjalankan
```bash
pip install -r requirements.txt
python main.py
```

## Roadmap
1. **Fase 1 (MVP)** — vault lokal tunggal, zero-knowledge murni, fitur inti. *(sedang berjalan)*
2. **Fase 2** — recovery key sederhana, audit log, password health checker.
3. **Fase 3** — multi-device sync terenkripsi end-to-end.
4. **Fase 4** — porting logika inti ke Rust/Tauri untuk keamanan memori yang lebih ketat.

## Palette — Midnight Obsidian
| | Hex | Peran |
|---|---|---|
| ⬛ | `#0C0F14` | Background gelap |
| ⬛ | `#151B23` | Background sekunder / card |
| 🟦 | `#65D0EA` | Aksen cyan |
| 🟦 | `#3662E3` | Aksen biru |
| ⬜ | `#F2F5F9` | Teks / foreground terang |

## Lisensi
Proyek belajar pribadi — belum ada lisensi resmi.

---

<div align="center">

Dibuat oleh **[Mar0x02](https://github.com/Mar0x02)**

</div>
