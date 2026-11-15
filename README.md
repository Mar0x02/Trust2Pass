# Trust2Pass

<img src="assets/icon.jpg" alt="Trust2Pass icon" width="128"/>

Credential manager **lokal-first** untuk penggunaan pribadi, dibuat sebagai sarana belajar cybersecurity — khususnya penerapan **CIA Triad** (Confidentiality, Integrity, Availability) dalam desain kriptografi nyata.

> ⚠️ Status: skeleton / under development (Fase 1 MVP). Belum untuk dipakai menyimpan password asli.

## Fitur Inti (MVP)
- Master password untuk membuka vault.
- CRUD entri kredensial: situs, username, password, URL, catatan.
- Password generator (modul `secrets`).
- Auto-lock setelah idle.

## Desain Keamanan
- **KDF**: Argon2id (`argon2-cffi`) — password tidak pernah dipakai langsung sebagai kunci.
- **Enkripsi**: AES-256-GCM (`cryptography`) — AEAD, confidentiality + integrity sekaligus.
- **Zero-knowledge**: satu vault, satu device, tanpa server pusat, tanpa recovery (Fase 1).
- Vault ditulis secara atomic (tulis sementara → fsync → rename) agar tahan crash.

## Stack
Python + PySide6 (desktop, cross-platform: Windows/macOS/Linux).

## Palette — Midnight Obsidian
| | Hex | Peran |
|---|---|---|
| ⬛ | `#0C0F14` | Background gelap |
| ⬛ | `#151B23` | Background sekunder / card |
| 🟦 | `#65D0EA` | Aksen cyan |
| 🟦 | `#3662E3` | Aksen biru |
| ⬜ | `#F2F5F9` | Teks / foreground terang |

Source icon: `assets/icon.jpg`.

## Menjalankan
```bash
pip install -r requirements.txt
python main.py
```

## Struktur
```
crypto/   KDF, cipher AES-GCM, zeroize memori
vault/    model entri & storage vault terenkripsi
ui/       dialog unlock & window utama
```

## Lisensi
Proyek belajar pribadi — belum ada lisensi resmi.
