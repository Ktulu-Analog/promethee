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
ocr_engine.py — Extraction de texte depuis les images avec Tesseract
"""
from pathlib import Path
from typing import Optional, Tuple

# Vérifier si tesseract est disponible
try:
    import pytesseract
    from PIL import Image
    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False


def is_available() -> bool:
    """Vérifie si l'OCR est disponible."""
    if not TESSERACT_AVAILABLE:
        return False
    
    # Vérifier que tesseract est installé sur le système
    try:
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


def extract_text_from_image(image_path: str, lang: str = "fra+eng") -> Tuple[Optional[str], Optional[str]]:
    """
    Extrait le texte d'une image avec Tesseract OCR.
    
    Args:
        image_path: Chemin vers l'image
        lang: Langues à utiliser (fra+eng par défaut pour français et anglais)
    
    Returns:
        (texte_extrait, erreur)
        - texte_extrait: Le texte détecté ou None
        - erreur: Message d'erreur ou None
    """
    if not is_available():
        return None, "Tesseract non disponible (installez pytesseract et tesseract-ocr)"
    
    try:
        # Charger l'image
        image = Image.open(image_path)
        
        # Configuration OCR optimisée
        custom_config = r'--oem 3 --psm 3'  # OEM 3 = LSTM, PSM 3 = Auto page segmentation
        
        # Extraire le texte
        text = pytesseract.image_to_string(
            image,
            lang=lang,
            config=custom_config
        )
        
        # Nettoyer le texte
        text = text.strip()
        
        if not text:
            return None, "Aucun texte détecté dans l'image"
        
        return text, None
    
    except pytesseract.TesseractNotFoundError:
        return None, "Tesseract non installé sur le système"
    
    except Exception as e:
        return None, f"Erreur OCR : {str(e)}"


def extract_text_from_pil_image(pil_image, lang: str = "fra+eng") -> Tuple[Optional[str], Optional[str]]:
    """
    Extrait le texte d'une image PIL.
    
    Args:
        pil_image: Image PIL
        lang: Langues à utiliser
    
    Returns:
        (texte_extrait, erreur)
    """
    if not is_available():
        return None, "Tesseract non disponible"
    
    try:
        custom_config = r'--oem 3 --psm 3'
        text = pytesseract.image_to_string(pil_image, lang=lang, config=custom_config)
        text = text.strip()
        
        if not text:
            return None, "Aucun texte détecté"
        
        return text, None
    
    except Exception as e:
        return None, f"Erreur OCR : {str(e)}"


def detect_text_confidence(image_path: str, lang: str = "fra+eng") -> Tuple[Optional[dict], Optional[str]]:
    """
    Détecte le texte avec le niveau de confiance pour chaque mot.
    
    Args:
        image_path: Chemin vers l'image
        lang: Langues à utiliser
    
    Returns:
        (données, erreur)
        - données: Dict avec 'text', 'confidence', 'words'
        - erreur: Message d'erreur ou None
    """
    if not is_available():
        return None, "Tesseract non disponible"
    
    try:
        image = Image.open(image_path)
        
        # Obtenir les données détaillées
        data = pytesseract.image_to_data(image, lang=lang, output_type=pytesseract.Output.DICT)
        
        # Calculer la confiance moyenne
        confidences = [int(conf) for conf in data['conf'] if int(conf) > 0]
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0
        
        # Extraire les mots avec bonne confiance
        words = []
        for i, conf in enumerate(data['conf']):
            if int(conf) > 60:  # Seuil de confiance minimum
                word = data['text'][i].strip()
                if word:
                    words.append({
                        'text': word,
                        'confidence': int(conf)
                    })
        
        # Texte complet
        text = ' '.join([w['text'] for w in words])
        
        return {
            'text': text,
            'confidence': round(avg_confidence, 2),
            'words': words,
            'total_words': len(words)
        }, None
    
    except Exception as e:
        return None, f"Erreur détection : {str(e)}"


def get_supported_languages() -> list:
    """Retourne la liste des langues supportées par Tesseract."""
    if not is_available():
        return []
    
    try:
        langs = pytesseract.get_languages()
        return langs
    except Exception:
        return ['eng', 'fra']  # Fallback


def extract_text_from_pdf(pdf_path: str, lang: str = "fra+eng", max_pages: int = None) -> Tuple[Optional[str], Optional[str]]:
    """
    Extrait le texte d'un PDF avec OCR si nécessaire.
    Détecte automatiquement si le PDF contient déjà du texte ou s'il est scanné.
    
    Args:
        pdf_path: Chemin vers le PDF
        lang: Langues pour l'OCR
        max_pages: Nombre maximum de pages à traiter (None = toutes)
    
    Returns:
        (texte_extrait, erreur)
    """
    if not is_available():
        return None, "OCR non disponible"
    
    try:
        import fitz  # PyMuPDF
        from PIL import Image
        import io
        
        doc = fitz.open(pdf_path)
        total_pages = len(doc)
        pages_to_process = min(total_pages, max_pages) if max_pages else total_pages
        
        all_text = []
        ocr_used = False
        
        for page_num in range(pages_to_process):
            page = doc[page_num]
            
            # Essayer d'extraire le texte normalement
            text = page.get_text().strip()
            
            # Si pas de texte ou très peu, utiliser l'OCR
            if len(text) < 50:  # Seuil : moins de 50 caractères = probablement scanné
                ocr_used = True
                
                # Rendre la page en image
                pix = page.get_pixmap(matrix=fitz.Matrix(300/72, 300/72))  # 300 DPI pour OCR
                img_data = pix.tobytes("png")
                
                # Convertir en PIL Image
                pil_image = Image.open(io.BytesIO(img_data))
                
                # OCR
                custom_config = r'--oem 3 --psm 3'
                ocr_text = pytesseract.image_to_string(pil_image, lang=lang, config=custom_config)
                text = ocr_text.strip()
            
            if text:
                all_text.append(f"--- Page {page_num + 1} ---\n{text}\n")
        
        doc.close()
        
        if not all_text:
            return None, "Aucun texte détecté dans le PDF"
        
        final_text = "\n".join(all_text)
        
        # Ajouter une note si OCR a été utilisé
        if ocr_used:
            final_text = f"[OCR utilisé sur {pages_to_process} page(s)]\n\n" + final_text
        
        return final_text, None
    
    except ImportError as e:
        if "fitz" in str(e):
            return None, "PyMuPDF non installé"
        elif "PIL" in str(e):
            return None, "Pillow non installé"
        else:
            return None, "Dépendances manquantes"
    
    except Exception as e:
        return None, f"Erreur OCR PDF : {str(e)}"


def detect_pdf_type(pdf_path: str) -> str:
    """
    Détecte si un PDF contient du texte ou s'il est scanné (images).
    
    Args:
        pdf_path: Chemin vers le PDF
    
    Returns:
        "text" | "scanned" | "mixed" | "unknown"
    """
    try:
        import fitz
        
        doc = fitz.open(pdf_path)
        text_pages = 0
        image_pages = 0
        
        # Analyser les 5 premières pages max
        sample_size = min(5, len(doc))
        
        for page_num in range(sample_size):
            page = doc[page_num]
            text = page.get_text().strip()
            
            if len(text) > 100:
                text_pages += 1
            else:
                image_pages += 1
        
        doc.close()
        
        if text_pages == sample_size:
            return "text"
        elif image_pages == sample_size:
            return "scanned"
        elif text_pages > 0 and image_pages > 0:
            return "mixed"
        else:
            return "unknown"
    
    except Exception:
        return "unknown"

