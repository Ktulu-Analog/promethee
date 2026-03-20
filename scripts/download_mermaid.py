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
download_mermaid.py — Télécharge Mermaid dans assets/mermaid/
À exécuter une seule fois : python scripts/download_mermaid.py

Mermaid version 11.13.0
Fichier nécessaire :
  - mermaid.min.js  (bundle autonome, pas de dépendances)
"""
import urllib.request
import sys
from pathlib import Path

MERMAID_VERSION = "11.13.0"
BASE_URL = f"https://cdn.jsdelivr.net/npm/mermaid@{MERMAID_VERSION}/dist"

# Répertoire de destination (relatif à la racine du projet)
SCRIPT_DIR   = Path(__file__).parent
MERMAID_DIR  = SCRIPT_DIR.parent / "assets" / "mermaid"


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
    print(f"=== Téléchargement Mermaid {MERMAID_VERSION} ===")
    print(f"Destination : {MERMAID_DIR}\n")

    MERMAID_DIR.mkdir(parents=True, exist_ok=True)

    download(
        f"{BASE_URL}/mermaid.min.js",
        MERMAID_DIR / "mermaid.min.js",
    )

    print(f"\n✅ Mermaid installé dans {MERMAID_DIR}")
    print("   Vous pouvez maintenant lancer l'application.")
    print("\n   Les diagrammes Mermaid s'affichent dans les blocs :")
    print("   ```mermaid")
    print("   graph TD")
    print("       A[Début] --> B[Fin]")
    print("   ```")


if __name__ == "__main__":
    main()
