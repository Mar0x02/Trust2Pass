"""Helper zeroize untuk data sensitif (bytearray), best-effort di Python.

Best-effort karena str/bytes immutable bisa aja udah disalin interpreter/GC/Qt
sebelum titik ini - zeroize cuma menghapus SATU salinan yang kita pegang (bytearray).
Makanya data sensitif (password, Master Key) wajib disimpan sebagai bytearray dari awal,
bukan str/bytes, supaya ada sesuatu yang benar-benar bisa di-zeroize.
"""


def zeroize(buf: bytearray) -> None:
    """Overwrite buf in place dengan nol. Hanya menerima bytearray (mutable) -
    bytes/str akan raise TypeError, itu disengaja supaya salah pakai ketahuan langsung."""
    for i in range(len(buf)):
        buf[i] = 0


if __name__ == "__main__":
    secret = bytearray(b"super secret master key")
    length = len(secret)
    zeroize(secret)
    assert secret == bytearray(length)  # semua byte jadi 0
    assert len(secret) == length  # panjang tidak berubah

    # bytes immutable -> harus gagal, bukan diam-diam no-op.
    try:
        zeroize(bytearray(b"ok"))  # sanity: bytearray kosong pun aman
        zeroize(b"not mutable")  # type: ignore[arg-type]
        raise AssertionError("harusnya TypeError untuk bytes immutable")
    except TypeError:
        pass

    print("memory.py self-check OK")
