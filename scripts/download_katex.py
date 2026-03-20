#!/usr/bin/env python3
# ============================================================================
# Prométhée — Assistant IA desktop
# ============================================================================
# Auteur  : Pierre COUGET
# Licence : GNU Affero General Public License v3.0 (AGPL-3.0)
#           https://www.gnu.org/licenses/agpl-3.0.html
# Année   : 2026
# ----------------------------------------------------------------------------
# Ce fichier fait partie du projet Prométhée.
# Vous pouvez le redistribuer et/ou le modifier selon les termes de la
# licence AGPL-3.0 publiée par la Free Software Foundation.
# ============================================================================

"""
download_katex.py — Télécharge KaTeX dans assets/katex/
À exécuter une seule fois : python download_katex.py

KaTeX version 0.16.33
Fichiers nécessaires :
  - katex.min.js
  - katex.min.css
  - fonts/ (subset : woff2 uniquement)
"""
import urllib.request
import os
import sys
from pathlib import Path

KATEX_VERSION = "0.16.33"
BASE_URL = f"https://cdn.jsdelivr.net/npm/katex@{KATEX_VERSION}/dist"

# Répertoire de destination (relatif à la racine du projet)
SCRIPT_DIR = Path(__file__).parent
KATEX_DIR  = SCRIPT_DIR.parent / "assets" / "katex"
FONTS_DIR  = KATEX_DIR  / "fonts"

# Polices woff2 nécessaires (subset minimal pour les maths)
FONTS = [
    "KaTeX_AMS-Regular.woff2",
    "KaTeX_Caligraphic-Bold.woff2",
    "KaTeX_Caligraphic-Regular.woff2",
    "KaTeX_Fraktur-Bold.woff2",
    "KaTeX_Fraktur-Regular.woff2",
    "KaTeX_Main-Bold.woff2",
    "KaTeX_Main-BoldItalic.woff2",
    "KaTeX_Main-Italic.woff2",
    "KaTeX_Main-Regular.woff2",
    "KaTeX_Math-BoldItalic.woff2",
    "KaTeX_Math-Italic.woff2",
    "KaTeX_SansSerif-Bold.woff2",
    "KaTeX_SansSerif-Italic.woff2",
    "KaTeX_SansSerif-Regular.woff2",
    "KaTeX_Script-Regular.woff2",
    "KaTeX_Size1-Regular.woff2",
    "KaTeX_Size2-Regular.woff2",
    "KaTeX_Size3-Regular.woff2",
    "KaTeX_Size4-Regular.woff2",
    "KaTeX_Typewriter-Regular.woff2",
]


def download(url: str, dest: Path):
    if dest.exists():
        print(f"  ✓ déjà présent : {dest.name}")
        return
    print(f"  ↓ {dest.name} ...", end=" ", flush=True)
    try:
        urllib.request.urlretrieve(url, dest)
        size = dest.stat().st_size // 1024
        print(f"{size} Ko")
    except Exception as e:
        print(f"ERREUR : {e}")
        sys.exit(1)


def main():
    print(f"=== Téléchargement KaTeX {KATEX_VERSION} ===")
    print(f"Destination : {KATEX_DIR}\n")

    KATEX_DIR.mkdir(parents=True, exist_ok=True)
    FONTS_DIR.mkdir(parents=True, exist_ok=True)

    # Fichiers principaux
    download(f"{BASE_URL}/katex.min.js",  KATEX_DIR / "katex.min.js")
    download(f"{BASE_URL}/katex.min.css", KATEX_DIR / "katex.min.css")

    # Auto-render (pour rendre automatiquement toutes les expressions)
    download(
        f"{BASE_URL}/contrib/auto-render.min.js",
        KATEX_DIR / "auto-render.min.js",
    )

    # Polices
    print(f"\nPolices ({len(FONTS)}) :")
    for font in FONTS:
        download(f"{BASE_URL}/fonts/{font}", FONTS_DIR / font)

    print(f"\n✅ KaTeX installé dans {KATEX_DIR}")
    print("   Vous pouvez maintenant lancer l'application.")


if __name__ == "__main__":
    main()
