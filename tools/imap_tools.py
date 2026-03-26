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
tools/imap_tools.py — Outils d'accès messagerie via IMAP / SMTP
================================================================

Outils exposés (8) :

  Lecture (3) :
    - imap_list_mails     : liste les N derniers mails d'un dossier
    - imap_search_mails   : recherche multicritères (expéditeur, objet, date, corps)
    - imap_read_mail      : lit un mail complet (headers + corps + pièces jointes)

  Écriture (2) :
    - imap_send_mail      : envoie un mail via SMTP (HTML, PJ chemin disque ou base64)
    - imap_reply_mail     : répond à un mail existant (In-Reply-To, References, HTML, PJ)

  Gestion (3) :
    - imap_mark_mail      : marque lu / non-lu / important / supprimé
    - imap_move_mail      : déplace un mail vers un autre dossier
    - imap_list_folders   : liste les dossiers IMAP disponibles

  Gestion (3) :
    - imap_mark_mail      : marque lu / non-lu / important / supprimé
    - imap_move_mail      : déplace un mail vers un autre dossier
    - imap_list_folders   : liste les dossiers IMAP disponibles

Profils (multi-comptes) :
  Chaque opération accepte un paramètre optionnel `profil` qui correspond
  à un préfixe de variables d'environnement. Sans profil, le compte par
  défaut (IMAP_HOST, IMAP_USER…) est utilisé.

  Exemple avec profil "pro" :
    IMAP_PRO_HOST, IMAP_PRO_PORT, IMAP_PRO_USER, IMAP_PRO_PASSWORD,
    IMAP_PRO_SSL, IMAP_PRO_OAUTH2_TOKEN,
    SMTP_PRO_HOST, SMTP_PRO_PORT, SMTP_PRO_USER, SMTP_PRO_PASSWORD

Authentification :
  Détection automatique dans l'ordre :
    1. XOAUTH2 si IMAP_[PROFIL_]OAUTH2_TOKEN est défini
    2. LOGIN/mot de passe sinon

Pièces jointes :
  imap_read_mail retourne les métadonnées de toutes les PJ.
  Les PJ PDF, images (jpg/png/gif/webp) et Office (docx/xlsx/pptx) sont
  décodées en base64 pour transmission directe à l'agent.
  Les autres types sont disponibles en téléchargement brut (base64).

Usage :
    import tools.imap_tools   # suffit à enregistrer les outils
"""

import base64
import email
import email.header
import email.policy
import email.utils
import imaplib
import os
import smtplib
import ssl
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from typing import Optional

from core.tools_engine import tool, set_current_family, _TOOL_ICONS

set_current_family("imap_tools", "Messagerie IMAP", "📧")

# ── Icônes UI ─────────────────────────────────────────────────────────────────
_TOOL_ICONS.update({
    "imap_list_mails":   "📬",
    "imap_search_mails": "🔎",
    "imap_read_mail":    "📧",
    "imap_send_mail":    "📤",
    "imap_reply_mail":   "↩️",
    "imap_mark_mail":    "🏷️",
    "imap_move_mail":    "📁",
    "imap_list_folders": "🗂️",
})

# Extensions de pièces jointes décodées inline (base64 transmis à l'agent)
_INLINE_EXTENSIONS = {
    ".pdf", ".jpg", ".jpeg", ".png", ".gif", ".webp",
    ".docx", ".xlsx", ".pptx", ".doc", ".xls", ".ppt",
}


# ══════════════════════════════════════════════════════════════════════════════
# Helpers internes
# ══════════════════════════════════════════════════════════════════════════════

def _get_profile_config(profil: Optional[str] = None) -> dict:
    """
    Construit la configuration IMAP/SMTP pour un profil donné.

    Sans profil : utilise IMAP_HOST, IMAP_USER, IMAP_PASSWORD, etc.
    Avec profil "pro" : utilise IMAP_PRO_HOST, IMAP_PRO_USER, etc.

    Returns dict avec les clés :
        imap_host, imap_port, imap_user, imap_password, imap_ssl,
        imap_oauth2_token,
        smtp_host, smtp_port, smtp_user, smtp_password, smtp_ssl,
        from_address, display_name
    """
    prefix = f"IMAP_{profil.upper()}_" if profil else "IMAP_"
    smtp_prefix = f"SMTP_{profil.upper()}_" if profil else "SMTP_"

    def _get(key: str, default: str = "") -> str:
        return os.getenv(key, default).strip()

    def _bool(key: str, default: bool = True) -> bool:
        val = os.getenv(key, "").strip().upper()
        if not val:
            return default
        return val in ("ON", "TRUE", "1", "YES")

    return {
        "imap_host":        _get(f"{prefix}HOST"),
        "imap_port":        int(os.getenv(f"{prefix}PORT", "993" if _bool(f"{prefix}SSL") else "143")),
        "imap_user":        _get(f"{prefix}USER"),
        "imap_password":    _get(f"{prefix}PASSWORD"),
        "imap_ssl":         _bool(f"{prefix}SSL", default=True),
        "imap_oauth2_token":_get(f"{prefix}OAUTH2_TOKEN"),
        "smtp_host":        _get(f"{smtp_prefix}HOST") or _get(f"{prefix}HOST"),
        "smtp_port":        int(os.getenv(f"{smtp_prefix}PORT", "465")),
        "smtp_user":        _get(f"{smtp_prefix}USER") or _get(f"{prefix}USER"),
        "smtp_password":    _get(f"{smtp_prefix}PASSWORD") or _get(f"{prefix}PASSWORD"),
        "smtp_ssl":         _bool(f"{smtp_prefix}SSL", default=True),
        "smtp_oauth2_token":_get(f"{smtp_prefix}OAUTH2_TOKEN") or _get(f"{prefix}OAUTH2_TOKEN"),
        "from_address":     _get(f"{prefix}FROM") or _get(f"{prefix}USER"),
        "display_name":     _get(f"{prefix}DISPLAY_NAME"),
    }


def _validate_config(cfg: dict, need_smtp: bool = False) -> tuple[bool, str]:
    """Vérifie que les variables minimales sont définies."""
    missing = []
    for key in ("imap_host", "imap_user"):
        if not cfg.get(key):
            missing.append(key.upper())
    if not cfg.get("imap_password") and not cfg.get("imap_oauth2_token"):
        missing.append("IMAP_PASSWORD ou IMAP_OAUTH2_TOKEN")
    if need_smtp and not cfg.get("smtp_host"):
        missing.append("SMTP_HOST")
    if missing:
        return False, (
            f"Configuration incomplète — variables manquantes : {', '.join(missing)}. "
            "Vérifiez votre fichier .env."
        )
    return True, ""


def _imap_connect(cfg: dict) -> tuple[bool, "imaplib.IMAP4 | str"]:
    """
    Ouvre une connexion IMAP authentifiée.

    Détection automatique du mécanisme :
      1. XOAUTH2 si imap_oauth2_token est défini
      2. LOGIN sinon (compatibilité maximale)

    Returns (success, imap_connection | error_message)
    """
    try:
        if cfg["imap_ssl"]:
            context = ssl.create_default_context()
            imap = imaplib.IMAP4_SSL(cfg["imap_host"], cfg["imap_port"], ssl_context=context)
        else:
            imap = imaplib.IMAP4(cfg["imap_host"], cfg["imap_port"])
            # STARTTLS si disponible
            if "STARTTLS" in imap.capabilities:
                imap.starttls()

        # Authentification
        if cfg.get("imap_oauth2_token"):
            auth_string = f"user={cfg['imap_user']}\x01auth=Bearer {cfg['imap_oauth2_token']}\x01\x01"
            imap.authenticate("XOAUTH2", lambda x: auth_string.encode())
        else:
            imap.login(cfg["imap_user"], cfg["imap_password"])

        return True, imap

    except imaplib.IMAP4.error as e:
        msg = str(e)
        if "AUTHENTICATIONFAILED" in msg or "authentication failed" in msg.lower():
            return False, (
                "Authentification IMAP échouée. Vérifiez IMAP_USER / IMAP_PASSWORD "
                "(ou IMAP_OAUTH2_TOKEN si OAuth2)."
            )
        return False, f"Erreur IMAP : {msg}"
    except Exception as e:
        return False, f"Impossible de se connecter à {cfg['imap_host']}:{cfg['imap_port']} — {e}"


def _decode_header(value: str) -> str:
    """Décode un header email (encoded-words RFC 2047)."""
    if not value:
        return ""
    parts = email.header.decode_header(value)
    decoded = []
    for part, charset in parts:
        if isinstance(part, bytes):
            try:
                decoded.append(part.decode(charset or "utf-8", errors="replace"))
            except Exception:
                decoded.append(part.decode("latin-1", errors="replace"))
        else:
            decoded.append(str(part))
    return " ".join(decoded).strip()


def _extract_body(msg: email.message.Message) -> tuple[str, str]:
    """
    Extrait le corps du message.
    Retourne (texte_plain, texte_html).
    """
    plain, html = "", ""

    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            disp = str(part.get("Content-Disposition", ""))
            if "attachment" in disp:
                continue
            payload = part.get_payload(decode=True)
            if payload is None:
                continue
            charset = part.get_content_charset() or "utf-8"
            text = payload.decode(charset, errors="replace")
            if ct == "text/plain" and not plain:
                plain = text
            elif ct == "text/html" and not html:
                html = text
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            text = payload.decode(charset, errors="replace")
            if msg.get_content_type() == "text/html":
                html = text
            else:
                plain = text

    return plain, html


def _extract_attachments(msg: email.message.Message) -> list[dict]:
    """
    Extrait les pièces jointes.
    Les types inline (_INLINE_EXTENSIONS) sont encodés en base64.
    """
    attachments = []

    if not msg.is_multipart():
        return attachments

    for part in msg.walk():
        disp = str(part.get("Content-Disposition", ""))
        filename = part.get_filename()
        if not filename and "attachment" not in disp:
            continue

        filename = _decode_header(filename or "fichier_sans_nom")
        content_type = part.get_content_type()
        payload = part.get_payload(decode=True)
        if payload is None:
            continue

        ext = os.path.splitext(filename)[1].lower()
        att: dict = {
            "filename":     filename,
            "content_type": content_type,
            "size_bytes":   len(payload),
        }

        if ext in _INLINE_EXTENSIONS:
            att["data_base64"] = base64.b64encode(payload).decode("ascii")
            att["inline"] = True
        else:
            att["data_base64"] = base64.b64encode(payload).decode("ascii")
            att["inline"] = False

        attachments.append(att)

    return attachments


def _parse_message(raw: bytes) -> dict:
    """Parse un message brut en dict structuré."""
    msg = email.message_from_bytes(raw, policy=email.policy.compat32)
    plain, html = _extract_body(msg)
    attachments = _extract_attachments(msg)

    date_str = msg.get("Date", "")
    try:
        date_parsed = email.utils.parsedate_to_datetime(date_str).isoformat()
    except Exception:
        date_parsed = date_str

    return {
        "message_id": msg.get("Message-ID", "").strip(),
        "from":       _decode_header(msg.get("From", "")),
        "to":         _decode_header(msg.get("To", "")),
        "cc":         _decode_header(msg.get("Cc", "")),
        "subject":    _decode_header(msg.get("Subject", "(sans objet)")),
        "date":       date_parsed,
        "body_plain": plain,
        "body_html":  html if not plain else "",   # html seulement si pas de plain
        "attachments": attachments,
        "in_reply_to": msg.get("In-Reply-To", "").strip(),
        "references":  msg.get("References", "").strip(),
    }


def _imap_select_folder(imap, folder: str) -> tuple[bool, str]:
    """Sélectionne un dossier IMAP, avec fallback sur variantes encodées."""
    # Essai direct
    typ, data = imap.select(f'"{folder}"')
    if typ == "OK":
        return True, folder
    # Essai sans guillemets
    typ, data = imap.select(folder)
    if typ == "OK":
        return True, folder
    return False, f"Dossier '{folder}' introuvable. Utilisez imap_list_folders pour lister les dossiers disponibles."


# ══════════════════════════════════════════════════════════════════════════════
# Outils exposés
# ══════════════════════════════════════════════════════════════════════════════

@tool(
    name="imap_list_folders",
    description=(
        "Liste les dossiers (boîtes) disponibles sur le serveur IMAP. "
        "Utile pour connaître le nom exact des dossiers avant de les utiliser "
        "dans les autres outils (INBOX, Sent, Trash, dossiers personnalisés…)."
    ),
    parameters={
        "type": "object",
        "properties": {
            "profil": {
                "type": "string",
                "description": (
                    "Nom du profil de compte (optionnel). Correspond au préfixe "
                    "des variables .env : 'pro' → IMAP_PRO_HOST, etc. "
                    "Sans valeur : compte par défaut (IMAP_HOST)."
                ),
            },
        },
        "required": [],
    },
)
def imap_list_folders(profil: Optional[str] = None) -> dict:
    cfg = _get_profile_config(profil)
    ok, err = _validate_config(cfg)
    if not ok:
        return {"status": "error", "error": err}

    ok, result = _imap_connect(cfg)
    if not ok:
        return {"status": "error", "error": result}

    imap = result
    try:
        typ, data = imap.list()
        folders = []
        for item in data:
            if isinstance(item, bytes):
                decoded = item.decode("utf-8", errors="replace")
                # Format : (\HasNoChildren) "/" "INBOX"
                parts = decoded.rsplit('" ', 1)
                if len(parts) == 2:
                    folders.append(parts[1].strip().strip('"'))
                else:
                    folders.append(decoded)
        folders.sort()
        return {
            "status": "success",
            "compte": cfg["imap_user"],
            "nb_dossiers": len(folders),
            "dossiers": folders,
        }
    except Exception as e:
        return {"status": "error", "error": f"Erreur listage dossiers : {e}"}
    finally:
        try:
            imap.logout()
        except Exception:
            pass


@tool(
    name="imap_list_mails",
    description=(
        "Liste les derniers mails d'un dossier IMAP (INBOX par défaut). "
        "Retourne les N messages les plus récents avec expéditeur, objet, date et indicateurs. "
        "Utiliser imap_list_folders pour connaître les noms de dossiers disponibles."
    ),
    parameters={
        "type": "object",
        "properties": {
            "dossier": {
                "type": "string",
                "description": "Nom du dossier IMAP (défaut : INBOX).",
            },
            "n": {
                "type": "integer",
                "description": "Nombre de mails à retourner (défaut : 20, max : 100).",
            },
            "non_lus_seulement": {
                "type": "boolean",
                "description": "Si true, ne retourne que les mails non lus (défaut : false).",
            },
            "profil": {
                "type": "string",
                "description": "Nom du profil de compte (optionnel, défaut : compte principal).",
            },
        },
        "required": [],
    },
)
def imap_list_mails(
    dossier: str = "INBOX",
    n: int = 20,
    non_lus_seulement: bool = False,
    profil: Optional[str] = None,
) -> dict:
    cfg = _get_profile_config(profil)
    ok, err = _validate_config(cfg)
    if not ok:
        return {"status": "error", "error": err}

    n = min(max(1, n), 100)

    ok, result = _imap_connect(cfg)
    if not ok:
        return {"status": "error", "error": result}

    imap = result
    try:
        ok_sel, err_sel = _imap_select_folder(imap, dossier)
        if not ok_sel:
            return {"status": "error", "error": err_sel}

        # Recherche des UIDs
        criteria = "UNSEEN" if non_lus_seulement else "ALL"
        typ, data = imap.search(None, criteria)
        if typ != "OK":
            return {"status": "error", "error": f"Erreur recherche dans {dossier}."}

        uids = data[0].split()
        uids = uids[-n:]  # Les N plus récents

        if not uids:
            return {
                "status": "success",
                "dossier": dossier,
                "compte": cfg["imap_user"],
                "mails": [],
                "message": "Aucun mail trouvé.",
            }

        mails = []
        for uid in reversed(uids):
            typ, msg_data = imap.fetch(uid, "(BODY.PEEK[HEADER.FIELDS (FROM TO SUBJECT DATE FLAGS)])")
            if typ != "OK" or not msg_data or not msg_data[0]:
                continue
            raw = msg_data[0][1] if isinstance(msg_data[0], tuple) else msg_data[0]
            msg = email.message_from_bytes(raw)

            # Flags (lu, important…)
            typ_f, flags_data = imap.fetch(uid, "(FLAGS)")
            flags_str = flags_data[0].decode("utf-8", errors="replace") if flags_data else ""
            is_read = "\\Seen" in flags_str
            is_flagged = "\\Flagged" in flags_str

            date_str = msg.get("Date", "")
            try:
                date_parsed = email.utils.parsedate_to_datetime(date_str).isoformat()
            except Exception:
                date_parsed = date_str

            mails.append({
                "uid":      uid.decode(),
                "from":     _decode_header(msg.get("From", "")),
                "to":       _decode_header(msg.get("To", "")),
                "subject":  _decode_header(msg.get("Subject", "(sans objet)")),
                "date":     date_parsed,
                "lu":       is_read,
                "important": is_flagged,
            })

        return {
            "status":  "success",
            "dossier": dossier,
            "compte":  cfg["imap_user"],
            "nb":      len(mails),
            "mails":   mails,
        }

    except Exception as e:
        return {"status": "error", "error": f"Erreur lecture dossier : {e}"}
    finally:
        try:
            imap.logout()
        except Exception:
            pass


@tool(
    name="imap_search_mails",
    description=(
        "Recherche des mails dans un dossier IMAP selon plusieurs critères : "
        "expéditeur, destinataire, objet, corps du message, période. "
        "Tous les critères sont optionnels et cumulatifs (ET logique). "
        "Retourne les N mails les plus récents correspondant à la recherche."
    ),
    parameters={
        "type": "object",
        "properties": {
            "dossier": {
                "type": "string",
                "description": "Dossier dans lequel chercher (défaut : INBOX).",
            },
            "expediteur": {
                "type": "string",
                "description": "Filtre sur l'expéditeur (FROM, recherche partielle).",
            },
            "destinataire": {
                "type": "string",
                "description": "Filtre sur le destinataire (TO, recherche partielle).",
            },
            "objet": {
                "type": "string",
                "description": "Filtre sur l'objet du mail (SUBJECT, recherche partielle).",
            },
            "corps": {
                "type": "string",
                "description": "Filtre sur le corps du mail (BODY, recherche partielle).",
            },
            "depuis": {
                "type": "string",
                "description": "Date de début au format YYYY-MM-DD (ex: 2025-01-01).",
            },
            "jusqu_au": {
                "type": "string",
                "description": "Date de fin au format YYYY-MM-DD (ex: 2025-12-31).",
            },
            "non_lus_seulement": {
                "type": "boolean",
                "description": "Si true, filtre sur les mails non lus.",
            },
            "n": {
                "type": "integer",
                "description": "Nombre maximum de résultats (défaut : 20, max : 50).",
            },
            "profil": {
                "type": "string",
                "description": "Nom du profil de compte (optionnel).",
            },
        },
        "required": [],
    },
)
def imap_search_mails(
    dossier: str = "INBOX",
    expediteur: Optional[str] = None,
    destinataire: Optional[str] = None,
    objet: Optional[str] = None,
    corps: Optional[str] = None,
    depuis: Optional[str] = None,
    jusqu_au: Optional[str] = None,
    non_lus_seulement: bool = False,
    n: int = 20,
    profil: Optional[str] = None,
) -> dict:
    cfg = _get_profile_config(profil)
    ok, err = _validate_config(cfg)
    if not ok:
        return {"status": "error", "error": err}

    n = min(max(1, n), 50)

    ok, result = _imap_connect(cfg)
    if not ok:
        return {"status": "error", "error": result}

    imap = result
    try:
        ok_sel, err_sel = _imap_select_folder(imap, dossier)
        if not ok_sel:
            return {"status": "error", "error": err_sel}

        # Construction des critères IMAP SEARCH
        criteria = []
        if non_lus_seulement:
            criteria.append("UNSEEN")
        if expediteur:
            criteria.extend(["FROM", f'"{expediteur}"'])
        if destinataire:
            criteria.extend(["TO", f'"{destinataire}"'])
        if objet:
            criteria.extend(["SUBJECT", f'"{objet}"'])
        if corps:
            criteria.extend(["BODY", f'"{corps}"'])
        if depuis:
            try:
                dt = datetime.strptime(depuis, "%Y-%m-%d")
                imap_date = dt.strftime("%d-%b-%Y")
                criteria.extend(["SINCE", imap_date])
            except ValueError:
                pass
        if jusqu_au:
            try:
                dt = datetime.strptime(jusqu_au, "%Y-%m-%d") + timedelta(days=1)
                imap_date = dt.strftime("%d-%b-%Y")
                criteria.extend(["BEFORE", imap_date])
            except ValueError:
                pass

        if not criteria:
            criteria = ["ALL"]

        # imaplib.search attend une chaîne ou des bytes
        search_str = " ".join(criteria)
        typ, data = imap.search(None, search_str)
        if typ != "OK":
            return {"status": "error", "error": "Erreur lors de la recherche IMAP."}

        uids = data[0].split()
        uids = uids[-n:]

        if not uids:
            return {
                "status": "success",
                "dossier": dossier,
                "compte": cfg["imap_user"],
                "mails": [],
                "message": "Aucun mail ne correspond aux critères.",
            }

        mails = []
        for uid in reversed(uids):
            typ, msg_data = imap.fetch(uid, "(BODY.PEEK[HEADER.FIELDS (FROM TO SUBJECT DATE)])")
            if typ != "OK" or not msg_data or not msg_data[0]:
                continue
            raw = msg_data[0][1] if isinstance(msg_data[0], tuple) else msg_data[0]
            msg = email.message_from_bytes(raw)

            date_str = msg.get("Date", "")
            try:
                date_parsed = email.utils.parsedate_to_datetime(date_str).isoformat()
            except Exception:
                date_parsed = date_str

            mails.append({
                "uid":     uid.decode(),
                "from":    _decode_header(msg.get("From", "")),
                "to":      _decode_header(msg.get("To", "")),
                "subject": _decode_header(msg.get("Subject", "(sans objet)")),
                "date":    date_parsed,
            })

        return {
            "status":   "success",
            "dossier":  dossier,
            "compte":   cfg["imap_user"],
            "nb":       len(mails),
            "criteres": {k: v for k, v in {
                "expediteur": expediteur, "destinataire": destinataire,
                "objet": objet, "corps": corps, "depuis": depuis,
                "jusqu_au": jusqu_au,
            }.items() if v},
            "mails": mails,
        }

    except Exception as e:
        return {"status": "error", "error": f"Erreur recherche : {e}"}
    finally:
        try:
            imap.logout()
        except Exception:
            pass


@tool(
    name="imap_read_mail",
    description=(
        "Lit le contenu complet d'un mail : headers, corps (texte et/ou HTML), "
        "et pièces jointes (PDF, images, Office, tous types). "
        "Nécessite l'UID du mail obtenu via imap_list_mails ou imap_search_mails."
    ),
    parameters={
        "type": "object",
        "properties": {
            "uid": {
                "type": "string",
                "description": "UID du mail (champ 'uid' retourné par imap_list_mails / imap_search_mails).",
            },
            "dossier": {
                "type": "string",
                "description": "Dossier contenant le mail (défaut : INBOX).",
            },
            "inclure_html": {
                "type": "boolean",
                "description": "Inclure le corps HTML en plus du texte plain (défaut : false).",
            },
            "inclure_pj": {
                "type": "boolean",
                "description": "Inclure les pièces jointes encodées en base64 (défaut : true).",
            },
            "profil": {
                "type": "string",
                "description": "Nom du profil de compte (optionnel).",
            },
        },
        "required": ["uid"],
    },
)
def imap_read_mail(
    uid: str,
    dossier: str = "INBOX",
    inclure_html: bool = False,
    inclure_pj: bool = True,
    profil: Optional[str] = None,
) -> dict:
    cfg = _get_profile_config(profil)
    ok, err = _validate_config(cfg)
    if not ok:
        return {"status": "error", "error": err}

    ok, result = _imap_connect(cfg)
    if not ok:
        return {"status": "error", "error": result}

    imap = result
    try:
        ok_sel, err_sel = _imap_select_folder(imap, dossier)
        if not ok_sel:
            return {"status": "error", "error": err_sel}

        typ, msg_data = imap.fetch(uid.encode(), "(RFC822)")
        if typ != "OK" or not msg_data or not msg_data[0]:
            return {"status": "error", "error": f"Mail UID {uid} introuvable dans {dossier}."}

        raw = msg_data[0][1] if isinstance(msg_data[0], tuple) else msg_data[0]
        parsed = _parse_message(raw)

        # Marquer comme lu
        imap.store(uid.encode(), "+FLAGS", "\\Seen")

        result_dict = {
            "status":     "success",
            "uid":        uid,
            "dossier":    dossier,
            "compte":     cfg["imap_user"],
            "message_id": parsed["message_id"],
            "from":       parsed["from"],
            "to":         parsed["to"],
            "cc":         parsed["cc"],
            "subject":    parsed["subject"],
            "date":       parsed["date"],
            "body":       parsed["body_plain"] or "(corps vide)",
            "in_reply_to": parsed["in_reply_to"],
            "references": parsed["references"],
        }

        if inclure_html and parsed["body_html"]:
            result_dict["body_html"] = parsed["body_html"]

        if inclure_pj:
            result_dict["attachments"] = parsed["attachments"]
            result_dict["nb_attachments"] = len(parsed["attachments"])
        else:
            # Retourner seulement les métadonnées sans le base64
            result_dict["attachments"] = [
                {"filename": a["filename"], "content_type": a["content_type"],
                 "size_bytes": a["size_bytes"]}
                for a in parsed["attachments"]
            ]
            result_dict["nb_attachments"] = len(parsed["attachments"])

        return result_dict

    except Exception as e:
        return {"status": "error", "error": f"Erreur lecture mail : {e}"}
    finally:
        try:
            imap.logout()
        except Exception:
            pass


@tool(
    name="imap_mark_mail",
    description=(
        "Marque un mail : lu, non-lu, important (étoilé), non-important, ou supprimé. "
        "La suppression marque le mail \\Deleted — il faut un EXPUNGE pour le retirer définitivement "
        "(effectué automatiquement lors de la déconnexion)."
    ),
    parameters={
        "type": "object",
        "properties": {
            "uid": {
                "type": "string",
                "description": "UID du mail à marquer.",
            },
            "action": {
                "type": "string",
                "enum": ["lu", "non_lu", "important", "non_important", "supprime"],
                "description": (
                    "Action à effectuer : "
                    "'lu' → \\Seen, 'non_lu' → retire \\Seen, "
                    "'important' → \\Flagged, 'non_important' → retire \\Flagged, "
                    "'supprime' → \\Deleted + EXPUNGE."
                ),
            },
            "dossier": {
                "type": "string",
                "description": "Dossier contenant le mail (défaut : INBOX).",
            },
            "profil": {
                "type": "string",
                "description": "Nom du profil de compte (optionnel).",
            },
        },
        "required": ["uid", "action"],
    },
)
def imap_mark_mail(
    uid: str,
    action: str,
    dossier: str = "INBOX",
    profil: Optional[str] = None,
) -> dict:
    cfg = _get_profile_config(profil)
    ok, err = _validate_config(cfg)
    if not ok:
        return {"status": "error", "error": err}

    _FLAG_MAP = {
        "lu":           ("+FLAGS", "\\Seen"),
        "non_lu":       ("-FLAGS", "\\Seen"),
        "important":    ("+FLAGS", "\\Flagged"),
        "non_important":("-FLAGS", "\\Flagged"),
        "supprime":     ("+FLAGS", "\\Deleted"),
    }
    if action not in _FLAG_MAP:
        return {"status": "error", "error": f"Action inconnue : {action}"}

    ok, result = _imap_connect(cfg)
    if not ok:
        return {"status": "error", "error": result}

    imap = result
    try:
        ok_sel, err_sel = _imap_select_folder(imap, dossier)
        if not ok_sel:
            return {"status": "error", "error": err_sel}

        op, flag = _FLAG_MAP[action]
        typ, _ = imap.store(uid.encode(), op, flag)
        if typ != "OK":
            return {"status": "error", "error": f"Impossible de marquer le mail UID {uid}."}

        if action == "supprime":
            imap.expunge()

        return {
            "status":  "success",
            "uid":     uid,
            "dossier": dossier,
            "action":  action,
            "message": f"Mail UID {uid} marqué '{action}'.",
        }

    except Exception as e:
        return {"status": "error", "error": f"Erreur marquage : {e}"}
    finally:
        try:
            imap.logout()
        except Exception:
            pass


@tool(
    name="imap_move_mail",
    description=(
        "Déplace un mail d'un dossier vers un autre sur le serveur IMAP. "
        "Utiliser imap_list_folders pour connaître les dossiers disponibles."
    ),
    parameters={
        "type": "object",
        "properties": {
            "uid": {
                "type": "string",
                "description": "UID du mail à déplacer.",
            },
            "dossier_source": {
                "type": "string",
                "description": "Dossier source (défaut : INBOX).",
            },
            "dossier_destination": {
                "type": "string",
                "description": "Dossier de destination.",
            },
            "profil": {
                "type": "string",
                "description": "Nom du profil de compte (optionnel).",
            },
        },
        "required": ["uid", "dossier_destination"],
    },
)
def imap_move_mail(
    uid: str,
    dossier_destination: str,
    dossier_source: str = "INBOX",
    profil: Optional[str] = None,
) -> dict:
    cfg = _get_profile_config(profil)
    ok, err = _validate_config(cfg)
    if not ok:
        return {"status": "error", "error": err}

    ok, result = _imap_connect(cfg)
    if not ok:
        return {"status": "error", "error": result}

    imap = result
    try:
        ok_sel, err_sel = _imap_select_folder(imap, dossier_source)
        if not ok_sel:
            return {"status": "error", "error": err_sel}

        # MOVE (RFC 6851) si disponible, sinon COPY + DELETE
        if b"MOVE" in imap.capabilities or "MOVE" in str(imap.capabilities):
            typ, _ = imap.uid("MOVE", uid.encode(), f'"{dossier_destination}"')
            if typ != "OK":
                return {"status": "error", "error": f"Erreur MOVE vers '{dossier_destination}'."}
        else:
            # Fallback COPY + DELETE
            typ, _ = imap.uid("COPY", uid.encode(), f'"{dossier_destination}"')
            if typ != "OK":
                return {"status": "error", "error": f"Erreur COPY vers '{dossier_destination}'."}
            imap.store(uid.encode(), "+FLAGS", "\\Deleted")
            imap.expunge()

        return {
            "status":      "success",
            "uid":         uid,
            "source":      dossier_source,
            "destination": dossier_destination,
            "message":     f"Mail UID {uid} déplacé de '{dossier_source}' vers '{dossier_destination}'.",
        }

    except Exception as e:
        return {"status": "error", "error": f"Erreur déplacement : {e}"}
    finally:
        try:
            imap.logout()
        except Exception:
            pass


@tool(
    name="imap_send_mail",
    description=(
        "Envoie un mail via SMTP. "
        "Supporte le texte brut et/ou HTML, et les pièces jointes (chemins fichiers sur disque "
        "ou données base64 nommées). "
        "L'expéditeur est défini par IMAP_FROM (ou IMAP_USER) dans le .env."
    ),
    parameters={
        "type": "object",
        "properties": {
            "destinataires": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Liste des adresses email des destinataires (TO).",
            },
            "objet": {
                "type": "string",
                "description": "Objet du mail.",
            },
            "corps": {
                "type": "string",
                "description": "Corps du mail en texte brut (repli obligatoire).",
            },
            "corps_html": {
                "type": "string",
                "description": "Corps du mail en HTML (optionnel, complète le texte brut).",
            },
            "cc": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Destinataires en copie (optionnel).",
            },
            "cci": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Destinataires en copie cachée (optionnel).",
            },
            "pieces_jointes": {
                "type": "array",
                "description": (
                    "Pièces jointes à attacher au mail (optionnel). "
                    "Chaque élément est un objet avec SOIT 'chemin' (chemin absolu du fichier sur disque), "
                    "SOIT 'data_base64' + 'nom_fichier' + 'type_mime' (données en base64). "
                    "Exemples : "
                    "{\"chemin\": \"/home/pierre/Exports/rapport.pdf\"} "
                    "ou {\"data_base64\": \"...\", \"nom_fichier\": \"rapport.pdf\", \"type_mime\": \"application/pdf\"}."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "chemin": {
                            "type": "string",
                            "description": "Chemin absolu du fichier sur le disque.",
                        },
                        "data_base64": {
                            "type": "string",
                            "description": "Contenu du fichier encodé en base64.",
                        },
                        "nom_fichier": {
                            "type": "string",
                            "description": "Nom du fichier tel qu'il apparaîtra dans le mail.",
                        },
                        "type_mime": {
                            "type": "string",
                            "description": "Type MIME (ex: application/pdf, image/png). Défaut : application/octet-stream.",
                        },
                    },
                },
            },
            "profil": {
                "type": "string",
                "description": "Nom du profil de compte (optionnel).",
            },
        },
        "required": ["destinataires", "objet", "corps"],
    },
)
def imap_send_mail(
    destinataires: list,
    objet: str,
    corps: str,
    corps_html: Optional[str] = None,
    cc: Optional[list] = None,
    cci: Optional[list] = None,
    pieces_jointes: Optional[list] = None,
    profil: Optional[str] = None,
) -> dict:
    cfg = _get_profile_config(profil)
    ok, err = _validate_config(cfg, need_smtp=True)
    if not ok:
        return {"status": "error", "error": err}

    try:
        # Construction du message
        # Si PJ présentes → MIMEMultipart("mixed") obligatoire
        # Si HTML + PJ     → mixed > alternative (plain + html) + PJ
        # Si HTML seulement → alternative (plain + html)
        # Si texte seul    → MIMEText simple
        has_attachments = bool(pieces_jointes)

        if has_attachments:
            outer = MIMEMultipart("mixed")
            if corps_html:
                alt = MIMEMultipart("alternative")
                alt.attach(MIMEText(corps, "plain", "utf-8"))
                alt.attach(MIMEText(corps_html, "html", "utf-8"))
                outer.attach(alt)
            else:
                outer.attach(MIMEText(corps, "plain", "utf-8"))
            msg = outer
        elif corps_html:
            msg = MIMEMultipart("alternative")
            msg.attach(MIMEText(corps, "plain", "utf-8"))
            msg.attach(MIMEText(corps_html, "html", "utf-8"))
        else:
            msg = MIMEText(corps, "plain", "utf-8")

        from_addr   = cfg["from_address"]
        display     = cfg["display_name"]
        from_header = f"{display} <{from_addr}>" if display else from_addr

        msg["From"]    = from_header
        msg["To"]      = ", ".join(destinataires)
        msg["Subject"] = objet
        if cc:
            msg["Cc"] = ", ".join(cc)

        # Ajout des pièces jointes
        pj_errors = []
        pj_added  = []
        if pieces_jointes:
            for pj in pieces_jointes:
                try:
                    chemin      = pj.get("chemin")
                    data_b64    = pj.get("data_base64")
                    nom_fichier = pj.get("nom_fichier")
                    type_mime   = pj.get("type_mime", "application/octet-stream")

                    if chemin:
                        # Chargement depuis le disque
                        chemin = os.path.expanduser(chemin)
                        if not os.path.isfile(chemin):
                            pj_errors.append(f"Fichier introuvable : {chemin}")
                            continue
                        with open(chemin, "rb") as f:
                            data = f.read()
                        nom_fichier = nom_fichier or os.path.basename(chemin)
                        # Détection du type MIME depuis l'extension si non fourni
                        if type_mime == "application/octet-stream":
                            import mimetypes
                            guessed, _ = mimetypes.guess_type(chemin)
                            if guessed:
                                type_mime = guessed
                    elif data_b64 and nom_fichier:
                        data = base64.b64decode(data_b64)
                    else:
                        pj_errors.append(
                            "Pièce jointe ignorée : fournir 'chemin' ou 'data_base64' + 'nom_fichier'."
                        )
                        continue

                    # Construction de la partie MIME
                    maintype, subtype = type_mime.split("/", 1) if "/" in type_mime else ("application", "octet-stream")
                    part = MIMEBase(maintype, subtype)
                    part.set_payload(data)
                    encoders.encode_base64(part)
                    part.add_header(
                        "Content-Disposition",
                        "attachment",
                        filename=nom_fichier,
                    )
                    msg.attach(part)
                    pj_added.append(nom_fichier)

                except Exception as e:
                    pj_errors.append(f"Erreur PJ '{pj.get('nom_fichier') or pj.get('chemin', '?')}' : {e}")

        all_recipients = destinataires + (cc or []) + (cci or [])

        # Connexion SMTP
        if cfg["smtp_ssl"]:
            context = ssl.create_default_context()
            server = smtplib.SMTP_SSL(cfg["smtp_host"], cfg["smtp_port"], context=context)
        else:
            server = smtplib.SMTP(cfg["smtp_host"], cfg["smtp_port"])
            server.ehlo()
            if server.has_extn("STARTTLS"):
                server.starttls()
                server.ehlo()

        # Auth SMTP
        if cfg.get("smtp_oauth2_token"):
            auth_string = f"user={cfg['smtp_user']}\x01auth=Bearer {cfg['smtp_oauth2_token']}\x01\x01"
            server.docmd("AUTH", "XOAUTH2 " + base64.b64encode(auth_string.encode()).decode())
        else:
            server.login(cfg["smtp_user"], cfg["smtp_password"])

        server.sendmail(from_addr, all_recipients, msg.as_bytes())
        server.quit()

        result = {
            "status":        "success",
            "from":          from_header,
            "destinataires": destinataires,
            "cc":            cc or [],
            "objet":         objet,
            "pieces_jointes": pj_added,
            "message":       f"Mail envoyé à {', '.join(destinataires)}."
                             + (f" PJ : {', '.join(pj_added)}." if pj_added else ""),
        }
        if pj_errors:
            result["avertissements_pj"] = pj_errors
        return result

    except smtplib.SMTPAuthenticationError:
        return {"status": "error", "error": "Authentification SMTP échouée. Vérifiez SMTP_USER / SMTP_PASSWORD."}
    except Exception as e:
        return {"status": "error", "error": f"Erreur envoi : {e}"}


@tool(
    name="imap_reply_mail",
    description=(
        "Répond à un mail existant en conservant le fil de conversation "
        "(In-Reply-To et References correctement remplis). "
        "Supporte le HTML et les pièces jointes. "
        "Utiliser imap_read_mail pour obtenir le message_id avant de répondre."
    ),
    parameters={
        "type": "object",
        "properties": {
            "uid": {
                "type": "string",
                "description": "UID du mail auquel répondre.",
            },
            "corps": {
                "type": "string",
                "description": "Corps de la réponse (texte brut, repli obligatoire).",
            },
            "corps_html": {
                "type": "string",
                "description": (
                    "Corps de la réponse en HTML (optionnel). "
                    "Si fourni, le mail est envoyé en HTML avec texte brut de repli. "
                    "Inclure la citation du message original et la signature Prométhée."
                ),
            },
            "dossier": {
                "type": "string",
                "description": "Dossier contenant le mail original (défaut : INBOX).",
            },
            "repondre_a_tous": {
                "type": "boolean",
                "description": "Si true, répond à tous les destinataires (Reply-All). Défaut : false.",
            },
            "pieces_jointes": {
                "type": "array",
                "description": (
                    "Pièces jointes à attacher à la réponse (optionnel). "
                    "Même format que imap_send_mail : 'chemin' ou 'data_base64' + 'nom_fichier' + 'type_mime'."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "chemin":      {"type": "string"},
                        "data_base64": {"type": "string"},
                        "nom_fichier": {"type": "string"},
                        "type_mime":   {"type": "string"},
                    },
                },
            },
            "profil": {
                "type": "string",
                "description": "Nom du profil de compte (optionnel).",
            },
        },
        "required": ["uid", "corps"],
    },
)
def imap_reply_mail(
    uid: str,
    corps: str,
    corps_html: Optional[str] = None,
    dossier: str = "INBOX",
    repondre_a_tous: bool = False,
    pieces_jointes: Optional[list] = None,
    profil: Optional[str] = None,
) -> dict:
    cfg = _get_profile_config(profil)
    ok, err = _validate_config(cfg, need_smtp=True)
    if not ok:
        return {"status": "error", "error": err}

    # Lire le mail original pour extraire les headers
    ok, result = _imap_connect(cfg)
    if not ok:
        return {"status": "error", "error": result}

    imap = result
    try:
        ok_sel, err_sel = _imap_select_folder(imap, dossier)
        if not ok_sel:
            return {"status": "error", "error": err_sel}

        typ, msg_data = imap.fetch(uid.encode(), "(RFC822)")
        if typ != "OK" or not msg_data or not msg_data[0]:
            return {"status": "error", "error": f"Mail UID {uid} introuvable."}

        raw = msg_data[0][1] if isinstance(msg_data[0], tuple) else msg_data[0]
        original = email.message_from_bytes(raw)
    except Exception as e:
        return {"status": "error", "error": f"Erreur lecture mail original : {e}"}
    finally:
        try:
            imap.logout()
        except Exception:
            pass

    # Construction de la réponse
    orig_subject = _decode_header(original.get("Subject", ""))
    reply_subject = orig_subject if orig_subject.lower().startswith("re:") else f"Re: {orig_subject}"

    orig_from = original.get("Reply-To") or original.get("From", "")
    orig_to   = original.get("To", "")
    orig_cc   = original.get("Cc", "")

    if repondre_a_tous:
        all_to = [orig_from] + [a.strip() for a in orig_to.split(",") if a.strip()]
        # Exclure sa propre adresse
        destinataires = [a for a in all_to if cfg["from_address"] not in a]
        cc_list = [a.strip() for a in orig_cc.split(",") if a.strip() and cfg["from_address"] not in a]
    else:
        destinataires = [orig_from]
        cc_list = []

    orig_message_id = original.get("Message-ID", "").strip()
    orig_references = original.get("References", "").strip()
    new_references  = f"{orig_references} {orig_message_id}".strip() if orig_references else orig_message_id

    # Citer le message original (texte brut)
    orig_plain, orig_html_body = _extract_body(original)
    orig_date = original.get("Date", "")
    citation_plain = f"\n\n--- Le {orig_date}, {_decode_header(orig_from)} a écrit :\n"
    citation_plain += "\n".join(f"> {line}" for line in orig_plain.splitlines()[:30])
    full_body_plain = corps + citation_plain

    try:
        from_addr   = cfg["from_address"]
        display     = cfg["display_name"]
        from_header = f"{display} <{from_addr}>" if display else from_addr

        has_attachments = bool(pieces_jointes)

        # Construction MIME (même logique que imap_send_mail)
        if has_attachments:
            outer = MIMEMultipart("mixed")
            if corps_html:
                alt = MIMEMultipart("alternative")
                alt.attach(MIMEText(full_body_plain, "plain", "utf-8"))
                alt.attach(MIMEText(corps_html, "html", "utf-8"))
                outer.attach(alt)
            else:
                outer.attach(MIMEText(full_body_plain, "plain", "utf-8"))
            msg = outer
        elif corps_html:
            msg = MIMEMultipart("alternative")
            msg.attach(MIMEText(full_body_plain, "plain", "utf-8"))
            msg.attach(MIMEText(corps_html, "html", "utf-8"))
        else:
            msg = MIMEText(full_body_plain, "plain", "utf-8")

        msg["From"]        = from_header
        msg["To"]          = ", ".join(destinataires)
        msg["Subject"]     = reply_subject
        msg["In-Reply-To"] = orig_message_id
        msg["References"]  = new_references
        if cc_list:
            msg["Cc"] = ", ".join(cc_list)

        # Ajout des pièces jointes (réutilise la même logique)
        pj_errors = []
        pj_added  = []
        if pieces_jointes:
            for pj in pieces_jointes:
                try:
                    chemin      = pj.get("chemin")
                    data_b64    = pj.get("data_base64")
                    nom_fichier = pj.get("nom_fichier")
                    type_mime   = pj.get("type_mime", "application/octet-stream")

                    if chemin:
                        chemin = os.path.expanduser(chemin)
                        if not os.path.isfile(chemin):
                            pj_errors.append(f"Fichier introuvable : {chemin}")
                            continue
                        with open(chemin, "rb") as f:
                            data = f.read()
                        nom_fichier = nom_fichier or os.path.basename(chemin)
                        if type_mime == "application/octet-stream":
                            import mimetypes
                            guessed, _ = mimetypes.guess_type(chemin)
                            if guessed:
                                type_mime = guessed
                    elif data_b64 and nom_fichier:
                        data = base64.b64decode(data_b64)
                    else:
                        pj_errors.append(
                            "Pièce jointe ignorée : fournir 'chemin' ou 'data_base64' + 'nom_fichier'."
                        )
                        continue

                    maintype, subtype = type_mime.split("/", 1) if "/" in type_mime else ("application", "octet-stream")
                    part = MIMEBase(maintype, subtype)
                    part.set_payload(data)
                    encoders.encode_base64(part)
                    part.add_header("Content-Disposition", "attachment", filename=nom_fichier)
                    msg.attach(part)
                    pj_added.append(nom_fichier)

                except Exception as e:
                    pj_errors.append(f"Erreur PJ '{pj.get('nom_fichier') or pj.get('chemin', '?')}' : {e}")

        all_recipients = destinataires + cc_list

        if cfg["smtp_ssl"]:
            context = ssl.create_default_context()
            server = smtplib.SMTP_SSL(cfg["smtp_host"], cfg["smtp_port"], context=context)
        else:
            server = smtplib.SMTP(cfg["smtp_host"], cfg["smtp_port"])
            server.ehlo()
            if server.has_extn("STARTTLS"):
                server.starttls()
                server.ehlo()

        if cfg.get("smtp_oauth2_token"):
            auth_string = f"user={cfg['smtp_user']}\x01auth=Bearer {cfg['smtp_oauth2_token']}\x01\x01"
            server.docmd("AUTH", "XOAUTH2 " + base64.b64encode(auth_string.encode()).decode())
        else:
            server.login(cfg["smtp_user"], cfg["smtp_password"])

        server.sendmail(from_addr, all_recipients, msg.as_bytes())
        server.quit()

        result = {
            "status":          "success",
            "uid_original":    uid,
            "destinataires":   destinataires,
            "objet":           reply_subject,
            "repondre_a_tous": repondre_a_tous,
            "pieces_jointes":  pj_added,
            "message":         f"Réponse envoyée à {', '.join(destinataires)}."
                               + (f" PJ : {', '.join(pj_added)}." if pj_added else ""),
        }
        if pj_errors:
            result["avertissements_pj"] = pj_errors
        return result

    except smtplib.SMTPAuthenticationError:
        return {"status": "error", "error": "Authentification SMTP échouée."}
    except Exception as e:
        return {"status": "error", "error": f"Erreur envoi réponse : {e}"}
