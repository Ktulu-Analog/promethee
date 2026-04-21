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
long_term_memory.py — Mémoire long terme inter-conversations

Architecture
────────────
Ce module fait le pont entre deux systèmes déjà en place :

  • HistoryDB (SQLite)  → source de vérité, historique brut de toutes les
                          conversations (messages, titres, horodatages).

  • rag_engine (Qdrant) → moteur de recherche sémantique, déjà utilisé pour
                          les documents ingérés manuellement.

Collection Qdrant dédiée
─────────────────────────
Les souvenirs sont stockés dans la collection LTM de l'utilisateur courant, une collection
SÉPARÉE de la collection RAG documentaire de l'utilisateur. Cela évite la
pollution croisée entre souvenirs de conversations et documents manuels.

Le nommage suit exactement les mêmes règles que la collection documentaire :

  • LTM_COLLECTION dans .env     → respecté tel quel
  • sinon                        → promethee_memory_<user_id>

  Où <user_id> est résolu dans l'ordre : RAG_USER_ID (.env) > getuser()
  > hostname > "default". Même logique que QDRANT_COLLECTION, préfixe
  "promethee_memory_" au lieu de "promethee_".

Isolation multi-instances
──────────────────────────
Sur un serveur Qdrant partagé entre plusieurs postes, chaque instance
dispose ainsi de deux collections qui lui sont propres :

  promethee_pierre          ← RAG documentaire
  promethee_memory_pierre   ← mémoire long terme

La protection _is_own_collection() de rag_engine couvre les deux préfixes
("promethee_" et "promethee_memory_") et refuse toute lecture/écriture dans
la collection d'un autre utilisateur.

Principe de fonctionnement
──────────────────────────
1. À la fermeture d'une conversation, `index_conversation()` est appelée.
   Elle construit un texte structuré à partir des messages SQLite et
   l'ingère dans la collection LTM de l'utilisateur courant.

2. Au premier message d'une nouvelle conversation, `recall()` cherche dans
   la collection LTM de l'utilisateur courant les souvenirs sémantiquement proches et retourne
   un bloc de contexte injecté avant le RAG documentaire dans le system prompt.

3. `index_all_unindexed()` indexe rétroactivement toutes les conversations.

Suivi de l'état d'indexation
─────────────────────────────
La table kv_store de HistoryDB est utilisée comme registre :
  key   = "ltm:indexed:<conv_id>"
  value = updated_at de la conversation au moment de l'indexation

Une conversation n'est jamais ré-indexée si elle n'a pas changé depuis la
dernière indexation. L'opération est idempotente et interruptible.

Stratégie de chunking pour les dialogues
─────────────────────────────────────────
Les conversations sont découpées en blocs de N échanges (user+assistant)
qui préservent la cohérence sémantique d'un fil de discussion. Chaque chunk
porte l'en-tête complet (titre + date) pour que l'embedding soit contextuel.

Configuration (.env) — valeurs lues via Config
────────────────────────────────────────────────
  LTM_ENABLED=ON              # activer la mémoire long terme (défaut: OFF)
  LTM_COLLECTION=...          # surcharger le nom de collection (optionnel)
  LTM_EXCHANGES_PER_CHUNK=6   # échanges user/assistant par chunk Qdrant
  LTM_MAX_CHARS_PER_MSG=600   # troncature d'un message individuel
  LTM_TOP_K=4                 # souvenirs remontés par recall()
  LTM_MIN_SCORE=0.45          # score de similarité minimum (0.0–1.0)
  LTM_RECENT_K=2              # N conversations récentes toujours injectées (0 = désactivé)
  LTM_MIN_MESSAGES=4          # ignorer les conversations trop courtes

Intégration (déjà faite dans main_window.py et chat_panel.py)
──────────────────────────────────────────────────────────────
  from core.long_term_memory import LongTermMemory, is_enabled as ltm_enabled

  # Fermeture d'un onglet :
  if ltm_enabled():
      LongTermMemory(db).index_conversation(conv_id)

  # Suppression d'une conversation :
  if ltm_enabled():
      LongTermMemory(db).forget_conversation(conv_id)

  # Premier message (dans _build_system_prompt) :
  if ltm_enabled():
      ctx = LongTermMemory(db).recall(query, exclude_conv_id=self.conv_id)
      if ctx:
          sys_prompt = ctx + "\\n\\n" + sys_prompt
"""

import logging
from datetime import datetime
from typing import Optional

from .config import Config
from . import request_context as _req_ctx

_log = logging.getLogger("promethee.long_term_memory")

# ── Constantes de registre kv_store ───────────────────────────────────────────

_KV_PREFIX             = "ltm:indexed:"           # key = "ltm:indexed:<conv_id>"
_KV_CONSOLIDATION_CTR  = "ltm:consolidation_counter"  # compteur de cycles d'indexation


# ── Prompts LTM — Résumé de conversation ─────────────────────────────────────

_LTM_SUMMARY_SYSTEM = """\
Tu es un assistant qui résume des conversations pour une mémoire long terme.
Réponds UNIQUEMENT en français, de manière concise et structurée.
Ne réponds rien d'autre que le résumé demandé.
"""

_LTM_SUMMARY_PROMPT = """\
Voici une conversation entre un utilisateur et un assistant IA.
Génère un résumé structuré en MAXIMUM {max_chars} caractères couvrant :

1. **Sujet principal** : de quoi parlait cette conversation (1-2 phrases).
2. **Points clés échangés** : décisions, faits importants, informations partagées.
3. **Contexte utilisateur** : préférences, contraintes ou informations personnelles révélées.
4. **Résultats** : ce qui a été produit, résolu ou conclu.

Sois factuel et précis. Préserve les noms propres, valeurs numériques et termes techniques.
Si une section n'a pas de contenu pertinent, omets-la.

--- Conversation : {title} ({date}) ---
{dialogue}
--- Fin ---
"""


# ── Prompts LTM — Consolidation thématique ───────────────────────────────────

_LTM_CONSOLIDATION_SYSTEM = """\
Tu es un assistant qui consolide des souvenirs anciens en résumés thématiques.
Réponds UNIQUEMENT en français, de manière concise et structurée.
Ne réponds rien d'autre que le résumé demandé.
"""

_LTM_CONSOLIDATION_PROMPT = """\
Voici plusieurs extraits de mémoire issus de conversations passées avec un utilisateur.
Fusionne-les en un résumé thématique cohérent en MAXIMUM {max_chars} caractères.

Conserve impérativement :
- Les faits importants et récurrents concernant l'utilisateur
- Ses préférences, habitudes et contraintes mentionnées
- Les projets ou sujets abordés régulièrement
- Les décisions ou conclusions importantes
- Les noms propres, valeurs numériques et termes techniques distinctifs

Élimine sans regret :
- Les répétitions et redondances entre extraits
- Les anecdotes ponctuelles sans valeur durable
- Les détails procéduraux non significatifs

--- Extraits à consolider ({n_chunks} souvenirs) ---
{memories}
--- Fin ---
"""


# ── Classe principale ─────────────────────────────────────────────────────────

class LongTermMemory:
    """
    Mémoire long terme : indexation des conversations passées dans Qdrant
    (collection la collection LTM de l'utilisateur courant) et rappel sémantique au démarrage
    d'une nouvelle conversation.

    Toutes les valeurs de configuration sont lues depuis Config, elle-même
    alimentée par le .env. Il n'est pas nécessaire de passer des paramètres
    manuellement sauf pour les tests.

    Parameters
    ----------
    db : HistoryDB
        Instance de la base SQLite (déjà ouverte, passphrase déjà fournie
        si chiffrement activé).
    exchanges_per_chunk : int, optional
        Surcharge de LTM_EXCHANGES_PER_CHUNK.
    max_chars_per_msg : int, optional
        Surcharge de LTM_MAX_CHARS_PER_MSG.
    top_k : int, optional
        Surcharge de LTM_TOP_K.
    min_score : float, optional
        Surcharge de LTM_MIN_SCORE.
    recent_k : int, optional
        Surcharge de LTM_RECENT_K. Nombre de conversations récentes toujours
        injectées indépendamment du score sémantique (0 = désactivé).
    min_messages : int, optional
        Surcharge de LTM_MIN_MESSAGES.
    """

    def __init__(
        self,
        db,
        client=None,
        model: str = None,
        exchanges_per_chunk: int   = None,
        max_chars_per_msg:   int   = None,
        top_k:               int   = None,
        min_score:           float = None,
        min_messages:        int   = None,
        recent_k:            int   = None,
        use_summary:         bool  = None,
        summary_max_chars:   int   = None,
        consolidation_every: int   = None,
        consolidation_max_chunks: int = None,
    ):
        self._db = db

        # ── Client LLM (optionnel) — nécessaire pour LTM_USE_SUMMARY et consolidation
        self._client = client
        self._model  = model or Config.active_model()

        # Paramètres existants : argument explicite > Config (.env) > défaut codé
        self._exchanges_per_chunk = exchanges_per_chunk \
            if exchanges_per_chunk is not None else Config.LTM_EXCHANGES_PER_CHUNK
        self._max_chars_per_msg   = max_chars_per_msg \
            if max_chars_per_msg   is not None else Config.LTM_MAX_CHARS_PER_MSG
        self._top_k               = top_k \
            if top_k               is not None else Config.LTM_TOP_K
        self._min_score           = min_score \
            if min_score           is not None else Config.LTM_MIN_SCORE
        self._min_messages        = min_messages \
            if min_messages        is not None else Config.LTM_MIN_MESSAGES
        self._recent_k            = recent_k \
            if recent_k            is not None else Config.LTM_RECENT_K

        # ── Nouveaux paramètres : résumés LLM et consolidation ────────────────
        self._use_summary = use_summary \
            if use_summary is not None else Config.LTM_USE_SUMMARY
        self._summary_max_chars = summary_max_chars \
            if summary_max_chars is not None else Config.LTM_SUMMARY_MAX_CHARS
        self._consolidation_every = consolidation_every \
            if consolidation_every is not None else Config.LTM_CONSOLIDATION_EVERY
        self._consolidation_max_chunks = consolidation_max_chunks \
            if consolidation_max_chunks is not None else Config.LTM_CONSOLIDATION_MAX_CHUNKS

        # La collection LTM est propre à l'utilisateur courant — lue depuis le request_context.
        _ucfg = _req_ctx.get_user_config()
        if _ucfg is None:
            raise RuntimeError(
                "[LongTermMemory] Aucun UserConfig dans le request_context. "
                "Vérifiez que la route FastAPI utilise Depends(get_current_user_config) "
                "et appelle set_user_config(user_cfg) avant l'instanciation."
            )
        self._collection = _ucfg.LTM_COLLECTION

        # Compteur d'indexations depuis la dernière consolidation (persisté dans kv_store)
        self._indexations_since_consolidation: int = self._load_consolidation_counter()




    # ── API publique ──────────────────────────────────────────────────────────

    def index_conversation(self, conv_id: str, force: bool = False) -> int:
        """
        Indexe une conversation dans la collection LTM de Qdrant.

        Si la conversation a déjà été indexée après sa dernière modification,
        l'opération est ignorée sauf si force=True.

        Parameters
        ----------
        conv_id : str
            Identifiant de la conversation SQLite.
        force : bool
            Si True, ré-indexe même si déjà à jour.

        Returns
        -------
        int
            Nombre de chunks ingérés (0 si ignoré ou trop courte).
        """
        from . import rag_engine

        if not rag_engine.is_available():
            _log.debug("[LTM] RAG non disponible — indexation ignorée")
            return 0

        conv = self._db.get_conversation(conv_id)
        if not conv:
            _log.warning("[LTM] Conversation inconnue : %s", conv_id)
            return 0

        if not force and self._is_up_to_date(conv_id, conv.get("updated_at", "")):
            _log.debug("[LTM] %s déjà à jour — indexation ignorée", conv_id)
            return 0

        messages = self._db.get_messages(conv_id)
        dialogue = [m for m in messages if m["role"] in ("user", "assistant")]

        if len(dialogue) < self._min_messages:
            _log.debug(
                "[LTM] %s trop courte (%d messages < %d) — ignorée",
                conv_id, len(dialogue), self._min_messages,
            )
            return 0

        # Supprimer les chunks précédents (ré-indexation propre)
        source_name = f"memory:{conv_id}"
        rag_engine.delete_by_source(source_name, conversation_id=None,
                                    collection_name=self._collection)

        # ── Choix de la stratégie d'indexation ────────────────────────────────
        # Mode résumé LLM : un seul chunk structuré par conversation.
        # Mode brut (historique) : plusieurs chunks couvrant les échanges bruts.
        # Le fallback vers les chunks bruts est automatique si le LLM échoue.
        if self._use_summary and self._client is not None:
            chunks = self._build_summary_chunk(conv, dialogue)
            if not chunks:
                _log.warning(
                    "[LTM] Résumé LLM échoué pour %s — fallback chunks bruts", conv_id
                )
                chunks = self._build_chunks(conv, dialogue)
        else:
            chunks = self._build_chunks(conv, dialogue)

        if not chunks:
            return 0

        total = 0
        for chunk_text in chunks:
            n = rag_engine.ingest_text(
                text=chunk_text,
                source=source_name,
                conversation_id="global",
                collection_name=self._collection,
            )
            total += n

        self._mark_indexed(conv_id, conv.get("updated_at", ""))

        _log.info(
            "[LTM] %s indexée → %d chunk(s) | mode=%s | collection=%s | titre=%s",
            conv_id, total,
            "résumé" if (self._use_summary and self._client is not None) else "brut",
            self._collection, conv.get("title", "?")[:60],
        )

        # ── Consolidation périodique ───────────────────────────────────────────
        # Incrémente le compteur et déclenche la consolidation si le seuil est atteint.
        self._indexations_since_consolidation += 1
        self._save_consolidation_counter(self._indexations_since_consolidation)

        if (
            self._consolidation_every > 0
            and self._client is not None
            and self._indexations_since_consolidation >= self._consolidation_every
        ):
            _log.info(
                "[LTM] Seuil de consolidation atteint (%d/%d) — lancement",
                self._indexations_since_consolidation, self._consolidation_every,
            )
            self.consolidate_old_memories()

        return total

    def recall(self, query: str, exclude_conv_id: str = None) -> str:
        """
        Recherche les souvenirs pertinents pour une requête dans la collection LTM de l'utilisateur courant
        et retourne un bloc de contexte formaté prêt à injecter dans le system prompt.

        Combine deux sources :
        - recall sémantique (similarité cosinus ≥ LTM_MIN_SCORE)
        - N conversations les plus récentes (LTM_RECENT_K), toujours injectées

        Parameters
        ----------
        query : str
            Requête de l'utilisateur (première question de la session).
        exclude_conv_id : str, optional
            Conversation courante à exclure (évite l'auto-référence).

        Returns
        -------
        str
            Bloc de contexte ou chaîne vide si aucun souvenir pertinent.
        """
        from . import rag_engine

        if not rag_engine.is_available():
            return ""

        exclude_source = f"memory:{exclude_conv_id}" if exclude_conv_id else None

        # ── 1. Recall sémantique ──────────────────────────────────────────
        hits = rag_engine.search(
            query=query,
            top_k=self._top_k + 2,   # marge pour le filtrage post-score
            conversation_id=None,     # scope global uniquement
            collection_name=self._collection,
        )
        semantic = [
            h for h in hits
            if h["score"] >= self._min_score
            and h.get("source") != exclude_source
        ][:self._top_k]

        # ── 2. Conversations récentes (toujours injectées) ────────────────
        recent: list[dict] = []
        if self._recent_k > 0:
            recent = self._get_recent_hits(
                exclude_source=exclude_source,
                n=self._recent_k,
            )

        # ── 3. Fusion sans doublons (source + début de texte comme clé) ──
        seen_sources: set[str] = set()
        merged: list[dict] = []
        for h in semantic + recent:
            key = (h.get("source", ""), h.get("text", "")[:60])
            if key not in seen_sources:
                seen_sources.add(key)
                merged.append(h)

        if not merged:
            _log.debug("[LTM] recall() — aucun souvenir (seuil=%.2f, recent_k=%d)",
                       self._min_score, self._recent_k)
            return ""

        _log.debug("[LTM] recall() — %d souvenir(s) injecté(s) (%d sémantique, %d récent(s)) depuis %s",
                   len(merged), len(semantic), len(recent), self._collection)
        return self._format_recall(merged)

    def _get_recent_hits(self, exclude_source: str | None, n: int) -> list[dict]:
        """
        Retourne un chunk représentatif des N conversations les plus récentes
        (d'après SQLite updated_at), indépendamment du score sémantique.
        Les chunks sont marqués avec score=-1.0 pour les distinguer.
        """
        from . import rag_engine
        from qdrant_client.models import Filter, FieldCondition, MatchValue

        try:
            conversations = self._db.get_conversations()
        except Exception as e:
            _log.warning("[LTM] _get_recent_hits : lecture DB échouée : %s", e)
            return []

        qc = rag_engine._client()
        if qc is None:
            return []

        recent_hits: list[dict] = []
        seen: set[str] = set()

        for conv in conversations:
            if len(seen) >= n:
                break
            conv_id = conv.get("id", "")
            source  = f"memory:{conv_id}"
            if source == exclude_source or conv_id in seen:
                continue
            if not self.is_indexed(conv_id):
                continue

            try:
                results, _ = qc.scroll(
                    collection_name=self._collection,
                    scroll_filter=Filter(
                        must=[FieldCondition(key="source", match=MatchValue(value=source))]
                    ),
                    limit=1,
                    with_payload=True,
                    with_vectors=False,
                )
                if results:
                    payload = results[0].payload or {}
                    recent_hits.append({
                        "text":   payload.get("text", ""),
                        "source": payload.get("source", source),
                        "score":  -1.0,   # marqueur "récent, non sémantique"
                    })
                    seen.add(conv_id)
            except Exception as e:
                _log.debug("[LTM] _get_recent_hits scroll(%s) : %s", conv_id[:8], e)

        return recent_hits

    def index_all_unindexed(self, progress_cb=None) -> tuple[int, int]:
        """
        Indexe rétroactivement toutes les conversations non encore indexées.

        Utile pour initialiser la mémoire long terme sur une base existante.
        Lancer une seule fois depuis un shell Python :

            db  = HistoryDB()
            ltm = LongTermMemory(db)
            indexed, skipped = ltm.index_all_unindexed(
                progress_cb=lambda d, t: print(f"{d}/{t}", end="\\r")
            )

        Parameters
        ----------
        progress_cb : callable(done: int, total: int) | None

        Returns
        -------
        (n_indexed, n_skipped)
        """
        conversations = self._db.get_conversations()
        total   = len(conversations)
        indexed = 0
        skipped = 0

        for i, conv in enumerate(conversations):
            conv_id = conv["id"]
            if self._is_up_to_date(conv_id, conv.get("updated_at", "")):
                skipped += 1
            else:
                n = self.index_conversation(conv_id)
                indexed += 1 if n > 0 else 0
                skipped += 0 if n > 0 else 1

            if progress_cb:
                progress_cb(i + 1, total)

        _log.info("[LTM] Indexation initiale : %d indexées, %d ignorées sur %d",
                  indexed, skipped, total)
        return indexed, skipped

    def forget_conversation(self, conv_id: str) -> int:
        """
        Supprime les souvenirs d'une conversation de la collection LTM de l'utilisateur courant
        et du registre kv_store.

        À appeler quand l'utilisateur supprime une conversation de l'historique.

        Returns
        -------
        int
            Nombre de chunks supprimés.
        """
        from . import rag_engine

        source_name = f"memory:{conv_id}"
        n = rag_engine.delete_by_source(source_name, conversation_id=None,
                                        collection_name=self._collection)
        self._clear_index_marker(conv_id)
        _log.info("[LTM] Conversation %s oubliée (%d chunk(s) supprimés) depuis %s",
                  conv_id, n, self._collection)
        return n

    def is_indexed(self, conv_id: str) -> bool:
        """Retourne True si la conversation a déjà été indexée et est à jour."""
        conv = self._db.get_conversation(conv_id)
        if not conv:
            return False
        return self._is_up_to_date(conv_id, conv.get("updated_at", ""))

    @property
    def collection(self) -> str:
        """Nom de la collection Qdrant LTM utilisée par cette instance."""
        return self._collection

    # ── Construction des chunks ───────────────────────────────────────────────

    def _build_summary_chunk(self, conv: dict, dialogue: list[dict]) -> list[str]:
        """
        Génère UN SEUL chunk par conversation via un résumé LLM structuré.

        Le résumé est plus dense sémantiquement que les chunks bruts et produit
        de meilleurs vecteurs d'embedding (moins de bruit, meilleure précision du
        recall). L'en-tête [Mémoire — titre — date] est conservé pour que
        l'embedding capture le contexte temporel.

        Retourne [] si le LLM échoue ou si le résumé produit est vide.
        Le caller (index_conversation) applique un fallback sur _build_chunks().
        """
        title    = conv.get("title", "Conversation sans titre")
        date_raw = conv.get("created_at", "")
        date_str = date_raw[:10] if date_raw else "date inconnue"
        header   = f"[Mémoire — {title} — {date_str}]\n"

        # Construire le dialogue brut pour le prompt LLM
        dialogue_text = self._format_dialogue(dialogue)

        # Plafonner la taille envoyée au LLM pour éviter les dépassements de contexte.
        # Ratio 6 : un résumé de 1200 chars accepte ~7200 chars de dialogue en entrée.
        max_input = self._summary_max_chars * 6
        if len(dialogue_text) > max_input:
            dialogue_text = dialogue_text[:max_input].rstrip() + "\n[… dialogue tronqué …]"

        prompt = (
            _LTM_SUMMARY_SYSTEM.strip()
            + "\n\n"
            + _LTM_SUMMARY_PROMPT.format(
                max_chars=self._summary_max_chars,
                title=title,
                date=date_str,
                dialogue=dialogue_text,
            )
        )

        try:
            stream_resp = self._client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
                stream=True,
                max_tokens=500,
            )
            parts: list[str] = []
            for chunk in stream_resp:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                if delta and delta.content:
                    parts.append(delta.content)

            summary = "".join(parts).strip()
            if not summary:
                _log.warning("[LTM] _build_summary_chunk : résumé LLM vide pour '%s'", title[:40])
                return []

            if len(summary) > self._summary_max_chars:
                summary = summary[: self._summary_max_chars].rstrip() + "…"

            _log.debug(
                "[LTM] résumé LLM généré pour '%s' : %d chars", title[:40], len(summary)
            )
            return [header + summary]

        except Exception as e:
            _log.error("[LTM] _build_summary_chunk échoué : %s", e, exc_info=True)
            return []

    def consolidate_old_memories(self, max_chunks: int = None) -> int:
        """
        Consolide les souvenirs les plus anciens de LTM_COLLECTION en un résumé
        thématique unique, puis supprime les chunks originaux.

        Fonctionne par lot : récupère les `max_chunks` points Qdrant les plus
        anciens (hors chunks déjà consolidés, marqués _consolidated=True),
        les fusionne via LLM en un résumé thématique dense, puis remplace les
        originaux par ce unique point consolidé.

        Cette opération est idempotente : les chunks consolidés (marqués
        _consolidated=True dans leur payload) sont exclus des passages suivants.

        Nécessite un client LLM (self._client non None).

        Parameters
        ----------
        max_chunks : int, optional
            Nombre de chunks à consolider par appel.
            Défaut : Config.LTM_CONSOLIDATION_MAX_CHUNKS.

        Returns
        -------
        int
            Nombre de chunks originaux supprimés (0 si échec ou rien à faire).
        """
        from . import rag_engine
        from qdrant_client.models import (
            Filter, FieldCondition, MatchValue, PointIdsList,
        )

        if self._client is None:
            _log.warning("[LTM] consolidate_old_memories : pas de client LLM — opération ignorée")
            return 0

        if not rag_engine.is_available():
            return 0

        n = max_chunks or self._consolidation_max_chunks
        qc = rag_engine._client()
        if qc is None:
            return 0

        # ── Récupérer les N chunks les plus anciens non encore consolidés ─────
        # Les chunks consolidés portent _consolidated=True dans leur payload.
        # On les exclut en filtrant sur _consolidated=false (ou absente).
        # Qdrant ne supporte pas directement "champ absent" — on filtre sur
        # _consolidated=False et on compte sur le fait que les anciens chunks
        # n'ont pas ce champ (match_value ignorera les absents).
        try:
            results, _ = qc.scroll(
                collection_name=self._collection,
                scroll_filter=Filter(
                    must_not=[
                        FieldCondition(
                            key="_consolidated",
                            match=MatchValue(value=True),
                        )
                    ]
                ),
                limit=n,
                with_payload=True,
                with_vectors=False,
            )
        except Exception as e:
            _log.warning("[LTM] consolidate : scroll échoué : %s", e)
            return 0

        if not results:
            _log.debug("[LTM] consolidate : aucun chunk à consolider")
            self._reset_consolidation_counter()
            return 0

        # ── Préparer le texte pour le LLM de consolidation ───────────────────
        memory_parts: list[str] = []
        point_ids: list = []
        for pt in results:
            payload = pt.payload or {}
            text = payload.get("text", "").strip()
            if text:
                memory_parts.append(text)
                point_ids.append(pt.id)

        if not memory_parts:
            self._reset_consolidation_counter()
            return 0

        memories_text = "\n\n---\n\n".join(memory_parts)
        max_input = self._summary_max_chars * 8
        if len(memories_text) > max_input:
            memories_text = memories_text[:max_input] + "\n[… tronqué …]"

        consolidation_max_chars = self._summary_max_chars * 2
        prompt = (
            _LTM_CONSOLIDATION_SYSTEM.strip()
            + "\n\n"
            + _LTM_CONSOLIDATION_PROMPT.format(
                max_chars=consolidation_max_chars,
                n_chunks=len(memory_parts),
                memories=memories_text,
            )
        )

        # ── Appel LLM de consolidation ────────────────────────────────────────
        try:
            stream_resp = self._client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
                stream=True,
                max_tokens=600,
            )
            parts: list[str] = []
            for chunk in stream_resp:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                if delta and delta.content:
                    parts.append(delta.content)
            consolidated_text = "".join(parts).strip()
        except Exception as e:
            _log.error("[LTM] consolidation LLM échouée : %s", e, exc_info=True)
            return 0

        if not consolidated_text:
            _log.warning("[LTM] consolidation : résumé LLM vide — abandon")
            return 0

        if len(consolidated_text) > consolidation_max_chars:
            consolidated_text = consolidated_text[:consolidation_max_chars].rstrip() + "…"

        # ── Supprimer les chunks originaux ────────────────────────────────────
        try:
            qc.delete(
                collection_name=self._collection,
                points_selector=PointIdsList(points=point_ids),
            )
        except Exception as e:
            _log.error("[LTM] consolidation : suppression des chunks originaux échouée : %s", e)
            return 0

        # ── Supprimer les anciens chunks consolidés avant d'en ingérer un nouveau ──
        # Sans cette étape, chaque cycle accumule un chunk supplémentaire
        # sous la même source "memory:consolidated".
        try:
            rag_engine.delete_by_source(
                "memory:consolidated",
                conversation_id=None,
                collection_name=self._collection,
            )
        except Exception as e:
            _log.warning("[LTM] consolidate : suppression anciens consolidés échouée : %s", e)

        # ── Ingérer le nouveau chunk consolidé avec marqueur _consolidated=True ──
        rag_engine.ingest_text(
            text=f"[Mémoire consolidée]\n{consolidated_text}",
            source="memory:consolidated",
            conversation_id="global",
            collection_name=self._collection,
            extra_payload={"_consolidated": True},
        )

        self._reset_consolidation_counter()
        _log.info(
            "[LTM] Consolidation terminée : %d chunks → 1 résumé (%d chars) | collection=%s",
            len(point_ids), len(consolidated_text), self._collection,
        )
        return len(point_ids)

    # ── Construction des chunks ───────────────────────────────────────────────

    def _build_chunks(self, conv: dict, dialogue: list[dict]) -> list[str]:
        """
        Découpe le dialogue en blocs thématiques et retourne les textes
        prêts à ingérer.

        Chaque chunk porte l'en-tête complet (titre + date) pour que les
        embeddings capturent le contexte de la conversation entière.
        """
        title    = conv.get("title", "Conversation sans titre")
        date_raw = conv.get("created_at", "")
        date_str = date_raw[:10] if date_raw else "date inconnue"
        header   = f"[Mémoire — {title} — {date_str}]\n"

        # Cas dégénéré : tout en un seul chunk
        if self._exchanges_per_chunk <= 0:
            body = self._format_dialogue(dialogue)
            return [header + body]

        # Regrouper par paires user/assistant (un "échange")
        exchanges: list[list[dict]] = []
        i = 0
        while i < len(dialogue):
            group: list[dict] = []
            if dialogue[i]["role"] == "user":
                group.append(dialogue[i])
                i += 1
                if i < len(dialogue) and dialogue[i]["role"] == "assistant":
                    group.append(dialogue[i])
                    i += 1
            else:
                # Réponse orpheline (assistant sans question)
                group.append(dialogue[i])
                i += 1
            exchanges.append(group)

        # Regrouper les échanges en chunks de taille N
        chunks: list[str] = []
        step = max(1, self._exchanges_per_chunk)
        for start in range(0, len(exchanges), step):
            block = exchanges[start : start + step]
            flat  = [m for ex in block for m in ex]
            body  = self._format_dialogue(flat)
            chunks.append(header + body)

        return chunks

    def _format_dialogue(self, messages: list[dict]) -> str:
        """Formate une liste de messages en texte lisible pour l'embedding."""
        lines = []
        role_labels = {"user": "Utilisateur", "assistant": "Assistant"}
        for m in messages:
            role    = role_labels.get(m["role"], m["role"].capitalize())
            content = (m.get("content") or "").strip()
            if len(content) > self._max_chars_per_msg:
                content = content[: self._max_chars_per_msg].rstrip() + "…"
            if content:
                lines.append(f"{role} : {content}")
        return "\n".join(lines)

    # ── Formatage du contexte de rappel ───────────────────────────────────────

    @staticmethod
    def _format_recall(hits: list[dict], max_total_chars: int = 2000) -> str:
        """
        Formate les souvenirs en un bloc de contexte destiné
        à être injecté au début du system prompt.

        Parameters
        ----------
        hits : list[dict]
            Souvenirs retournés par le recall sémantique.
        max_total_chars : int
            Taille maximale totale du contenu des souvenirs (hors en-tête).
            Limite la pollution du contexte en cas de chunks volumineux.
            Défaut : 2000 caractères.
        """
        parts = [
                    "### Mémoire personnelle (conversations précédentes)\n"
                    "Tu disposes d'une mémoire des échanges passés avec cet utilisateur. "
                    "Les extraits ci-dessous sont issus de tes conversations précédentes "
                    "et sont pertinents pour la demande actuelle. "
                    "Tu peux t'y référer directement sans mentionner "
                    "que tu ne te souviens pas des échanges passés :\n"
        ]
        total = 0
        for i, h in enumerate(hits, 1):
            score = h.get("score", 0.0)
            text  = h.get("text", "").strip()
            label = "récent" if score < 0 else f"score={score:.2f}"
            remaining = max_total_chars - total
            if remaining <= 0:
                _log.debug(
                    "[LTM] _format_recall : plafond %d cars atteint — %d souvenir(s) élagué(s)",
                    max_total_chars, len(hits) - i + 1,
                )
                break
            if len(text) > remaining:
                text = text[:remaining].rstrip() + "…"
            parts.append(f"[{i}] ({label})\n{text}\n")
            total += len(text)
        parts.append("---\n")
        return "\n".join(parts)

    # ── Registre kv_store ─────────────────────────────────────────────────────

    def _kv_key(self, conv_id: str) -> str:
        return f"{_KV_PREFIX}{conv_id}"

    def _is_up_to_date(self, conv_id: str, updated_at: str) -> bool:
        """
        Retourne True si la conversation a été indexée APRÈS sa dernière
        modification (comparaison lexicographique sur les timestamps ISO).
        """
        key = self._kv_key(conv_id)
        try:
            with self._db._conn() as conn:
                row = conn.execute(
                    "SELECT value FROM kv_store WHERE key = ?", (key,)
                ).fetchone()
            if row is None:
                return False
            return row[0] >= updated_at
        except Exception as e:
            _log.warning("[LTM] Impossible de lire kv_store (%s) : %s", key, e)
            return False

    def _kv_set(self, key: str, value: str) -> None:
        """Écrit ou met à jour une entrée dans kv_store (upsert).

        Méthode interne partagée par _mark_indexed et _save_consolidation_counter
        pour éviter la duplication du pattern INSERT … ON CONFLICT DO UPDATE.

        Parameters
        ----------
        key : str
            Clé unique dans kv_store.
        value : str
            Valeur à stocker.
        """
        try:
            with self._db._conn() as conn:
                conn.execute(
                    "INSERT INTO kv_store(key, value) VALUES (?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (key, value),
                )
        except Exception as e:
            _log.warning("[LTM] kv_store write error (%s) : %s", key, e)

    def _mark_indexed(self, conv_id: str, updated_at: str) -> None:
        """Enregistre dans kv_store que la conversation a été indexée."""
        key   = self._kv_key(conv_id)
        value = updated_at or datetime.now().isoformat()
        self._kv_set(key, value)

    def _clear_index_marker(self, conv_id: str) -> None:
        """Supprime le marqueur d'indexation d'une conversation."""
        key = self._kv_key(conv_id)
        try:
            with self._db._conn() as conn:
                conn.execute("DELETE FROM kv_store WHERE key = ?", (key,))
        except Exception as e:
            _log.warning("[LTM] Impossible de supprimer kv_store (%s) : %s", key, e)

    def _load_consolidation_counter(self) -> int:
        """Lit le compteur de cycles d'indexation depuis kv_store."""
        try:
            with self._db._conn() as conn:
                row = conn.execute(
                    "SELECT value FROM kv_store WHERE key = ?",
                    (_KV_CONSOLIDATION_CTR,),
                ).fetchone()
            return int(row[0]) if row else 0
        except Exception:
            return 0

    def _save_consolidation_counter(self, value: int) -> None:
        """Persiste le compteur de cycles d'indexation dans kv_store."""
        self._kv_set(_KV_CONSOLIDATION_CTR, str(value))

    def _reset_consolidation_counter(self) -> None:
        """Remet le compteur à zéro (après une consolidation réussie)."""
        self._indexations_since_consolidation = 0
        self._save_consolidation_counter(0)


# ── Helper module-level ───────────────────────────────────────────────────────

def is_enabled() -> bool:
    """Retourne True si LTM_ENABLED=ON dans .env."""
    return Config.LTM_ENABLED
