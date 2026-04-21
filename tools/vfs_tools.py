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
tools/vfs_tools.py — Outils système de fichiers via VFS (20 outils)
=====================================================================

Remplacement direct de system_tools.py

Chaque outil reproduit exactement la même interface (nom, paramètres,
structure de réponse) que son équivalent dans system_tools.py, de sorte
que le LLM n'a pas à changer ses appels d'outils.

La différence est interne : les opérations s'effectuent dans le système
de fichiers virtuel (VirtualFS) de l'utilisateur courant, stocké en
SQLite, et non sur le système de fichiers réel du serveur.

Outils exposés (20) :

  Lecture / Écriture (5) :
    vfs_read_file, vfs_write_file, vfs_tail_file, vfs_head_file,
    vfs_find_and_replace

  Navigation (3) :
    vfs_list_files, vfs_tree_view, vfs_search_files

  Gestion (6) :
    vfs_copy_file, vfs_move_file, vfs_delete_file, vfs_create_directory,
    vfs_get_file_info, vfs_count_lines

  Archives (2) :
    vfs_compress_files, vfs_extract_archive

  Comparaison (1) :
    vfs_diff_files

  Batch (2) :
    vfs_batch_rename, vfs_batch_delete

  Administration (1) :
    vfs_quota — espace utilisé / nombre de fichiers

Activation dans tools/__init__.py :
    from tools import vfs_tools          # remplace system_tools
"""

from typing import Optional, List

from core.tools_engine import tool, set_current_family, _TOOL_ICONS
from core.virtual_fs import get_vfs, VFSError, VFSNotFound, VFSExists, \
    VFSPermission, VFSTooBig

set_current_family("vfs_tools", "Fichiers (VFS)", "🗂️")

_TOOL_ICONS.update({
    "vfs_read_file":       "📄",
    "vfs_write_file":      "✍️",
    "vfs_tail_file":       "📜",
    "vfs_head_file":       "📋",
    "vfs_find_and_replace":"🔍",
    "vfs_list_files":      "📁",
    "vfs_tree_view":       "🌳",
    "vfs_search_files":    "🔎",
    "vfs_copy_file":       "📋",
    "vfs_move_file":       "🔄",
    "vfs_delete_file":     "🗑️",
    "vfs_create_directory":"📂",
    "vfs_get_file_info":   "ℹ️",
    "vfs_count_lines":     "🔢",
    "vfs_compress_files":  "📦",
    "vfs_extract_archive": "📂",
    "vfs_diff_files":      "↔️",
    "vfs_batch_rename":    "✏️",
    "vfs_batch_delete":    "🗑️",
    "vfs_quota":           "📊",
})


def _ok(**kwargs) -> dict:
    return {"status": "success", **kwargs}


def _err(msg: str) -> dict:
    return {"status": "error", "error": msg}


def _catch(fn):
    """Wrapper qui capture toutes les exceptions VFS et les transforme en erreur JSON."""
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except VFSTooBig as e:
            return _err(str(e))
        except VFSPermission as e:
            return _err(f"Accès refusé : {e}")
        except VFSExists as e:
            return _err(str(e))
        except VFSNotFound as e:
            return _err(str(e))
        except VFSError as e:
            return _err(str(e))
        except Exception as e:
            return _err(f"Erreur inattendue : {e}")
    wrapper.__name__ = fn.__name__
    return wrapper


# ==============================================================================
# LECTURE / ÉCRITURE (5 outils)
# ==============================================================================

@tool(
    name="vfs_read_file",
    description=(
        "Lit un fichier de l'espace de travail virtuel de l'utilisateur. "
        "Supporte les plages de lignes (start_line / end_line). "
        "Les chemins sont de la forme /dossier/fichier.txt "
        "(toujours absolus, séparateur '/')."
    ),
    parameters={
        "type": "object",
        "properties": {
            "path":       {"type": "string",  "description": "Chemin virtuel du fichier"},
            "max_chars":  {"type": "integer", "default": 4000},
            "start_line": {"type": "integer", "description": "Ligne de départ (1-indexed)"},
            "end_line":   {"type": "integer", "description": "Ligne de fin (-1 pour fin)"},
            "encoding":   {"type": "string",  "default": "utf-8"},
        },
        "required": ["path"],
    },
)
@_catch
def vfs_read_file(path: str, max_chars: int = 4000,
                  start_line: Optional[int] = None,
                  end_line: Optional[int] = None,
                  encoding: str = "utf-8") -> dict:
    vfs = get_vfs()
    content = vfs.read_text(path, encoding)

    if start_line or end_line:
        lines = content.split("\n")
        s = (start_line - 1) if start_line else 0
        e = end_line if (end_line and end_line != -1) else len(lines)
        content = "\n".join(lines[s:e])

    original_len = len(content)
    truncated = original_len > max_chars
    return _ok(
        content=content[:max_chars],
        size=original_len,
        truncated=truncated,
        file=path,
    )


@tool(
    name="vfs_write_file",
    description=(
        "Écrit du contenu dans un fichier de l'espace virtuel (max 10 MB). "
        "Crée le fichier et les dossiers parents si nécessaire. "
        "mode : 'w' = écraser, 'a' = ajouter, 'x' = créer uniquement."
    ),
    parameters={
        "type": "object",
        "properties": {
            "path":     {"type": "string"},
            "content":  {"type": "string"},
            "mode":     {"type": "string", "default": "w",
                         "description": "w (écraser), a (ajouter), x (créer uniquement)"},
            "encoding": {"type": "string", "default": "utf-8"},
        },
        "required": ["path", "content"],
    },
)
@_catch
def vfs_write_file(path: str, content: str,
                   mode: str = "w", encoding: str = "utf-8") -> dict:
    vfs = get_vfs()
    vfs.write_text(path, content, encoding=encoding, mode=mode)
    size = len(content.encode(encoding))
    return _ok(file=path, size_bytes=size,
               size=f"{size / 1024:.1f} KB" if size >= 1024 else f"{size} B")


@tool(
    name="vfs_tail_file",
    description="Affiche les dernières lignes d'un fichier de l'espace virtuel.",
    parameters={
        "type": "object",
        "properties": {
            "path":  {"type": "string"},
            "lines": {"type": "integer", "default": 10},
        },
        "required": ["path"],
    },
)
@_catch
def vfs_tail_file(path: str, lines: int = 10) -> dict:
    vfs = get_vfs()
    content, total = vfs.tail(path, lines)
    return _ok(content=content, lines_shown=len(content.split("\n")),
               total_lines=total)


@tool(
    name="vfs_head_file",
    description="Affiche les premières lignes d'un fichier de l'espace virtuel.",
    parameters={
        "type": "object",
        "properties": {
            "path":  {"type": "string"},
            "lines": {"type": "integer", "default": 10},
        },
        "required": ["path"],
    },
)
@_catch
def vfs_head_file(path: str, lines: int = 10) -> dict:
    vfs = get_vfs()
    content, total = vfs.head(path, lines)
    return _ok(content=content, lines_shown=len(content.split("\n")),
               total_lines=total)


@tool(
    name="vfs_find_and_replace",
    description=(
        "Recherche et remplace du texte dans les fichiers d'un dossier virtuel. "
        "preview=true montre les changements sans les appliquer."
    ),
    parameters={
        "type": "object",
        "properties": {
            "path":      {"type": "string"},
            "find":      {"type": "string"},
            "replace":   {"type": "string"},
            "pattern":   {"type": "string", "default": "*.txt"},
            "recursive": {"type": "boolean", "default": True},
            "preview":   {"type": "boolean", "default": True},
        },
        "required": ["path", "find", "replace"],
    },
)
@_catch
def vfs_find_and_replace(path: str, find: str, replace: str,
                          pattern: str = "*.txt", recursive: bool = True,
                          preview: bool = True) -> dict:
    vfs = get_vfs()
    results = vfs.find_and_replace(path, find, replace,
                                   pattern=pattern, preview=preview)
    return _ok(mode="preview" if preview else "applied",
               files_found=len(results), results=results[:20])


# ==============================================================================
# NAVIGATION (3 outils)
# ==============================================================================

@tool(
    name="vfs_list_files",
    description=(
        "Liste les fichiers et dossiers dans un chemin virtuel. "
        "Les chemins commencent par '/' : /uploads, /documents, /exports…"
    ),
    parameters={
        "type": "object",
        "properties": {
            "path":        {"type": "string",  "default": "/"},
            "pattern":     {"type": "string",  "default": "*",
                            "description": "Filtre glob (ex: *.pdf)"},
            "sort_by":     {"type": "string",  "default": "name",
                            "description": "name | size | date"},
            "show_hidden": {"type": "boolean", "default": False},
        },
        "required": [],
    },
)
@_catch
def vfs_list_files(path: str = "/", pattern: str = "*",
                   sort_by: str = "name", show_hidden: bool = False) -> dict:
    import fnmatch as _fnmatch
    vfs = get_vfs()
    entries = vfs.listdir(path)

    # Filtre glob
    if pattern != "*":
        entries = [e for e in entries
                   if e["type"] == "dir" or _fnmatch.fnmatch(e["name"], pattern)]

    # Masquer cachés
    if not show_hidden:
        entries = [e for e in entries if not e["name"].startswith(".")]

    # Tri
    if sort_by == "size":
        entries.sort(key=lambda x: x["size_bytes"], reverse=True)
    elif sort_by == "date":
        entries.sort(key=lambda x: x["updated_at"] or "", reverse=True)
    else:
        entries.sort(key=lambda x: (x["type"] != "dir", x["name"]))

    return _ok(path=path, count=len(entries), files=entries[:100])


@tool(
    name="vfs_tree_view",
    description="Affiche l'arborescence d'un dossier virtuel.",
    parameters={
        "type": "object",
        "properties": {
            "path":        {"type": "string",  "default": "/"},
            "max_depth":   {"type": "integer", "default": 3},
            "show_hidden": {"type": "boolean", "default": False},
        },
        "required": [],
    },
)
@_catch
def vfs_tree_view(path: str = "/", max_depth: int = 3,
                  show_hidden: bool = False) -> dict:
    vfs = get_vfs()
    tree = vfs.tree(path, max_depth=max_depth, show_hidden=show_hidden)
    return _ok(tree=tree)


@tool(
    name="vfs_search_files",
    description=(
        "Recherche avancée de fichiers dans l'espace virtuel. "
        "name_pattern : glob (ex: '*.pdf'). "
        "content : texte à rechercher dans le contenu."
    ),
    parameters={
        "type": "object",
        "properties": {
            "path":         {"type": "string",  "default": "/"},
            "name_pattern": {"type": "string"},
            "content":      {"type": "string"},
            "max_results":  {"type": "integer", "default": 50},
        },
        "required": [],
    },
)
@_catch
def vfs_search_files(path: str = "/",
                      name_pattern: Optional[str] = None,
                      content: Optional[str] = None,
                      max_results: int = 50) -> dict:
    vfs = get_vfs()
    results = vfs.search(path, name_pattern=name_pattern,
                         content=content, max_results=max_results)
    return _ok(found=len(results), results=results)


# ==============================================================================
# GESTION (6 outils)
# ==============================================================================

@tool(
    name="vfs_copy_file",
    description="Copie un fichier vers une nouvelle destination dans l'espace virtuel.",
    parameters={
        "type": "object",
        "properties": {
            "source":      {"type": "string"},
            "destination": {"type": "string"},
            "overwrite":   {"type": "boolean", "default": False},
        },
        "required": ["source", "destination"],
    },
)
@_catch
def vfs_copy_file(source: str, destination: str, overwrite: bool = False) -> dict:
    vfs = get_vfs()
    vfs.copy(source, destination, overwrite=overwrite)
    return _ok(copied=source, to=destination)


@tool(
    name="vfs_move_file",
    description="Déplace ou renomme un fichier dans l'espace virtuel.",
    parameters={
        "type": "object",
        "properties": {
            "source":      {"type": "string"},
            "destination": {"type": "string"},
        },
        "required": ["source", "destination"],
    },
)
@_catch
def vfs_move_file(source: str, destination: str) -> dict:
    vfs = get_vfs()
    vfs.move(source, destination)
    return _ok(moved=source, to=destination)


@tool(
    name="vfs_delete_file",
    description=(
        "Supprime un fichier ou dossier de l'espace virtuel. "
        "confirm DOIT être True pour confirmer la suppression."
    ),
    parameters={
        "type": "object",
        "properties": {
            "path":    {"type": "string"},
            "confirm": {"type": "boolean",
                        "description": "DOIT être True pour confirmer"},
        },
        "required": ["path", "confirm"],
    },
)
@_catch
def vfs_delete_file(path: str, confirm: bool) -> dict:
    if not confirm:
        return {"status": "cancelled", "message": "Suppression annulée (confirm=False)"}
    vfs = get_vfs()
    vfs.delete(path, confirm=True)
    return _ok(deleted=path)


@tool(
    name="vfs_create_directory",
    description="Crée un dossier (et ses parents si nécessaire) dans l'espace virtuel.",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string"},
        },
        "required": ["path"],
    },
)
@_catch
def vfs_create_directory(path: str) -> dict:
    vfs = get_vfs()
    vfs.mkdir(path, exist_ok=False)
    return _ok(created=path)


@tool(
    name="vfs_get_file_info",
    description="Retourne les métadonnées complètes d'un fichier ou dossier virtuel.",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string"},
        },
        "required": ["path"],
    },
)
@_catch
def vfs_get_file_info(path: str) -> dict:
    vfs = get_vfs()
    info = vfs.get_info(path)
    return _ok(**info)


@tool(
    name="vfs_count_lines",
    description="Compte les lignes dans les fichiers d'un dossier virtuel.",
    parameters={
        "type": "object",
        "properties": {
            "path":      {"type": "string"},
            "pattern":   {"type": "string", "default": "*.py"},
            "recursive": {"type": "boolean", "default": True},
        },
        "required": ["path"],
    },
)
@_catch
def vfs_count_lines(path: str, pattern: str = "*.py",
                    recursive: bool = True) -> dict:
    vfs = get_vfs()
    result = vfs.count_lines(path, pattern=pattern, recursive=recursive)
    return _ok(**result)


# ==============================================================================
# ARCHIVES (2 outils)
# ==============================================================================

@tool(
    name="vfs_compress_files",
    description=(
        "Crée une archive ZIP ou TAR à partir de fichiers de l'espace virtuel. "
        "format : 'zip' (défaut), 'tar', 'tar.gz'."
    ),
    parameters={
        "type": "object",
        "properties": {
            "files":  {"type": "array", "items": {"type": "string"},
                       "description": "Chemins virtuels des fichiers à archiver"},
            "output": {"type": "string",
                       "description": "Chemin virtuel de l'archive de sortie"},
            "format": {"type": "string", "default": "zip"},
        },
        "required": ["files", "output"],
    },
)
@_catch
def vfs_compress_files(files: List[str], output: str,
                        format: str = "zip") -> dict:
    vfs = get_vfs()
    result = vfs.compress(files, output, fmt=format)
    return _ok(**result)


@tool(
    name="vfs_extract_archive",
    description=(
        "Extrait une archive (ZIP, TAR, TAR.GZ…) dans l'espace virtuel, "
        "ou liste son contenu sans l'extraire (liste_seulement=true)."
    ),
    parameters={
        "type": "object",
        "properties": {
            "archive":        {"type": "string",
                               "description": "Chemin virtuel de l'archive"},
            "destination":    {"type": "string",
                               "description": "Dossier de destination (défaut : /tmp)"},
            "liste_seulement":{"type": "boolean", "default": False},
        },
        "required": ["archive"],
    },
)
@_catch
def vfs_extract_archive(archive: str, destination: Optional[str] = None,
                         liste_seulement: bool = False) -> dict:
    vfs = get_vfs()
    dest = destination or "/tmp"
    result = vfs.extract(archive, dest, list_only=liste_seulement)
    return _ok(**result)


# ==============================================================================
# COMPARAISON (1 outil)
# ==============================================================================

@tool(
    name="vfs_diff_files",
    description=(
        "Compare deux fichiers de l'espace virtuel et retourne leurs différences. "
        "mode : 'unified' (défaut), 'stats'. "
        "Idéal pour vérifier des modifications avant de les valider."
    ),
    parameters={
        "type": "object",
        "properties": {
            "source_a": {"type": "string"},
            "source_b": {"type": "string"},
            "contexte": {"type": "integer", "default": 3},
            "mode":     {"type": "string",  "default": "unified",
                         "enum": ["unified", "stats"]},
        },
        "required": ["source_a", "source_b"],
    },
)
@_catch
def vfs_diff_files(source_a: str, source_b: str,
                    contexte: int = 3, mode: str = "unified") -> dict:
    vfs = get_vfs()
    result = vfs.diff(source_a, source_b, context=contexte, mode=mode)
    return _ok(label_a=source_a, label_b=source_b, **result)


# ==============================================================================
# BATCH (2 outils)
# ==============================================================================

@tool(
    name="vfs_batch_rename",
    description=(
        "Renomme plusieurs fichiers dans un dossier virtuel en remplaçant "
        "une chaîne dans leur nom. preview=true pour prévisualiser."
    ),
    parameters={
        "type": "object",
        "properties": {
            "path":    {"type": "string"},
            "find":    {"type": "string"},
            "replace": {"type": "string"},
            "pattern": {"type": "string", "default": "*"},
            "preview": {"type": "boolean", "default": True},
        },
        "required": ["path", "find", "replace"],
    },
)
@_catch
def vfs_batch_rename(path: str, find: str, replace: str,
                      pattern: str = "*", preview: bool = True) -> dict:
    vfs = get_vfs()
    renames = vfs.batch_rename(path, find, replace,
                                pattern=pattern, preview=preview)
    return _ok(mode="preview" if preview else "applied",
               renamed=len(renames), results=renames[:20])


@tool(
    name="vfs_batch_delete",
    description="Supprime plusieurs fichiers de l'espace virtuel. confirm DOIT être True.",
    parameters={
        "type": "object",
        "properties": {
            "files":   {"type": "array", "items": {"type": "string"}},
            "confirm": {"type": "boolean"},
        },
        "required": ["files", "confirm"],
    },
)
@_catch
def vfs_batch_delete(files: List[str], confirm: bool) -> dict:
    if not confirm:
        return {"status": "cancelled", "message": "Suppression annulée"}
    vfs = get_vfs()
    deleted = []
    errors = []
    for path in files:
        try:
            vfs.delete(path, confirm=True)
            deleted.append(path)
        except VFSError as e:
            errors.append({"file": path, "error": str(e)})
    return _ok(deleted=len(deleted), errors=len(errors),
               deleted_files=deleted[:20], error_files=errors[:10])


# ==============================================================================
# ADMINISTRATION (1 outil)
# ==============================================================================

@tool(
    name="vfs_quota",
    description=(
        "Retourne les statistiques d'utilisation de l'espace virtuel : "
        "nombre de fichiers, taille totale, répartition par dossier."
    ),
    parameters={
        "type": "object",
        "properties": {},
        "required": [],
    },
)
@_catch
def vfs_quota() -> dict:
    import sqlite3 as _sqlite3
    from pathlib import Path as _Path
    vfs = get_vfs()

    with vfs._conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) as n, COALESCE(SUM(size_bytes), 0) as total "
            "FROM vfs_nodes WHERE user_id=? AND node_type='file'",
            (vfs.user_id,),
        ).fetchone()

        dirs_by_root = conn.execute(
            """
            SELECT
                COALESCE(
                    (SELECT name FROM vfs_nodes p WHERE p.id = n.parent_id
                     AND p.parent_id IS NULL),
                    n.name
                ) as top_dir,
                SUM(n.size_bytes) as sz
            FROM vfs_nodes n
            WHERE n.user_id=? AND n.node_type='file'
            GROUP BY top_dir
            ORDER BY sz DESC
            """,
            (vfs.user_id,),
        ).fetchall()

    db_size = _Path(vfs._db_path).stat().st_size

    from core.virtual_fs import _format_size
    return _ok(
        user_id=vfs.user_id,
        total_files=row["n"],
        total_size=_format_size(row["total"]),
        total_bytes=row["total"],
        db_size=_format_size(db_size),
        by_folder=[
            {"folder": f"/{r['top_dir']}", "size": _format_size(r["sz"])}
            for r in dirs_by_root
        ],
    )
