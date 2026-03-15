#!/usr/bin/env python3
"""
ingest3.py — Script CLI interactif pour indexer un répertoire dans Qdrant

Usage:
    python ingest3.py                                            # Mode interactif
    python ingest3.py /path --collection ma_collection          # Mode direct
    python ingest3.py /path --collection ma_collection --no-ctx # Désactiver le chunking contextuel

Améliorations RAG intégrées :
    • Chunking hybride sémantique (réutilise rag_engine._chunk_text)
    • Chunking contextuel LLM (Anthropic Contextual Retrieval) si RAG_CONTEXTUAL_CHUNKING=ON
      → enrichit chaque chunk d'un préfixe contextuel avant l'embedding
      → activable/désactivable via --ctx / --no-ctx en ligne de commande

Dépendances OCR (optionnelles) :
    pip install pytesseract pdf2image
    Tesseract doit être installé sur le système :
        Ubuntu/Debian : sudo apt install tesseract-ocr tesseract-ocr-fra
        macOS         : brew install tesseract
        Windows       : https://github.com/UB-Mannheim/tesseract/wiki
"""
import os
import sys
import argparse
from pathlib import Path
from typing import List, Optional
from dotenv import load_dotenv

# Chercher le .env à la racine du projet (dossier parent de scripts/)
_env_candidates = [
    Path(__file__).parent.parent / ".env",  # …/promethee/.env
    Path(".env"),
]
for _ep in _env_candidates:
    if _ep.exists():
        load_dotenv(_ep)
        break
else:
    load_dotenv()

# Import des fonctions nécessaires
try:
    from qdrant_client import QdrantClient
    from qdrant_client.models import Distance, VectorParams, PointStruct
    QDRANT_OK = True
except ImportError:
    print("❌ Erreur : qdrant-client non installé")
    print("   Installez avec : pip install qdrant-client")
    sys.exit(1)

try:
    from openai import OpenAI
    OPENAI_OK = True
except ImportError:
    print("❌ Erreur : openai non installé")
    print("   Installez avec : pip install openai")
    sys.exit(1)

# Import du chunker hybride et du générateur de contexte depuis rag_engine.
# On ajoute le dossier parent (racine du projet) au path pour permettre
# l'import même quand le script est lancé directement depuis scripts/.
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
try:
    from promethee.core.rag_engine import _chunk_text, _contextual_prefix_batch
    RAG_ENGINE_OK = True
except ImportError:
    RAG_ENGINE_OK = False  # Fallback sur le chunker local si rag_engine indisponible

import uuid
import re

# Vérification des dépendances OCR (optionnelles mais recommandées pour les PDF scannés)
try:
    import pytesseract
    PYTESSERACT_OK = True
except ImportError:
    PYTESSERACT_OK = False

try:
    from pdf2image import convert_from_path
    PDF2IMAGE_OK = True
except ImportError:
    PDF2IMAGE_OK = False

try:
    from tqdm import tqdm
    TQDM_OK = True
except ImportError:
    TQDM_OK = False


# ══════════════════════════════════════════════════════════════════════
#  Configuration depuis les variables d'environnement
# ══════════════════════════════════════════════════════════════════════

QDRANT_URL         = os.getenv("QDRANT_URL", "http://localhost:6333")
EMBEDDING_API_BASE = os.getenv("EMBEDDING_API_BASE", "https://api.openai.com/v1")
OPENAI_API_KEY     = os.getenv("OPENAI_API_KEY", "")
EMBEDDING_MODEL    = os.getenv("EMBEDDING_MODEL", "text-embedding-ada-002")
EMBEDDING_DIMENSION = int(os.getenv("EMBEDDING_DIMENSION", "1536"))

# LLM pour le chunking contextuel (même modèle que le moteur principal)
OPENAI_API_BASE    = os.getenv("OPENAI_API_BASE", "")
OPENAI_MODEL       = os.getenv("OPENAI_MODEL", "")
LOCAL              = os.getenv("LOCAL", "OFF").strip().upper() == "ON"
OLLAMA_BASE_URL    = os.getenv("OLLAMA_BASE_URL", "")
OLLAMA_MODEL       = os.getenv("OLLAMA_MODEL", "")

# Modèle dédié au chunking contextuel (ingestion).
# Si vide, utilise OPENAI_MODEL. Recommandé : modèle léger (ex: Mistral-Small-3.2-24B)
RAG_INGESTION_MODEL = os.getenv("RAG_INGESTION_MODEL", "").strip()

# Chunking contextuel (Anthropic Contextual Retrieval)
RAG_CONTEXTUAL_CHUNKING          = os.getenv("RAG_CONTEXTUAL_CHUNKING", "OFF").strip().upper() == "ON"
RAG_CONTEXTUAL_PREFIX_MAX_TOKENS = int(os.getenv("RAG_CONTEXTUAL_PREFIX_MAX_TOKENS", "100"))
RAG_CONTEXTUAL_DOC_MAX_CHARS     = int(os.getenv("RAG_CONTEXTUAL_DOC_MAX_CHARS", "10000"))

# Configuration pour l'insertion dans Qdrant
QDRANT_BATCH_SIZE  = int(os.getenv("QDRANT_BATCH_SIZE", "100"))
QDRANT_MAX_RETRIES = int(os.getenv("QDRANT_MAX_RETRIES", "3"))
QDRANT_TIMEOUT     = int(os.getenv("QDRANT_TIMEOUT", "60"))

# Configuration OCR
OCR_TEXT_THRESHOLD = int(os.getenv("OCR_TEXT_THRESHOLD", "100"))
OCR_LANG           = os.getenv("OCR_LANG", "fra+eng")
OCR_DPI            = int(os.getenv("OCR_DPI", "300"))

# Extensions de fichiers supportées
SUPPORTED_EXTENSIONS = {
    '.txt', '.md', '.markdown', '.rst',
    '.py', '.js', '.jsx', '.ts', '.tsx',
    '.json', '.yaml', '.yml', '.xml',
    '.csv', '.tsv',
    '.pdf',
    '.docx', '.doc',
    '.html', '.htm',
}


# ══════════════════════════════════════════════════════════════════════
#  Interface utilisateur
# ══════════════════════════════════════════════════════════════════════

class Colors:
    """Codes couleur ANSI pour un affichage coloré."""
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    END = '\033[0m'


def print_header(text: str):
    """Affiche un en-tête stylisé."""
    msg = f"\n{Colors.BOLD}{Colors.CYAN}{'═' * 70}{Colors.END}\n{Colors.BOLD}{Colors.CYAN}  {text}{Colors.END}\n{Colors.BOLD}{Colors.CYAN}{'═' * 70}{Colors.END}\n"
    (tqdm.write if TQDM_OK else print)(msg)


def print_section(text: str):
    """Affiche un titre de section."""
    msg = f"\n{Colors.BOLD}{Colors.BLUE}▶ {text}{Colors.END}"
    (tqdm.write if TQDM_OK else print)(msg)


def print_success(text: str):
    """Affiche un message de succès."""
    msg = f"{Colors.GREEN}✓ {text}{Colors.END}"
    (tqdm.write if TQDM_OK else print)(msg)


def print_error(text: str):
    """Affiche un message d'erreur."""
    msg = f"{Colors.RED}✗ {text}{Colors.END}"
    (tqdm.write if TQDM_OK else print)(msg)


def print_warning(text: str):
    """Affiche un avertissement."""
    msg = f"{Colors.YELLOW}⚠ {text}{Colors.END}"
    (tqdm.write if TQDM_OK else print)(msg)


def print_info(text: str):
    """Affiche une information."""
    msg = f"{Colors.CYAN}ℹ {text}{Colors.END}"
    (tqdm.write if TQDM_OK else print)(msg)


def prompt_input(text: str, default: str = None) -> str:
    """Demande une saisie utilisateur avec valeur par défaut."""
    if default:
        prompt = f"{Colors.BOLD}{text}{Colors.END} [{default}]: "
    else:
        prompt = f"{Colors.BOLD}{text}{Colors.END}: "

    value = input(prompt).strip()
    return value if value else default


def prompt_yes_no(text: str, default: bool = True) -> bool:
    """Demande une confirmation oui/non."""
    default_str = "O/n" if default else "o/N"
    prompt = f"{Colors.BOLD}{text}{Colors.END} [{default_str}]: "

    while True:
        response = input(prompt).strip().lower()
        if not response:
            return default
        if response in ['o', 'oui', 'y', 'yes']:
            return True
        if response in ['n', 'non', 'no']:
            return False
        print_error("Réponse invalide. Utilisez 'o' ou 'n'.")


def prompt_choice(text: str, choices: list, default: int = 0) -> int:
    """Demande un choix parmi une liste."""
    print(f"\n{Colors.BOLD}{text}{Colors.END}")
    for i, choice in enumerate(choices, 1):
        marker = "▸" if i == default + 1 else " "
        print(f"  {marker} {i}. {choice}")

    while True:
        response = prompt_input("Votre choix", str(default + 1))
        try:
            choice = int(response)
            if 1 <= choice <= len(choices):
                return choice - 1
            print_error(f"Choisissez un nombre entre 1 et {len(choices)}.")
        except ValueError:
            print_error("Veuillez entrer un nombre valide.")


def show_banner():
    """Affiche la bannière du script."""
    banner = f"""
{Colors.BOLD}{Colors.CYAN}
╔═══════════════════════════════════════════════════════════════════════╗
║                                                                       ║
║              📚  QDRANT DIRECTORY INDEXER  📚                        ║
║                                                                       ║
║          Indexation de répertoires dans Qdrant                       ║
║          avec génération d'embeddings vectoriels                     ║
║                                                                       ║
╚═══════════════════════════════════════════════════════════════════════╝
{Colors.END}
"""
    print(banner)


def show_config():
    """Affiche la configuration actuelle."""
    print_section("Configuration actuelle")
    print(f"  • Qdrant URL       : {Colors.CYAN}{QDRANT_URL}{Colors.END}")
    print(f"  • API Embeddings   : {Colors.CYAN}{EMBEDDING_API_BASE}{Colors.END}")
    print(f"  • Modèle embedding : {Colors.CYAN}{EMBEDDING_MODEL}{Colors.END}")
    print(f"  • Dimension        : {Colors.CYAN}{EMBEDDING_DIMENSION}{Colors.END}")
    print(f"  • API Key définie  : {Colors.GREEN if OPENAI_API_KEY else Colors.RED}{'Oui' if OPENAI_API_KEY else 'Non'}{Colors.END}")

    # Chunker hybride
    chunker_label = "rag_engine._chunk_text (hybride sémantique)" if RAG_ENGINE_OK else "chunk_text local (fallback)"
    chunker_color = Colors.GREEN if RAG_ENGINE_OK else Colors.YELLOW
    print(f"  • Chunker          : {chunker_color}{chunker_label}{Colors.END}")

    # Chunking contextuel
    ctx_active = RAG_CONTEXTUAL_CHUNKING
    ctx_color  = Colors.GREEN if ctx_active else Colors.YELLOW
    ctx_label  = f"Activé (préfixe ≤{RAG_CONTEXTUAL_PREFIX_MAX_TOKENS} tokens, doc ≤{RAG_CONTEXTUAL_DOC_MAX_CHARS} chars)" if ctx_active else "Désactivé (RAG_CONTEXTUAL_CHUNKING=OFF)"
    print(f"  • Chunking contextuel : {ctx_color}{ctx_label}{Colors.END}")
    if ctx_active:
        effective_model = RAG_INGESTION_MODEL or (OLLAMA_MODEL if LOCAL else OPENAI_MODEL) or "(non défini)"
        llm_label = f"{'Ollama' if LOCAL else 'OpenAI-compat'} · {effective_model}"
        if RAG_INGESTION_MODEL:
            llm_label += f"  {Colors.CYAN}(RAG_INGESTION_MODEL){Colors.END}"
        else:
            llm_label += f"  {Colors.YELLOW}(modèle principal — pensez à définir RAG_INGESTION_MODEL){Colors.END}"
        print(f"    └ LLM contexte : {Colors.CYAN}{llm_label}")

    # OCR
    ocr_available = PYTESSERACT_OK and PDF2IMAGE_OK
    ocr_status = Colors.GREEN if ocr_available else Colors.YELLOW
    ocr_label = "Disponible" if ocr_available else "Non disponible"
    if not PYTESSERACT_OK:
        ocr_label += " (pytesseract manquant)"
    if not PDF2IMAGE_OK:
        ocr_label += " (pdf2image manquant)"
    print(f"  • OCR Tesseract    : {ocr_status}{ocr_label}{Colors.END}")
    if ocr_available:
        print(f"  • OCR Langue       : {Colors.CYAN}{OCR_LANG}{Colors.END}")
        print(f"  • OCR DPI          : {Colors.CYAN}{OCR_DPI}{Colors.END}")
        print(f"  • Seuil texte PDF  : {Colors.CYAN}{OCR_TEXT_THRESHOLD} caractères{Colors.END}")


# ══════════════════════════════════════════════════════════════════════
#  OCR — Extraction de texte par Tesseract sur PDF scanné
# ══════════════════════════════════════════════════════════════════════

def ocr_pdf(file_path: Path, lang: str = None, dpi: int = None) -> str:
    """
    Convertit un PDF page par page en image puis applique l'OCR Tesseract.

    Args:
        file_path : chemin vers le fichier PDF
        lang      : langue(s) Tesseract (ex: "fra+eng"). None → utilise OCR_LANG
        dpi       : résolution de conversion PDF→image. None → utilise OCR_DPI

    Returns:
        Texte extrait par OCR, ou chaîne vide si l'OCR est indisponible/échoue.
    """
    if lang is None:
        lang = OCR_LANG
    if dpi is None:
        dpi = OCR_DPI

    if not PYTESSERACT_OK:
        print_warning("pytesseract non installé — OCR impossible")
        print_warning("  Installez avec : pip install pytesseract")
        return ""

    if not PDF2IMAGE_OK:
        print_warning("pdf2image non installé — OCR impossible")
        print_warning("  Installez avec : pip install pdf2image")
        return ""

    # Vérifier que Tesseract est accessible sur le système
    try:
        pytesseract.get_tesseract_version()
    except pytesseract.TesseractNotFoundError:
        print_warning("Tesseract introuvable sur le système.")
        print_warning("  Ubuntu/Debian : sudo apt install tesseract-ocr tesseract-ocr-fra")
        print_warning("  macOS         : brew install tesseract")
        return ""

    try:
        print_info(f"  OCR en cours (DPI={dpi}, lang={lang})…")
        images = convert_from_path(str(file_path), dpi=dpi)
    except Exception as e:
        print_warning(f"  Conversion PDF→image échouée : {e}")
        return ""

    pages_text = []
    for page_num, image in enumerate(images, start=1):
        try:
            page_text = pytesseract.image_to_string(image, lang=lang)
            pages_text.append(page_text)
        except Exception as e:
            print_warning(f"  OCR page {page_num} échoué : {e}")
            pages_text.append("")  # page vide plutôt que d'arrêter tout le document

    full_text = "\n\n".join(pages_text)
    return full_text


# ══════════════════════════════════════════════════════════════════════
#  Utilitaires
# ══════════════════════════════════════════════════════════════════════

def chunk_text(text: str, chunk_size: int = 500, overlap: int = 80) -> List[str]:
    """Découpe le texte en chunks.

    Délègue au chunker hybride sémantique de rag_engine (_chunk_text) si disponible.
    Ce chunker gère correctement texte courant, code, tableaux et listes,
    avec une mesure de la taille en tokens plutôt qu'en caractères.

    Fallback : découpage basique par phrases si rag_engine n'est pas importable
    (ex : script lancé hors du projet Prométhée).
    """
    if RAG_ENGINE_OK:
        # max_tokens=256 ≈ ~900 chars — cohérent avec ingest_text() de rag_engine
        return _chunk_text(text, max_tokens=256, overlap_tokens=32, hard_max_tokens=512)

    # ── Fallback : découpage basique par phrases ──────────────────────
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    chunks, current, length = [], [], 0
    for s in sentences:
        current.append(s)
        length += len(s)
        if length >= chunk_size:
            chunks.append(" ".join(current))
            current = current[-2:] if len(current) > 2 else []
            length = sum(len(x) for x in current)
    if current:
        chunks.append(" ".join(current))
    return chunks


def get_embeddings(texts: List[str], client: OpenAI, model: str) -> List[List[float]]:
    """Génère les embeddings via l'API OpenAI-compatible."""
    if not texts:
        return []

    try:
        batch_size = 64
        all_embeddings = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            response = client.embeddings.create(
                input=batch,
                model=model,
                encoding_format="float",
            )
            all_embeddings.extend(item.embedding for item in response.data)
        return all_embeddings
    except Exception as e:
        print_error(f"Erreur lors de la génération des embeddings : {e}")
        return []


def extract_text_from_pdf(file_path: Path) -> tuple[str, bool]:
    """
    Extrait le texte d'un PDF.

    Stratégie :
      1. Extraction directe du texte numérique via PyMuPDF (fitz).
      2. Si le texte extrait est trop court (PDF scanné ou image),
         bascule automatiquement sur l'OCR Tesseract.

    Returns:
        (texte extrait, ocr_utilisé: bool)
    """
    text = ""
    ocr_used = False

    # ── Étape 1 : extraction native du texte (PyMuPDF) ──────────────
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(str(file_path))
        text = "\n".join(page.get_text() for page in doc)
        doc.close()
    except ImportError:
        print_warning(f"PyMuPDF non installé, impossible d'extraire le texte natif de {file_path.name}")
        print_warning("  Installez avec : pip install pymupdf")
    except Exception as e:
        print_warning(f"Erreur PyMuPDF sur {file_path.name} : {e}")

    # ── Étape 2 : fallback OCR si le texte extrait est insuffisant ───
    if len(text.strip()) < OCR_TEXT_THRESHOLD:
        if len(text.strip()) == 0:
            print_info(f"  PDF sans texte natif détecté → OCR Tesseract")
        else:
            print_info(
                f"  Texte natif insuffisant ({len(text.strip())} car. < seuil {OCR_TEXT_THRESHOLD}) "
                f"→ OCR Tesseract"
            )

        ocr_text = ocr_pdf(file_path)

        if ocr_text and len(ocr_text.strip()) > len(text.strip()):
            text = ocr_text
            ocr_used = True
        elif not ocr_text:
            # L'OCR n'a rien retourné : conserver le texte natif même s'il est court
            print_warning(f"  OCR n'a retourné aucun texte pour {file_path.name}")

    return text, ocr_used


def extract_text_from_file(file_path: Path) -> str:
    """Extrait le texte d'un fichier selon son extension."""
    suffix = file_path.suffix.lower()

    if suffix == '.pdf':
        text, ocr_used = extract_text_from_pdf(file_path)
        if ocr_used:
            print_success(f"  Texte extrait par OCR ({len(text)} caractères)")
        return text

    elif suffix == '.docx':
        # Nouveau format .docx (Office Open XML)
        try:
            import docx2txt
            text = docx2txt.process(str(file_path))
            return text
        except ImportError:
            print_warning(f"docx2txt non installé, impossible de lire {file_path.name}")
            return ""
        except Exception as e:
            print_warning(f"Erreur lors de la lecture de {file_path.name} : {e}")
            return ""

    elif suffix == '.doc':
        # Ancien format .doc (binaire) - essayer plusieurs méthodes
        # Méthode 1 : antiword (via subprocess)
        try:
            import subprocess
            result = subprocess.run(
                ['antiword', str(file_path)],
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode == 0 and result.stdout:
                return result.stdout
        except FileNotFoundError:
            pass  # antiword n'est pas installé, essayer autre chose
        except Exception:
            pass

        # Méthode 2 : textract (si disponible)
        try:
            import textract
            text = textract.process(str(file_path)).decode('utf-8', errors='replace')
            return text
        except ImportError:
            pass
        except Exception:
            pass

        # Méthode 3 : python-docx avec récupération partielle
        try:
            from docx import Document
            doc = Document(str(file_path))
            text = "\n".join([para.text for para in doc.paragraphs])
            if text.strip():
                return text
        except Exception:
            pass

        # Méthode 4 : olefile pour extraction brute (dernière tentative)
        try:
            import olefile
            if olefile.isOleFile(str(file_path)):
                ole = olefile.OleFileIO(str(file_path))
                if ole.exists('WordDocument'):
                    data = ole.openstream('WordDocument').read()
                    text = data.decode('latin-1', errors='ignore')
                    text = ''.join(char for char in text if char.isprintable() or char in '\n\r\t')
                    text = re.sub(r'[^\w\s\.,;:!?\-\'\"àâäéèêëïîôùûüÿçÀÂÄÉÈÊËÏÎÔÙÛÜŸÇ()\[\]{}/@#%&+=]+', '', text)
                    ole.close()
                    if len(text.strip()) > 100:
                        return text
        except ImportError:
            pass
        except Exception:
            pass

        print_warning(f"Format .doc ancien non supporté pour {file_path.name}")
        print_warning(f"  Installez 'antiword' (système) ou 'textract' (pip) pour supporter ce format")
        return ""

    else:
        try:
            return file_path.read_text(encoding='utf-8', errors='replace')
        except Exception as e:
            print_warning(f"Erreur lors de la lecture de {file_path.name} : {e}")
            return ""


def get_existing_collections(client: QdrantClient) -> List[str]:
    """Récupère la liste des collections existantes."""
    try:
        return [c.name for c in client.get_collections().collections]
    except Exception:
        return []


def ensure_collection(client: QdrantClient, collection_name: str, dimension: int) -> bool:
    """Crée la collection si elle n'existe pas."""
    try:
        collections = {c.name: c for c in client.get_collections().collections}

        if collection_name in collections:
            info = client.get_collection(collection_name)
            existing_dim = info.config.params.vectors.size
            if existing_dim != dimension:
                print_warning(
                    f"La collection '{collection_name}' existe avec une dimension "
                    f"différente ({existing_dim} vs {dimension})"
                )
                if prompt_yes_no("Voulez-vous la supprimer et la recréer ?", default=False):
                    client.delete_collection(collection_name)
                    client.create_collection(
                        collection_name=collection_name,
                        vectors_config=VectorParams(size=dimension, distance=Distance.COSINE),
                    )
                    print_success(f"Collection '{collection_name}' recréée avec dimension={dimension}")
                else:
                    print_error("Opération annulée")
                    return False
            else:
                print_success(f"Collection '{collection_name}' déjà existante (dimension={dimension})")
        else:
            client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(size=dimension, distance=Distance.COSINE),
            )
            print_success(f"Collection '{collection_name}' créée avec dimension={dimension}")

        return True
    except Exception as e:
        print_error(f"Erreur lors de la création/vérification de la collection : {e}")
        return False


def upsert_with_retry(
    qclient: QdrantClient,
    collection_name: str,
    points: List[PointStruct],
    max_retries: int = None,
    batch_size: int = None,
    timeout: int = None,
) -> bool:
    """
    Insère les points dans Qdrant avec gestion des timeouts et retry.
    Découpe en batches pour éviter les timeouts sur les gros volumes.
    """
    import time

    if max_retries is None:
        max_retries = QDRANT_MAX_RETRIES
    if batch_size is None:
        batch_size = QDRANT_BATCH_SIZE
    if timeout is None:
        timeout = QDRANT_TIMEOUT

    total_points = len(points)

    if total_points <= batch_size:
        for attempt in range(max_retries):
            try:
                qclient.upsert(
                    collection_name=collection_name,
                    points=points,
                )
                return True
            except Exception as e:
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt
                    print_warning(f"Timeout/erreur (tentative {attempt + 1}/{max_retries}), retry dans {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    print_error(f"Échec après {max_retries} tentatives : {e}")
                    return False

    print_info(f"Découpage en batches de {batch_size} points ({total_points} total)...")

    for i in range(0, total_points, batch_size):
        batch = points[i:i + batch_size]
        batch_num = (i // batch_size) + 1
        total_batches = (total_points + batch_size - 1) // batch_size

        for attempt in range(max_retries):
            try:
                qclient.upsert(
                    collection_name=collection_name,
                    points=batch,
                )
                print(f"  Batch {batch_num}/{total_batches} ({len(batch)} points) ✓")
                break

            except Exception as e:
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt
                    print_warning(f"  Batch {batch_num}/{total_batches} erreur ({type(e).__name__}: {e}), retry dans {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    print_error(f"  Batch {batch_num}/{total_batches} échec après {max_retries} tentatives : {type(e).__name__}: {e}")
                    return False

    return True


def _contextual_prefix_batch_local(document: str, chunks: List[str]) -> List[str]:
    """Fallback autonome pour le chunking contextuel quand rag_engine n'est pas importable.

    Reproduit la logique de rag_engine._contextual_prefix_batch() sans dépendance
    à l'objet Config — lit directement les variables d'environnement du module.

    Utilisé uniquement si l'import de rag_engine échoue (script lancé en dehors
    du projet Prométhée). Dans le cas normal, c'est _contextual_prefix_batch()
    de rag_engine qui est appelé.
    """
    doc_excerpt = document[:RAG_CONTEXTUAL_DOC_MAX_CHARS]
    prefixes: List[str] = []

    system_prompt = (
        "Tu es un assistant qui aide à contextualiser des extraits de documents. "
        "Réponds uniquement avec le contexte demandé, sans introduction."
    )

    for i, chunk in enumerate(chunks):
        user_prompt = (
            "<document>\n"
            f"{doc_excerpt}\n"
            "</document>\n\n"
            "Voici l'extrait à contextualiser :\n"
            "<chunk>\n"
            f"{chunk}\n"
            "</chunk>\n\n"
            "Génère une courte phrase (max 2 phrases) qui situe cet extrait dans "
            "le document : de quoi parle-t-il globalement, dans quel contexte "
            "apparaît-il ? Ne répète pas le contenu de l'extrait."
        )

        prefix = ""

        # Modèle à utiliser : RAG_INGESTION_MODEL si défini, sinon modèle principal.
        ingestion_model = RAG_INGESTION_MODEL or OPENAI_MODEL

        # ── API OpenAI-compatible ────────────────────────────────────────
        if not LOCAL and OPENAI_API_BASE and OPENAI_API_KEY and ingestion_model:
            try:
                llm = OpenAI(base_url=OPENAI_API_BASE, api_key=OPENAI_API_KEY)
                resp = llm.chat.completions.create(
                    model=ingestion_model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user",   "content": user_prompt},
                    ],
                    max_tokens=RAG_CONTEXTUAL_PREFIX_MAX_TOKENS,
                    temperature=0.1,
                )
                prefix = resp.choices[0].message.content.strip()
            except Exception as e:
                print_warning(f"  [CTX] chunk {i + 1}/{len(chunks)} — échec API : {e}")

        # ── Ollama ───────────────────────────────────────────────────────
        elif LOCAL and OLLAMA_BASE_URL and OLLAMA_MODEL:
            try:
                import urllib.request as _ur
                import json as _j
                payload = _j.dumps({
                    "model": OLLAMA_MODEL,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user",   "content": user_prompt},
                    ],
                    "stream": False,
                    "options": {
                        "num_predict": RAG_CONTEXTUAL_PREFIX_MAX_TOKENS,
                        "temperature": 0.1,
                    },
                }).encode()
                req = _ur.Request(
                    f"{OLLAMA_BASE_URL.rstrip('/')}/api/chat",
                    data=payload,
                    headers={"Content-Type": "application/json"},
                )
                with _ur.urlopen(req, timeout=20) as r:
                    prefix = _j.loads(r.read())["message"]["content"].strip()
            except Exception as e:
                print_warning(f"  [CTX] chunk {i + 1}/{len(chunks)} — échec Ollama : {e}")

        prefixes.append(prefix)

    return prefixes


def ingest_file(
    file_path: Path,
    collection_name: str,
    qclient: QdrantClient,
    embedding_client: OpenAI,
    embedding_model: str,
    use_contextual_chunking: bool = None,
) -> int:
    """Ingère un fichier dans Qdrant. Retourne le nombre de chunks indexés.

    Parameters
    ----------
    use_contextual_chunking : bool, optional
        Active/désactive le chunking contextuel pour ce fichier.
        None → utilise la valeur de RAG_CONTEXTUAL_CHUNKING (.env).
    """
    text = extract_text_from_file(file_path)
    if not text or len(text.strip()) < 50:
        return 0

    chunks = chunk_text(text)
    if not chunks:
        return 0

    # ── Chunking contextuel (Anthropic Contextual Retrieval) ─────────────
    # Génère un préfixe contextuel LLM pour chaque chunk afin d'enrichir
    # l'embedding et améliorer la précision du retrieval.
    #
    # Deux chemins possibles :
    #   1. RAG_ENGINE_OK → délègue à _contextual_prefix_batch() de rag_engine
    #      (même logique que lors d'une ingestion via l'interface)
    #   2. Fallback local → implémentation minimale autonome sans import rag_engine
    #
    # Si le chunking contextuel est désactivé, context_prefixes reste une liste
    # de chaînes vides et les chunks sont embedés tels quels (comportement historique).
    ctx_enabled = RAG_CONTEXTUAL_CHUNKING if use_contextual_chunking is None else use_contextual_chunking

    context_prefixes: List[str] = [""] * len(chunks)

    if ctx_enabled:
        print_info(f"  Génération des préfixes contextuels ({len(chunks)} chunks)…")
        if RAG_ENGINE_OK:
            # Délégation au générateur de rag_engine (cohérence garantie)
            context_prefixes = _contextual_prefix_batch(text, chunks)
        else:
            # Fallback autonome : même logique mais sans dépendance à rag_engine
            context_prefixes = _contextual_prefix_batch_local(text, chunks)

        n_ok = sum(1 for p in context_prefixes if p)
        print_info(f"  → {n_ok}/{len(chunks)} préfixes générés")

    # Textes à embedder : "préfixe\n\nchunk" si préfixe disponible, sinon chunk brut
    texts_to_embed = [
        f"{prefix}\n\n{chunk}" if prefix else chunk
        for prefix, chunk in zip(context_prefixes, chunks)
    ]

    embeddings = get_embeddings(texts_to_embed, embedding_client, embedding_model)
    if not embeddings or len(embeddings) != len(chunks):
        return 0

    points = [
        PointStruct(
            id=str(uuid.uuid4()),
            vector=emb,
            payload={
                "text":            chunk,
                "source":          file_path.name,
                "file_path":       str(file_path),
                "conversation_id": "global",
                # Préfixe contextuel stocké pour traçabilité (omis si vide)
                **({"context_prefix": prefix} if prefix else {}),
            }
        )
        for chunk, emb, prefix in zip(chunks, embeddings, context_prefixes)
    ]

    success = upsert_with_retry(qclient, collection_name, points)
    return len(chunks) if success else 0


def scan_directory(
    directory: Path,
    recursive: bool,
    extensions: set = None,
) -> List[Path]:
    """Scanne un répertoire et retourne la liste des fichiers à traiter."""
    if extensions is None:
        extensions = SUPPORTED_EXTENSIONS

    files = []

    if recursive:
        for file_path in directory.rglob('*'):
            if file_path.is_file() and file_path.suffix.lower() in extensions:
                files.append(file_path)
    else:
        for file_path in directory.glob('*'):
            if file_path.is_file() and file_path.suffix.lower() in extensions:
                files.append(file_path)

    return sorted(files)


# ══════════════════════════════════════════════════════════════════════
#  Mode interactif
# ══════════════════════════════════════════════════════════════════════

def interactive_mode():
    """Mode interactif avec menu."""
    show_banner()
    show_config()

    # Avertissement si OCR indisponible
    if not (PYTESSERACT_OK and PDF2IMAGE_OK):
        print_warning("L'OCR Tesseract n'est pas disponible. Les PDF scannés ne seront pas indexés.")
        print_warning("  pip install pytesseract pdf2image")
        print_warning("  + Tesseract système : sudo apt install tesseract-ocr tesseract-ocr-fra")

    # Connexion à Qdrant
    print_section("Connexion à Qdrant")
    try:
        qclient = QdrantClient(url=QDRANT_URL, timeout=QDRANT_TIMEOUT)
        qclient.get_collections()
        print_success(f"Connecté à Qdrant ({QDRANT_URL})")
    except Exception as e:
        print_error(f"Impossible de se connecter à Qdrant : {e}")
        print_info("Vérifiez que Qdrant est démarré et que QDRANT_URL est correct dans .env")
        sys.exit(1)

    # Liste des collections existantes
    existing_collections = get_existing_collections(qclient)
    if existing_collections:
        print_info(f"{len(existing_collections)} collection(s) existante(s) : {', '.join(existing_collections)}")

    # Sélection du répertoire
    print_section("Répertoire à indexer")
    while True:
        directory_path = prompt_input("Chemin du répertoire", os.getcwd())
        directory = Path(directory_path).expanduser()

        if directory.exists() and directory.is_dir():
            print_success(f"Répertoire validé : {directory}")
            break
        else:
            print_error(f"Le répertoire '{directory}' n'existe pas ou n'est pas un répertoire")

    # Options de scan
    print_section("Options de scan")
    recursive = prompt_yes_no("Scanner récursivement les sous-répertoires ?", default=True)

    # Extensions
    print_info(f"Extensions supportées par défaut : {', '.join(sorted(SUPPORTED_EXTENSIONS))}")
    custom_ext = prompt_yes_no("Voulez-vous filtrer certaines extensions uniquement ?", default=False)

    if custom_ext:
        print_info("Entrez les extensions séparées par des espaces (ex: .pdf .txt .md)")
        ext_input = prompt_input("Extensions")
        extensions = {ext if ext.startswith('.') else f'.{ext}' for ext in ext_input.split()}
        print_success(f"Filtrage sur : {', '.join(sorted(extensions))}")
    else:
        extensions = SUPPORTED_EXTENSIONS

    # Scan préliminaire
    print_section("Analyse du répertoire")
    print_info("Scan en cours...")
    files = scan_directory(directory, recursive, extensions)

    if not files:
        print_error("Aucun fichier trouvé avec les critères spécifiés")
        return

    print_success(f"{len(files)} fichier(s) trouvé(s)")

    # Aperçu des fichiers
    if len(files) <= 10:
        print_info("Fichiers à traiter :")
        for f in files:
            print(f"  • {f.relative_to(directory)}")
    else:
        print_info(f"Aperçu (10 premiers sur {len(files)}) :")
        for f in files[:10]:
            print(f"  • {f.relative_to(directory)}")
        print(f"  ... et {len(files) - 10} autres fichiers")

    # Collection
    print_section("Collection Qdrant")

    if existing_collections:
        use_existing = prompt_yes_no("Utiliser une collection existante ?", default=True)
        if use_existing:
            choice = prompt_choice(
                "Sélectionnez une collection :",
                existing_collections + ["[Créer une nouvelle collection]"]
            )
            if choice < len(existing_collections):
                collection_name = existing_collections[choice]
            else:
                collection_name = prompt_input("Nom de la nouvelle collection")
        else:
            collection_name = prompt_input("Nom de la nouvelle collection")
    else:
        collection_name = prompt_input("Nom de la collection")

    print_success(f"Collection sélectionnée : {collection_name}")

    # Chunking contextuel — proposition interactive
    print_section("Chunking contextuel (Anthropic Contextual Retrieval)")
    if not (OPENAI_MODEL or OLLAMA_MODEL):
        print_warning("Aucun modèle LLM configuré (OPENAI_MODEL / OLLAMA_MODEL) — chunking contextuel indisponible")
        use_ctx = False
    else:
        if RAG_CONTEXTUAL_CHUNKING:
            print_info("RAG_CONTEXTUAL_CHUNKING=ON détecté dans .env")
            use_ctx = prompt_yes_no(
                "Activer le chunking contextuel (enrichit chaque chunk d'un préfixe LLM — plus lent) ?",
                default=True,
            )
        else:
            print_info("RAG_CONTEXTUAL_CHUNKING=OFF dans .env (désactivé par défaut)")
            use_ctx = prompt_yes_no(
                "Activer le chunking contextuel quand même pour cette session ?",
                default=False,
            )
        if use_ctx:
            effective_model = RAG_INGESTION_MODEL or (OLLAMA_MODEL if LOCAL else OPENAI_MODEL)
            llm_label = f"{'Ollama' if LOCAL else 'OpenAI-compat'} · {effective_model}"
            if RAG_INGESTION_MODEL:
                llm_label += " (RAG_INGESTION_MODEL)"
            print_success(f"Chunking contextuel activé — LLM : {llm_label}")
            print_warning(f"Attention : {len(files)} fichier(s) × ~N chunks = N appels LLM supplémentaires")
        else:
            print_info("Chunking contextuel désactivé")

    # Récapitulatif
    print_header("Récapitulatif")
    print(f"  • Répertoire      : {Colors.CYAN}{directory}{Colors.END}")
    print(f"  • Récursif        : {Colors.CYAN}{'Oui' if recursive else 'Non'}{Colors.END}")
    print(f"  • Extensions      : {Colors.CYAN}{', '.join(sorted(extensions))}{Colors.END}")
    print(f"  • Fichiers        : {Colors.CYAN}{len(files)}{Colors.END}")
    print(f"  • Collection      : {Colors.CYAN}{collection_name}{Colors.END}")
    print(f"  • Modèle embed.   : {Colors.CYAN}{EMBEDDING_MODEL}{Colors.END}")
    ctx_color = Colors.GREEN if use_ctx else Colors.YELLOW
    print(f"  • Chunking ctx    : {ctx_color}{'Activé' if use_ctx else 'Désactivé'}{Colors.END}")
    ocr_available = PYTESSERACT_OK and PDF2IMAGE_OK
    print(f"  • OCR Tesseract   : {Colors.GREEN if ocr_available else Colors.YELLOW}{'Activé' if ocr_available else 'Désactivé'}{Colors.END}")
    print()

    if not prompt_yes_no("Lancer l'indexation ?", default=True):
        print_info("Opération annulée")
        return

    # Préparation
    print_section("Préparation")

    embedding_client = OpenAI(
        base_url=EMBEDDING_API_BASE,
        api_key=OPENAI_API_KEY or "none",
    )

    if not ensure_collection(qclient, collection_name, EMBEDDING_DIMENSION):
        return

    # Indexation
    print_header("Indexation en cours")

    total_chunks = 0
    success_count = 0
    error_count = 0

    progress = tqdm(
        files,
        desc="Indexation",
        unit="fichier",
        colour="cyan",
        dynamic_ncols=True,
    ) if TQDM_OK else files

    for file_path in progress:
        rel_path = file_path.relative_to(directory)

        if TQDM_OK:
            progress.set_description(f"{rel_path.name[:40]}")

        try:
            chunks = ingest_file(
                file_path,
                collection_name,
                qclient,
                embedding_client,
                EMBEDDING_MODEL,
                use_contextual_chunking=use_ctx,
            )

            if chunks > 0:
                total_chunks += chunks
                success_count += 1
                if TQDM_OK:
                    progress.set_postfix(chunks=total_chunks, ok=success_count, err=error_count)
                print_success(f"{rel_path} — {chunks} chunks")
            else:
                error_count += 1
                if TQDM_OK:
                    progress.set_postfix(chunks=total_chunks, ok=success_count, err=error_count)
                print_warning(f"{rel_path} — ignoré")

        except Exception as e:
            error_count += 1
            if TQDM_OK:
                progress.set_postfix(chunks=total_chunks, ok=success_count, err=error_count)
            print_error(f"{rel_path} — {e}")

    # Résumé final
    print_header("✨ Indexation terminée !")
    print(f"  • Fichiers traités : {Colors.GREEN}{success_count}{Colors.END}/{len(files)}")
    print(f"  • Erreurs/Ignorés  : {Colors.YELLOW}{error_count}{Colors.END}")
    print(f"  • Total chunks     : {Colors.CYAN}{total_chunks}{Colors.END}")
    print(f"  • Collection       : {Colors.CYAN}{collection_name}{Colors.END}")
    ctx_color = Colors.GREEN if use_ctx else Colors.YELLOW
    print(f"  • Chunking ctx     : {ctx_color}{'Activé' if use_ctx else 'Désactivé'}{Colors.END}")
    print()


# ══════════════════════════════════════════════════════════════════════
#  Main
# ══════════════════════════════════════════════════════════════════════

def main():
    global OCR_LANG, OCR_DPI, PYTESSERACT_OK, PDF2IMAGE_OK

    parser = argparse.ArgumentParser(
        description="Indexer un répertoire dans Qdrant (mode interactif ou direct)",
        add_help=True,
    )

    parser.add_argument(
        'directory',
        type=str,
        nargs='?',
        help="Chemin du répertoire à indexer"
    )

    parser.add_argument(
        '--collection', '-c',
        type=str,
        help="Nom de la collection Qdrant"
    )

    parser.add_argument(
        '--recursive', '-r',
        action='store_true',
        help="Scanner récursivement les sous-répertoires"
    )

    parser.add_argument(
        '--extensions', '-e',
        nargs='+',
        help="Extensions de fichiers à traiter"
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help="Afficher les fichiers sans les indexer"
    )

    parser.add_argument(
        '--interactive', '-i',
        action='store_true',
        help="Forcer le mode interactif"
    )

    parser.add_argument(
        '--ocr-lang',
        type=str,
        default=None,
        help=f"Langue(s) Tesseract pour l'OCR (ex: fra, eng, fra+eng). Défaut: {OCR_LANG}"
    )

    parser.add_argument(
        '--ocr-dpi',
        type=int,
        default=None,
        help=f"DPI pour la conversion PDF→image (défaut: {OCR_DPI})"
    )

    parser.add_argument(
        '--no-ocr',
        action='store_true',
        help="Désactiver l'OCR même si Tesseract est disponible"
    )

    ctx_group = parser.add_mutually_exclusive_group()
    ctx_group.add_argument(
        '--ctx',
        action='store_true',
        default=None,
        help="Forcer l'activation du chunking contextuel LLM (override RAG_CONTEXTUAL_CHUNKING)"
    )
    ctx_group.add_argument(
        '--no-ctx',
        action='store_true',
        help="Forcer la désactivation du chunking contextuel LLM (override RAG_CONTEXTUAL_CHUNKING)"
    )

    args = parser.parse_args()

    # Résoudre la valeur effective du chunking contextuel
    # Priorité : --ctx/--no-ctx > RAG_CONTEXTUAL_CHUNKING (.env)
    if args.ctx:
        use_ctx = True
    elif args.no_ctx:
        use_ctx = False
    else:
        use_ctx = RAG_CONTEXTUAL_CHUNKING

    # Appliquer les overrides OCR depuis la ligne de commande
    if args.ocr_lang:
        OCR_LANG = args.ocr_lang
    if args.ocr_dpi:
        OCR_DPI = args.ocr_dpi
    if args.no_ocr:
        PYTESSERACT_OK = False
        PDF2IMAGE_OK = False

    # Mode interactif si pas d'arguments ou flag --interactive
    if args.interactive or (not args.directory and not args.collection):
        interactive_mode()
        return

    # Mode direct (ligne de commande)
    if not args.directory:
        print_error("Le chemin du répertoire est requis en mode direct")
        print_info("Utilisez --interactive ou -i pour le mode interactif")
        sys.exit(1)

    if not args.collection:
        print_error("Le nom de la collection est requis en mode direct")
        print_info("Utilisez --interactive ou -i pour le mode interactif")
        sys.exit(1)

    # Validation du répertoire
    directory = Path(args.directory)
    if not directory.exists():
        print_error(f"Le répertoire '{directory}' n'existe pas")
        sys.exit(1)

    if not directory.is_dir():
        print_error(f"'{directory}' n'est pas un répertoire")
        sys.exit(1)

    # Extensions
    extensions = SUPPORTED_EXTENSIONS
    if args.extensions:
        extensions = {ext if ext.startswith('.') else f'.{ext}' for ext in args.extensions}

    # Statut OCR
    ocr_available = PYTESSERACT_OK and PDF2IMAGE_OK
    print_info(f"OCR Tesseract : {'activé (lang={}, dpi={})'.format(OCR_LANG, OCR_DPI) if ocr_available else 'désactivé'}")
    ctx_color = Colors.GREEN if use_ctx else Colors.YELLOW
    print(f"  Chunking contextuel : {ctx_color}{'activé' if use_ctx else 'désactivé'}{Colors.END}")

    # Scanner
    print_info(f"Scan du répertoire : {directory}")
    files = scan_directory(directory, args.recursive, extensions)

    if not files:
        print_error("Aucun fichier trouvé")
        sys.exit(1)

    print_success(f"{len(files)} fichier(s) trouvé(s)")

    if args.dry_run:
        print_info("Mode dry-run : liste des fichiers")
        for f in files:
            print(f"  • {f.relative_to(directory)}")
        return

    # Connexion
    try:
        qclient = QdrantClient(url=QDRANT_URL, timeout=QDRANT_TIMEOUT)
        qclient.get_collections()
        print_success(f"Connecté à Qdrant")
    except Exception as e:
        print_error(f"Impossible de se connecter à Qdrant : {e}")
        sys.exit(1)

    embedding_client = OpenAI(
        base_url=EMBEDDING_API_BASE,
        api_key=OPENAI_API_KEY or "none",
    )

    if not ensure_collection(qclient, args.collection, EMBEDDING_DIMENSION):
        sys.exit(1)

    # Indexation
    print_info("Indexation en cours...")

    total_chunks = 0
    success_count = 0
    error_count = 0

    progress = tqdm(
        files,
        desc="Indexation",
        unit="fichier",
        colour="cyan",
        dynamic_ncols=True,
    ) if TQDM_OK else files

    for file_path in progress:
        rel_path = file_path.relative_to(directory)

        if TQDM_OK:
            progress.set_description(f"{rel_path.name[:40]}")

        chunks = ingest_file(
            file_path,
            args.collection,
            qclient,
            embedding_client,
            EMBEDDING_MODEL,
            use_contextual_chunking=use_ctx,
        )
        if chunks > 0:
            total_chunks += chunks
            success_count += 1
            print_success(f"{rel_path} — {chunks} chunks")
        else:
            error_count += 1
            print_warning(f"{rel_path} — ignoré")

        if TQDM_OK:
            progress.set_postfix(chunks=total_chunks, ok=success_count, err=error_count)

    print_success(f"Terminé : {success_count}/{len(files)} fichiers, {total_chunks} chunks")
    ctx_label = "avec" if use_ctx else "sans"
    print_info(f"Chunking contextuel : {ctx_label} préfixe LLM")


if __name__ == "__main__":
    main()
