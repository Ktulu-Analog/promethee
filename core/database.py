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
database.py — Historique persistant des conversations (SQLite)

v3 — Chiffrement applicatif optionnel AES-256-GCM
===================================================

Activation : DB_ENCRYPTION=ON dans .env + passphrase fournie via
HistoryDB.set_passphrase() avant tout accès aux données.

Colonnes chiffrées
------------------
  conversations : title, system_prompt
  messages      : content, metadata

Colonnes NON chiffrées (intentionnel)
--------------------------------------
  conversations : id, created_at, updated_at, model
  messages      : id, conversation_id, role, created_at

  Les index FTS5 (messages_fts, conversations_title_fts) stockent le texte
  EN CLAIR pour conserver la recherche plein-texte. Si ce compromis est
  inacceptable, désactivez la recherche via DB_ENCRYPTION_SEARCH=OFF dans
  .env : dans ce cas les index FTS5 ne sont pas peuplés et
  search_conversations() retourne toujours une liste vide.

Migration transparente
----------------------
  Les valeurs en clair (base existante avant activation du chiffrement) sont
  retournées telles quelles par crypto.decrypt() — aucune migration forcée.
  Pour chiffrer une base existante, utilisez HistoryDB.migrate_to_encrypted().

Vérification de la passphrase
------------------------------
  Un sentinel chiffré est stocké dans la table kv_store à la première
  initialisation avec chiffrement. A chaque ouverture suivante, la passphrase
  est vérifiée contre ce sentinel avant tout accès.

Historique
----------
  v2 : PRAGMA foreign_keys = ON + FTS5
  v3 : chiffrement applicatif AES-256-GCM
  v4 : dossiers de conversations (table folders + colonne folder_id)
"""

import sqlite3
import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional
from .config import Config
from . import crypto

log = logging.getLogger(__name__)


class WrongPassphraseError(Exception):
    """La passphrase fournie ne correspond pas a la base chiffree."""


class EncryptionRequiredError(Exception):
    """Le chiffrement est active mais aucune passphrase n'a ete fournie."""


class HistoryDB:
    """
    Acces a la base SQLite de l'historique des conversations.

    Parametres
    ----------
    db_path : str | None
        Chemin vers le fichier SQLite. Defaut : Config.HISTORY_DB.
    passphrase : str | None
        Passphrase de chiffrement. Peut aussi etre definie plus tard via
        set_passphrase(). Ignoree si DB_ENCRYPTION=OFF.
    """

    def __init__(self, db_path: str = None, passphrase: str = None):
        self.db_path     = db_path or Config.HISTORY_DB
        self._passphrase = passphrase or ""
        self._encrypt    = Config.DB_ENCRYPTION
        self._search_idx = Config.DB_ENCRYPTION_SEARCH
        self._init_db()

    # -- Passphrase --------------------------------------------------------

    def set_passphrase(self, passphrase: str) -> None:
        """
        Definit (ou change) la passphrase de chiffrement.

        Doit etre appele avant tout acces aux donnees si DB_ENCRYPTION=ON.
        Valide la passphrase contre le sentinel stocke en base.

        Raises
        ------
        WrongPassphraseError : si la passphrase ne correspond pas.
        """
        if not self._encrypt:
            return
        self._passphrase = passphrase
        self._verify_or_create_sentinel()

    def _verify_or_create_sentinel(self) -> None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT value FROM kv_store WHERE key = 'sentinel'"
            ).fetchone()

        if row is None:
            sentinel = crypto.create_sentinel(self._passphrase)
            with self._conn() as conn:
                conn.execute(
                    "INSERT INTO kv_store(key, value) VALUES ('sentinel', ?)",
                    (sentinel,)
                )
            log.info("[DB] Sentinel cree — chiffrement initialise.")
        else:
            if not crypto.verify_passphrase(self._passphrase, row["value"]):
                self._passphrase = ""
                raise WrongPassphraseError(
                    "Passphrase incorrecte. La base de donnees ne peut pas etre ouverte."
                )
            log.info("[DB] Passphrase verifiee avec succes.")

    def is_encrypted(self) -> bool:
        """Retourne True si le chiffrement est actif pour cette instance."""
        return self._encrypt and bool(self._passphrase)

    # -- Chiffrement / Dechiffrement ---------------------------------------

    def _enc(self, value: Optional[str]) -> Optional[str]:
        if not self._encrypt or not self._passphrase or value is None:
            return value
        return crypto.encrypt(value, self._passphrase)

    def _dec(self, value: Optional[str]) -> Optional[str]:
        if not self._encrypt or not self._passphrase or value is None:
            return value
        try:
            return crypto.decrypt(value, self._passphrase)
        except crypto.CryptoError as e:
            log.error("[DB] Erreur dechiffrement : %s", e)
            return value

    def _dec_conv(self, row: dict) -> dict:
        if not self._encrypt or not self._passphrase:
            return row
        return {
            **row,
            "title":         self._dec(row.get("title")),
            "system_prompt": self._dec(row.get("system_prompt")),
        }

    def _dec_msg(self, row: dict) -> dict:
        if not self._encrypt or not self._passphrase:
            return row
        return {
            **row,
            "content":  self._dec(row.get("content")),
            "metadata": self._dec(row.get("metadata")),
        }

    # -- Connexion ---------------------------------------------------------

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    # -- Initialisation ----------------------------------------------------

    def _init_db(self):
        with self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL DEFAULT 'Nouvelle conversation',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    model TEXT,
                    system_prompt TEXT
                );

                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    metadata TEXT,
                    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_messages_conv
                    ON messages(conversation_id, created_at);

                CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
                    conversation_id UNINDEXED,
                    body,
                    tokenize='unicode61'
                );

                CREATE VIRTUAL TABLE IF NOT EXISTS conversations_title_fts USING fts5(
                    conversation_id UNINDEXED,
                    title,
                    tokenize='unicode61'
                );

                CREATE TABLE IF NOT EXISTS kv_store (
                    key   TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS folders (
                    id         TEXT PRIMARY KEY,
                    name       TEXT NOT NULL,
                    parent_id  TEXT REFERENCES folders(id) ON DELETE SET NULL,
                    position   INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_folders_parent
                    ON folders(parent_id);
            """)

            # Migration v4 : ajouter folder_id a conversations si absente
            cols = {r[1] for r in conn.execute("PRAGMA table_info(conversations)").fetchall()}
            if "folder_id" not in cols:
                conn.execute(
                    "ALTER TABLE conversations ADD COLUMN folder_id TEXT "
                    "REFERENCES folders(id) ON DELETE SET NULL"
                )
                log.info("[DB] Migration v4 : colonne folder_id ajoutee.")

            # Migration v5 : ajouter starred a conversations si absente
            cols = {r[1] for r in conn.execute("PRAGMA table_info(conversations)").fetchall()}
            if "starred" not in cols:
                conn.execute(
                    "ALTER TABLE conversations ADD COLUMN starred INTEGER NOT NULL DEFAULT 0"
                )
                log.info("[DB] Migration v5 : colonne starred ajoutee.")

    # -- Conversations -----------------------------------------------------

    def create_conversation(self, title: str = "Nouvelle conversation",
                            system_prompt: str = "", model: str = None,
                            folder_id: str = None) -> str:
        cid = str(uuid.uuid4())
        now = datetime.now().isoformat()
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO conversations (id, title, created_at, updated_at, model, system_prompt, folder_id)"
                " VALUES (?,?,?,?,?,?,?)",
                (cid, self._enc(title), now, now,
                 model or Config.active_model(),
                 self._enc(system_prompt),
                 folder_id)
            )
            if self._search_idx:
                conn.execute(
                    "INSERT INTO conversations_title_fts(conversation_id, title) VALUES (?,?)",
                    (cid, title)
                )
        return cid

    def get_conversations(self) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM conversations ORDER BY updated_at DESC"
            ).fetchall()
        return [self._dec_conv(dict(r)) for r in rows]

    def get_conversation(self, cid: str) -> Optional[dict]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM conversations WHERE id=?", (cid,)
            ).fetchone()
        return self._dec_conv(dict(row)) if row else None

    def update_conversation_title(self, cid: str, title: str):
        truncated = title[:80]
        with self._conn() as conn:
            conn.execute(
                "UPDATE conversations SET title=?, updated_at=? WHERE id=?",
                (self._enc(truncated), datetime.now().isoformat(), cid)
            )
            if self._search_idx:
                conn.execute(
                    "DELETE FROM conversations_title_fts WHERE conversation_id=?", (cid,)
                )
                conn.execute(
                    "INSERT INTO conversations_title_fts(conversation_id, title) VALUES (?,?)",
                    (cid, truncated)
                )

    def update_conversation_touched(self, cid: str):
        with self._conn() as conn:
            conn.execute(
                "UPDATE conversations SET updated_at=? WHERE id=?",
                (datetime.now().isoformat(), cid)
            )

    def star_conversation(self, cid: str, starred: bool):
        with self._conn() as conn:
            conn.execute(
                "UPDATE conversations SET starred=? WHERE id=?",
                (1 if starred else 0, cid)
            )

    def delete_conversation(self, cid: str):
        with self._conn() as conn:
            conn.execute("DELETE FROM messages_fts WHERE conversation_id=?", (cid,))
            conn.execute("DELETE FROM conversations_title_fts WHERE conversation_id=?", (cid,))
            conn.execute("DELETE FROM conversations WHERE id=?", (cid,))

    # -- Messages ----------------------------------------------------------

    def add_message(self, conversation_id: str, role: str, content: str,
                    metadata: dict = None) -> str:
        mid = str(uuid.uuid4())
        now = datetime.now().isoformat()
        meta_str = json.dumps(metadata) if metadata else None
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO messages VALUES (?,?,?,?,?,?)",
                (mid, conversation_id, role,
                 self._enc(content), now,
                 self._enc(meta_str))
            )
            if self._search_idx:
                conn.execute(
                    "INSERT INTO messages_fts(conversation_id, body) VALUES (?,?)",
                    (conversation_id, content)
                )
        self.update_conversation_touched(conversation_id)
        return mid

    def get_messages(self, conversation_id: str) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM messages WHERE conversation_id=? ORDER BY created_at",
                (conversation_id,)
            ).fetchall()
        return [self._dec_msg(dict(r)) for r in rows]

    def clear_messages(self, conversation_id: str):
        with self._conn() as conn:
            conn.execute("DELETE FROM messages WHERE conversation_id=?", (conversation_id,))
            conn.execute("DELETE FROM messages_fts WHERE conversation_id=?", (conversation_id,))

    def search_conversations(self, query: str) -> list[dict]:
        """
        Recherche plein-texte via FTS5.

        Note chiffrement : les index FTS5 contiennent le texte EN CLAIR.
        Si DB_ENCRYPTION_SEARCH=OFF, retourne toujours [].
        """
        if not self._search_idx:
            return []

        with self._conn() as conn:
            try:
                rows = conn.execute("""
                    SELECT DISTINCT c.* FROM conversations c
                    WHERE c.id IN (
                        SELECT conversation_id FROM conversations_title_fts
                        WHERE conversations_title_fts MATCH ?
                        UNION
                        SELECT conversation_id FROM messages_fts
                        WHERE messages_fts MATCH ?
                    )
                    ORDER BY c.updated_at DESC
                """, (query, query)).fetchall()
            except sqlite3.OperationalError:
                q = f"%{query}%"
                rows = conn.execute("""
                    SELECT DISTINCT c.* FROM conversations c
                    LEFT JOIN messages m ON m.conversation_id = c.id
                    WHERE c.title LIKE ? OR m.content LIKE ?
                    ORDER BY c.updated_at DESC
                """, (q, q)).fetchall()

        return [self._dec_conv(dict(r)) for r in rows]


    # -- Dossiers ----------------------------------------------------------
    #
    # Deux niveaux maximum (racine + sous-dossier).

    def create_folder(self, name: str, parent_id: str = None) -> str:
        """Cree un dossier (ou sous-dossier) et retourne son id.

        Raises
        ------
        ValueError : si parent_id est lui-meme un sous-dossier (> 1 niveau).
        """
        if parent_id is not None:
            parent = self.get_folder(parent_id)
            if parent and parent.get("parent_id") is not None:
                raise ValueError(
                    "Les sous-dossiers ne peuvent pas etre imbriques "
                    "(profondeur maximale : 2 niveaux)."
                )
        fid = str(uuid.uuid4())
        now = datetime.now().isoformat()
        with self._conn() as conn:
            row = conn.execute(
                "SELECT COALESCE(MAX(position), -1) FROM folders WHERE parent_id IS ?",
                (parent_id,)
            ).fetchone()
            position = (row[0] + 1) if row else 0
            conn.execute(
                "INSERT INTO folders (id, name, parent_id, position, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (fid, name.strip(), parent_id, position, now)
            )
        log.info("[DB] Dossier cree : %r (id=%s parent=%s)", name, fid, parent_id)
        return fid

    def get_folder(self, folder_id: str) -> "Optional[dict]":
        """Retourne les metadonnees d'un dossier, ou None."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM folders WHERE id=?", (folder_id,)
            ).fetchone()
        return dict(row) if row else None

    def get_folders(self, parent_id: str = None) -> "list[dict]":
        """Retourne les dossiers enfants directs d'un parent (None = racine)."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM folders WHERE parent_id IS ? ORDER BY position",
                (parent_id,)
            ).fetchall()
        return [dict(r) for r in rows]

    def get_all_folders(self) -> "list[dict]":
        """Retourne tous les dossiers, liste plate ordonnee."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM folders ORDER BY (parent_id IS NULL) DESC, position"
            ).fetchall()
        return [dict(r) for r in rows]

    def rename_folder(self, folder_id: str, name: str) -> None:
        """Renomme un dossier."""
        with self._conn() as conn:
            conn.execute("UPDATE folders SET name=? WHERE id=?", (name.strip(), folder_id))

    def reorder_folder(self, folder_id: str, new_position: int) -> None:
        """Change la position d'un dossier dans son groupe parent."""
        with self._conn() as conn:
            conn.execute("UPDATE folders SET position=? WHERE id=?", (new_position, folder_id))

    def delete_folder(self, folder_id: str) -> None:
        """Supprime un dossier et ses sous-dossiers.

        Les conversations sont detachees (folder_id NULL) plutot que supprimees.
        """
        with self._conn() as conn:
            conn.execute("UPDATE conversations SET folder_id=NULL WHERE folder_id=?", (folder_id,))
            conn.execute(
                "UPDATE conversations SET folder_id=NULL "
                "WHERE folder_id IN (SELECT id FROM folders WHERE parent_id=?)",
                (folder_id,)
            )
            conn.execute("DELETE FROM folders WHERE parent_id=?", (folder_id,))
            conn.execute("DELETE FROM folders WHERE id=?", (folder_id,))
        log.info("[DB] Dossier supprime : %s", folder_id)

    def move_conversation_to_folder(self, conversation_id: str, folder_id: "Optional[str]") -> None:
        """Deplace une conversation dans un dossier (None = sans dossier)."""
        with self._conn() as conn:
            conn.execute(
                "UPDATE conversations SET folder_id=? WHERE id=?",
                (folder_id, conversation_id)
            )

    def get_conversations_in_folder(self, folder_id: "Optional[str]") -> "list[dict]":
        """Retourne les conversations d'un dossier. folder_id=None -> sans dossier."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM conversations WHERE folder_id IS ? ORDER BY updated_at DESC",
                (folder_id,)
            ).fetchall()
        return [self._dec_conv(dict(r)) for r in rows]

    # -- Migration ---------------------------------------------------------

    def migrate_to_encrypted(self, passphrase: str,
                              progress_cb=None) -> tuple[int, int]:
        """
        Chiffre en place toutes les valeurs en clair d'une base existante.

        Les valeurs deja chiffrees (detectees via crypto.is_encrypted) sont
        ignorees — la migration est donc idempotente et interruptible.

        Parameters
        ----------
        passphrase : str
            Passphrase de chiffrement.
        progress_cb : callable(done: int, total: int) | None
            Callback optionnel de progression (appele par lot de conversations).

        Returns
        -------
        (n_conversations, n_messages) : nombre de lignes effectivement migrees.

        Raises
        ------
        RuntimeError : si DB_ENCRYPTION=OFF.
        """
        if not self._encrypt:
            raise RuntimeError(
                "Le chiffrement n'est pas active (DB_ENCRYPTION=OFF)."
            )

        n_conv = n_msg = 0

        with self._conn() as conn:
            convs = conn.execute(
                "SELECT id, title, system_prompt FROM conversations"
            ).fetchall()

            total = len(convs)
            for i, row in enumerate(convs):
                cid    = row["id"]
                title  = row["title"]  or ""
                syspmt = row["system_prompt"] or ""

                new_title  = crypto.encrypt(title,  passphrase) if not crypto.is_encrypted(title)  else title
                new_syspmt = crypto.encrypt(syspmt, passphrase) if not crypto.is_encrypted(syspmt) else syspmt

                conn.execute(
                    "UPDATE conversations SET title=?, system_prompt=? WHERE id=?",
                    (new_title, new_syspmt, cid)
                )
                n_conv += 1
                if progress_cb:
                    progress_cb(i + 1, total)

            msgs = conn.execute(
                "SELECT id, content, metadata FROM messages"
            ).fetchall()

            for row in msgs:
                mid      = row["id"]
                content  = row["content"]  or ""
                metadata = row["metadata"]

                new_content  = crypto.encrypt(content,  passphrase) if not crypto.is_encrypted(content)  else content
                new_metadata = None
                if metadata:
                    new_metadata = crypto.encrypt(metadata, passphrase) if not crypto.is_encrypted(metadata) else metadata

                conn.execute(
                    "UPDATE messages SET content=?, metadata=? WHERE id=?",
                    (new_content, new_metadata, mid)
                )
                n_msg += 1

        # Creer le sentinel avec la passphrase de migration
        saved = self._passphrase
        self._passphrase = passphrase
        self._verify_or_create_sentinel()
        self._passphrase = saved

        log.info("[DB] Migration : %d conversations, %d messages chiffres.", n_conv, n_msg)
        return n_conv, n_msg

    # ── Accès générique au kv_store ───────────────────────────────────────────

    def kv_get(self, key: str) -> "Optional[str]":
        """Lit une valeur dans kv_store. Retourne None si la clé n'existe pas."""
        try:
            with self._conn() as conn:
                row = conn.execute(
                    "SELECT value FROM kv_store WHERE key = ?", (key,)
                ).fetchone()
            return row[0] if row else None
        except Exception as e:
            log.warning("[DB] kv_get(%s) échoué : %s", key, e)
            return None

    def kv_set(self, key: str, value: str) -> None:
        """Écrit ou met à jour une valeur dans kv_store (upsert)."""
        try:
            with self._conn() as conn:
                conn.execute(
                    "INSERT INTO kv_store(key, value) VALUES (?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (key, value),
                )
        except Exception as e:
            log.warning("[DB] kv_set(%s) échoué : %s", key, e)

    def kv_delete(self, key: str) -> None:
        """Supprime une entrée de kv_store si elle existe."""
        try:
            with self._conn() as conn:
                conn.execute("DELETE FROM kv_store WHERE key = ?", (key,))
        except Exception as e:
            log.warning("[DB] kv_delete(%s) échoué : %s", key, e)
