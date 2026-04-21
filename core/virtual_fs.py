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
core/virtual_fs.py — Système de fichiers virtuel par utilisateur (backend GarageHQ/S3)
========================================================================================

Architecture hybride :
  - SQLite (data/{user_id}/history.db) : arborescence, métadonnées, index
  - GarageHQ (API S3-compatible)       : contenu binaire des fichiers

Chaque fichier est identifié dans le bucket S3 par la clé :
    {user_id}/{node_uuid}

La table ``vfs_nodes`` ne stocke plus de BLOB — elle contient uniquement les
métadonnées (id, parent_id, name, node_type, mime_type, size_bytes, dates).

Avantages par rapport au stockage SQLite pur :
  - Pas de limite de taille de base (SQLite gère mal les gros BLOBs)
  - Lectures/écritures parallèles sans lock global de la DB
  - Passage à l'échelle horizontal (GarageHQ distribué ou tout backend S3-compatible)
  - Streaming natif pour les gros fichiers

Configuration (.env) :
    S3_ENDPOINT=http://localhost:3900   # URL complète avec schéma (port 3900 = API S3 Garage)
    S3_ACCESS_KEY=<clé_garage>
    S3_SECRET_KEY=<secret_garage>
    S3_BUCKET=promethee-vfs
    S3_REGION=garage                   # valeur arbitraire, ignorée par GarageHQ

Usage (identique à l'ancienne API) :
    from core.virtual_fs import get_vfs
    vfs = get_vfs()
    content = vfs.read_text("/docs/rapport.txt")
    vfs.write_text("/docs/rapport.txt", nouveau_contenu)
    entries = vfs.listdir("/docs")
"""

import sqlite3
import uuid
import difflib
import fnmatch
import logging
import zipfile
import tarfile
import io
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Optional

import boto3
from botocore.exceptions import ClientError
_MAX_WRITE_BYTES = 50 * 1024 * 1024  # 50 MB
from .request_context import get_user_config

log = logging.getLogger(__name__)

_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
_MAX_WRITE_BYTES = 50 * 1024 * 1024  # 50 MB


# ── Schéma SQL (métadonnées uniquement — plus de BLOB) ────────────────────────

_SCHEMA = """
CREATE TABLE IF NOT EXISTS vfs_nodes (
    id          TEXT    PRIMARY KEY,
    user_id     TEXT    NOT NULL,
    parent_id   TEXT,
    name        TEXT    NOT NULL,
    node_type   TEXT    NOT NULL CHECK(node_type IN ('file', 'dir')),
    mime_type   TEXT    DEFAULT 'text/plain',
    size_bytes  INTEGER DEFAULT 0,
    created_at  TEXT    NOT NULL,
    updated_at  TEXT    NOT NULL,
    UNIQUE(user_id, parent_id, name),
    FOREIGN KEY(parent_id) REFERENCES vfs_nodes(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_vfs_user_parent
    ON vfs_nodes(user_id, parent_id);
"""

_DEFAULT_DIRS = ["/", "/uploads", "/documents", "/exports", "/tmp"]


# ── Exceptions ────────────────────────────────────────────────────────────────

class VFSError(Exception):
    """Erreur générique du système de fichiers virtuel."""

class VFSNotFound(VFSError):
    """Chemin introuvable dans le VFS."""

class VFSExists(VFSError):
    """Le nœud existe déjà."""

class VFSPermission(VFSError):
    """Opération non autorisée."""

class VFSTooBig(VFSError):
    """Contenu dépasse la limite autorisée."""


# ── Helpers ───────────────────────────────────────────────────────────────────

def _format_size(size_bytes: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} TB"


def _now() -> str:
    return datetime.now().isoformat()


def _normalize_path(path: str) -> str:
    p = PurePosixPath("/" + path.lstrip("/"))
    normalized = str(p)
    return normalized if normalized else "/"


def _path_parts(path: str) -> list[str]:
    p = _normalize_path(path)
    if p == "/":
        return []
    return [s for s in p.split("/") if s]


# ── Client S3/GarageHQ (singleton) ───────────────────────────────────────────

_s3_client = None
_s3_bucket: str = ""


def _get_s3():
    """Retourne le client boto3 S3 et le nom du bucket (singleton par processus)."""
    global _s3_client, _s3_bucket
    if _s3_client is None:
        import os
        endpoint   = os.getenv("GARAGE_ENDPOINT",   "http://localhost:3900")
        access_key = os.getenv("GARAGE_ACCESS_KEY", "")
        secret_key = os.getenv("GARAGE_SECRET_KEY", "")
        bucket     = os.getenv("GARAGE_BUCKET",     "promethee-vfs")
        region     = os.getenv("GARAGE_REGION",     "garage")

        client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
        )
        # Crée le bucket s'il n'existe pas
        try:
            client.head_bucket(Bucket=bucket)
        except ClientError as e:
            code = e.response["Error"]["Code"]
            if code in ("404", "NoSuchBucket"):
                client.create_bucket(Bucket=bucket)
                log.info("[VFS/S3] Bucket créé : %s", bucket)
            else:
                raise

        _s3_client = client
        _s3_bucket = bucket

    return _s3_client, _s3_bucket


def _s3_key(user_id: str, node_id: str) -> str:
    return f"{user_id}/{node_id}"


# ── Classe principale ─────────────────────────────────────────────────────────

class VirtualFS:
    """
    Système de fichiers virtuel — arborescence dans SQLite, contenu dans GarageHQ (S3).

    L'API publique est identique à l'ancienne version SQLite-only.
    """

    def __init__(self, user_id: str, db_path: Optional[str] = None):
        if not user_id:
            raise ValueError("user_id est requis pour VirtualFS")
        self.user_id = user_id
        user_dir = _DATA_DIR / user_id
        user_dir.mkdir(parents=True, exist_ok=True)
        self._db_path = db_path or str(user_dir / "history.db")
        self._ensure_schema()
        self._ensure_default_dirs()
        # Initialise le client S3 et crée le bucket si nécessaire.
        # Sans cet appel, le bucket n'est créé qu'au premier write_bytes(),
        # ce qui laisse le stockage vide après un simple démarrage.
        _get_s3()

    # ── SQLite ────────────────────────────────────────────────────────────────

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

    def _ensure_schema(self) -> None:
        with self._conn() as conn:
            conn.executescript(_SCHEMA)

    def _ensure_default_dirs(self) -> None:
        for path in _DEFAULT_DIRS:
            try:
                self.mkdir(path, exist_ok=True)
            except VFSError:
                pass

    # ── S3 / GarageHQ ─────────────────────────────────────────────────────────

    def _s3_put(self, node_id: str, data: bytes, mime_type: str) -> None:
        client, bucket = _get_s3()
        client.put_object(
            Bucket=bucket,
            Key=_s3_key(self.user_id, node_id),
            Body=data,
            ContentType=mime_type,
        )

    def _s3_get(self, node_id: str) -> bytes:
        client, bucket = _get_s3()
        key = _s3_key(self.user_id, node_id)
        try:
            response = client.get_object(Bucket=bucket, Key=key)
            return response["Body"].read()
        except ClientError as e:
            raise VFSError(f"Erreur S3 ({key}): {e}") from e

    def _s3_delete_many(self, node_ids: list[str]) -> None:
        if not node_ids:
            return
        client, bucket = _get_s3()
        objects = [{"Key": _s3_key(self.user_id, nid)} for nid in node_ids]
        resp = client.delete_objects(
            Bucket=bucket,
            Delete={"Objects": objects, "Quiet": True},
        )
        for err in resp.get("Errors", []):
            log.warning("[VFS/S3] Erreur suppression : %s", err)

    # ── Résolution de chemin ──────────────────────────────────────────────────

    def _node_id_of(self, path: str) -> Optional[str]:
        parts = _path_parts(path)
        if not parts:
            return None
        with self._conn() as conn:
            parent_id: Optional[str] = None
            node_id: Optional[str] = None
            for part in parts:
                row = conn.execute(
                    "SELECT id FROM vfs_nodes "
                    "WHERE user_id=? AND parent_id IS ? AND name=?",
                    (self.user_id, parent_id, part),
                ).fetchone()
                if not row:
                    return None
                node_id = row["id"]
                parent_id = node_id
            return node_id

    def _get_node(self, path: str) -> Optional[sqlite3.Row]:
        node_id = self._node_id_of(path)
        if node_id is None:
            return None
        with self._conn() as conn:
            return conn.execute(
                "SELECT * FROM vfs_nodes WHERE id=?", (node_id,)
            ).fetchone()

    def _require_node(self, path: str) -> sqlite3.Row:
        node = self._get_node(path)
        if node is None:
            raise VFSNotFound(f"Chemin introuvable : {path}")
        return node

    def _parent_id_and_name(self, path: str) -> tuple[Optional[str], str]:
        parts = _path_parts(path)
        if not parts:
            raise VFSError("Impossible de décomposer la racine '/'")
        name = parts[-1]
        parent_parts = parts[:-1]
        parent_id: Optional[str] = None
        with self._conn() as conn:
            for part in parent_parts:
                row = conn.execute(
                    "SELECT id, node_type FROM vfs_nodes "
                    "WHERE user_id=? AND parent_id IS ? AND name=?",
                    (self.user_id, parent_id, part),
                ).fetchone()
                if row is None:
                    raise VFSNotFound(
                        f"Dossier parent manquant : /{'/'.join(parent_parts[:parent_parts.index(part)+1])}"
                    )
                if row["node_type"] != "dir":
                    raise VFSError(f"'{part}' n'est pas un dossier")
                parent_id = row["id"]
        return parent_id, name

    # ── Lecture ───────────────────────────────────────────────────────────────

    def read_bytes(self, path: str) -> bytes:
        """Lit un fichier — contenu récupéré depuis Garage."""
        node = self._require_node(path)
        if node["node_type"] != "file":
            raise VFSError(f"'{path}' est un dossier, pas un fichier")
        return self._s3_get(node["id"])

    def read_text(self, path: str, encoding: str = "utf-8") -> str:
        return self.read_bytes(path).decode(encoding, errors="replace")

    def head(self, path: str, lines: int = 10) -> tuple[str, int]:
        content = self.read_text(path)
        all_lines = content.split("\n")
        return "\n".join(all_lines[:lines]), len(all_lines)

    def tail(self, path: str, lines: int = 10) -> tuple[str, int]:
        content = self.read_text(path)
        all_lines = content.split("\n")
        return "\n".join(all_lines[-lines:]), len(all_lines)

    # ── Écriture ──────────────────────────────────────────────────────────────

    def write_bytes(self, path: str, content: bytes,
                    mime_type: str = "application/octet-stream") -> None:
        """Écrit des bytes : métadonnées → SQLite, contenu → Garage."""
        if len(content) > _MAX_WRITE_BYTES:
            raise VFSTooBig(
                f"Fichier trop grand : {_format_size(len(content))} > "
                f"{_format_size(_MAX_WRITE_BYTES)}"
            )

        # ── Vérification quota utilisateur ────────────────────────────────
        try:
            from . import user_manager as _um
            quota_limit = _um.get_vfs_quota(self.user_id)
            with self._conn() as _c:
                # Taille actuelle totale des fichiers de l'utilisateur
                _row = _c.execute(
                    "SELECT COALESCE(SUM(size_bytes),0) as total FROM vfs_nodes "
                    "WHERE user_id=? AND node_type='file'",
                    (self.user_id,),
                ).fetchone()
                current_total = _row["total"]
                # Si le fichier existe déjà, on soustrait son ancienne taille
                _norm = str(path)
                _existing_row = _c.execute(
                    "SELECT size_bytes FROM vfs_nodes "
                    "WHERE user_id=? AND node_type='file' AND "
                    "id=(SELECT id FROM vfs_nodes WHERE user_id=? AND "
                    "    parent_id IS (SELECT id FROM vfs_nodes WHERE user_id=? AND name=? AND parent_id IS NULL) "
                    "    LIMIT 1)",
                    (self.user_id, self.user_id, self.user_id, _norm),
                ).fetchone()
                # Calcul simplifié : récupération de la taille du nœud existant si applicable
                existing_size = 0
                try:
                    parent_id_check, name_check = self._parent_id_and_name(path)
                    _ex = _c.execute(
                        "SELECT size_bytes FROM vfs_nodes "
                        "WHERE user_id=? AND parent_id IS ? AND name=? AND node_type='file'",
                        (self.user_id, parent_id_check, name_check),
                    ).fetchone()
                    if _ex:
                        existing_size = _ex["size_bytes"] or 0
                except Exception:
                    existing_size = 0
            projected = current_total - existing_size + len(content)
            if projected > quota_limit:
                raise VFSTooBig(
                    f"Quota VFS dépassé : {_format_size(projected)} > "
                    f"{_format_size(quota_limit)} alloués. "
                    f"Libérez de l'espace ou contactez un administrateur."
                )
        except VFSTooBig:
            raise
        except Exception as _qe:
            log.debug("[VFS] Impossible de vérifier le quota : %s", _qe)

        parent_id, name = self._parent_id_and_name(path)
        now = _now()

        with self._conn() as conn:
            existing = conn.execute(
                "SELECT id FROM vfs_nodes "
                "WHERE user_id=? AND parent_id IS ? AND name=?",
                (self.user_id, parent_id, name),
            ).fetchone()

            if existing:
                node_id = existing["id"]
                conn.execute(
                    "UPDATE vfs_nodes SET mime_type=?, size_bytes=?, "
                    "updated_at=? WHERE id=?",
                    (mime_type, len(content), now, node_id),
                )
            else:
                node_id = str(uuid.uuid4())
                conn.execute(
                    "INSERT INTO vfs_nodes "
                    "(id, user_id, parent_id, name, node_type, "
                    " mime_type, size_bytes, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, 'file', ?, ?, ?, ?)",
                    (node_id, self.user_id, parent_id, name,
                     mime_type, len(content), now, now),
                )

        # Upload Garage hors transaction SQLite
        self._s3_put(node_id, content, mime_type)

    def write_text(self, path: str, content: str,
                   encoding: str = "utf-8", mode: str = "w") -> None:
        if mode == "x" and self.exists(path):
            raise VFSExists(f"Le fichier existe déjà : {path}")
        if mode == "a" and self.exists(path):
            existing = self.read_bytes(path).decode(encoding, errors="replace")
            content = existing + content
        self.write_bytes(path, content.encode(encoding), mime_type="text/plain")

    # ── Navigation ────────────────────────────────────────────────────────────

    def exists(self, path: str) -> bool:
        if _normalize_path(path) == "/":
            return True
        return self._node_id_of(path) is not None

    def is_file(self, path: str) -> bool:
        node = self._get_node(path)
        return node is not None and node["node_type"] == "file"

    def is_dir(self, path: str) -> bool:
        if _normalize_path(path) == "/":
            return True
        node = self._get_node(path)
        return node is not None and node["node_type"] == "dir"

    def listdir(self, path: str = "/") -> list[dict]:
        if not self.is_dir(path):
            raise VFSNotFound(f"Dossier introuvable : {path}")
        parent_id = self._node_id_of(path)
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM vfs_nodes "
                "WHERE user_id=? AND parent_id IS ? "
                "ORDER BY node_type DESC, name",
                (self.user_id, parent_id),
            ).fetchall()
        base = _normalize_path(path)
        return [
            {
                "name":       row["name"],
                "path":       base.rstrip("/") + "/" + row["name"],
                "type":       row["node_type"],
                "size_bytes": row["size_bytes"],
                "size":       _format_size(row["size_bytes"]),
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "mime_type":  row["mime_type"],
            }
            for row in rows
        ]

    def tree(self, path: str = "/", max_depth: int = 3,
             show_hidden: bool = False, _depth: int = 0) -> str:
        lines = []
        if _depth == 0:
            lines.append(path)
        if _depth >= max_depth:
            return "\n".join(lines)
        try:
            entries = self.listdir(path)
        except VFSNotFound:
            return "\n".join(lines)
        for i, entry in enumerate(entries):
            if not show_hidden and entry["name"].startswith("."):
                continue
            is_last = i == len(entries) - 1
            prefix = "└── " if is_last else "├── "
            icon = "📁 " if entry["type"] == "dir" else ""
            lines.append(f"{'    ' * _depth}{prefix}{icon}{entry['name']}")
            if entry["type"] == "dir" and _depth < max_depth:
                subtree = self.tree(entry["path"], max_depth, show_hidden, _depth + 1)
                if subtree:
                    lines.append(subtree)
        return "\n".join(lines)

    def search(self, path: str = "/", name_pattern: Optional[str] = None,
               content: Optional[str] = None,
               max_results: int = 50) -> list[dict]:
        results = []

        def _walk(current_path: str):
            if len(results) >= max_results:
                return
            try:
                entries = self.listdir(current_path)
            except VFSNotFound:
                return
            for entry in entries:
                if len(results) >= max_results:
                    break
                if entry["type"] == "dir":
                    _walk(entry["path"])
                    continue
                if name_pattern and not fnmatch.fnmatch(entry["name"], name_pattern):
                    continue
                if content:
                    try:
                        text = self.read_text(entry["path"])
                        if content not in text:
                            continue
                    except Exception:
                        continue
                results.append(entry)

        _walk(path)
        return results

    # ── Gestion ───────────────────────────────────────────────────────────────

    def mkdir(self, path: str, exist_ok: bool = False) -> None:
        norm = _normalize_path(path)
        if norm == "/":
            return
        parts = _path_parts(norm)
        with self._conn() as conn:
            parent_id: Optional[str] = None
            for i, part in enumerate(parts):
                row = conn.execute(
                    "SELECT id, node_type FROM vfs_nodes "
                    "WHERE user_id=? AND parent_id IS ? AND name=?",
                    (self.user_id, parent_id, part),
                ).fetchone()
                if row:
                    if row["node_type"] != "dir":
                        raise VFSError(f"'{part}' existe déjà en tant que fichier")
                    parent_id = row["id"]
                    if i == len(parts) - 1 and not exist_ok:
                        raise VFSExists(f"Le dossier existe déjà : {path}")
                else:
                    now = _now()
                    node_id = str(uuid.uuid4())
                    conn.execute(
                        "INSERT INTO vfs_nodes "
                        "(id, user_id, parent_id, name, node_type, "
                        " size_bytes, created_at, updated_at) "
                        "VALUES (?, ?, ?, ?, 'dir', 0, ?, ?)",
                        (node_id, self.user_id, parent_id, part, now, now),
                    )
                    parent_id = node_id

    def copy(self, src: str, dst: str, overwrite: bool = False) -> None:
        if not self.is_file(src):
            raise VFSNotFound(f"Fichier source introuvable : {src}")
        if self.exists(dst) and not overwrite:
            raise VFSExists(f"Destination existe (utilisez overwrite=True) : {dst}")
        content = self.read_bytes(src)
        src_node = self._require_node(src)
        self.write_bytes(dst, content, mime_type=src_node["mime_type"])

    def move(self, src: str, dst: str) -> None:
        """Déplace ou renomme — seules les métadonnées SQLite bougent."""
        if not self.exists(src):
            raise VFSNotFound(f"Source introuvable : {src}")
        parent_id, new_name = self._parent_id_and_name(dst)
        node_id = self._node_id_of(src)
        with self._conn() as conn:
            conn.execute(
                "UPDATE vfs_nodes SET parent_id=?, name=?, updated_at=? WHERE id=?",
                (parent_id, new_name, _now(), node_id),
            )
        # La clé Garage {user_id}/{node_id} reste inchangée — pas de copie objet.

    def delete(self, path: str, confirm: bool = True) -> None:
        """Supprime un nœud et purge le contenu de ses fichiers dans Garage."""
        if not confirm:
            raise VFSPermission("Suppression annulée (confirm=False)")
        norm = _normalize_path(path)
        protected = {"/", "/uploads", "/documents", "/exports"}
        if norm in protected:
            raise VFSPermission(f"Dossier système protégé : {norm}")
        node_id = self._node_id_of(norm)
        if node_id is None:
            raise VFSNotFound(f"Chemin introuvable : {path}")

        file_ids = self._collect_file_ids(node_id)

        with self._conn() as conn:
            conn.execute("DELETE FROM vfs_nodes WHERE id=?", (node_id,))

        self._s3_delete_many(file_ids)

    def _collect_file_ids(self, root_node_id: str) -> list[str]:
        """Retourne récursivement tous les node_ids de type 'file' sous root_node_id."""
        collected: list[str] = []
        with self._conn() as conn:
            def _recurse(nid: str):
                row = conn.execute(
                    "SELECT id, node_type FROM vfs_nodes WHERE id=?", (nid,)
                ).fetchone()
                if not row:
                    return
                if row["node_type"] == "file":
                    collected.append(nid)
                else:
                    children = conn.execute(
                        "SELECT id FROM vfs_nodes WHERE parent_id=?", (nid,)
                    ).fetchall()
                    for child in children:
                        _recurse(child["id"])
            _recurse(root_node_id)
        return collected

    def get_info(self, path: str) -> dict:
        norm = _normalize_path(path)
        if norm == "/":
            return {
                "path": "/", "name": "/", "type": "dir",
                "size_bytes": 0, "size": "0 B",
                "created_at": None, "updated_at": None,
                "mime_type": None,
            }
        node = self._require_node(path)
        return {
            "path":       norm,
            "name":       node["name"],
            "type":       node["node_type"],
            "size_bytes": node["size_bytes"],
            "size":       _format_size(node["size_bytes"]),
            "created_at": node["created_at"],
            "updated_at": node["updated_at"],
            "mime_type":  node["mime_type"],
        }

    def quota(self) -> dict:
        """Statistiques d'utilisation depuis SQLite (pas de requête Garage)."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT COUNT(*) as n, COALESCE(SUM(size_bytes),0) as total "
                "FROM vfs_nodes WHERE user_id=? AND node_type='file'",
                (self.user_id,),
            ).fetchone()
        used_bytes = row["total"]
        # Récupération du quota individuel depuis user_manager
        try:
            from . import user_manager as _um
            limit_bytes = _um.get_vfs_quota(self.user_id)
        except Exception:
            limit_bytes = 500 * 1024 * 1024  # fallback 500 Mo
        pct = round((used_bytes / limit_bytes * 100), 1) if limit_bytes > 0 else 0.0
        return {
            "user_id":           self.user_id,
            "total_files":       row["n"],
            "total_size":        _format_size(used_bytes),
            "total_bytes":       used_bytes,
            "quota_limit_bytes": limit_bytes,
            "quota_limit":       _format_size(limit_bytes),
            "quota_used_pct":    pct,
            "quota_exceeded":    used_bytes > limit_bytes,
            "backend":           "garage",
        }

    # ── Opérations avancées ───────────────────────────────────────────────────

    def find_and_replace(self, path: str, find: str, replace: str,
                         pattern: str = "*", preview: bool = True) -> list[dict]:
        results = []
        entries = self.search(path, name_pattern=pattern, content=find)
        for entry in entries:
            try:
                text = self.read_text(entry["path"])
                count = text.count(find)
                if count > 0:
                    if not preview:
                        self.write_text(entry["path"], text.replace(find, replace))
                    results.append({"path": entry["path"], "occurrences": count})
            except Exception:
                pass
        return results

    def diff(self, path_a: str, path_b: str,
             context: int = 3, mode: str = "unified") -> dict:
        content_a = self.read_text(path_a)
        content_b = self.read_text(path_b)
        lines_a = content_a.splitlines(keepends=True)
        lines_b = content_b.splitlines(keepends=True)
        matcher = difflib.SequenceMatcher(None, lines_a, lines_b, autojunk=False)
        added = deleted = changed = 0
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == "insert":
                added += j2 - j1
            elif tag == "delete":
                deleted += i2 - i1
            elif tag == "replace":
                changed += max(i2 - i1, j2 - j1)
        stats = {
            "lines_a": len(lines_a), "lines_b": len(lines_b),
            "added": added, "deleted": deleted, "changed": changed,
            "identical": added == 0 and deleted == 0 and changed == 0,
        }
        if stats["identical"] or mode == "stats":
            return {"stats": stats, "diff": None}
        diff_text = "".join(difflib.unified_diff(
            lines_a, lines_b, fromfile=path_a, tofile=path_b, n=context,
        ))
        MAX = 20_000
        truncated = len(diff_text) > MAX
        return {
            "stats": stats,
            "diff": diff_text[:MAX] + ("\n... [tronqué]" if truncated else ""),
            "truncated": truncated,
        }

    def compress(self, paths: list[str], output_path: str, fmt: str = "zip") -> dict:
        buf = io.BytesIO()
        added = 0
        if fmt == "zip":
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                for p in paths:
                    if self.is_file(p):
                        zf.writestr(PurePosixPath(p).name, self.read_bytes(p))
                        added += 1
            mime = "application/zip"
        elif fmt in ("tar", "tar.gz"):
            mode = "w:gz" if fmt == "tar.gz" else "w"
            with tarfile.open(fileobj=buf, mode=mode) as tf:
                for p in paths:
                    if self.is_file(p):
                        data = self.read_bytes(p)
                        info = tarfile.TarInfo(name=PurePosixPath(p).name)
                        info.size = len(data)
                        tf.addfile(info, io.BytesIO(data))
                        added += 1
            mime = "application/x-tar"
        else:
            raise VFSError(f"Format non supporté : {fmt}")
        raw = buf.getvalue()
        self.write_bytes(output_path, raw, mime_type=mime)
        return {"archive": output_path, "files_added": added,
                "size": _format_size(len(raw))}

    def extract(self, archive_path: str, dest_path: str,
                list_only: bool = False) -> dict:
        raw = self.read_bytes(archive_path)
        name = PurePosixPath(archive_path).name.lower()
        entries = []
        if name.endswith(".zip"):
            with zipfile.ZipFile(io.BytesIO(raw)) as zf:
                for info in zf.infolist():
                    entries.append({"name": info.filename,
                                    "size": _format_size(info.file_size),
                                    "is_dir": info.filename.endswith("/")})
                if not list_only:
                    self.mkdir(dest_path, exist_ok=True)
                    for info in zf.infolist():
                        if not info.filename.endswith("/"):
                            dest = dest_path.rstrip("/") + "/" + info.filename
                            self.mkdir(str(PurePosixPath(dest).parent), exist_ok=True)
                            self.write_bytes(dest, zf.read(info.filename))
        elif any(name.endswith(e) for e in
                 (".tar.gz", ".tgz", ".tar.bz2", ".tar.xz", ".tar")):
            with tarfile.open(fileobj=io.BytesIO(raw)) as tf:
                for member in tf.getmembers():
                    entries.append({"name": member.name,
                                    "size": _format_size(member.size),
                                    "is_dir": member.isdir()})
                if not list_only:
                    self.mkdir(dest_path, exist_ok=True)
                    for member in tf.getmembers():
                        if member.isfile():
                            f = tf.extractfile(member)
                            if f:
                                dest = dest_path.rstrip("/") + "/" + member.name
                                self.mkdir(str(PurePosixPath(dest).parent), exist_ok=True)
                                self.write_bytes(dest, f.read())
        else:
            raise VFSError(f"Format d'archive non reconnu : {archive_path}")
        return {
            "archive": archive_path,
            "entries": entries[:100],
            "total": len(entries),
            "extracted_to": None if list_only else dest_path,
        }

    def batch_rename(self, path: str, find: str, replace: str,
                     pattern: str = "*", preview: bool = True) -> list[dict]:
        if not self.is_dir(path):
            raise VFSNotFound(f"Dossier introuvable : {path}")
        entries = self.listdir(path)
        renames = []
        for entry in entries:
            if entry["type"] != "file":
                continue
            if not fnmatch.fnmatch(entry["name"], pattern):
                continue
            if find not in entry["name"]:
                continue
            new_name = entry["name"].replace(find, replace)
            new_path = path.rstrip("/") + "/" + new_name
            if not preview:
                self.move(entry["path"], new_path)
            renames.append({"from": entry["name"], "to": new_name,
                            "done": not preview})
        return renames

    def count_lines(self, path: str, pattern: str = "*.py",
                    recursive: bool = True) -> dict:
        entries = self.search(path, name_pattern=pattern) if recursive \
            else [e for e in self.listdir(path)
                  if e["type"] == "file"
                  and fnmatch.fnmatch(e["name"], pattern)]
        total = 0
        files = []
        for entry in entries:
            try:
                text = self.read_text(entry["path"])
                n = len(text.split("\n"))
                total += n
                files.append({"file": entry["name"], "lines": n})
            except Exception:
                pass
        return {
            "total_lines": total,
            "files": len(files),
            "details": sorted(files, key=lambda x: x["lines"], reverse=True)[:10],
        }


# ── Accesseur de contexte ─────────────────────────────────────────────────────

def get_vfs() -> VirtualFS:
    """
    Retourne un VirtualFS pour l'utilisateur de la requête courante.

    Usage dans les tools :
        from core.virtual_fs import get_vfs
        vfs = get_vfs()
    """
    ucfg = get_user_config()
    if ucfg is None:
        raise VFSError(
            "Aucun contexte utilisateur disponible. "
            "Assurez-vous que set_user_config() a été appelé dans ws_chat.py."
        )
    return VirtualFS(ucfg.user_id)
