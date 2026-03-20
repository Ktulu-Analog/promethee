# ============================================================================
# Prométhée — Assistant IA desktop
# ============================================================================
# Auteur  : Pierre COUGET
# Licence : GNU Affero General Public License v3.0 (AGPL-3.0)
#           https://www.gnu.org/licenses/agpl-3.0.html
# Année   : 2026
# ============================================================================

"""
mermaid_renderer.py — Détection et rendu des diagrammes Mermaid
===============================================================

Rôle
----
Module symétrique à latex_renderer.py.
S'interface avec message_widget.py via quatre fonctions publiques :

    is_available()               → True si assets/mermaid/mermaid.min.js existe
    mermaid_html_tags()          → balises <script> à injecter dans le <head>
    mermaid_css()                → CSS complémentaire pour les blocs Mermaid
    protect_mermaid(text)        → extrait les blocs mermaid avant Markdown
    restore_mermaid(html, cache) → réinjecte les blocs après Markdown

Stratégie protect/restore
--------------------------
Le parser Markdown transforme les blocs mermaid en <pre><code> au lieu de
les laisser tels quels. La stratégie est :
  1. protect_mermaid() extrait chaque bloc, le stocke dans un cache et le
     remplace par un placeholder <!-- MERMAID_n -->.
  2. Le Markdown est rendu normalement (il ne voit que du texte neutre).
  3. restore_mermaid() remplace chaque placeholder par <div class="mermaid">.
  4. Mermaid.js détecte les .mermaid et rend le SVG.

Sanitization
------------
Mermaid n'est PAS du HTML. Les labels [] et {} acceptent & et " tels quels.
On ne doit donc PAS encoder ces caractères en entités HTML (&amp;, &quot;).

Corrections appliquées :

  Universelles (tous types) :
    - Tirets insécables → tiret ASCII
    - Espaces insécables → espace normal
    - Guillemets typographiques → ASCII droits
    - Directive %%{ init: ... }%% → supprimée (multi-lignes)

  Sankey uniquement :
    - En-tête "sankey" → "sankey-beta"
    - Syntaxe LLM ("A" --> "B" : N  ou  A -> B N) → CSV A,B,N
    - Lignes non-CSV (title, classDef, class, %%, NodeID[...]) → supprimées
    - Flux à valeur 0 → supprimés (sankey-beta les rejette)

  Diagrammes structurés (flowchart, sequence, etc.) :
    - Flèches Unicode → syntaxe ASCII Mermaid
    - Comparateurs ≥ ≤ → >= <=
    - Emojis dans les labels d'arêtes |...| → supprimés
    - Lignes ## → supprimées
    - IDs réservés (end, start, loop…) → préfixés _node_

Blocs imbriqués
---------------
Les LLM enveloppent parfois un bloc mermaid dans ```markdown pour "montrer
la syntaxe". protect_mermaid() détecte et extrait ce cas.

Dépendances
-----------
- Aucune dépendance Python externe (stdlib uniquement).
- assets/mermaid/mermaid.min.js doit être présent.
"""

import base64
import csv
import io
import logging
import re
from pathlib import Path

_log = logging.getLogger("promethee.mermaid_renderer")

# ── Chemins assets ────────────────────────────────────────────────────────────

_ASSETS_DIR        = Path(__file__).parent.parent.parent / "assets" / "mermaid"
_MERMAID_JS        = _ASSETS_DIR / "mermaid.min.js"
_MERMAID_AVAILABLE = _MERMAID_JS.exists()

# ── Placeholders ──────────────────────────────────────────────────────────────

_PLACEHOLDER_PREFIX = "MERMAID"
_PLACEHOLDER_RE     = re.compile(r"<!--\s*MERMAID_(\d+)\s*-->")
_PLACEHOLDER_P_RE   = re.compile(r"<p>\s*<!--\s*MERMAID_(\d+)\s*-->\s*</p>")

# ── Détection des blocs ───────────────────────────────────────────────────────

# Bloc ```mermaid ... ``` au premier niveau
_BLOCK_RE = re.compile(
    r"```[ \t]*[Mm]ermaid[ \t]*\n(.*?)```",
    re.DOTALL,
)

# Bloc mermaid imbriqué dans ```markdown ... ``` (LLM mode démonstration)
_NESTED_BLOCK_RE = re.compile(
    r"```[ \t]*(?:markdown|md)[ \t]*\n"
    r"(?:.*?\n)*?"
    r"```[ \t]*[Mm]ermaid[ \t]*\n"
    r"(.*?)"
    r"```\n?"
    r"(?:.*?\n)*?"
    r"```",
    re.DOTALL,
)

# ── Types de diagrammes ───────────────────────────────────────────────────────

# Diagrammes à syntaxe libre (CSV, texte) sans syntaxe flowchart
_PLAIN_DIAGRAM_TYPES = frozenset({
    "sankey-beta", "sankey",
    "timeline", "mindmap", "gitgraph", "xychart-beta",
    "journey",
    "architecture-beta", "kanban", "packet-beta",
    "c4context", "c4container", "c4component", "c4dynamic", "c4deployment",
})

# Types de diagrammes valides comme première ligne (en-tête requis).
# Un bloc mermaid qui ne commence pas par un de ces types est un fragment
# (ex : subgraph seul dans un exemple de prose) → ne pas le rendre.
_VALID_DIAGRAM_TYPES = frozenset({
    "flowchart", "graph",
    "sequencediagram",
    "classdiagram",
    "statediagram-v2", "statediagram",
    "erdiagram",
    "gantt",
    "pie",
    "sankey-beta", "sankey",
    "gitgraph",
    "mindmap",
    "timeline",
    "xychart-beta",
    "requirementdiagram",
    "c4context", "c4container", "c4component", "c4dynamic", "c4deployment",
    "quadrantchart",
    "block-beta",
    "journey",
    "architecture-beta",
    "kanban",
    "packet-beta",
})

# ── Regex de sanitization ─────────────────────────────────────────────────────

_EMOJI_RE = re.compile(
    "["
    "\U0001F000-\U0001FFFF"
    "\U00002702-\U000027B0"
    "\U0000FE00-\U0000FE0F"
    "\U000020E3"
    "\U0001F1E0-\U0001F1FF"
    "]+",
    flags=re.UNICODE,
)

_INIT_DIRECTIVE_RE = re.compile(r"%%\{.*?\}%%", re.DOTALL)
_EDGE_LABEL_RE     = re.compile(r"\|([^|]+)\|")

# Mots réservés Mermaid qui causent des erreurs de parsing quand utilisés
# comme identifiants de noeuds. Les LLM les utilisent fréquemment (start, end).
_MERMAID_RESERVED_IDS = frozenset({
    "end", "start",
    "subgraph", "direction",
    "state", "note",
    "loop", "alt", "else", "opt", "par", "and", "rect",
    "left", "right",
    "click", "call", "href",
    "link", "linkStyle",
})

# ── Regex requirementDiagram ────────────────────────────────────────────────
# Les propriétés risk / verifyMethod / type / method attendent des mots-clés
# sans guillemets. Le LLM les entoure souvent de " → erreur "got qString".
_REQ_PROP_QUOTES_RE = re.compile(
    r'^(\s*(?:risk|verifyMethod|type|method)\s*:\s*)"([^"]+)"',
    re.MULTILINE | re.IGNORECASE,
)

# ── Regex Sankey ──────────────────────────────────────────────────────────────

_SANKEY_ARROW_RE = re.compile(
    r'^"?([^">\n]+?)"?'
    r"\s*-{1,2}>\s*"
    r'"?([^">\n,]+?)"?'
    r"\s*:?\s*"
    r"(\d+(?:\.\d+)?)"
    r"\s*(?:%%.*)?$",
)
_SANKEY_IGNORE_RE = re.compile(
    r"^(title\b|classDef\b|class\b|%%|[A-Za-z_]\w*\s*[\[({])"
)


# ══════════════════════════════════════════════════════════════════════════════
#  API publique
# ══════════════════════════════════════════════════════════════════════════════

def is_available() -> bool:
    """Retourne True si l'asset Mermaid local est présent."""
    return _MERMAID_AVAILABLE


def mermaid_html_tags() -> str:
    """
    Retourne les balises <script> Mermaid à injecter dans le <head>.

    - Charge mermaid.min.js depuis les assets locaux.
    - Initialise Mermaid avec le thème adapté au mode clair/sombre.
    - Lance mermaid.run() après 250 ms pour laisser QWebEngineView
      atteindre sa largeur définitive.
    - Notifie Qt de la nouvelle hauteur après rendu SVG.
    """
    if not _MERMAID_AVAILABLE:
        return "<!-- Mermaid non disponible : assets/mermaid/mermaid.min.js introuvable -->"

    try:
        from .styles import ThemeManager
        is_dark = ThemeManager.is_dark()
    except Exception:
        is_dark = False

    theme = "dark" if is_dark else "default"
    uri   = _MERMAID_JS.as_uri()

    return f"""\
<script src="{uri}"></script>
<script>
(function() {{
    function initMermaid() {{
        if (typeof mermaid === 'undefined') return;
        mermaid.initialize({{
            startOnLoad: false,
            theme: '{theme}',
            securityLevel: 'loose',
            fontFamily: '"Segoe UI","SF Pro Text","Helvetica Neue",sans-serif',
            flowchart: {{ htmlLabels: true, useMaxWidth: true, curve: 'basis' }},
            sequence:  {{ useMaxWidth: true }},
            gantt:     {{ useMaxWidth: true }},
        }});
        setTimeout(function() {{
            // Décoder le source base64 avant que mermaid.run() lise textContent
            document.querySelectorAll('.mermaid[data-mermaid-src]').forEach(function(el) {{
                try {{
                    var b64 = el.getAttribute('data-mermaid-src');
                    var bin = atob(b64);
                    var bytes = new Uint8Array(bin.length);
                    for (var k=0; k<bin.length; k++) bytes[k] = bin.charCodeAt(k);
                    el.textContent = new TextDecoder('utf-8').decode(bytes);
                }} catch(e) {{ el.textContent = atob(el.getAttribute('data-mermaid-src') || ''); }}
                if (el.getBoundingClientRect().width < 200) {{
                    el.style.minWidth = '600px';
                    el.style.width    = '100%';
                }}
            }});
            window._mermaidErrors = [];
            mermaid.run({{ querySelector: '.mermaid' }}).then(function() {{
                if (typeof getContentHeight === 'function') {{
                    try {{ window._mermaidHeight = getContentHeight(); }}
                    catch(e) {{}}
                }}
            }}).catch(function(err) {{
                var msg = (err && err.message) ? err.message : String(err);
                window._mermaidErrors.push(msg);
            }});
        }}, 250);
    }}
    if (document.readyState === 'loading') {{
        document.addEventListener('DOMContentLoaded', initMermaid);
    }} else {{
        initMermaid();
    }}

}})();
window._mermaidSvgPending = null;
window.mermaidSaveSvg = function(idx) {{
    var el = document.getElementById('mermaid-diag-' + idx);
    if (!el) return;
    var svgEl = el.querySelector('svg');
    if (!svgEl) return;
    var clone = svgEl.cloneNode(true);
    clone.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
    var r = svgEl.getBoundingClientRect();
    if (r.width)  clone.setAttribute('width',  Math.round(r.width));
    if (r.height) clone.setAttribute('height', Math.round(r.height));
    window._mermaidSvgPending = new XMLSerializer().serializeToString(clone);
}};
</script>"""


def mermaid_css() -> str:
    """
    CSS complementaire pour les blocs Mermaid.
    IMPORTANT : pas de f-string globale -- son resultat est insere dans
    une f-string dans message_widget.py, les accolades doivent rester simples.
    """
    try:
        from .styles import ThemeManager
        is_dark = ThemeManager.is_dark()
    except Exception:
        is_dark = False

    btn_bg      = ThemeManager.inline('mermaid_btn_bg')
    btn_color   = ThemeManager.inline('mermaid_btn_color')
    btn_border  = ThemeManager.inline('mermaid_btn_border')
    btn_bg_hov  = ThemeManager.inline('mermaid_btn_hover_bg')
    btn_col_hov = ThemeManager.inline('mermaid_btn_hover_color')

    css  = ".mermaid {display:block;text-align:center;margin:14px 0 4px;"
    css += "overflow-x:auto;min-width:200px;width:100%;box-sizing:border-box;}\n"
    css += ".mermaid svg {max-width:100%;height:auto;}\n"
    css += ".mermaid-toolbar {display:flex;justify-content:flex-end;margin:0 0 10px 0;}\n"
    css += ".mermaid-dl-btn {"
    css += "display:inline-flex;align-items:center;gap:5px;"
    css += "padding:3px 10px 3px 8px;border-radius:5px;cursor:pointer;"
    css += "border:1px solid " + btn_border + ";"
    css += "background:" + btn_bg + ";"
    css += "color:" + btn_color + ";"
    css += "font-size:11px;}\n"
    css += ".mermaid-dl-btn:hover {"
    css += "background:" + btn_bg_hov + ";"
    css += "color:" + btn_col_hov + ";"
    css += "border-color:" + btn_col_hov + ";}\n"

    svg_bg     = ThemeManager.inline('mermaid_svg_btn_bg')
    svg_color  = ThemeManager.inline('mermaid_svg_btn_color')
    svg_border = ThemeManager.inline('mermaid_svg_btn_border')
    css += ".mermaid-svg-btn {"
    css += "display:inline-flex;align-items:center;gap:4px;"
    css += "padding:3px 10px;margin:4px 0 10px;"
    css += f"border:1px solid {svg_border};border-radius:4px;"
    css += f"background:{svg_bg};color:{svg_color};"
    css += "font-size:12px;cursor:pointer;}\n"
    return css

def protect_mermaid(text: str) -> tuple[str, dict[int, str]]:
    """
    Extrait les blocs mermaid du texte et les remplace par des placeholders.

    Doit être appelé AVANT protect_latex() et AVANT le rendu Markdown.

    Gère deux cas :
    - Blocs mermaid au premier niveau (cas normal)
    - Blocs mermaid imbriqués dans un bloc markdown (mode LLM démonstration)

    Returns
    -------
    protected_text : str
        Texte avec les blocs Mermaid remplacés par <!-- MERMAID_n -->.
    cache : dict[int, str]
        Dictionnaire {index: source_mermaid_sanitisé}.
    """
    cache: dict[int, str] = {}
    counter = [0]

    def store(raw: str) -> str:
        """Stocke le bloc si c'est un diagramme autonome valide.
        Un fragment (subgraph seul, exemple de syntaxe) est rejeté :
        il reste comme bloc de code ordinaire plutôt que de faire planter
        Mermaid.js avec un contenu sans en-tête de diagramme reconnu.
        """
        raw_type = _diagram_type(raw.strip())
        sanitized = _sanitize(raw.strip())
        # Vérifier que le bloc commence par un type de diagramme reconnu
        dtype = _diagram_type(sanitized)
        if dtype not in _VALID_DIAGRAM_TYPES:
            # Bloc invalide ou fragment → restituer tel quel (sera rendu en <pre>)
            _log.warning(
                "[Mermaid] Bloc rejeté — type non reconnu : %r (brut: %r) | "
                "première ligne : %r",
                dtype or "(vide)",
                raw_type or "(vide)",
                raw.strip().splitlines()[0][:120] if raw.strip() else "",
            )
            return f"```mermaid\n{raw}```"
        idx = counter[0]
        cache[idx] = sanitized
        counter[0] += 1
        _log.debug(
            "[Mermaid] Bloc #%d accepté — type=%s | %d lignes | "
            "sanitization: %s",
            idx,
            dtype,
            len(sanitized.splitlines()),
            "oui" if sanitized != raw.strip() else "non",
        )
        return f"<!-- {_PLACEHOLDER_PREFIX}_{idx} -->"

    # Blocs imbriqués dans ```markdown / ```md en premier
    text = _NESTED_BLOCK_RE.sub(lambda m: store(m.group(1)), text)
    # Blocs mermaid de premier niveau
    text = _BLOCK_RE.sub(lambda m: store(m.group(1)), text)

    return text, cache


def restore_mermaid(html: str, cache: dict[int, str]) -> str:
    """
    Réinjecte les blocs Mermaid dans le HTML rendu sous forme de <div class="mermaid">.

    Doit être appelé APRÈS le rendu Markdown et APRÈS restore_latex().
    """
    if not cache:
        return html

    def replace(m: re.Match) -> str:
        idx = int(m.group(1))
        if idx not in cache:
            return m.group(0)
        btn = (
            f'<div style="text-align:right">'
            f'<button class="mermaid-svg-btn" '
            f'onclick="mermaidSaveSvg({idx})" '
            'title="T\u00e9l\u00e9charger en SVG">'
            '\u2b07 SVG'
            '</button></div>'
        )
        src_b64 = base64.b64encode(cache[idx].encode('utf-8')).decode('ascii')
        return (
            f'<div class="mermaid" id="mermaid-diag-{idx}"'
            f' data-mermaid-src="{src_b64}"></div>'
        ) + btn


    html = _PLACEHOLDER_P_RE.sub(replace, html)
    html = _PLACEHOLDER_RE.sub(replace, html)
    return html


# ══════════════════════════════════════════════════════════════════════════════
#  Sanitization interne
# ══════════════════════════════════════════════════════════════════════════════

def _diagram_type(src: str) -> str:
    """
    Retourne le type depuis la première ligne non vide et non-directive.
    Ex : "flowchart", "sankey-beta", "sequencediagram", ...
    """
    for line in src.splitlines():
        s = line.strip().lower()
        if s and not s.startswith("%%"):
            # "gitGraph:" ou "gitGraph LR:" → retirer le ":" éventuel
            return s.split()[0].rstrip(":")
    return ""


def _sanitize(src: str) -> str:
    """
    Applique les corrections non-destructives au source Mermaid brut.
    Voir la docstring du module pour le détail des corrections.
    """
    # 1. Supprimer %%{ init }%% avant la détection du type
    src_before_init = src
    src = _INIT_DIRECTIVE_RE.sub("", src).strip()
    if src != src_before_init.strip():
        _log.debug("[Mermaid] Correction : directive %%{init}%% supprimée")

    dtype = _diagram_type(src)

    # 2a. Fragment sans en-tête valide : un bloc qui commence par "subgraph"
    #     ou dont le type n'est pas reconnu est un extrait incomplet généré
    #     par le LLM (ex: exemple dans les "astuces" d'une réponse).
    #     On préfixe avec "flowchart TD" pour que Mermaid puisse le parser.
    _KNOWN_TYPES = {
        "flowchart", "graph", "sequencediagram", "classdiagram",
        "statediagram", "statediagram-v2", "erdiagram", "gantt",
        "pie", "gitgraph", "mindmap", "timeline", "xychart-beta",
        "sankey-beta", "sankey", "requirementdiagram", "c4context",
        "journey", "quadrantchart", "block-beta",
        "architecture-beta", "kanban", "packet-beta",
        "c4context", "c4container", "c4component", "c4dynamic", "c4deployment",
        # Alias LLM (en-têtes incorrects mais fréquents)
        "xychart", "block", "architecturediagram", "architecture_diagram",
        "architecture",
        "packetdiagram", "packet_diagram", "packet",
    }
    if dtype == "subgraph" or (dtype and dtype not in _KNOWN_TYPES):
        _log.debug(
            "[Mermaid] Correction : en-tête manquant/inconnu (%r) → préfixe flowchart TD ajouté",
            dtype,
        )
        src = "flowchart TD\n" + src

    # Re-détecter après ajout éventuel de l'en-tête
    dtype = _diagram_type(src)

    # 2b. Normaliser les alias LLM vers l'en-tête Mermaid exact
    _DTYPE_ALIASES = {
        "xychart":            "xychart-beta",
        "block":              "block-beta",
        "architecture":       "architecture-beta",
        "architecturediagram":  "architecture-beta",
        "architecture_diagram": "architecture-beta",
        "packet":             "packet-beta",
        "packetdiagram":      "packet-beta",
        "packet_diagram":     "packet-beta",
    }
    if dtype in _DTYPE_ALIASES:
        correct = _DTYPE_ALIASES[dtype]
        _log.debug(
            "[Mermaid] Normalisation alias : %r → %r",
            dtype, correct,
        )
        # Remplacer la première ligne non-vide par l'en-tête correct
        lines = src.splitlines()
        for idx, line in enumerate(lines):
            if line.strip():
                lines[idx] = correct
                break
        src = "\n".join(lines)
        dtype = correct

    # 2. Sankey : réécriture complète en sankey-beta CSV
    if dtype in ("sankey", "sankey-beta"):
        result = _fix_sankey(src)
        n_original = len(src.splitlines())
        n_result   = len(result.splitlines())
        _log.debug(
            "[Mermaid] Correction Sankey : %d lignes → %d lignes (CSV sankey-beta)",
            n_original, n_result,
        )
        return result

    # 3. requirementDiagram : retirer les guillemets sur risk/verifyMethod/type
    if dtype == "requirementdiagram":
        src = _REQ_PROP_QUOTES_RE.sub(r'\1\2', src)

    # 3b. erDiagram : guillemets obligatoires sur les labels de relation
    #     Mermaid 11 rejette les accents hors guillemets dans les labels de relation.
    #     Pattern : ENTITE card--card ENTITE : label_sans_guillemets
    if dtype == "erdiagram":
        def _quote_er_label(m: re.Match) -> str:
            label = m.group(2).strip()
            if label.startswith('"') and label.endswith('"'):
                return m.group(0)
            return m.group(1) + '"' + label + '"'
        src = re.sub(
            r'(\s:\s*)([^"\n{][^\n]*?)\s*$',
            _quote_er_label,
            src,
            flags=re.MULTILINE,
        )
        # 3c. erDiagram : translittérer les accents dans les noms d'attributs.
        #     Mermaid 11 rejette les caractères non-ASCII dans les identifiants
        #     type/nom d'attribut (ex: 'string désignation' → erreur 'got é').
        #     On translittère uniquement les tokens à l'intérieur des blocs { }.
        import unicodedata as _ud
        def _transliterate(s: str) -> str:
            return ''.join(
                c for c in _ud.normalize('NFD', s)
                if _ud.category(c) != 'Mn'
            )
        def _fix_er_attr_line(m: re.Match) -> str:
            line = m.group(0)
            # Ligne d'attribut : "    type nom [PK|FK|UK] [\"comment\"]"
            # Translittérer uniquement type et nom (avant le premier PK/FK/UK ou guillemet)
            attr_m = re.match(
                r'^(\s*)(\S+)(\s+)(\S+)(.*)',
                line,
            )
            if attr_m:
                indent, typ, sep, nom, rest = attr_m.groups()
                return indent + _transliterate(typ) + sep + _transliterate(nom) + rest
            return line
        # Appliquer sur les lignes à l'intérieur des blocs {}
        in_block = False
        lines_out = []
        for line in src.splitlines():
            stripped = line.strip()
            if stripped.endswith('{'):
                in_block = True
                lines_out.append(line)
            elif stripped == '}':
                in_block = False
                lines_out.append(line)
            elif in_block and stripped and not stripped.startswith('%%'):
                lines_out.append(_fix_er_attr_line(re.match(r'(.*)', line)))
            else:
                lines_out.append(line)
        src = '\n'.join(lines_out)

    # 4. Corrections universelles (tirets, espaces insécables, guillemets typo)
    src_before = src
    src = _fix_universal(src)
    if src != src_before:
        _log.debug("[Mermaid] Correction universelle : caractères Unicode normalisés")

    # 5. Corrections spécifiques aux diagrammes structurés
    if dtype not in _PLAIN_DIAGRAM_TYPES:
        src_before = src
        src = _fix_structured(src)
        if src != src_before:
            _log.debug(
                "[Mermaid] Correction structurée appliquée (type=%s) : "
                "%d → %d lignes",
                dtype,
                len(src_before.splitlines()),
                len(src.splitlines()),
            )

    return src


def _fix_universal(src: str) -> str:
    """Corrections applicables à tous les types de diagrammes."""
    # Tirets insécables
    src = src.replace("\u2010", "-").replace("\u2011", "-")
    src = src.replace("\u2013", "-").replace("\u2014", "-")
    # Espaces insécables
    src = src.replace("\u00a0", " ").replace("\u202f", " ")
    # Guillemets typographiques → ASCII droits
    src = src.replace("\u00ab", '"').replace("\u00bb", '"')
    src = src.replace("\u2018", "'").replace("\u2019", "'")
    src = src.replace("\u201c", '"').replace("\u201d", '"')
    return src




def _fix_structured(src: str) -> str:
    """
    Corrections pour les diagrammes à syntaxe flowchart/sequence/etc.

    Principes :
    - Mermaid n'est PAS du HTML. Les labels [] et {} acceptent & et " tels quels.
      Ne jamais encoder & en &amp; ni " en &quot; dans les labels.
    - Le & de jointure Mermaid (NodeA & NodeB --> NodeC) est de la syntaxe,
      pas du texte : le conserver tel quel.
    - Se limiter aux corrections strictement nécessaires.
    """
    # Flèches Unicode → ASCII Mermaid
    src = src.replace("\u2192", "-->").replace("\u2190", "<--")
    src = src.replace("\u21d2", "==>").replace("\u25ba", "-->")
    # Comparateurs (utiles dans les noeuds de décision {})
    src = src.replace("\u2265", ">=").replace("\u2264", "<=")
    # Mots réservés Mermaid utilisés comme IDs de noeuds
    src = _fix_reserved_ids(src)
    # Supprimer les titres ## générés par le LLM dans le corps du diagramme
    src = "\n".join(
        line for line in src.splitlines()
        if not line.strip().startswith("##")
    )
    # Emojis dans les labels d'arêtes |...|
    src = _EDGE_LABEL_RE.sub(_clean_edge_label, src)
    return src


def _clean_edge_label(m: re.Match) -> str:
    content = _EMOJI_RE.sub("", m.group(1)).strip()
    content = re.sub(r"^\d+\s*", "", content)
    return f"|{content}|"


def _fix_reserved_ids(src: str) -> str:
    """
    Renomme les identifiants de noeuds qui sont des mots réservés Mermaid.

    Cas traités :
    - start[...] / start([...]) / start --> B → _node_start
    - A --> end[...] / A --> end → _node_end
    - MAIS "end" seul sur une ligne (fermeture de subgraph) → conservé

    Les LLM utilisent fréquemment start et end comme IDs. Mermaid les
    interprète comme des mots-clés de syntaxe et plante le parser.
    """
    # "end" seul (avec indentation éventuelle) = fermeture de subgraph en Mermaid
    _SUBGRAPH_END_RE = re.compile(r'^\s*end\s*$')

    result = []
    renamed: list[str] = []
    for line in src.splitlines():
        stripped = line.strip()

        # Ignorer les commentaires, classDef, class, subgraph header
        if (stripped.startswith("%%")
                or stripped.startswith("classDef")
                or stripped.startswith("class ")
                or stripped.startswith("subgraph ")):
            result.append(line)
            continue

        # "end" seul = fermeture de subgraph → NE PAS renommer
        if _SUBGRAPH_END_RE.match(line):
            result.append(line)
            continue

        # Renommer les IDs réservés uniquement dans la partie AVANT le ":"
        # Le contenu après ":" est un label de transition/relation → ne pas toucher.
        # Exemple : "Idle --> Running : start" → seul "Idle", "Running" sont traités.
        # Exemple : "fr1 ..> tc1 : vérifié par" → "vérifié par" est protégé.
        colon_pos = -1
        # Chercher le ":" de label : présent si la ligne contient " : " ou finit par " :..."
        # On exclut les ":" dans les URL (://) et dans les accolades (classDiagram)
        colon_match = re.search(r'\s:\s(?!\s*//)', line)
        if colon_match:
            colon_pos = colon_match.start()

        if colon_pos >= 0:
            pre  = line[:colon_pos]
            post = line[colon_pos:]  # inclut le " : label"
        else:
            pre  = line
            post = ""

        new_pre = pre
        for word in _MERMAID_RESERVED_IDS:
            new_pre = re.sub(
                r'(?<![_"\w])(' + re.escape(word) + r')(?=\s*(?:[\[{(]|-->|--\s|$|\s*-->))',
                lambda m: f"_node_{m.group(1)}",
                new_pre,
            )
        new_line = new_pre + post
        if new_line != line:
            renamed.append(stripped[:80])
        result.append(new_line)

    if renamed:
        _log.debug(
            "[Mermaid] Correction IDs réservés : %d ligne(s) renommée(s) : %s",
            len(renamed),
            " | ".join(renamed[:5]),
        )
    return "\n".join(result)


def _parse_sankey_csv_line(s: str):
    """
    Parse une ligne CSV Sankey avec support des guillemets (csv.reader).
    Retourne (source, dest, valeur_float) ou None.
    Rejette silencieusement les en-têtes textuels (ex: Source,Dest,Value).
    """
    try:
        import csv, io
        rows = list(csv.reader(io.StringIO(s)))
        if not rows or len(rows[0]) != 3:
            return None
        src_s, dst_s, val_s = [f.strip().strip('"').strip() for f in rows[0]]
        if not src_s or not dst_s:
            return None
        return src_s, dst_s, float(val_s)
    except (ValueError, StopIteration):
        return None


def _fix_sankey(src: str) -> str:
    """
    Convertit n'importe quelle variante de syntaxe Sankey LLM en sankey-beta CSV.

    Sortie garantie :
        sankey-beta
        Source,Cible,Valeur
        ...
    """
    lines = src.splitlines()
    out: list[str] = ["sankey-beta"]
    skipped_zero   = 0
    skipped_other  = 0

    # L'en-tête peut ne pas être en ligne 0 si des commentaires %% précèdent.
    header_idx = next(
        (i for i, l in enumerate(lines) if l.strip().lower().startswith("sankey")),
        0,
    )

    for i, raw in enumerate(lines):
        if i == header_idx:
            continue

        s = raw.strip()
        if not s:
            continue
        if _SANKEY_IGNORE_RE.match(s):
            skipped_other += 1
            continue

        # Parsing CSV avec support guillemets (virgules dans les noms)
        parsed = _parse_sankey_csv_line(s)
        if parsed:
            src_n, dst_n, val = parsed
            # Nettoyer les crochets [xxx] dans les noms (syntaxe Mermaid node invalide en Sankey)
            src_n = re.sub(r'\[.*?\]', '', src_n).strip()
            dst_n = re.sub(r'\[.*?\]', '', dst_n).strip()
            if val == 0:
                skipped_zero += 1
                continue
            out.append(f"{src_n},{dst_n},{val:g}")
            continue

        # Syntaxe flèche LLM simple : "A" --> "B" : N  ou  A --> B : N
        m = _SANKEY_ARROW_RE.match(s)
        if m:
            val = float(m.group(3))
            if val == 0:
                skipped_zero += 1
                continue
            out.append(f"{m.group(1).strip().strip(chr(34))},{m.group(2).strip().strip(chr(34))},{val:g}")
            continue

        # Syntaxe flèche chaînée sans valeur : A --> B --> C  ou  A --> B[label] --> C
        # Le LLM l'utilise comme un flowchart au lieu de CSV.
        # On extrait les nœuds de la chaîne et on crée des flux avec valeur 1.
        chain_nodes = re.findall(
            r'(?:^|-->)\s*"?([^"\[\]>\n,]+?)"?\s*(?:\[[^\]]*\])?\s*(?=-->|$)',
            s,
        )
        # Nettoyer les noms extraits
        chain_nodes = [re.sub(r'\[.*?\]', '', n).strip() for n in chain_nodes if n.strip()]
        if len(chain_nodes) >= 2:
            for a, b in zip(chain_nodes, chain_nodes[1:]):
                out.append(f"{a},{b},1")
            _log.debug(
                "[Mermaid] Sankey — flèche chaînée convertie : %d flux depuis %r",
                len(chain_nodes) - 1, s[:60],
            )
            continue

        # Ligne non reconnue
        _log.debug("[Mermaid] Sankey — ligne ignorée (syntaxe inconnue) : %r", s[:80])
        skipped_other += 1

    while len(out) > 1 and not out[-1].strip():
        out.pop()

    _log.debug(
        "[Mermaid] Sankey : %d flux CSV produits | %d flux zéro supprimés | %d lignes ignorées",
        len(out) - 1,
        skipped_zero,
        skipped_other,
    )
    if len(out) == 1:
        _log.warning(
            "[Mermaid] Sankey vide : aucun flux CSV produit. "
            "Le LLM a probablement généré une syntaxe flowchart au lieu de CSV "
            "(ex: 'A --> B --> C'). Utilisez le format : 'Source,Cible,Valeur'."
        )
    return "\n".join(out)
