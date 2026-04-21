# ============================================================================
# Prométhée — Assistant IA avancé
# ============================================================================
# Auteur  : Pierre COUGET ktulu.analog@gmail.com
# Licence : GNU Affero General Public License v3.0 (AGPL-3.0)
#           https://www.gnu.org/licenses/agpl-3.0.html
# Année   : 2026
# ----------------------------------------------------------------------------
# Ce fichier fait partie du projet Prométhée.
# Vous pouvez le redistribuer et/ou le modifier selon les termes de la
# licence AGPL-3.0 publiée par la Free Software Foundation.
# ============================================================================

"""
tools/ocr_tools.py — OCR : extraction de texte depuis images et PDF scannés
============================================================================

Outils exposés (4) :

  - ocr_image          : extrait le texte d'un fichier image (PNG, JPG, TIFF, BMP…)
  - ocr_pdf            : extrait le texte d'un PDF, en utilisant l'OCR sur les pages
                         scannées et l'extraction native sur les pages numériques
  - ocr_pdf_detect     : détecte le type d'un PDF (numérique / scanné / mixte)
                         sans extraire le texte
  - ocr_languages      : liste les langues Tesseract disponibles sur le système

Ce module est un pont vers core/ocr_engine.py qui contient la logique
Tesseract/PyMuPDF. Il en fait une famille d'outils LLM invocable en mode agent,
ce qui permet de traiter automatiquement des lots de documents sans intervention
manuelle (glisser-déposer dans l'interface).

Prérequis système :
    apt install tesseract-ocr tesseract-ocr-fra tesseract-ocr-eng
    pip install pytesseract pillow pymupdf

Variables .env (optionnelles) :
    OCR_DEFAULT_LANG=fra+eng   # langues Tesseract par défaut (défaut: fra+eng)
    OCR_MAX_PAGES=50           # nombre max de pages PDF à traiter (défaut: 50)
"""

import sys  # conservé pour compatibilité éventuelle
from pathlib import Path
from typing import Optional

from core.config import Config
from core.tools_engine import tool, set_current_family, _TOOL_ICONS

set_current_family("ocr_tools", "OCR — Extraction de texte", "🔎")

# ── Icônes UI ─────────────────────────────────────────────────────────────────
_TOOL_ICONS.update({
    "ocr_image":      "🖼️",
    "ocr_pdf":        "📄",
    "ocr_pdf_detect": "🔬",
    "ocr_languages":  "🌐",
})

# ── Constantes ────────────────────────────────────────────────────────────────
_DEFAULT_LANG     = getattr(Config, "OCR_DEFAULT_LANG", "fra+eng")
_DEFAULT_MAX_PAGES = int(getattr(Config, "OCR_MAX_PAGES", 50))
_MAX_RESULT_CHARS = 80_000   # éviter de saturer le contexte LLM

# Extensions image supportées
_IMAGE_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".tiff", ".tif",
    ".bmp", ".gif", ".webp", ".ppm", ".pgm",
}


# ── Résolution VFS → chemin réel ──────────────────────────────────────────────

import tempfile
import atexit

# Fichiers temporaires créés pour les fichiers VFS — nettoyés à la sortie
_TMP_FILES: list[str] = []


def _cleanup_tmp() -> None:
    for p in _TMP_FILES:
        try:
            Path(p).unlink(missing_ok=True)
        except Exception:
            pass


atexit.register(_cleanup_tmp)


def _resolve_path(chemin: str) -> tuple[Path, bool]:
    """
    Résout un chemin qui peut être soit un chemin filesystem réel, soit un
    chemin virtuel VFS (stocké dans SQLite + Garage).

    Stratégie :
      1. Si le chemin existe déjà sur le filesystem → retour direct.
      2. Sinon → tentative de lecture via get_vfs(). Si le fichier existe dans
         le VFS, son contenu est écrit dans un fichier temporaire et le chemin
         de ce temporaire est retourné.
      3. Si le VFS échoue aussi → retourne le chemin original (l'appelant
         produira le message d'erreur habituel "Fichier introuvable").

    Returns
    -------
    tuple[Path, bool]
        (chemin_résolu, depuis_vfs)
        depuis_vfs=True si le fichier a été extrait du VFS dans un temporaire.
    """
    real = Path(chemin).expanduser().resolve()
    if real.exists():
        return real, False

    # Tentative VFS
    try:
        from core.virtual_fs import get_vfs
        vfs = get_vfs()
        if vfs.exists(chemin) and vfs.is_file(chemin):
            data = vfs.read_bytes(chemin)
            suffix = Path(chemin).suffix or ".bin"
            tmp = tempfile.NamedTemporaryFile(
                delete=False, suffix=suffix, prefix="promethee_ocr_"
            )
            tmp.write(data)
            tmp.close()
            _TMP_FILES.append(tmp.name)
            return Path(tmp.name), True
    except Exception:
        pass  # VFS indisponible ou chemin absent → l'appelant gère l'erreur

    return real, False


# ── Import conditionnel du moteur OCR ─────────────────────────────────────────

def _get_ocr_engine():
    """
    Importe ocr_engine depuis core/ de façon robuste.
    Retourne le module ou None si les dépendances sont absentes.
    """
    try:
        from core import ocr_engine
        return ocr_engine
    except ImportError:
        return None


def _ocr_available() -> tuple[bool, str]:
    """
    Vérifie la disponibilité de l'OCR.
    Retourne (disponible, message_erreur).
    """
    engine = _get_ocr_engine()
    if engine is None:
        return False, (
            "Module ocr_engine introuvable. "
            "Vérifiez que les dépendances sont accessibles (core/ocr_engine.py)."
        )
    if not engine.is_available():
        return False, (
            "Tesseract non disponible. "
            "Installez : apt install tesseract-ocr tesseract-ocr-fra ; "
            "pip install pytesseract pillow"
        )
    return True, ""


def _truncate(text: str, max_chars: int = _MAX_RESULT_CHARS) -> tuple[str, bool]:
    """Tronque le texte si nécessaire. Retourne (texte, tronqué)."""
    if len(text) <= max_chars:
        return text, False
    return (
        text[:max_chars].rstrip()
        + f"\n\n[… texte tronqué : {len(text):,} → {max_chars:,} caractères]",
        True,
    )


# ══════════════════════════════════════════════════════════════════════════════
# OUTILS
# ══════════════════════════════════════════════════════════════════════════════

@tool(
    name="ocr_image",
    description=(
        "Extrait le texte d'un fichier image via OCR (Tesseract). "
        "Supporte PNG, JPG, TIFF, BMP, WebP et la plupart des formats courants. "
        "Utile pour lire des captures d'écran, photos de documents, "
        "tableaux scannés, formulaires papier numérisés. "
        "Pour les PDFs scannés, utiliser ocr_pdf à la place."
    ),
    parameters={
        "type": "object",
        "properties": {
            "chemin": {
                "type": "string",
                "description": (
                    "Chemin absolu ou relatif vers le fichier image. "
                    "Exemple : '/home/user/Documents/scan.png'"
                ),
            },
            "langues": {
                "type": "string",
                "description": (
                    f"Langues Tesseract à utiliser, séparées par '+' (défaut: '{_DEFAULT_LANG}'). "
                    "Exemples : 'fra', 'eng', 'fra+eng', 'deu'. "
                    "Utiliser ocr_languages pour voir les langues disponibles."
                ),
            },
            "confiance_min": {
                "type": "integer",
                "description": (
                    "Seuil de confiance minimum (0-100) pour inclure un mot (défaut: 0 = tout inclure). "
                    "Augmenter à 60-70 pour filtrer les reconnaissances douteuses."
                ),
            },
        },
        "required": ["chemin"],
    },
)
def ocr_image(
    chemin: str,
    langues: str = _DEFAULT_LANG,
    confiance_min: int = 0,
) -> dict:
    ok, err = _ocr_available()
    if not ok:
        return {"status": "error", "error": err}

    path, _from_vfs = _resolve_path(chemin)

    if not path.exists():
        return {"status": "error", "error": f"Fichier introuvable : {chemin}"}

    if not path.is_file():
        return {"status": "error", "error": f"Le chemin ne pointe pas vers un fichier : {chemin}"}

    ext = Path(chemin).suffix.lower()  # extension d'origine, pas du tmp
    if ext not in _IMAGE_EXTENSIONS:
        return {
            "status": "error",
            "error": (
                f"Extension '{ext}' non supportée. "
                f"Extensions valides : {', '.join(sorted(_IMAGE_EXTENSIONS))}"
            ),
        }

    engine = _get_ocr_engine()

    try:
        if confiance_min > 0:
            # Mode avec filtrage par confiance
            data, err = engine.detect_text_confidence(str(path), lang=langues)
            if err:
                return {"status": "error", "error": err}

            # Filtrer les mots sous le seuil
            mots_filtres = [
                w["text"] for w in data["words"]
                if w["confidence"] >= confiance_min
            ]
            texte = " ".join(mots_filtres)
            confiance_moyenne = data["confidence"]
            nb_mots = data["total_words"]
        else:
            # Mode standard : texte brut complet
            texte, err = engine.extract_text_from_image(str(path), lang=langues)
            if err:
                return {"status": "error", "error": err}
            confiance_moyenne = None
            nb_mots = len(texte.split()) if texte else 0

        if not texte:
            return {
                "status":  "success",
                "fichier": str(path),
                "texte":   "",
                "nb_mots": 0,
                "message": "Aucun texte détecté dans l'image.",
            }

        texte, tronque = _truncate(texte)

        result = {
            "status":  "success",
            "fichier": str(path),
            "langues": langues,
            "texte":   texte,
            "nb_mots": nb_mots,
            "tronque": tronque,
        }
        if confiance_moyenne is not None:
            result["confiance_moyenne"] = confiance_moyenne

        return result

    except Exception as e:
        return {"status": "error", "error": f"Erreur OCR : {e}"}


@tool(
    name="ocr_pdf",
    description=(
        "Extrait le texte d'un fichier PDF. "
        "Pour les pages numériques (texte sélectionnable), extrait directement le texte. "
        "Pour les pages scannées (images), applique automatiquement l'OCR Tesseract. "
        "Gère les PDFs mixtes (certaines pages numériques, d'autres scannées). "
        "Retourne le texte page par page avec indication de la méthode utilisée."
    ),
    parameters={
        "type": "object",
        "properties": {
            "chemin": {
                "type": "string",
                "description": "Chemin absolu ou relatif vers le fichier PDF.",
            },
            "langues": {
                "type": "string",
                "description": (
                    f"Langues pour l'OCR des pages scannées (défaut: '{_DEFAULT_LANG}'). "
                    "Ignoré pour les pages avec texte natif."
                ),
            },
            "pages_max": {
                "type": "integer",
                "description": (
                    f"Nombre maximum de pages à traiter (défaut: {_DEFAULT_MAX_PAGES}). "
                    "Pour les PDFs volumineux, réduire pour limiter le temps de traitement."
                ),
            },
            "pages": {
                "type": "string",
                "description": (
                    "Pages spécifiques à extraire, au format '1-3,5,8-10' (numérotation à partir de 1). "
                    "Si absent, traite toutes les pages jusqu'à pages_max."
                ),
            },
        },
        "required": ["chemin"],
    },
)
def ocr_pdf(
    chemin: str,
    langues: str = _DEFAULT_LANG,
    pages_max: int = _DEFAULT_MAX_PAGES,
    pages: Optional[str] = None,
) -> dict:
    ok, err = _ocr_available()
    if not ok:
        return {"status": "error", "error": err}

    path, _from_vfs = _resolve_path(chemin)

    if not path.exists():
        return {"status": "error", "error": f"Fichier introuvable : {chemin}"}

    if Path(chemin).suffix.lower() != ".pdf":  # vérifier l'extension d'origine
        return {
            "status": "error",
            "error": (
                f"Ce fichier n'est pas un PDF (extension : '{path.suffix}'). "
                "Utilisez ocr_image pour les fichiers image."
            ),
        }

    engine = _get_ocr_engine()

    # Parser la sélection de pages si fournie
    pages_indices: Optional[list[int]] = None
    if pages:
        try:
            pages_indices = []
            for part in pages.split(","):
                part = part.strip()
                if "-" in part:
                    start, end = part.split("-", 1)
                    pages_indices.extend(range(int(start) - 1, int(end)))
                else:
                    pages_indices.append(int(part) - 1)
            pages_indices = sorted(set(p for p in pages_indices if p >= 0))
        except ValueError:
            return {
                "status": "error",
                "error": (
                    f"Format de sélection de pages invalide : '{pages}'. "
                    "Utilisez le format '1-3,5,8-10'."
                ),
            }

    try:
        # Utiliser extract_text_from_pdf qui gère déjà le mixte natif/OCR
        if pages_indices is not None:
            # Traitement page par page pour respecter la sélection
            try:
                import fitz
                from PIL import Image
                import io

                doc    = fitz.open(str(path))
                total  = len(doc)
                textes = []
                ocr_count = 0
                nat_count = 0

                for idx in pages_indices[:pages_max]:
                    if idx >= total:
                        continue
                    page    = doc[idx]
                    txt_nat = page.get_text().strip()

                    if len(txt_nat) >= 50:
                        textes.append(f"--- Page {idx + 1} (natif) ---\n{txt_nat}")
                        nat_count += 1
                    else:
                        import pytesseract
                        pix     = page.get_pixmap(matrix=fitz.Matrix(300 / 72, 300 / 72))
                        img     = Image.open(io.BytesIO(pix.tobytes("png")))
                        txt_ocr = pytesseract.image_to_string(
                            img, lang=langues, config="--oem 3 --psm 3"
                        ).strip()
                        textes.append(f"--- Page {idx + 1} (OCR) ---\n{txt_ocr}")
                        ocr_count += 1

                doc.close()
                texte_final = "\n\n".join(textes)
                nb_pages_traitees = len(textes)

            except ImportError as e:
                return {"status": "error", "error": f"Dépendance manquante : {e}"}
        else:
            texte_final, err = engine.extract_text_from_pdf(
                str(path), lang=langues, max_pages=pages_max
            )
            if err:
                return {"status": "error", "error": err}

            # Compter pages OCR vs natives depuis les marqueurs insérés par ocr_engine
            ocr_count = texte_final.count("(OCR)") if texte_final else 0
            nat_count = texte_final.count("(natif)") if texte_final else 0
            nb_pages_traitees = ocr_count + nat_count

        if not texte_final:
            return {
                "status":  "success",
                "fichier": str(path),
                "texte":   "",
                "message": "Aucun texte détecté dans le PDF.",
            }

        texte_final, tronque = _truncate(texte_final)

        return {
            "status":            "success",
            "fichier":           str(path),
            "langues_ocr":       langues,
            "nb_pages_traitees": nb_pages_traitees,
            "texte":             texte_final,
            "tronque":           tronque,
        }

    except Exception as e:
        return {"status": "error", "error": f"Erreur extraction PDF : {e}"}


@tool(
    name="ocr_pdf_detect",
    description=(
        "Analyse un PDF et détecte s'il contient du texte natif (numérique), "
        "des pages scannées (images) ou un mélange des deux. "
        "Rapide car n'effectue pas d'OCR — utile avant d'appeler ocr_pdf "
        "pour adapter les paramètres."
    ),
    parameters={
        "type": "object",
        "properties": {
            "chemin": {
                "type": "string",
                "description": "Chemin vers le fichier PDF à analyser.",
            },
        },
        "required": ["chemin"],
    },
)
def ocr_pdf_detect(chemin: str) -> dict:
    path, _from_vfs = _resolve_path(chemin)

    if not path.exists():
        return {"status": "error", "error": f"Fichier introuvable : {chemin}"}

    if Path(chemin).suffix.lower() != ".pdf":
        return {"status": "error", "error": f"Ce fichier n'est pas un PDF : {chemin}"}

    engine = _get_ocr_engine()
    if engine is None:
        return {"status": "error", "error": "Module ocr_engine introuvable."}

    try:
        type_pdf = engine.detect_pdf_type(str(path))

        _descriptions = {
            "text":    "PDF numérique — texte natif, extraction directe sans OCR.",
            "scanned": "PDF scanné — pages en images, OCR nécessaire.",
            "mixed":   "PDF mixte — certaines pages numériques, d'autres scannées.",
            "unknown": "Type indéterminé (PDF vide ou inaccessible).",
        }

        # Compter le nombre total de pages
        try:
            import fitz
            doc        = fitz.open(str(path))
            nb_pages   = len(doc)
            taille_mo  = round(path.stat().st_size / 1024 / 1024, 2)
            doc.close()
        except Exception:
            nb_pages  = None
            taille_mo = None

        result = {
            "status":      "success",
            "fichier":     str(path),
            "type":        type_pdf,
            "description": _descriptions.get(type_pdf, ""),
            "ocr_requis":  type_pdf in ("scanned", "mixed"),
        }
        if nb_pages is not None:
            result["nb_pages"] = nb_pages
        if taille_mo is not None:
            result["taille_mo"] = taille_mo

        return result

    except Exception as e:
        return {"status": "error", "error": f"Erreur analyse PDF : {e}"}


@tool(
    name="ocr_languages",
    description=(
        "Liste les langues Tesseract disponibles sur le système. "
        "Utile pour vérifier quelles langues peuvent être utilisées "
        "dans les paramètres 'langues' des outils ocr_image et ocr_pdf."
    ),
    parameters={
        "type": "object",
        "properties": {},
        "required": [],
    },
)
def ocr_languages() -> dict:
    ok, err = _ocr_available()
    if not ok:
        return {"status": "error", "error": err}

    engine = _get_ocr_engine()

    try:
        langues = engine.get_supported_languages()

        # Noms lisibles pour les langues courantes
        _noms = {
            "fra": "Français",
            "eng": "Anglais",
            "deu": "Allemand",
            "spa": "Espagnol",
            "ita": "Italien",
            "por": "Portugais",
            "nld": "Néerlandais",
            "ara": "Arabe",
            "chi_sim": "Chinois simplifié",
            "chi_tra": "Chinois traditionnel",
            "jpn": "Japonais",
            "rus": "Russe",
            "osd": "Détection d'orientation (OSD)",
        }

        langues_detail = [
            {"code": lang, "nom": _noms.get(lang, lang)}
            for lang in sorted(langues)
        ]

        return {
            "status":          "success",
            "nb_langues":      len(langues),
            "langue_defaut":   _DEFAULT_LANG,
            "langues":         langues_detail,
            "conseil":         (
                "Combinez plusieurs langues avec '+' pour de meilleurs résultats "
                "sur les documents multilingues. Exemple : 'fra+eng'."
            ),
        }

    except Exception as e:
        return {"status": "error", "error": f"Erreur listage langues : {e}"}
