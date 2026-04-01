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
message_widget.py — Widget de message (user/assistant)
Rendu via QWebEngineView : Markdown + Pygments (code).

Virtualisation mémoire
──────────────────────
Chaque MessageWidget peut exister dans deux états :

  ACTIF    — QWebEngineView visible, renderer Chromium en vie.
             Consommation : ~25-40 Mo RAM + un process GPU.

  DÉTACHÉ  — QWebEngineView mis en état « Discarded » (lifecycle Qt 6.2+).
             Le renderer est suspendu mais le widget Qt conserve sa hauteur
             connue (_cached_height), donc le layout reste stable (pas de
             saut visuel lors du re-scroll).
             Consommation : ~1-2 Mo (structures Qt uniquement).

La transition est pilotée par ViewportManager (chat_panel.py) :
  - attach()  → appelé quand le widget entre dans la zone visible + buffer
  - detach()  → appelé quand le widget sort de la zone visible + buffer

Invariants
──────────
• Un widget en streaming (start_streaming en cours) n'est jamais détaché.
• La hauteur conservée (_cached_height) garantit que le scroll reste
  cohérent même quand le WebView est suspendu.
• set_content() en état DÉTACHÉ met à jour _full_text et estime la hauteur
  (_dirty=True), puis déclenche un re-render au prochain attach().
"""
import html
import logging
import re
from pathlib import Path

_log = logging.getLogger("promethee.message_widget")
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QSizePolicy, QFileDialog,
    QMenu,
)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEngineSettings, QWebEnginePage
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal, QUrl
from PyQt6.QtGui import QGuiApplication, QDesktopServices, QCursor
from PyQt6.QtCore import QMimeData
from .styles import ThemeManager
from core.config import Config
from .latex_renderer import (
    is_available as latex_available,
    katex_html_tags,
    katex_css_extras,
    protect_latex,
    restore_latex,
)
from .mermaid_renderer import (
    is_available as mermaid_available,
    mermaid_html_tags,
    mermaid_css,
    protect_mermaid,
    restore_mermaid,
)

try:
    import markdown as md_lib
    _HAS_MD = True
except ImportError:
    _HAS_MD = False

try:
    from pygments import highlight
    from pygments.lexers import get_lexer_by_name, TextLexer
    from pygments.formatters import HtmlFormatter
    _HAS_PYGMENTS = True
except ImportError:
    _HAS_PYGMENTS = False

# Paramètres d'estimation de hauteur hors-ligne (état détaché)
_CHARS_PER_LINE  = 80   # ~80 caractères par ligne à la largeur nominale
_PX_PER_LINE     = 24   # hauteur d'une ligne (14px font + line-height 1.7)
_DETACHED_PADDING = 32  # marges verticales de la bulle

# Cache du CSS HTML : une entrée par thème (True=dark, False=light).
# Invalidé par invalidate_html_css_cache(), appelé depuis ThemeManager
# lors de chaque changement de thème.
_html_css_cache: dict[bool, str] = {}


def invalidate_html_css_cache() -> None:
    """Vide le cache CSS HTML. À appeler après chaque changement de thème."""
    _html_css_cache.clear()


# ── CSS HTML ──────────────────────────────────────────────────────────────────

def _build_html_css() -> str:
    dark = ThemeManager.is_dark()
    if dark in _html_css_cache:
        return _html_css_cache[dark]

    p    = ThemeManager.inline  # alias court : p("token") → valeur active

    pyg_style  = "one-dark" if dark else "friendly"
    pyg_bg     = p("code_block_bg")
    body_color = p("text_primary")
    link_color = p("link_color")
    code_color = p("code_inline_color")
    code_bg    = p("code_bg")
    code_bdr   = p("code_border")
    bq_bg      = p("blockquote_bg")
    bq_color   = p("text_muted")
    h_color    = p("text_primary")
    h_border   = p("border")
    th_bg      = p("code_bg")
    th_color   = p("text_secondary")
    td_border  = p("code_bg")
    tr_hover   = p("table_row_hover")
    hr_color   = p("border")

    pyg_css = HtmlFormatter(style=pyg_style).get_style_defs(".highlight") \
              if _HAS_PYGMENTS else ""

    latex_css = katex_css_extras() if latex_available() else ""
    mermaid_extra_css = mermaid_css() if mermaid_available() else ""

    css = f"""
* {{ box-sizing: border-box; }}
html, body {{
    margin: 0; padding: 0;
    background: transparent;
    color: {body_color};
    font-family: "Segoe UI", "SF Pro Text", "Helvetica Neue", sans-serif;
    font-size: 14px;
    line-height: 1.7;
    overflow-y: auto;
    overflow-x: hidden;
    max-height: 15900px;
}}
p  {{ margin: 4px 0 8px; }}
a  {{ color: {link_color}; }}

h1 {{ color:{h_color}; font-size:18px; font-weight:700;
     margin:14px 0 6px; border-bottom:1px solid {h_border}; padding-bottom:4px; }}
h2 {{ color:{h_color}; font-size:16px; font-weight:600; margin:12px 0 5px; }}
h3 {{ color:{h_color}; font-size:14px; font-weight:600; margin:10px 0 4px; }}

ul, ol {{ margin:4px 0 8px; padding-left:22px; }}
li {{ margin:2px 0; }}

blockquote {{
    border-left:3px solid {code_color};
    margin:8px 0; padding:4px 12px;
    color:{bq_color}; font-style:italic;
    background:{bq_bg};
    border-radius:0 6px 6px 0;
}}

code {{
    font-family:"JetBrains Mono","Fira Code","Cascadia Code",monospace;
    background:{code_bg}; border:1px solid {code_bdr};
    border-radius:4px; padding:1px 5px;
    font-size:12.5px; color:{code_color};
}}

.highlight {{
    background:{pyg_bg}; border-radius:8px;
    padding:12px 14px; margin:8px 0;
}}
.highlight pre {{
    background:transparent; border:none;
    padding:0; margin:0;
    font-family:"JetBrains Mono","Fira Code",monospace;
    font-size:12.5px; line-height:1.55;
    white-space:pre-wrap; word-wrap:break-word;
}}
.highlight pre code {{ background:none; border:none; padding:0; color:inherit; }}

table {{ border-collapse:collapse; width:100%; margin:8px 0; }}
th {{ background:{th_bg}; padding:6px 10px; color:{th_color};
     text-align:left; border-bottom:2px solid {code_bdr}; }}
td {{ padding:6px 10px; border-bottom:1px solid {td_border}; }}
tr:hover td {{ background:{tr_hover}; }}

hr {{ border:none; border-top:1px solid {hr_color}; margin:10px 0; }}

{pyg_css}

{latex_css}

{mermaid_extra_css}
"""
    _html_css_cache[dark] = css
    return css


# ── Images inline (matplotlib base64 + URLs https://) ────────────────────────
#
# Le LLM peut produire :
#   ![alt](data:image/png;base64,<données>)   ← image base64 inline
#   ![alt](https://example.com/image.png)     ← image distante
#
# Dans les deux cas, QWebEngineView ne peut pas afficher ces images :
#   • data-URI bloquées par la CSP file:// de setHtml()
#   • URLs https:// bloquées par LocalContentCanAccessRemoteUrls=False
#
# Stratégie : extraire TOUTES les images Markdown AVANT le pipeline de rendu,
# les télécharger/décoder en Python, stocker dans self._dataimg_cache,
# et remplacer par un bouton cliquable qui ouvre ImageViewerDialog (QPixmap).
#
# Cas supplémentaire : le LLM peut reproduire dans son texte de réponse une
# data-URI base64 tronquée (quand la chaîne dépasse les limites de contexte).
# Ces fragments sont invisibles dans la WebView (CSP) mais polluent le rendu
# texte sous forme de longues chaînes illisibles.  _clean_orphan_data_uris()
# les supprime proprement avant le pipeline Markdown.
#
_RE_DATA_IMAGE = re.compile(
    r'!\[([^\]]*)\]\((data:image/[^;]+;base64,[A-Za-z0-9+/=\s]+)\)',
    re.DOTALL,
)
_RE_URL_IMAGE = re.compile(
    r'!\[([^\]]*)\]\((https?://[^\s)]+)\)',
)
_DATAIMG_PLACEHOLDER = re.compile(r'<!--\s*DATAIMG_(\d+)\s*-->')

# Regex pour détecter les data-URI orphelines (tronquées ou sans parenthèse
# fermante) que _RE_DATA_IMAGE n'aurait pas capturées.
# On tolère les espaces/sauts de ligne dans la base64 (le LLM peut en insérer).
_RE_ORPHAN_DATA_URI = re.compile(
    r'data:image/[^;]+;base64,[A-Za-z0-9+/=\s]{20,}',
    re.DOTALL,
)


def _clean_orphan_data_uris(text: str) -> str:
    """
    Supprime du texte les fragments de data-URI base64 qui n'ont pas été
    capturés par _protect_data_images() — typiquement des URI tronquées que
    le LLM a reproduites dans sa réponse textuelle.

    Ces fragments sont remplacés par une note discrète plutôt que supprimés
    silencieusement, pour que l'utilisateur comprenne qu'une image était prévue
    mais n'a pas pu être rendue (données corrompues/tronquées).

    Doit être appelé APRÈS _protect_data_images() (qui traite les URI complètes)
    et AVANT protect_latex / protect_mermaid.
    """
    def _replace_orphan(m: re.Match) -> str:
        return "*(image non rendue — données tronquées)*"

    return _RE_ORPHAN_DATA_URI.sub(_replace_orphan, text)


def _fetch_url_as_data_uri(url: str) -> str | None:
    """
    Télécharge une image distante et retourne une data-URI base64, ou None si échec.
    Timeout court (8 s).
    """
    import urllib.request, base64
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Promethee/1.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            raw   = resp.read()
            ctype = resp.headers.get_content_type() or "image/png"
            b64   = base64.b64encode(raw).decode()
            return f"data:{ctype};base64,{b64}"
    except Exception as e:
        _log.warning("_fetch_url_as_data_uri(%s) : %s", url, e)
        return None


def _protect_data_images(text: str) -> tuple[str, dict]:
    """
    Extrait toutes les images Markdown (data-URI et URLs https://) et les
    remplace par des placeholders neutres.
    Doit être appelé AVANT protect_latex et protect_mermaid.
    Retourne (texte_protégé, cache) où cache = {idx: (alt, data_uri|url)}.

    Pour les URLs distantes, la data_uri stockée est l'URL originale —
    le téléchargement est fait de façon asynchrone par MessageWidget.
    """
    cache: dict[int, tuple[str, str]] = {}
    counter = [0]

    def store(alt: str, uri: str) -> str:
        idx = counter[0]
        cache[idx] = (alt, uri)
        counter[0] += 1
        return f"<!-- DATAIMG_{idx} -->"

    # 1. Images data-URI base64 inline
    def replace_data(m: re.Match) -> str:
        data_uri = re.sub(r'\s+', '', m.group(2))
        return store(m.group(1), data_uri)

    text = _RE_DATA_IMAGE.sub(replace_data, text)

    # 2. Images URL https:// — on stocke l'URL, le widget télécharge en async
    def replace_url(m: re.Match) -> str:
        return store(m.group(1), m.group(2))

    text = _RE_URL_IMAGE.sub(replace_url, text)

    return text, cache


def _restore_data_images(html_text: str, cache: dict) -> str:
    """
    Remplace chaque placeholder par un aperçu inline ou un bouton de repli.

    Pour les images data-URI déjà disponibles (base64), un <img> miniature
    est affiché directement dans la bulle — QWebEngineView autorise les
    data-URI dans setHtml() malgré LocalContentCanAccessRemoteUrls=False
    (elles ne sont pas considérées comme du contenu "distant").

    Pour les URLs distantes en cours de téléchargement, un bouton de repli
    est affiché ; il est remplacé par la miniature via JS dans _on_image_fetched.

    Dans les deux cas, un clic ouvre ImageViewerDialog (QPixmap natif).
    """
    if not cache:
        return html_text

    accent   = ThemeManager.inline('accent')
    bg       = ThemeManager.inline('elevated_bg')
    border   = ThemeManager.inline('border')
    text_col = ThemeManager.inline('text_primary')

    def replace(m: re.Match) -> str:
        idx = int(m.group(1))
        if idx not in cache:
            return m.group(0)
        alt, uri = cache[idx]
        safe_alt = html.escape(alt or "Graphique")
        label = safe_alt if len(safe_alt) <= 40 else safe_alt[:37] + "…"
        onclick = f"document.title='dataimg:{idx}'"

        if uri.startswith("data:"):
            # Image déjà disponible : miniature cliquable inline
            return (
                f'<div style="margin:12px 0;text-align:center;">'
                f'<img src="{uri}" alt="{safe_alt}" '
                f'onclick="{onclick}" '
                f'style="max-width:100%;max-height:500px;border-radius:8px;'
                f'cursor:zoom-in;border:1px solid {border};'
                f'box-shadow:0 2px 8px rgba(0,0,0,0.15);" '
                f'title="Cliquer pour agrandir" />'
                f'<div style="margin-top:4px;font-size:11px;color:{accent};'
                f'cursor:pointer;" onclick="{onclick}">'
                f'🔍 {label} — cliquer pour agrandir'
                f'</div>'
                f'</div>'
            )
        else:
            # URL distante pas encore téléchargée : bouton de repli
            # _on_image_fetched() mettra à jour le src dès que la data-URI sera disponible
            return (
                f'<div style="margin:12px 0;text-align:center;">'
                f'<img data-imgidx="{idx}" src="" alt="{safe_alt}" '
                f'style="display:none;max-width:100%;max-height:500px;'
                f'border-radius:8px;cursor:zoom-in;border:1px solid {border};" '
                f'onclick="{onclick}" title="Cliquer pour agrandir" />'
                f'<button onclick="{onclick}" data-imgidx="{idx}" '
                f'style="display:inline-flex;align-items:center;gap:8px;'
                f'padding:8px 18px;border-radius:8px;cursor:pointer;'
                f'background:{bg};border:1px solid {border};'
                f'color:{text_col};font-size:13px;font-family:inherit;">'
                f'<span style="font-size:16px;">🖼</span>'
                f'<span>{label}</span>'
                f'<span class="img-status" style="color:{accent};font-size:11px;">'
                f'— chargement…</span>'
                f'</button></div>'
            )

    return _DATAIMG_PLACEHOLDER.sub(replace, html_text)


# ── Visionneuse d'image dédiée ────────────────────────────────────────────────

class ImageViewerDialog:
    """
    Ouvre une QDialog affichant un QPixmap décodé depuis une data-URI base64.
    Utilise uniquement Qt natif — aucune contrainte WebEngine/CSP.
    """

    @staticmethod
    def open(parent, alt: str, data_uri: str) -> None:
        """
        Décode data_uri et affiche l'image dans une fenêtre modale légère.

        Parameters
        ----------
        parent   : QWidget — fenêtre parente pour le centrage
        alt      : str     — texte alternatif (titre de la fenêtre)
        data_uri : str     — « data:image/png;base64,<données> »
        """
        import base64
        from PyQt6.QtWidgets import (
            QDialog, QVBoxLayout, QHBoxLayout, QLabel,
            QPushButton, QScrollArea, QSizePolicy, QFileDialog,
            QMessageBox,
        )
        from PyQt6.QtGui import QPixmap
        from PyQt6.QtCore import Qt, QByteArray

        # ── Décodage ─────────────────────────────────────────────────
        try:
            header, b64data = data_uri.split(',', 1)
            # Supprimer les espaces/sauts de ligne éventuels dans la base64
            b64data = re.sub(r'\s+', '', b64data)
            raw = base64.b64decode(b64data)
        except Exception as e:
            _log.warning("ImageViewerDialog: décodage échoué : %s", e)
            QMessageBox.warning(
                parent,
                "Erreur d'affichage",
                f"Impossible de décoder l'image « {alt or 'Graphique'} ».\n\n"
                f"Détail : {e}\n\n"
                "L'image est peut-être corrompue ou tronquée.",
            )
            return

        pixmap = QPixmap()
        if not pixmap.loadFromData(QByteArray(raw)):
            _log.warning("ImageViewerDialog: QPixmap.loadFromData a échoué (%d octets)", len(raw))
            QMessageBox.warning(
                parent,
                "Erreur d'affichage",
                f"Impossible d'afficher l'image « {alt or 'Graphique'} ».\n\n"
                f"Les données reçues ({len(raw):,} octets) ne correspondent pas "
                "à un format image reconnu (PNG, JPEG, GIF, WebP).\n\n"
                "Conseil : si l'image provient d'un graphique matplotlib, "
                "vérifiez que le code n'a pas été interrompu avant la fin du tracé.",
            )
            return

        # ── Dialog ───────────────────────────────────────────────────
        dlg = QDialog(parent)
        dlg.setWindowTitle(alt or "Graphique")
        dlg.setModal(False)          # non-bloquant : l'utilisateur peut continuer
        dlg.resize(
            min(pixmap.width()  + 40, 1200),
            min(pixmap.height() + 100, 900),
        )
        dlg.setStyleSheet(ThemeManager.dialog_style())

        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # Zone scrollable pour les grandes images
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        img_label = QLabel()
        img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        img_label.setPixmap(pixmap)
        img_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        scroll.setWidget(img_label)
        layout.addWidget(scroll, stretch=1)

        # Barre d'actions
        bar = QHBoxLayout()
        bar.addStretch()

        save_btn = QPushButton("💾  Enregistrer…")
        save_btn.setFixedHeight(32)

        def _save():
            path, _ = QFileDialog.getSaveFileName(
                dlg, "Enregistrer l'image", f"{alt or 'graphique'}.png",
                "PNG (*.png);;JPEG (*.jpg *.jpeg);;Tous (*.*)"
            )
            if path:
                pixmap.save(path)

        save_btn.clicked.connect(_save)
        bar.addWidget(save_btn)

        close_btn = QPushButton("Fermer")
        close_btn.setFixedHeight(32)
        close_btn.clicked.connect(dlg.close)
        bar.addWidget(close_btn)

        layout.addLayout(bar)
        dlg.show()




# ── Worker de téléchargement d'image en arrière-plan ─────────────────────────

class _ImageFetchWorker(QThread):
    """
    Télécharge une image distante dans un thread séparé pour ne pas bloquer
    l'interface. Émet `done(idx, data_uri)` quand le téléchargement réussit,
    ou `done(idx, "")` en cas d'échec.
    """
    done = pyqtSignal(int, str)   # (idx, data_uri_or_empty)

    def __init__(self, idx: int, url: str, parent=None):
        super().__init__(parent)
        self._idx = idx
        self._url = url

    def run(self):
        data_uri = _fetch_url_as_data_uri(self._url)
        self.done.emit(self._idx, data_uri or "")


# ── Coloration syntaxique ─────────────────────────────────────────────────────

def _highlight_code_blocks(text: str) -> str:
    if not _HAS_PYGMENTS:
        return text

    def replace(match):
        lang = match.group(1) or ""
        code = match.group(2)
        try:
            lexer = get_lexer_by_name(lang, stripall=True) if lang else TextLexer()
        except Exception:
            lexer = TextLexer()
        style = "one-dark" if ThemeManager.is_dark() else "friendly"
        fmt   = HtmlFormatter(style=style, nowrap=False, cssclass="highlight")
        return highlight(code, lexer, fmt)

    return re.sub(r'```(\w+)?\n(.*?)```', replace, text, flags=re.DOTALL)


# ── HTML complet ──────────────────────────────────────────────────────────────

def _md_to_html(text: str) -> tuple[str, dict]:
    """
    Convertit le texte Markdown en HTML complet.

    Retourne (html, dataimg_cache) où dataimg_cache = {idx: (alt, data_uri)}.
    Le cache est stocké dans self._dataimg_cache par set_content() pour que
    _on_title_changed() puisse retrouver la data-URI au moment du clic.
    """
    # 0. Extraire les images base64 AVANT tout le reste pour les protéger
    #    du pipeline LaTeX/Markdown (les data-URI sont très longues et peuvent
    #    déclencher des faux positifs dans les regex de protect_latex).
    text, dataimg_cache = _protect_data_images(text)

    # 0b. Nettoyer les data-URI orphelines (tronquées) que _protect_data_images
    #     n'a pas capturées — typiquement quand le LLM reproduit une data-URI
    #     dans son texte de réponse et que la chaîne base64 est tronquée par les
    #     limites de contexte. Sans cette étape, la chaîne illisible s'affiche
    #     en clair dans la bulle de message.
    text = _clean_orphan_data_uris(text)

    # 1. Extraire les blocs Mermaid AVANT tout (protect_mermaid doit passer
    #    avant protect_latex et avant Markdown pour éviter toute altération)
    if mermaid_available():
        text, mermaid_cache = protect_mermaid(text)
    else:
        mermaid_cache = {}

    # 2. Extraire les blocs LaTeX AVANT que Markdown ne les abîme
    protected, latex_cache = protect_latex(text)

    # 3. Coloration syntaxique des blocs de code
    if _HAS_PYGMENTS:
        protected = _highlight_code_blocks(protected)

    # 4. Rendu Markdown
    if _HAS_MD:
        body = md_lib.markdown(protected, extensions=["tables", "nl2br", "sane_lists"])
    else:
        body = html.escape(protected).replace("\n", "<br>")

    # 5. Réinjecter les blocs LaTeX dans le HTML
    body = restore_latex(body, latex_cache)

    # 6. Réinjecter les blocs Mermaid dans le HTML
    if mermaid_cache:
        body = restore_mermaid(body, mermaid_cache)

    # 7. Réinjecter les images base64 comme boutons cliquables
    body = _restore_data_images(body, dataimg_cache)

    css      = _build_html_css()
    katex    = katex_html_tags() if latex_available() else ""
    mermaid  = mermaid_html_tags() if mermaid_available() else ""

    html_out = f"""<!DOCTYPE html><html><head>
<meta charset="utf-8">
<style>{css}</style>
{katex}
{mermaid}
<script>
function getContentHeight() {{
    return document.body ? document.body.scrollHeight : 0;
}}
</script>
</head><body>{body}</body></html>"""

    return html_out, dataimg_cache


# ── Estimation de hauteur hors-ligne ─────────────────────────────────────────

_IMAGE_HEIGHT_ESTIMATE = 420  # hauteur forfaitaire par image (px)
# Correspond à une image matplotlib typique 6×4 pouces à 96 dpi
# affichée dans une bulle de 920px de large.

_RE_IMAGE_TAG = re.compile(
    r'!\[.*?\]\(.*?\)'           # Markdown : ![alt](src)
    r'|<img\b[^>]*>',            # HTML : <img ...>
    re.IGNORECASE,
)


def _estimate_height(text: str) -> int:
    """
    Estime la hauteur en pixels d'un message sans interroger le renderer.

    Toujours bornée par MessageWidget._MAX_H pour ne jamais dépasser
    la limite de texture GPU (32 768px sur la plupart des pilotes).

    Les images (balises Markdown ![...](...) ou HTML <img>) sont
    détectées et comptabilisées séparément avec une hauteur forfaitaire,
    car le base64 qu'elles contiennent fausserait massivement le calcul
    basé sur le nombre de caractères.

    Parameters
    ----------
    text : str
        Contenu textuel brut du message (Markdown ou HTML).

    Returns
    -------
    int
        Hauteur estimée dans [MessageWidget._MIN_H, MessageWidget._MAX_H].
    """
    if not text:
        return MessageWidget._MIN_H

    # ── Compter et extraire les images ────────────────────────────────
    image_count = len(_RE_IMAGE_TAG.findall(text))
    text_without_images = _RE_IMAGE_TAG.sub("", text)

    # ── Hauteur du texte ──────────────────────────────────────────────
    # Les longues chaînes base64 dans data-URI gonflent artificiellement
    # le comptage : on tronque chaque ligne à 400 chars pour les ignorer.
    lines = text_without_images.split("\n")
    total_lines = sum(
        max(1, (min(len(line), 400) + _CHARS_PER_LINE - 1) // _CHARS_PER_LINE)
        for line in lines
    )
    text_height = total_lines * _PX_PER_LINE + _DETACHED_PADDING

    # ── Hauteur totale ────────────────────────────────────────────────
    raw = text_height + image_count * _IMAGE_HEIGHT_ESTIMATE
    return max(MessageWidget._MIN_H, min(raw, MessageWidget._MAX_H))



# ══════════════════════════════════════════════════════════════════════════════
#  _LinkPage — Page WebEngine qui intercepte les clics sur les liens
# ══════════════════════════════════════════════════════════════════════════════

class _LinkPage(QWebEnginePage):
    """
    QWebEnginePage personnalisée pour les bulles de message.

    Clic gauche sur un lien HTTP/HTTPS/FTP
    ───────────────────────────────────────
    Ouverture dans le navigateur système (QDesktopServices.openUrl).
    La navigation interne est bloquée pour préserver le contenu du message.

    Clic droit — menu contextuel minimaliste
    ─────────────────────────────────────────
    • Sur un lien  → « 📋 Copier le lien »
    • Sur une image → « 💾 Enregistrer l'image »
    • Ailleurs     → aucun menu (clic droit sans effet)

    Liens file:// (assets KaTeX/Mermaid locaux) → toujours autorisés.
    Autres schémas → bloqués.
    """

    def __init__(self, parent=None):
        super().__init__(parent)

    # ── Clic gauche : interception des navigations ───────────────────────────

    def acceptNavigationRequest(
        self,
        url: QUrl,
        nav_type: QWebEnginePage.NavigationType,
        is_main_frame: bool,
    ) -> bool:
        # Navigations programmatiques (setHtml, reload…) → toujours autoriser
        if nav_type != QWebEnginePage.NavigationType.NavigationTypeLinkClicked:
            return True

        scheme = url.scheme().lower()

        # Assets locaux KaTeX / Mermaid → autoriser
        if scheme == "file":
            return True

        # Liens web → navigateur système, navigation interne bloquée
        if scheme in ("http", "https", "ftp"):
            QDesktopServices.openUrl(url)
            return False

        # Autres schémas → bloquer
        return False

    # ── Clic droit : menu contextuel minimaliste ─────────────────────────────

    def contextMenuEvent(self, event) -> None:   # type: ignore[override]
        """
        Affiche un menu à une seule entrée selon l'élément sous le curseur :
          • Lien  → « 📋 Copier le lien »    (presse-papiers)
          • Image → « 💾 Enregistrer l'image » (QFileDialog)
          • Autre → aucun menu
        """
        data = self.contextMenuData()
        if not data.isValid():
            return

        link     = data.linkUrl()
        img_url  = data.mediaUrl()

        has_link = link.isValid() and link.scheme().lower() in ("http", "https", "ftp")
        has_img  = (
            img_url.isValid()
            and data.mediaType() == data.MediaType.MediaTypeImage
        )

        if not has_link and not has_img:
            return  # pas d'élément exploitable → pas de menu

        menu = QMenu()
        menu.setStyleSheet(self._menu_style())

        if has_link:
            act = menu.addAction("📋  Copier le lien")
            chosen = menu.exec(QCursor.pos())
            if chosen == act:
                QGuiApplication.clipboard().setText(link.toString())

        elif has_img:
            act = menu.addAction("💾  Enregistrer l'image")
            chosen = menu.exec(QCursor.pos())
            if chosen == act:
                self._save_image(img_url)

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _save_image(self, url: QUrl) -> None:
        """Télécharge l'image pointée par url et propose un QFileDialog."""
        import urllib.request, base64 as _b64
        from pathlib import Path

        # Nom de fichier suggéré à partir de l'URL
        suggested = Path(url.path()).name or "image"

        path, _ = QFileDialog.getSaveFileName(
            None,
            "Enregistrer l'image",
            suggested,
            "Images (*.png *.jpg *.jpeg *.gif *.webp *.svg);;Tous (*.*)",
        )
        if not path:
            return

        try:
            req = urllib.request.Request(
                url.toString(),
                headers={"User-Agent": "Promethee/1.0"},
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = resp.read()
            with open(path, "wb") as f:
                f.write(data)
        except Exception as e:
            _log.warning("_save_image(%s) : %s", url.toString(), e)

    @staticmethod
    def _menu_style() -> str:
        """Style QSS minimal cohérent avec les tokens Prométhée."""
        bg     = ThemeManager.inline("elevated_bg")
        border = ThemeManager.inline("border")
        color  = ThemeManager.inline("text_primary")
        sel_bg = ThemeManager.inline("accent")
        sel_fg = ThemeManager.inline("elevated_bg")
        return f"""
QMenu {{
    background-color: {bg};
    border: 1px solid {border};
    border-radius: 6px;
    padding: 4px 0;
    color: {color};
    font-size: 13px;
}}
QMenu::item {{
    padding: 6px 18px 6px 12px;
    border-radius: 4px;
    margin: 1px 4px;
}}
QMenu::item:selected {{
    background-color: {sel_bg};
    color: {sel_fg};
}}
"""


# ══════════════════════════════════════════════════════════════════════════════
#  MessageWidget
# ══════════════════════════════════════════════════════════════════════════════

class MessageWidget(QWidget):
    """
    Bulle de message user/assistant avec rendu WebEngine.

    États internes
    ──────────────
    _attached : bool
        True  → QWebEngineView actif (renderer Chromium en vie).
        False → WebView en état Discarded, layout stabilisé par _cached_height.

    _streaming : bool
        True entre start_streaming() et end_streaming().
        Un widget en streaming ne peut pas être détaché.

    _cached_height : int
        Dernière hauteur connue du contenu (pixels). Maintenu à jour après
        chaque interrogation JS réussie et après chaque estimation.
        Sert à stabiliser le layout quand le renderer est suspendu.

    _dirty : bool
        True si set_content() a été appelé en état détaché.
        Déclenche un re-render complet au prochain attach().
    """

    _MIN_H = 40
    _MAX_H = 16000  # Limite de sécurité pour éviter les crashes GPU

    def __init__(self, role: str, content: str = "", parent=None):
        super().__init__(parent)
        self.role = role
        self._full_text    = content
        self._attached     = True   # démarre toujours attaché
        self._streaming    = False
        self._pending_tokens   = ""
        self._cached_height    = self._MIN_H
        self._dirty        = False  # re-render requis au prochain attach ?
        self._dataimg_cache: dict[int, tuple[str, str]] = {}  # {idx: (alt, data_uri)}
        self._fetch_workers: list[_ImageFetchWorker] = []     # workers de téléchargement actifs

        # Timer de throttle streaming : flush toutes les 150ms pour ne pas
        # saturer le moteur WebEngine avec un token par runJavaScript().
        self._stream_timer = QTimer(self)
        self._stream_timer.setInterval(150)
        self._stream_timer.timeout.connect(self._flush_tokens)

        self._setup_ui()
        if content:
            self.set_content(content)

    # ── Construction de l'interface utilisateur ─────────────────────────────────

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 4, 0, 4)
        root.setSpacing(0)

        bubble = QWidget()
        bubble.setObjectName("msg_user" if self.role == "user" else "msg_assistant")
        bl = QVBoxLayout(bubble)
        bl.setContentsMargins(16, 10, 16, 10)
        bl.setSpacing(5)

        # Header
        header = QHBoxLayout()
        role_lbl = QLabel(Config.APP_USER if self.role == "user" else Config.APP_TITLE)
        role_lbl.setObjectName(
            "msg_role_user" if self.role == "user" else "msg_role_assistant"
        )
        header.addWidget(role_lbl)
        header.addStretch()

        self._copy_btn = QPushButton("📋")
        self._copy_btn.setObjectName("tool_btn")
        self._copy_btn.setFixedSize(32, 32)
        self._copy_btn.setToolTip("Copier (texte brut)")
        self._copy_btn.clicked.connect(self._copy)
        self._copy_btn.setVisible(False)
        header.addWidget(self._copy_btn)

        self._copy_rich_btn = QPushButton("📄")
        self._copy_rich_btn.setObjectName("tool_btn")
        self._copy_rich_btn.setFixedSize(32, 32)
        self._copy_rich_btn.setToolTip("Copier avec mise en forme (Word, LibreOffice…)")
        self._copy_rich_btn.clicked.connect(self._copy_rich)
        self._copy_rich_btn.setVisible(False)
        header.addWidget(self._copy_rich_btn)
        bl.addLayout(header)

        # QWebEngineView
        self._view = QWebEngineView()
        self._view.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self._view.setFixedHeight(self._MIN_H)

        # Page personnalisée : intercepte les clics sur les liens <a href>
        # et les ouvre dans le navigateur système au lieu de naviguer dans la vue.
        # Doit être installée AVANT tout appel à page() pour que les réglages
        # (setBackgroundColor, settings…) s'appliquent bien à cette page.
        # Page personnalisée : ouvre les liens <a href> dans le navigateur
        # système au lieu de naviguer dans la vue (ce qui remplacerait le
        # contenu du message).
        self._link_page = _LinkPage(self._view)
        self._view.setPage(self._link_page)

        self._view.page().setBackgroundColor(Qt.GlobalColor.transparent)

        s = self._view.settings()
        s.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        s.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, False)
        s.setAttribute(QWebEngineSettings.WebAttribute.ShowScrollBars, False)

        self._view.loadFinished.connect(self._on_load_finished)
        # titleChanged est le canal de communication JS→Python le plus fiable
        # dans Qt6 : le bouton image fait onclick="document.title='dataimg:N'"
        # et on intercepte ici pour ouvrir ImageViewerDialog.
        self._view.titleChanged.connect(self._on_title_changed)

        bl.addWidget(self._view)

        outer = QHBoxLayout()
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        if self.role == "user":
            outer.addStretch()
            bubble.setMaximumWidth(680)
        else:
            bubble.setMaximumWidth(920)
        outer.addWidget(bubble)
        root.addLayout(outer)
        self.bubble = bubble

    # ── Virtualisation viewport ───────────────────────────────────────

    @property
    def is_attached(self) -> bool:
        """True si le renderer WebEngine est actif."""
        return self._attached

    def detach(self):
        """
        Suspend le renderer WebEngine pour économiser la mémoire.

        Conditions de sécurité :
        - Sans effet si le widget est en cours de streaming.
        - Sans effet si déjà détaché.
        - La hauteur Qt est figée à _cached_height AVANT masquage pour
          éviter tout saut de layout dans le QScrollArea parent.

        Après detach(), _full_text reste intact : attach() effectuera
        un re-render complet si _dirty est True (contenu modifié pendant
        la suspension), ou restaurera simplement le renderer sinon.
        """
        if self._streaming or not self._attached or not self._view:
            return

        self._attached = False

        # Figer la hauteur avant de masquer la vue (évite le collapse à 0).
        h = max(self._MIN_H, min(self._cached_height, self._MAX_H))
        self._view.setMinimumHeight(h)
        self._view.setMaximumHeight(h)

        # Masquer d'abord, puis passer en Discarded via un singleShot(0).
        # Cela évite d'appeler processEvents() — qui causait une réentrance
        # dans _sync() et laissait Chromium avec une texture GPU incohérente
        # ("Compositor returned null texture").
        # Le singleShot(0) garantit que la visibilité est propagée au renderer
        # avant la transition d'état, sans traiter d'autres événements en cours.
        self._view.setVisible(False)

        try:
            page = self._view.page()
            QTimer.singleShot(0, lambda: self._discard_page(page))
        except AttributeError:
            pass

    def _discard_page(self, page):
        """Passe la page en état Discarded après que la visibilité a été propagée."""
        # Vérifier que le widget n'a pas été réattaché ou détruit entre-temps.
        if self._attached or not self._view:
            return
        try:
            page.setLifecycleState(QWebEnginePage.LifecycleState.Discarded)
        except AttributeError:
            # Qt < 6.2 : setLifecycleState absent — vider la page suffit
            page.setHtml("")
            self._dirty = True
        except RuntimeError:
            pass  # page déjà détruite

    def attach(self):
        """
        Réactive le renderer WebEngine et re-rend si le contenu a changé.

        Conditions de sécurité :
        - Sans effet si déjà attaché.

        Si _dirty est False (contenu inchangé depuis le dernier rendu),
        on réactive simplement le renderer sans recharger la page —
        ce qui est le cas nominal pour un simple scroll aller-retour.

        Si _dirty est True (set_content() appelé pendant la suspension),
        on effectue un re-render HTML complet.
        """
        if self._attached or not self._view:
            return

        self._attached = True
        self._view.setVisible(True)

        # Différer setLifecycleState(Active) d'un cycle d'événements pour
        # laisser Qt peindre le widget avant que Chromium alloue la texture GPU.
        # Sans ce délai, le compositor peut recevoir une demande de rendu sur
        # un widget encore invisible, produisant "Compositor returned null texture".
        if self._dirty:
            self._dirty = False
            content = self._full_text
            if content:
                QTimer.singleShot(0, lambda: self._activate_and_render(content))
            else:
                QTimer.singleShot(0, self._activate_page)
                self._view.setMinimumHeight(self._MIN_H)
                self._view.setMaximumHeight(self._MIN_H)
        else:
            QTimer.singleShot(0, self._activate_page)

    def _activate_page(self):
        """Passe la page en état Active après un cycle d'événements."""
        if not self._attached or not self._view:
            return
        try:
            self._view.page().setLifecycleState(QWebEnginePage.LifecycleState.Active)
        except (AttributeError, RuntimeError):
            pass

    def _activate_and_render(self, content: str):
        """Active la page puis re-rend le contenu (cas _dirty)."""
        if not self._attached or not self._view:
            return
        try:
            self._view.page().setLifecycleState(QWebEnginePage.LifecycleState.Active)
        except (AttributeError, RuntimeError):
            pass
        self.set_content(content)

    # ── Contenu ───────────────────────────────────────────────────────

    def set_content(self, text: str):
        """
        Définit ou met à jour le contenu du widget.

        En état DÉTACHÉ : met à jour _full_text, estime la hauteur pour
        stabiliser le layout, et marque _dirty=True. Le rendu HTML sera
        effectué au prochain attach().

        En état ATTACHÉ : charge le HTML complet dans le WebView.

        Parameters
        ----------
        text : str
            Texte Markdown brut du message.
        """
        self._full_text = text
        self._copy_btn.setVisible(bool(text))
        self._copy_rich_btn.setVisible(bool(text))

        if not self._attached:
            # Mettre à jour la hauteur estimée pour éviter les sauts de layout
            h = _estimate_height(text)
            self._cached_height = h
            self._view.setMinimumHeight(h)
            self._view.setMaximumHeight(h)
            self._dirty = True
            return

        if not self._view:
            return

        try:
            from PyQt6.QtCore import QUrl
            from .latex_renderer import _ASSETS_DIR as _KATEX_DIR
            base_url = QUrl.fromLocalFile(str(_KATEX_DIR) + "/")
            html_out, self._dataimg_cache = _md_to_html(text)
            self._view.page().setHtml(html_out, base_url)
            # Lancer les téléchargements async pour les URLs distantes
            self._start_image_fetches()
        except (RuntimeError, AttributeError):
            pass

    # ── Streaming ─────────────────────────────────────────────────────

    def start_streaming(self):
        """
        Passe en mode streaming.

        La page HTML est chargée une fois avec le contenu initial,
        puis les tokens sont injectés via JS sans rechargement.
        Le widget est réattaché si nécessaire (ne doit pas arriver en
        pratique — ViewportManager ne détache pas les widgets en streaming).
        """
        self._streaming = True
        self._pending_tokens = ""
        if not self._attached:
            self.attach()
        if not self._full_text:
            self.set_content("")
        self._stream_timer.start()

    def append_token(self, token: str):
        """
        Ajoute un token pendant le streaming.

        En streaming : accumule dans _pending_tokens (flush toutes les 150ms).
        Hors streaming : appelle set_content() directement.
        """
        self._full_text += token
        if self._streaming:
            self._pending_tokens += token
        else:
            self.set_content(self._full_text)

    def _flush_tokens(self):
        """Injecte les tokens accumulés dans la WebView via JS."""
        if not self._pending_tokens or not self._view:
            return

        escaped = (
            self._pending_tokens
            .replace("\\", "\\\\")
            .replace("`", "\\`")
            .replace("${", "\\${")
        )
        self._pending_tokens = ""

        try:
            self._view.page().runJavaScript(
                f"if (document.body) document.body.insertAdjacentText('beforeend', `{escaped}`);"
            )
            self._query_height()
        except (RuntimeError, AttributeError):
            pass

    def end_streaming(self):
        """
        Termine le mode streaming et effectue le rendu Markdown complet.

        Arrête le timer, flush les tokens restants, puis recharge la page
        avec le rendu Markdown/Pygments définitif.
        """
        self._stream_timer.stop()
        self._pending_tokens = ""
        self._streaming = False
        self.set_content(self._full_text)

    def refresh_theme(self):
        """Recharge le contenu avec le thème actif."""
        if self._full_text:
            if self._attached:
                self.set_content(self._full_text)
            else:
                self._dirty = True  # re-render au prochain attach()

    # ── Hauteur dynamique ─────────────────────────────────────────────

    def _query_height(self):
        """Interroge la hauteur du contenu via JS et applique le résultat."""
        if not self._view or not self._attached:
            return
        try:
            self._view.page().runJavaScript(
                "typeof getContentHeight === 'function' ? getContentHeight() : 0;",
                self._apply_height,
            )
        except (RuntimeError, AttributeError):
            pass

    def _on_load_finished(self, ok: bool):
        """
        Interroge la hauteur dès que la page est chargée.

        Trois passes sont effectuées :
        - Immédiate (0 ms)   : capture la hauteur du texte/HTML.
        - Différée  (350 ms) : capture la hauteur réelle après décodage
          des images base64 (matplotlib, etc.) dont la taille n'est pas
          connue du renderer au moment du premier loadFinished.
        - Différée  (700 ms) : capture la hauteur après rendu SVG Mermaid.
          Mermaid diffère son rendu de 250ms puis le SVG prend ~400ms
          supplémentaires — sans cette troisième passe la bulle reste
          trop courte et le diagramme est coupé au re-scroll.
        """
        if ok:
            self._query_height()
            QTimer.singleShot(350, self._query_height)
            QTimer.singleShot(700, self._query_height)
            if mermaid_available():
                self._start_svg_polling()

    def _apply_height(self, h):
        if not self._view or not self._attached:
            return
        try:
            height = int(h) if h else 0
            if height <= self._MIN_H:
                return

            # Borner avant de mémoriser : _cached_height est réutilisé dans
            # detach() pour figer la hauteur du widget — il ne doit jamais
            # dépasser _MAX_H, sinon Qt transmet la valeur brute au renderer
            # 3D et déclenche "Requested backing texture size is NxM" > 32 768.
            clamped = min(height, self._MAX_H)
            self._cached_height = clamped

            self._view.setMinimumHeight(clamped + (0 if height > self._MAX_H else 4))
            self._view.setMaximumHeight(clamped + (0 if height > self._MAX_H else 4))

            self.updateGeometry()
        except (RuntimeError, AttributeError, ValueError):
            pass

    def _start_image_fetches(self) -> None:
        """
        Lance un worker de téléchargement pour chaque image distante (URL https://)
        présente dans self._dataimg_cache. Les images base64 sont ignorées.
        """
        for idx, (alt, uri) in self._dataimg_cache.items():
            if uri.startswith("http://") or uri.startswith("https://"):
                worker = _ImageFetchWorker(idx, uri, parent=self)
                worker.done.connect(self._on_image_fetched)
                self._fetch_workers.append(worker)
                worker.start()

    def _on_image_fetched(self, idx: int, data_uri: str) -> None:
        """
        Appelé dans le thread principal quand un téléchargement se termine.
        Met à jour le cache avec la vraie data-URI, révèle l'<img> inline
        et masque le bouton de repli dans la WebView.
        """
        if not data_uri:
            _log.warning("_on_image_fetched: échec téléchargement idx=%d", idx)
            try:
                js = (
                    f"var b=document.querySelector('button[data-imgidx=\"{idx}\"]');"
                    f"if(b){{b.querySelector('.img-status').textContent='— échec du chargement';}}"
                )
                self._view.page().runJavaScript(js)
            except (RuntimeError, AttributeError):
                pass
            return

        if idx in self._dataimg_cache:
            alt, _ = self._dataimg_cache[idx]
            self._dataimg_cache[idx] = (alt, data_uri)

        # Révéler l'<img> inline avec la data-URI et masquer le bouton de repli
        try:
            escaped_uri = data_uri.replace("'", "\\'")
            js = (
                f"(function(){{"
                f"  var imgs=document.querySelectorAll('img[data-imgidx=\"{idx}\"]');"
                f"  imgs.forEach(function(img){{"
                f"    img.src='{escaped_uri}';"
                f"    img.style.display='';"
                f"  }});"
                f"  var btns=document.querySelectorAll('button[data-imgidx=\"{idx}\"]');"
                f"  btns.forEach(function(b){{b.style.display='none';}});"
                f"}})();"
            )
            self._view.page().runJavaScript(js)
            QTimer.singleShot(100, self._query_height)
        except (RuntimeError, AttributeError):
            pass

    def _on_title_changed(self, title: str) -> None:
        """
        Intercepte les changements de titre de la WebView.

        Le bouton image injecte onclick="document.title='dataimg:N'".
        Quand l'utilisateur clique, titleChanged est émis ici avec
        title='dataimg:N'. On extrait N, on récupère la data-URI dans
        self._dataimg_cache (propre à ce widget) et on ouvre ImageViewerDialog.
        """
        if not title.startswith("dataimg:"):
            return
        # Réinitialiser le titre immédiatement : titleChanged n'est émis que si
        # la valeur change. Sans ce reset, un second clic sur la même image
        # (ou toute image ayant le même idx) ne déclencherait plus le signal.
        self._view.page().runJavaScript("document.title = '';")
        try:
            idx = int(title.split(":", 1)[1])
        except (ValueError, IndexError):
            return
        entry = self._dataimg_cache.get(idx)
        if entry:
            alt, data_uri = entry
            ImageViewerDialog.open(self, alt, data_uri)

    # ── Copie ─────────────────────────────────────────────────────────

    def _copy(self):
        QGuiApplication.clipboard().setText(self._full_text)
        self._copy_btn.setText("✓")
        QTimer.singleShot(1500, lambda: self._copy_btn.setText("⎘"))

    def _copy_rich(self):
        """
        Copie le contenu dans le presse-papiers avec mise en forme HTML.

        Utilise QMimeData pour placer simultanément :
          - text/html   → lu par Word, LibreOffice, Outlook, etc.
          - text/plain  → repli si l'application cible ne supporte pas HTML

        Le HTML généré est une version allégée (sans CSS Pygments/KaTeX/Mermaid)
        adaptée au collage dans un traitement de texte : polices système standard,
        tableaux, gras, italique, titres, listes, blocs de code inline.
        """
        if not self._full_text:
            return

        html_body = self._build_rich_html(self._full_text)

        # Word attend un fragment HTML complet avec les balises CF_HTML standard.
        # Qt gère automatiquement l'encapsulation CF_HTML sur Windows quand on
        # passe du HTML via QMimeData.setHtml() — aucune manipulation manuelle
        # du header CF_HTML n'est nécessaire.
        mime = QMimeData()
        mime.setHtml(html_body)
        mime.setText(self._full_text)
        QGuiApplication.clipboard().setMimeData(mime)

        self._copy_rich_btn.setText("✓")
        QTimer.singleShot(1500, lambda: self._copy_rich_btn.setText("📄"))

    @staticmethod
    def _build_rich_html(markdown_text: str) -> str:
        """
        Convertit du Markdown en HTML haute fidélité pour Word/LibreOffice.

        Stratégie
        ─────────
        • Styles inline sur chaque balise — Word ignore souvent <style> en
          collage CF_HTML ; les styles inline sont la seule méthode fiable.
        • Coloration syntaxique Pygments (inline spans) — Word interprète
          correctement les <span style="color:..."> dans un <pre>.
        • Parser html.parser en deux passes : (1) coloration Pygments sur les
          blocs <code lang>, (2) injection inline sur toutes les balises.
        • Alternance thead/tbody correctement séparée pour les tableaux.
        • Alignement des colonnes préservé depuis les marqueurs Markdown
          |:---|:---:|---:| via l'attribut align= généré par python-markdown.
        • Listes ul/ol avec list-style-type explicite (Word peut l'ignorer sans).
        • Enveloppe HTML avec namespaces Office pour collage Word natif.

        Éléments supportés
        ──────────────────
        h1-h3 · p · strong/em · code inline · pre+code (coloré) · ul/ol/li
        table (thead/tbody, alternance, alignement) · blockquote · hr · a
        Mermaid → note · LaTeX $$ → note · images base64 → note · img URL → lien

        Dépendances optionnelles
        ────────────────────────
        markdown   (pip install markdown)    — requis pour rendu Markdown
        pygments   (pip install pygments)    — coloration syntaxique blocs code
        """
        from html.parser import HTMLParser

        # ── Palette et typographie ────────────────────────────────────────────
        FONT_BODY  = 'Calibri, "Segoe UI", Arial, sans-serif'
        FONT_MONO  = '"Consolas", "Courier New", monospace'
        C_TEXT     = '#1A1A1A'
        C_MUTED    = '#555555'
        C_LINK     = '#1155CC'
        C_H1       = '#1F3864'
        C_H2       = '#2E4C7E'
        C_H3       = '#2E4C7E'
        C_CODE_FG  = '#C7254E'   # rouge discret pour code inline
        C_CODE_BG  = '#F0F0F0'
        C_CODE_BD  = '#CCCCCC'
        C_PRE_BG   = '#F2F2F2'
        C_PRE_BD   = '#C8C8C8'
        C_TH_BG    = '#D9E1F2'   # bleu pâle style Word
        C_TD_ALT   = '#EEF2FA'   # alternance paire
        C_BQ_BD    = '#7F7F7F'
        C_HR       = '#AAAAAA'

        # ── 1. Pré-nettoyage du Markdown ─────────────────────────────────────

        text = markdown_text

        # Blocs Mermaid → note (non rendus dans un traitement de texte)
        text = re.sub(
            r'```mermaid\n.*?```',
            '\n> *\\[Diagramme — non disponible en texte enrichi\\]*\n',
            text, flags=re.DOTALL | re.IGNORECASE,
        )
        # LaTeX display $$ → note (inline $...$ conservé)
        text = re.sub(
            r'\$\$(.*?)\$\$',
            lambda m: f'\n> *\\[Formule : {m.group(1).strip()[:60]}\\]*\n',
            text, flags=re.DOTALL,
        )
        # Images base64 → note
        text = re.sub(
            r'!\[([^\]]*)\]\(data:image/[^)]+\)',
            lambda m: f'*\\[Image : {m.group(1) or "graphique"}\\]*',
            text,
        )
        # Images URL distantes → lien texte
        text = re.sub(
            r'!\[([^\]]*)\]\((https?://[^)]+)\)',
            lambda m: f'[{m.group(1) or "image"}]({m.group(2)})',
            text,
        )

        # ── 2. Rendu Markdown → HTML brut ────────────────────────────────────

        if _HAS_MD:
            raw_body = md_lib.markdown(
                text,
                extensions=["tables", "nl2br", "sane_lists", "fenced_code"],
            )
        else:
            raw_body = html.escape(text).replace("\n", "<br>")

        # ── 3. Coloration syntaxique Pygments (inline spans) ─────────────────
        #
        # Pygments HtmlFormatter(nowrap=True, inline_styles=True) produit des
        # <span style="color:..."> directement sur le texte, sans classes CSS.
        # Word lit ces spans correctement → coloration préservée au collage.
        #
        # On remplace chaque <code class="language-XXX">...</code> dans un <pre>
        # par le HTML coloré de Pygments.

        if _HAS_PYGMENTS:
            def _pygmentize_pre(m: re.Match) -> str:
                lang_attr = m.group(1) or ''
                code_text = m.group(2)

                # Extraire le nom de langage depuis class="language-python" ou "python"
                lang_m = re.search(r'language-(\w+)', lang_attr)
                lang   = lang_m.group(1) if lang_m else lang_attr.strip().strip('"\'')

                # Dé-échapper les entités HTML dans le code source
                code_src = (
                    code_text
                    .replace('&amp;',  '&')
                    .replace('&lt;',   '<')
                    .replace('&gt;',   '>')
                    .replace('&quot;', '"')
                    .replace('&#39;',  "'")
                )

                try:
                    lexer = get_lexer_by_name(lang, stripall=True) if lang else TextLexer()
                except Exception:
                    lexer = TextLexer()

                fmt = HtmlFormatter(
                    nowrap=True,
                    noclasses=True,     # convertit class= en style= inline (Word-compatible)
                    style='friendly',   # palette claire, lisible sur fond blanc
                )
                colored = highlight(code_src, lexer, fmt).rstrip('\n')

                pre_style = (
                    f'font-family:{FONT_MONO};font-size:10pt;'
                    f'background:{C_PRE_BG};border:1pt solid {C_PRE_BD};'
                    f'padding:8pt 10pt;margin:6pt 0;'
                    f'white-space:pre-wrap;word-wrap:break-word;'
                    f'line-height:1.45;border-radius:3pt;'
                )
                return f'<pre style="{pre_style}">{colored}</pre>'

            # Cibler <pre><code class="...">...</code></pre> ou <pre><code>...</code></pre>
            raw_body = re.sub(
                r'<pre><code([^>]*)>(.*?)</code></pre>',
                _pygmentize_pre,
                raw_body,
                flags=re.DOTALL,
            )

        # ── 4. Styles inline par balise ───────────────────────────────────────

        TAG_STYLES: dict[str, str] = {
            'h1': (
                f'font-family:{FONT_BODY};font-size:18pt;font-weight:bold;'
                f'color:{C_H1};margin:14pt 0 4pt 0;padding-bottom:4pt;'
                f'border-bottom:1.5pt solid {C_H1};line-height:1.2;'
                f'mso-outline-level:1;'
            ),
            'h2': (
                f'font-family:{FONT_BODY};font-size:14pt;font-weight:bold;'
                f'color:{C_H2};margin:12pt 0 3pt 0;line-height:1.3;'
                f'mso-outline-level:2;'
            ),
            'h3': (
                f'font-family:{FONT_BODY};font-size:12pt;font-weight:bold;'
                f'color:{C_H3};margin:10pt 0 2pt 0;line-height:1.3;'
                f'mso-outline-level:3;'
            ),
            'p': (
                f'font-family:{FONT_BODY};font-size:11pt;color:{C_TEXT};'
                f'margin:0 0 6pt 0;line-height:1.4;'
            ),
            'ul': (
                f'font-family:{FONT_BODY};font-size:11pt;color:{C_TEXT};'
                f'list-style-type:disc;margin:4pt 0 6pt 0;'
                f'padding-left:22pt;line-height:1.4;'
            ),
            'ol': (
                f'font-family:{FONT_BODY};font-size:11pt;color:{C_TEXT};'
                f'list-style-type:decimal;margin:4pt 0 6pt 0;'
                f'padding-left:22pt;line-height:1.4;'
            ),
            'li': (
                f'font-family:{FONT_BODY};font-size:11pt;color:{C_TEXT};'
                f'margin:2pt 0;line-height:1.4;'
            ),
            'blockquote': (
                f'font-family:{FONT_BODY};font-size:11pt;font-style:italic;'
                f'color:{C_MUTED};margin:6pt 0 6pt 8pt;padding:6pt 14pt;'
                f'border-left:3pt solid {C_BQ_BD};background:#F7F7F7;'
            ),
            # <pre> sans Pygments : bloc monospace neutre
            'pre': (
                f'font-family:{FONT_MONO};font-size:10pt;color:{C_TEXT};'
                f'background:{C_PRE_BG};border:1pt solid {C_PRE_BD};'
                f'padding:8pt 10pt;margin:6pt 0;'
                f'white-space:pre-wrap;word-wrap:break-word;'
                f'line-height:1.45;border-radius:3pt;'
            ),
            # <code> inline (hors <pre>) uniquement
            'code': (
                f'font-family:{FONT_MONO};font-size:10pt;color:{C_CODE_FG};'
                f'background:{C_CODE_BG};border:0.5pt solid {C_CODE_BD};'
                f'padding:1pt 4pt;border-radius:2pt;'
            ),
            'table': (
                f'font-family:{FONT_BODY};font-size:11pt;color:{C_TEXT};'
                f'border-collapse:collapse;width:100%;margin:8pt 0;'
            ),
            'th': (
                f'font-family:{FONT_BODY};font-size:11pt;font-weight:bold;'
                f'color:{C_TEXT};background:{C_TH_BG};'
                f'border:1pt solid {C_CODE_BD};padding:5pt 8pt;'
                f'text-align:left;vertical-align:middle;'
            ),
            'td': (
                f'font-family:{FONT_BODY};font-size:11pt;color:{C_TEXT};'
                f'border:1pt solid {C_CODE_BD};padding:5pt 8pt;'
                f'vertical-align:top;'
            ),
            'a':      f'color:{C_LINK};text-decoration:underline;',
            'strong': 'font-weight:bold;',
            'em':     'font-style:italic;',
            'hr': (
                f'border:none;border-top:1.5pt solid {C_HR};'
                f'margin:10pt 0;height:0;'
            ),
        }

        # ── 5. Parser HTML : injection de styles inline ───────────────────────

        class _InlineStyler(HTMLParser):
            """
            Réécrit le HTML Markdown en injectant style= inline sur chaque balise.

            Points clés
            ───────────
            • <pre> déjà stylé par Pygments → skip (style déjà injecté en étape 3)
            • <code> dans <pre> sans Pygments → fond transparent, pas de bordure
            • Tableaux : compteur de lignes séparé pour thead (jamais alterné)
              et tbody (alternance paire/impaire)
            • <td align="..."> généré par python-markdown → préservé et fusionné
            • Listes imbriquées : le style ul/ol est hérité, on ne l'écrase pas
            """

            def __init__(self):
                super().__init__(convert_charrefs=False)
                self.out: list[str] = []
                self._in_pre        = False
                self._pre_styled    = False   # True si le <pre> porte déjà un style
                self._in_table      = False
                self._in_thead      = False   # True entre <thead> et </thead>
                self._tbody_tr_idx  = 0       # compteur de <tr> dans <tbody>

            @staticmethod
            def _merge(existing: str, new: str) -> str:
                """Fusionne deux chaînes de style CSS (new prend la priorité)."""
                base: dict[str, str] = {}
                for part in existing.split(';'):
                    if ':' in part:
                        k, _, v = part.partition(':')
                        base[k.strip()] = v.strip()
                for part in new.split(';'):
                    if ':' in part:
                        k, _, v = part.partition(':')
                        base[k.strip()] = v.strip()
                return ';'.join(f'{k}:{v}' for k, v in base.items() if v)

            def _emit(self, tag: str, attrs: dict, self_closing: bool = False) -> None:
                parts = [tag]
                for k, v in attrs.items():
                    parts.append(f'{k}="{html.escape(str(v), quote=True)}"')
                tail = ' /' if self_closing else ''
                self.out.append(f'<{" ".join(parts)}{tail}>')

            def handle_starttag(self, tag: str, attrs: list) -> None:
                tag_l  = tag.lower()
                adict  = dict(attrs)

                # ── <pre> ────────────────────────────────────────────────────
                if tag_l == 'pre':
                    self._in_pre = True
                    # Si Pygments a déjà injecté style= sur ce <pre>, on le
                    # conserve tel quel sans écraser.
                    if 'style' in adict and 'font-family' in adict['style']:
                        self._pre_styled = True
                    else:
                        self._pre_styled = False
                        adict['style'] = self._merge(
                            adict.get('style', ''), TAG_STYLES['pre']
                        )
                    self._emit(tag, adict)
                    return

                # ── <code> dans <pre> ────────────────────────────────────────
                if tag_l == 'code' and self._in_pre:
                    # Fond transparent : le <pre> porte déjà le fond coloré
                    neutral = (
                        'font-family:inherit;font-size:inherit;'
                        'background:transparent;border:none;padding:0;color:inherit;'
                    )
                    adict['style'] = self._merge(adict.get('style', ''), neutral)
                    self._emit(tag, adict)
                    return

                # ── Tableaux ─────────────────────────────────────────────────
                if tag_l == 'table':
                    self._in_table     = True
                    self._in_thead     = False
                    self._tbody_tr_idx = 0

                elif tag_l == 'thead':
                    self._in_thead = True

                elif tag_l == 'tbody':
                    self._in_thead     = False
                    self._tbody_tr_idx = 0

                elif tag_l == 'td' and self._in_table:
                    base = TAG_STYLES['td']
                    # Alternance uniquement dans tbody
                    if not self._in_thead and self._tbody_tr_idx % 2 == 1:
                        base += f'background:{C_TD_ALT};'
                    # python-markdown émet style="text-align: ..." sur les <td>/<th>
                    # _merge() préserve cet alignement en le fusionnant avec notre base
                    adict['style'] = self._merge(adict.get('style', ''), base)
                    self._emit(tag, adict)
                    return

                elif tag_l == 'th' and self._in_table:
                    base  = TAG_STYLES['th']
                    adict['style'] = self._merge(adict.get('style', ''), base)
                    self._emit(tag, adict)
                    return

                # ── Style générique ───────────────────────────────────────────
                if tag_l in TAG_STYLES:
                    adict['style'] = self._merge(
                        adict.get('style', ''), TAG_STYLES[tag_l]
                    )

                self._emit(tag, adict)

            def handle_endtag(self, tag: str) -> None:
                tag_l = tag.lower()
                if tag_l == 'pre':
                    self._in_pre     = False
                    self._pre_styled = False
                elif tag_l == 'table':
                    self._in_table = False
                elif tag_l == 'thead':
                    self._in_thead = False
                elif tag_l == 'tbody':
                    self._tbody_tr_idx = 0
                elif tag_l == 'tr' and self._in_table and not self._in_thead:
                    self._tbody_tr_idx += 1
                self.out.append(f'</{tag}>')

            def handle_data(self, data: str)         -> None: self.out.append(data)
            def handle_entityref(self, name: str)    -> None: self.out.append(f'&{name};')
            def handle_charref(self, name: str)      -> None: self.out.append(f'&#{name};')
            def handle_comment(self, data: str)      -> None: self.out.append(f'<!--{data}-->')

            def result(self) -> str:
                return ''.join(self.out)

        styler = _InlineStyler()
        styler.feed(raw_body)
        styled_body = styler.result()

        # ── 6. Enveloppe HTML finale ──────────────────────────────────────────
        #
        # Namespaces Office → Word reconnaît le fragment comme natif et préserve
        # mieux la mise en forme (plans, tableaux, styles de titre).
        # La feuille <style> de secours bénéficie à LibreOffice et Outlook web.

        css_fallback = f"""
body {{
    font-family: {FONT_BODY};
    font-size: 11pt;
    color: {C_TEXT};
    line-height: 1.4;
    background: #ffffff;
    margin: 0;
    padding: 8pt;
}}
pre code {{
    background: transparent;
    border: none;
    padding: 0;
}}
tbody tr:nth-child(even) td {{
    background: {C_TD_ALT};
}}
"""
        return (
            '<!DOCTYPE html>'
            '<html xmlns:o="urn:schemas-microsoft-com:office:office"'
            ' xmlns:w="urn:schemas-microsoft-com:office:word"'
            ' xmlns="http://www.w3.org/TR/REC-html40">'
            '<head>'
            '<meta charset="utf-8">'
            '<meta name=ProgId content=Word.Document>'
            '<meta name=Generator content=Promethee>'
            f'<style>{css_fallback}</style>'
            '</head>'
            f'<body>{styled_body}</body>'
            '</html>'
        )



    # ── Téléchargement SVG Mermaid ────────────────────────────────────

    def _start_svg_polling(self):
        """
        Démarre un QTimer qui interroge window._mermaidSvgPending toutes les
        200 ms via runJavaScript. Dès qu'une valeur non-nulle est détectée,
        ouvre un QFileDialog et écrit le fichier SVG.
        Interroge aussi window._mermaidErrors pour logger les erreurs de rendu.
        """
        if not hasattr(self, '_svg_poll_timer'):
            self._svg_poll_timer = QTimer(self)
            self._svg_poll_timer.setInterval(200)
            self._svg_poll_timer.timeout.connect(self._poll_svg_pending)
            self._svg_poll_timer.timeout.connect(self._poll_mermaid_errors)
        self._svg_poll_timer.start()

    def _poll_mermaid_errors(self):
        """Récupère et logue les erreurs de rendu Mermaid remontées par JS."""
        if not self._view or not self._attached:
            return
        try:
            self._view.page().runJavaScript(
                "(function(){"
                "  var e = window._mermaidErrors;"
                "  if (e && e.length) { window._mermaidErrors = []; return JSON.stringify(e); }"
                "  return null;"
                "})();",
                self._handle_mermaid_errors,
            )
        except (RuntimeError, AttributeError):
            pass

    def _handle_mermaid_errors(self, errors_json):
        """Logue les erreurs Mermaid reçues depuis JS (tableau JSON)."""
        if not errors_json:
            return
        import json
        try:
            errors = json.loads(errors_json)
        except (ValueError, TypeError):
            errors = [str(errors_json)]
        for msg in errors:
            msg = str(msg).strip()
            if msg:
                _log.warning("[Mermaid] Erreur de rendu JS : %s", msg)

    def _poll_svg_pending(self):
        """Interroge JS et récupère le SVG si le bouton a été cliqué."""
        if not self._view or not self._attached:
            return
        try:
            self._view.page().runJavaScript(
                "window._mermaidSvgPending || null;",
                self._handle_svg_data,
            )
        except (RuntimeError, AttributeError):
            pass

    def _handle_svg_data(self, svg_data):
        """Callback runJavaScript : reçoit le SVG et ouvre QFileDialog."""
        if not svg_data:
            return
        # Effacer immédiatement côté JS pour éviter un double déclenchement
        try:
            self._view.page().runJavaScript("window._mermaidSvgPending = null;")
        except (RuntimeError, AttributeError):
            pass

        path, _ = QFileDialog.getSaveFileName(
            self,
            "Enregistrer le diagramme SVG",
            "diagramme.svg",
            "Images SVG (*.svg);;Tous les fichiers (*)",
        )
        if path:
            try:
                Path(path).write_text(svg_data, encoding="utf-8")
            except OSError as e:
                _log.error("Impossible d\'écrire le SVG : %s", e)

    # ── Nettoyage ─────────────────────────────────────────────────────

    def cleanup(self):
        """Nettoie proprement le QWebEngineView avant destruction."""
        self._stream_timer.stop()
        if hasattr(self, '_svg_poll_timer'):
            self._svg_poll_timer.stop()
        self._pending_tokens = ""
        self._streaming = False
        self._attached  = False

        if self._view:
            try:
                self._view.loadFinished.disconnect()
            except (TypeError, RuntimeError):
                pass
            self._view.stop()
            self._view.setHtml("")
            if self._view.page():
                self._view.page().deleteLater()
            self._view = None

    def __del__(self):
        try:
            self.cleanup()
        except (RuntimeError, AttributeError):
            pass
