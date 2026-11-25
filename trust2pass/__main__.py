"""Briefcase butuh entry point `<app_name>/__main__.py` - cuma delegasi ke main.py yang sudah ada,
supaya crypto/vault/ui gak perlu dipindah dari layout flat yang sudah ada.
"""

from main import main

if __name__ == "__main__":
    main()
