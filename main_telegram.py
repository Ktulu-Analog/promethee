#!/usr/bin/env python3
# ============================================================================
# Prométhée — Assistant IA desktop (Physique-Chimie) — Interface Telegram
# ============================================================================
# Licence : GNU Affero General Public License v3.0 (AGPL-3.0)
# ============================================================================

"""
main_telegram.py — Bot Telegram pour Prométhée AI
===================================================

Point d'entrée alternatif pour piloter le moteur Prométhée à distance
via Telegram, sans streaming, avec gestion des pièces jointes (photos, PDFs).

Prérequis :
    pip install python-telegram-bot python-dotenv
    Variable d'environnement : TELEGRAM_TOKEN (obtenu via @BotFather)
"""

import os
import sys
import logging
import re
from pathlib import Path

from dotenv import load_dotenv

# S'assurer que le dossier projet est dans le PYTHONPATH
sys.path.insert(0, str(Path(__file__).parent))

# Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# --- Chargement de la config et enregistrement des outils ---
# ⚠ Certaines sessions shell exportent OPENAI_API_KEY / OPENAI_BASE_URL
# (ex: DeepSeek, OpenCode, etc.) ce qui entre en conflit avec Albert IA.
# On les purge AVANT load_dotenv pour que le .env du projet prenne le dessus.
for _var in ("OPENAI_API_KEY", "OPENAI_API_BASE", "OPENAI_BASE_URL"):
    os.environ.pop(_var, None)

load_dotenv(override=True)

from core.config import Config
from tools import register_all

register_all()

from core import llm_service, tools_engine

# ── Debug : vérifier quelle clé API est réellement chargée ──
logger.info(
    "Config chargée — OPENAI_API_KEY: %s...%s (len=%d), model=%s",
    Config.OPENAI_API_KEY[:10], Config.OPENAI_API_KEY[-5:],
    len(Config.OPENAI_API_KEY), Config.active_model(),
)

# --- Import Telegram ---
try:
    from telegram import Update
    from telegram.ext import (
        Application,
        CommandHandler,
        MessageHandler,
        filters,
        ContextTypes,
    )
except ImportError:
    print(
        "Erreur : python-telegram-bot introuvable.\n"
        "Exécutez : pip install 'python-telegram-bot>=20'"
    )
    sys.exit(1)


# ══════════════════════════════════════════════════════════════════════════════
# Utilitaires
# ══════════════════════════════════════════════════════════════════════════════

_MAX_TG_LEN = 4000  # Telegram max = 4096, on garde une marge

# Extensions de fichiers à renvoyer automatiquement en pièce jointe
_SENDABLE_EXTENSIONS = (
    ".pdf", ".docx", ".doc", ".xlsx", ".xls", ".pptx", ".ppsx",
    ".odt", ".ods", ".odp", ".tex", ".xml", ".txt", ".csv", ".md",
    ".py", ".sh", ".js", ".html", ".css", ".json", ".yaml", ".yml",
    ".jpg", ".jpeg", ".png", ".gif", ".svg", ".zip", ".tar", ".gz"
)


def _latex_to_telegram(text: str) -> str:
    r"""
    Convertit les expressions LaTeX en Unicode lisible dans Telegram.
    Telegram ne supporte pas LaTeX ni les tableaux Markdown.
    Conversion best-effort :
    - Délimiteurs \(...\), \[...\], $$...$$ et $...$
    - Symboles grecs et mathématiques -> Unicode
    - Exposants/indices simples -> Unicode sup/sub
    - Fractions simples -> notation a/b
    - Tableaux Markdown -> texte lisible avec bullets
    """
    import re as _re

    # -- Symboles grecs --
    _GREEK = {
        r'\alpha': 'α', r'\beta': 'β', r'\gamma': 'γ', r'\delta': 'δ',
        r'\epsilon': 'ε', r'\varepsilon': 'ε', r'\zeta': 'ζ', r'\eta': 'η',
        r'\theta': 'θ', r'\vartheta': 'ϑ', r'\iota': 'ι', r'\kappa': 'κ',
        r'\lambda': 'λ', r'\mu': 'μ', r'\nu': 'ν', r'\xi': 'ξ',
        r'\pi': 'π', r'\varpi': 'ϖ', r'\rho': 'ρ', r'\varrho': 'ϱ',
        r'\sigma': 'σ', r'\varsigma': 'ς', r'\tau': 'τ', r'\upsilon': 'υ',
        r'\phi': 'φ', r'\varphi': 'φ', r'\chi': 'χ', r'\psi': 'ψ', r'\omega': 'ω',
        r'\Alpha': 'Α', r'\Beta': 'Β', r'\Gamma': 'Γ', r'\Delta': 'Δ',
        r'\Epsilon': 'Ε', r'\Zeta': 'Ζ', r'\Eta': 'Η', r'\Theta': 'Θ',
        r'\Lambda': 'Λ', r'\Mu': 'Μ', r'\Nu': 'Ν', r'\Xi': 'Ξ',
        r'\Pi': 'Π', r'\Rho': 'Ρ', r'\Sigma': 'Σ', r'\Tau': 'Τ',
        r'\Upsilon': 'Υ', r'\Phi': 'Φ', r'\Chi': 'Χ', r'\Psi': 'Ψ', r'\Omega': 'Ω',
    }
    # -- Opérateurs et symboles math --
    _MATH = {
        r'\times': '×', r'\cdot': '·', r'\div': '÷', r'\pm': '±', r'\mp': '∓',
        r'\leq': '≤', r'\geq': '≥', r'\neq': '≠', r'\approx': '≈', r'\equiv': '≡',
        r'\rightarrow': '→', r'\leftarrow': '←', r'\leftrightarrow': '⇔',
        r'\Rightarrow': '⇒', r'\Leftarrow': '⇐', r'\longrightarrow': '⟶',
        r'\infty': '∞', r'\partial': '∂', r'\nabla': '∇', r'\sqrt': '√',
        r'\sum': 'Σ', r'\prod': 'Π', r'\int': '∫', r'\oint': '∮',
        r'\degree': '°', r'\circ': '°', r'\bullet': '•',
        r'\hbar': 'ħ', r'\ldots': '...', r'\cdots': '⋯',
        r'\mathrm': '', r'\text': '', r'\mathbf': '', r'\mathbb': '',
        r'\left': '', r'\right': '', r'\big': '', r'\Big': '',
    }
    # -- Exposants Unicode --
    _SUP = {'0':'⁰','1':'¹','2':'²','3':'³','4':'⁴','5':'⁵',
             '6':'⁶','7':'⁷','8':'⁸','9':'⁹','+':'⁺','-':'⁻','n':'ⁿ'}
    # -- Indices Unicode --
    _SUB = {'0':'₀','1':'₁','2':'₂','3':'₃','4':'₄','5':'₅',
             '6':'₆','7':'₇','8':'₈','9':'₉','+':'₊','-':'₋','n':'ₙ'}

    # === 0. Convertir tableaux Markdown en texte lisible ===
    def _convert_table(text_block: str) -> str:
        """Convertit un tableau Markdown en lignes lisibles avec bullets."""
        lines = text_block.split('\n')
        result_lines: list[str] = []
        table_rows: list[list[str]] = []
        in_table = False

        for line in lines:
            stripped = line.strip()
            # Ligne de tableau : commence par | et contient au moins 2 |
            if stripped.startswith('|') and stripped.count('|') >= 2:
                # Ignorer les lignes de séparation (|---|---|)
                if _re.match(r'^\|[\s\-:]+\|', stripped):
                    in_table = True
                    continue
                cells = [c.strip() for c in stripped.split('|')[1:-1]]
                table_rows.append(cells)
                in_table = True
            else:
                # Fin du tableau, on le formate
                if table_rows and in_table:
                    result_lines.extend(_format_table_rows(table_rows))
                    table_rows = []
                    in_table = False
                result_lines.append(line)

        # Tableau restant en fin de texte
        if table_rows:
            result_lines.extend(_format_table_rows(table_rows))

        return '\n'.join(result_lines)

    def _format_table_rows(rows: list[list[str]]) -> list[str]:
        """Formate les lignes d'un tableau en texte lisible."""
        if not rows:
            return []
        formatted: list[str] = []
        # Si la 1ère ligne est un header (détecté heuristiquement)
        header = rows[0] if len(rows) > 1 else None
        data_rows = rows[1:] if header else rows

        if header and len(header) >= 2:
            # Format header comme titre
            formatted.append('  '.join(f"▸ {h}" for h in header if h))
            formatted.append('─' * 30)

        for row in data_rows:
            if len(row) >= 2:
                # Clé: Valeur
                key = row[0].strip()
                val = ' │ '.join(c.strip() for c in row[1:] if c.strip())
                if key:
                    formatted.append(f"  ▹ {key}: {val}")
                else:
                    formatted.append(f"    {val}")
            elif len(row) == 1:
                formatted.append(f"  ▹ {row[0]}")
        formatted.append('')  # ligne vide après le tableau
        return formatted

    # Appliquer la conversion des tableaux
    text = _convert_table(text)

    # === 1. Délimiteurs LaTeX : \[...\] et \(...\) ===
    text = _re.sub(r'\\\[(.+?)\\\]', lambda m: m.group(1), text, flags=_re.DOTALL)
    text = _re.sub(r'\\\((.+?)\\\)', lambda m: m.group(1), text, flags=_re.DOTALL)

    # === 2. Blocs display $$...$$ -> retrait des $$ ===
    text = _re.sub(r'\$\$(.+?)\$\$', lambda m: m.group(1), text, flags=_re.DOTALL)

    # === 3. Fractions \frac{a}{b} -> a/b ===
    text = _re.sub(r'\\frac\{([^}]+)\}\{([^}]+)\}', r'\1/\2', text)

    # === 4. Exposants ^{...} ou ^x ===
    def _replace_sup(m):
        inner = m.group(1) or m.group(2)
        return ''.join(_SUP.get(c, c) for c in inner)
    text = _re.sub(r'\^\{([^}]*)\}|\^([0-9+\-n])', _replace_sup, text)

    # === 5. Indices _{...} ou _x ===
    def _replace_sub(m):
        inner = m.group(1) or m.group(2)
        return ''.join(_SUB.get(c, c) for c in inner)
    text = _re.sub(r'_\{([^}]*)\}|_([0-9+\-n])', _replace_sub, text)

    # === 6. Symboles grecs et math (plus longs d'abord) ===
    for latex, uni in sorted({**_GREEK, **_MATH}.items(), key=lambda x: -len(x[0])):
        text = text.replace(latex, uni)

    # === 7. Accolades LaTeX restantes {} ===
    text = text.replace('{', '').replace('}', '')

    # === 8. Inline $...$ restants -> retrait des $ ===
    text = _re.sub(r'\$([^$]+?)\$', r'\1', text)

    # === 9. Commandes LaTeX génériques restantes \cmd -> retrait ===
    text = _re.sub(r'\\[a-zA-Z]+', '', text)

    return text


def _split_message(text: str, max_len: int = _MAX_TG_LEN) -> list[str]:
    """Découpe un message long et applique la conversion LaTeX→Unicode."""
    text = _latex_to_telegram(text)
    if len(text) <= max_len:
        return [text]
    chunks: list[str] = []
    while text:
        chunks.append(text[:max_len])
        text = text[max_len:]
    return chunks


async def _send_files_from_reply(
    reply: str,
    chat_id: int,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """
    Détecte les chemins de fichiers générés par les outils dans la réponse
    et les envoie automatiquement en pièce jointe Telegram.
    Supporte: PDF, DOCX, XLSX, PPTX, ODT, ODS, TEX, XML.
    """
    # Regex : chemins absolus contenant une extension connue
    pattern = r'(/(?:[\w/. \-_]|(?<=\\) )+(?:' + '|'.join(
        re.escape(e) for e in _SENDABLE_EXTENSIONS
    ) + r'))'
    found = re.findall(pattern, reply, re.IGNORECASE)
    sent: set[str] = set()
    for fpath in found:
        fpath = fpath.strip()
        if fpath in sent:
            continue
        sent.add(fpath)
        p = Path(fpath)
        if not p.exists() or p.stat().st_size == 0:
            continue
        try:
            with open(p, "rb") as f:
                await context.bot.send_document(
                    chat_id=chat_id,
                    document=f,
                    filename=p.name,
                    caption=f"📤 {p.name}",
                )
            logger.info("Pièce jointe envoyée : %s", fpath)
        except Exception as exc:
            logger.warning("Impossible d'envoyer %s : %s", fpath, exc)



def _get_history(context: ContextTypes.DEFAULT_TYPE) -> list[dict]:
    """Récupère (ou initialise) l'historique conversationnel de l'utilisateur."""
    if "history" not in context.user_data:
        context.user_data["history"] = []
    return context.user_data["history"]


# ══════════════════════════════════════════════════════════════════════════════
# Handlers
# ══════════════════════════════════════════════════════════════════════════════


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Commande /start."""
    user = update.effective_user
    context.user_data["history"] = []  # reset à chaque /start
    await update.message.reply_html(
        rf"Bonjour {user.mention_html()} ! 👋"
        "\nJe suis <b>Prométhée</b>, votre assistant IA de Physique-Chimie."
        "\n\nEnvoyez-moi :"
        "\n• Un <b>message</b> pour poser une question"
        "\n• Une <b>photo</b> de copie ou de schéma à analyser"
        "\n• Un <b>PDF</b> scanné pour en extraire le texte"
        "\n\n/clear pour réinitialiser la conversation"
        "\n/help pour l'aide",
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Commande /help."""
    await update.message.reply_text(
        "🔬 Outils disponibles :\n"
        "• Constantes physiques (NIST/CODATA)\n"
        "• Recherche PubChem (masses molaires, formules)\n"
        "• Export LaTeX → PDF\n"
        "• Export QCM Moodle XML\n"
        "• Analyse Python (numpy/scipy/matplotlib)\n"
        "• OCR Tesseract + Vision IA (copies manuscrites)\n"
        "\nEnvoyez simplement votre demande en langage naturel.",
    )


async def cmd_clear(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Commande /clear — réinitialise la mémoire conversationnelle."""
    context.user_data["history"] = []
    await update.message.reply_text(
        "♻️ Mémoire de conversation réinitialisée. Nous repartons sur un contexte vierge."
    )


async def _call_agent(
    messages: list[dict],
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
) -> str:
    """
    Appelle le moteur agent_loop avec la bonne signature et gère
    le callback de progression d'outils.
    """
    tool_messages: list[str] = []

    def _progress_cb(msg: str) -> None:
        tool_messages.append(msg)

    tools_engine.set_tool_progress_callback(_progress_cb)
    try:
        final_response = llm_service.agent_loop(messages)
    finally:
        tools_engine.set_tool_progress_callback(None)

    # Préfixer la réponse avec les outils invoqués (si pertinent)
    parts: list[str] = []
    if tool_messages:
        parts.append("🛠️ Outils utilisés :")
        for tm in tool_messages:
            parts.append(f"  • {tm}")
        parts.append("")
    parts.append(final_response)
    return "\n".join(parts)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Traite les messages texte de l'utilisateur."""
    user_text = update.message.text
    chat_id = update.effective_chat.id
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")

    history = _get_history(context)

    # Injecter le system prompt si absent (première interaction)
    if not history or history[0].get("role") != "system":
        syst_instruction = (
            "Tu es Prométhée, un assistant expert en Sciences Physiques et Chimiques.\n"
            "RÉPONSES : Utilise un ton pro, pédagogique et scientifique.\n"
            "FICHIERS : Si l'utilisateur demande de créer un fichier (ex: script Python, "
            "document texte, simulation), utilise l'outil `write_file` ou les outils d'export.\n"
            "IMPORTANT : Affiche toujours le CHEMIN ABSOLU du fichier généré dans ta réponse finale "
            "pour qu'il soit envoyé automatiquement en pièce jointe Telegram.\n"
        )
        history.insert(0, {"role": "system", "content": syst_instruction})

    history.append({"role": "user", "content": user_text})

    try:
        reply = await _call_agent(history, context, chat_id)
        history.append({"role": "assistant", "content": reply})

        # Détecter une éventuelle image matplotlib générée
        img_match = re.search(r"(/tmp/promethee_plot_[^\s]+\.png)", reply)

        for chunk in _split_message(reply):
            await update.message.reply_text(chunk, parse_mode=None)

        if img_match:
            img_path = img_match.group(1)
            if os.path.exists(img_path):
                with open(img_path, "rb") as f:
                    await context.bot.send_photo(chat_id=chat_id, photo=f)

        # Envoyer automatiquement les fichiers générés (PDF, DOCX, etc.)
        await _send_files_from_reply(reply, chat_id, context)

    except Exception as e:
        logger.exception("Erreur handle_message")
        await update.message.reply_text(f"❌ Erreur interne : {e}")


# Timers asyncio pour le batch de photos (un par chat_id)
import asyncio
_photo_batch_timers: dict[int, asyncio.Task] = {}


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Accumule les photos dans un buffer par utilisateur.
    Un timer asyncio de 30s se reset à chaque nouvelle photo.
    Quand le timer expire, toutes les photos sont traitées en un seul lot.
    """
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    # Télécharger la photo
    photo = update.message.photo[-1]  # meilleure résolution
    tg_file = await context.bot.get_file(photo.file_id)

    dl_dir = Path.home() / "Downloads" / "Promethee_Telegram"
    dl_dir.mkdir(parents=True, exist_ok=True)
    file_path = dl_dir / f"{photo.file_unique_id}.jpg"
    await tg_file.download_to_drive(file_path)

    # Initialiser le buffer si nécessaire
    if "photo_buffer" not in context.user_data:
        context.user_data["photo_buffer"] = []

    # Ajouter au buffer
    context.user_data["photo_buffer"].append(str(file_path))

    # Capturer le caption de la première photo comme consigne
    caption = update.message.caption
    if caption and "photo_caption" not in context.user_data:
        context.user_data["photo_caption"] = caption

    n = len(context.user_data["photo_buffer"])
    logger.info("Photo %d ajoutée au buffer : %s", n, file_path.name)

    # Annuler le timer précédent s'il existe
    old_task = _photo_batch_timers.get(chat_id)
    if old_task and not old_task.done():
        old_task.cancel()

    # Programmer un nouveau timer de 30 secondes
    _photo_batch_timers[chat_id] = asyncio.create_task(
        _photo_batch_timer(chat_id, user_id, context)
    )

    # Confirmer la réception
    await update.message.reply_text(
        f"📷 Photo {n} reçue. Envoyez les pages suivantes ou patientez 30s "
        f"pour lancer l'analyse du lot complet."
    )


async def _photo_batch_timer(
    chat_id: int, user_id: int, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Timer asyncio : attend 30s puis lance le traitement du lot."""
    try:
        await asyncio.sleep(30)
    except asyncio.CancelledError:
        return  # nouveau timer programmé, on abandonne
    # Timer expiré — lancer le traitement
    await _process_photo_batch(chat_id, user_id, context)


async def _process_photo_batch(
    chat_id: int, user_id: int, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Traite toutes les photos accumulées en un seul lot.
    Produit une correction consolidée avec une note unique.
    """
    # Récupérer le buffer depuis user_data
    user_data = context.user_data if hasattr(context, 'user_data') else {}
    photo_paths = user_data.pop("photo_buffer", [])
    caption = user_data.pop("photo_caption", None)

    if not photo_paths:
        return

    n = len(photo_paths)
    logger.info("Traitement du lot de %d photo(s) pour user %s", n, user_id)

    await context.bot.send_chat_action(chat_id=chat_id, action="typing")
    await context.bot.send_message(
        chat_id=chat_id,
        text=f"📚 Analyse de {n} page(s) en cours… Cela peut prendre quelques minutes.",
    )

    # Construire la liste des pages
    pages_list = "\n".join(
        f"  - Page {i+1} : '{p}'" for i, p in enumerate(photo_paths)
    )

    # Consigne utilisateur
    if not caption or caption.lower() in ("que représente cette image ?",):
        user_instruction = (
            "Corrige cette copie d'élève en physique-chimie. "
            "Attribue une note globale sur 20 avec un barème détaillé par exercice."
        )
    else:
        user_instruction = caption

    bot_prompt = (
        f"L'utilisateur vient de t'envoyer les {n} pages d'une copie d'élève "
        f"via Telegram.\n\n"
        f"Pages stockées :\n{pages_list}\n\n"
        f"CONSIGNE DE L'UTILISATEUR : \"{user_instruction}\"\n\n"
        f"INSTRUCTIONS OBLIGATOIRES :\n"
        f"1. Utilise l'outil `ocr_vision_openrouter` sur CHAQUE page pour "
        f"transcrire fidèlement le texte, les formules, les schémas.\n"
        f"2. Consolide les transcriptions en UN SEUL document cohérent "
        f"(c'est UNE SEULE copie en plusieurs pages).\n"
        f"3. Produis UN SEUL rapport de correction avec :\n"
        f"   - Transcription complète de la copie\n"
        f"   - Correction détaillée exercice par exercice\n"
        f"   - Points forts et erreurs identifiées\n"
        f"   - UNE SEULE note globale sur 20\n"
        f"4. NE produis PAS une note par page. C'est UNE copie = UNE note.\n"
        f"5. RÈGLE DE CALCUL OBLIGATOIRE pour la note finale :\n"
        f"   Si les barèmes des exercices ne font pas un total de 20 points, "
        f"   tu DOIS ramener la note sur 20 par proportionnalité :\n"
        f"   note_sur_20 = (total_points_obtenus / total_points_possibles) × 20\n"
        f"   Exemple : Exo1 = 12/16, Exo2 = 3.5/10. Total = 15.5/26. "
        f"   Note finale = (15.5/26) × 20 = 11.9/20.\n"
        f"   NE JAMAIS simplement additionner les notes si le barème total ≠ 20.\n"
        f"6. Si tu génères un rapport PDF avec export_pdf_latex :\n"
        f"   - Utilise un code LaTeX simple et correct\n"
        f"   - N'utilise PAS de packages exotiques (amsmath, geometry et inputenc suffisent)\n"
        f"   - Teste que le code compile avant de l'envoyer\n"
    )

    # Utiliser l'historique de l'utilisateur
    history = user_data.setdefault("history", [])
    history.append({"role": "user", "content": bot_prompt})

    try:
        # Appeler l'agent — un seul appel pour toutes les pages
        tool_messages: list[str] = []

        def _progress_cb(msg: str) -> None:
            tool_messages.append(msg)

        tools_engine.set_tool_progress_callback(_progress_cb)
        try:
            final_response = llm_service.agent_loop(history)
        finally:
            tools_engine.set_tool_progress_callback(None)

        # Construire la réponse
        parts: list[str] = []
        if tool_messages:
            parts.append("🛠️ Outils utilisés :")
            for tm in tool_messages:
                parts.append(f"  • {tm}")
            parts.append("")
        parts.append(final_response)
        reply = "\n".join(parts)

        history.append({"role": "assistant", "content": reply})

        for chunk in _split_message(reply):
            await context.bot.send_message(chat_id=chat_id, text=chunk)

        # Envoyer les fichiers générés (PDF, etc.)
        await _send_files_from_reply(reply, chat_id, context)

    except Exception as e:
        logger.exception("Erreur _process_photo_batch")
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"❌ Erreur lors de l'analyse du lot de {n} photos : {e}",
        )


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Traite les documents envoyés (PDF, CSV, etc.)."""
    chat_id = update.effective_chat.id
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")

    doc = update.message.document
    tg_file = await context.bot.get_file(doc.file_id)

    dl_dir = Path.home() / "Downloads" / "Promethee_Telegram"
    dl_dir.mkdir(parents=True, exist_ok=True)

    original_name = doc.file_name or f"document_{doc.file_unique_id}"
    file_path = dl_dir / original_name
    await tg_file.download_to_drive(file_path)

    caption = update.message.caption or "Analyse ce document."
    ext = file_path.suffix.lower()

    # Choisir l'outil adapté selon l'extension
    if ext == ".pdf":
        tool_hint = (
            "Utilise d'abord `ocr_pdf_detect` pour déterminer si c'est un PDF scanné ou numérique, "
            "puis `ocr_pdf` pour en extraire le texte."
        )
    elif ext in (".csv", ".xlsx", ".xls"):
        tool_hint = "Utilise `df_read` pour charger ce fichier de données, puis réponds à la consigne."
    else:
        tool_hint = "Analyse le fichier selon son type et réponds à la consigne."

    bot_prompt = (
        f"L'utilisateur vient de t'envoyer un document via Telegram.\n"
        f"Fichier : '{file_path}' (type : {ext})\n"
        f"Consigne : \"{caption}\"\n"
        f"{tool_hint}"
    )

    history = _get_history(context)
    history.append({"role": "user", "content": bot_prompt})

    try:
        reply = await _call_agent(history, context, chat_id)
        history.append({"role": "assistant", "content": reply})

        for chunk in _split_message(reply):
            await update.message.reply_text(chunk, parse_mode=None)

        # Envoyer automatiquement les fichiers générés (PDF, DOCX, etc.)
        await _send_files_from_reply(reply, chat_id, context)

    except Exception as e:
        logger.exception("Erreur handle_document")
        await update.message.reply_text(f"❌ Erreur interne : {e}")


# ══════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════


def main() -> None:
    """Démarre le bot Telegram Prométhée."""
    TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

    if not TELEGRAM_TOKEN:
        logger.error("TELEGRAM_TOKEN manquant dans le .env")
        print("Erreur : définissez TELEGRAM_TOKEN dans le fichier .env.")
        sys.exit(1)

    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # Commandes
    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("help", cmd_help))
    application.add_handler(CommandHandler("clear", cmd_clear))

    # Messages
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))

    logger.info("Bot Telegram Prométhée démarré. En attente de messages...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
