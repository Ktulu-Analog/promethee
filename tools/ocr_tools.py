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
tools/ocr_tools.py — OCR : extraction de texte depuis images et PDF scannés
============================================================================

Outils exposés (4) :

  - ocr_image          : extrait le texte d'un fichier image (PNG, JPG, TIFF, BMP…)
  - ocr_pdf            : extrait le texte d'un PDF, en utilisant l'OCR sur les pages
                         scannées et l'extraction native sur les pages numériques
  - ocr_pdf_detect     : détecte le type d'un PDF (numérique / scanné / mixte)
                         sans extraire le texte
  - ocr_languages      : liste les langues Tesseract disponibles sur le système

Ce module est un pont vers ui/widgets/ocr_engine.py qui contient la logique
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

import sys
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
    "ocr_vision_openrouter": "👁️",
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


# ── Import conditionnel du moteur OCR ─────────────────────────────────────────

def _get_ocr_engine():
    """
    Importe ocr_engine depuis ui/widgets/ de façon robuste.
    Retourne le module ou None si les dépendances sont absentes.
    """
    try:
        # Ajouter la racine du projet au path si nécessaire
        project_root = Path(__file__).parent.parent
        if str(project_root) not in sys.path:
            sys.path.insert(0, str(project_root))
        from ui.widgets import ocr_engine
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
            "Vérifiez que les dépendances UI sont accessibles."
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

    path = Path(chemin).expanduser().resolve()

    if not path.exists():
        return {"status": "error", "error": f"Fichier introuvable : {chemin}"}

    if not path.is_file():
        return {"status": "error", "error": f"Le chemin ne pointe pas vers un fichier : {chemin}"}

    ext = path.suffix.lower()
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

    path = Path(chemin).expanduser().resolve()

    if not path.exists():
        return {"status": "error", "error": f"Fichier introuvable : {chemin}"}

    if path.suffix.lower() != ".pdf":
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
    path = Path(chemin).expanduser().resolve()

    if not path.exists():
        return {"status": "error", "error": f"Fichier introuvable : {chemin}"}

    if path.suffix.lower() != ".pdf":
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

# ══════════════════════════════════════════════════════════════════════════════
# VISION MULTIMODALE (OPENROUTER / CLAUDE 3.5 SONNET)
# ══════════════════════════════════════════════════════════════════════════════

import base64
import os
import requests

# Prompt système scientifique injecté automatiquement avant le prompt utilisateur
_SCIENTIFIC_SYSTEM_PROMPT = (
    "Analyse cette copie de physique-chimie. "
    "Transcris fidèlement tout le texte, les formules, les équations de réaction et les calculs "
    "en utilisant le formatage LaTeX (avec les délimiteurs $ et $$). "
    "Décris de manière exhaustive les schémas présents : "
    "topologie des circuits électriques (vérifie le respect de la convention récepteur/générateur "
    "européenne avec des flèches de tension et d'intensité parfaitement droites), "
    "allures des courbes de titrage (points d'équivalence, sauts de pH), "
    "mécanismes réactionnels (flèches courbes) et tracés de vecteurs (forces, vitesses). "
    "Ne juge pas encore, fournis uniquement une retranscription textuelle et géométrique absolue."
)

@tool(
    name="ocr_vision_openrouter",
    description=(
        "Extrait le texte, analyse les schémas et évalue les copies manuscrites "
        "via un modèle Vision scientifique sur OpenRouter "
        "(par défaut qwen/qwen3-vl-235b-a22b-thinking, 235B paramètres, spécialisé STEM). "
        "À utiliser en relais de ocr_image quand l'intelligence est requise : "
        "copie d'élève raturée, montage expérimental dessiné, circuits électriques, "
        "courbes de titrage, formules de Lewis, vecteurs. "
        "Attention : ce modèle est payant (API OpenRouter), utilisez-le de façon ciblée."
    ),
    parameters={
        "type": "object",
        "properties": {
            "chemin": {
                "type": "string",
                "description": "Chemin absolu vers l'image à analyser (png, jpg, webp, etc.)."
            },
            "prompt": {
                "type": "string",
                "description": (
                    "Instructions spécifiques pour le modèle vision (en plus du prompt scientifique injecté). "
                    "Exemples : 'Transcris cette copie d\'élève fidèlement', "
                    "'Que représente ce schéma de TP ?', 'Évalue cette réponse en fonction du BO.'"
                )
            },
            "model": {
                "type": "string",
                "description": "Modèle OpenRouter à utiliser (défaut: 'qwen/qwen3-vl-235b-a22b-thinking').",
                "default": "qwen/qwen3-vl-235b-a22b-thinking"
            }
        },
        "required": ["chemin", "prompt"],
    },
)
def ocr_vision_openrouter(chemin: str, prompt: str, model: str = "qwen/qwen3-vl-235b-a22b-thinking") -> dict:
    from core.tools_engine import report_progress
    report_progress(f"Analyse vision de l'image (modèle {model})...")

    # Table de correspondance MIME complète pour toutes les extensions supportées
    _MIME_MAP = {
        ".png": "image/png", ".webp": "image/webp",
        ".gif": "image/gif", ".tiff": "image/tiff", ".tif": "image/tiff",
        ".bmp": "image/bmp", ".ppm": "image/x-portable-pixmap",
        ".pgm": "image/x-portable-graymap",
    }
    
    path = Path(chemin).expanduser().resolve()
    if not path.exists() or not path.is_file():
        return {"status": "error", "error": f"Fichier introuvable : {chemin}"}

    ext = path.suffix.lower()
    if ext not in _IMAGE_EXTENSIONS:
        return {"status": "error", "error": f"Format image non supporté : {ext}"}
        
    # Récupérer la clé API OpenRouter — PAS de fallback sur OPENAI_API_KEY (risque 401)
    api_key = getattr(Config, "OPENROUTER_API_KEY", None) or os.getenv("OPENROUTER_API_KEY")

    if not api_key:
        return {
            "status": "error",
            "error": (
                "Variable OPENROUTER_API_KEY introuvable. "
                "Ajoutez OPENROUTER_API_KEY=sk-or-... dans votre fichier .env"
            ),
        }

    # Encoder l'image en base 64
    try:
        with open(path, "rb") as image_file:
            encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
    except Exception as e:
        return {"status": "error", "error": f"Erreur lecture fichier: {e}"}

    # Déterminer le mime type via la table complète
    mime_type = _MIME_MAP.get(ext, "image/jpeg")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": "https://github.com/Ktulu-Analog/promethee", # Required by OpenRouter
        "X-Title": "Promethee AI Physique-Chimie",
        "Content-Type": "application/json"
    }

    # Construire le prompt complet : prompt système scientifique + prompt utilisateur
    full_prompt = f"{_SCIENTIFIC_SYSTEM_PROMPT}\n\n{prompt}"

    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": full_prompt
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{mime_type};base64,{encoded_string}"
                        }
                    }
                ]
            }
        ]
    }

    try:
        response = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload, timeout=60)
        response.raise_for_status()
        result = response.json()
        
        reply = result["choices"][0]["message"]["content"]
        
        return {
            "status": "success",
            "fichier": str(path),
            "model_used": model,
            "texte": reply
        }
    except requests.exceptions.RequestException as e:
        error_msg = str(e)
        if hasattr(e, 'response') and e.response is not None:
             error_msg += f" - Response: {e.response.text}"
        return {"status": "error", "error": f"Erreur API Vision OpenRouter: {error_msg}"}
    except Exception as e:
        return {"status": "error", "error": f"Erreur inattendue API Vision: {e}"}

