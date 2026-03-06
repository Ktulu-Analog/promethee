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
rag_engine.py — Moteur RAG : ingestion de documents → Qdrant, recherche sémantique
"""
import logging
import uuid
import re
from pathlib import Path
from typing import Optional
from .config import Config

_log = logging.getLogger(__name__)

try:
    from qdrant_client import QdrantClient
    from qdrant_client.models import (
        Distance, VectorParams, PointStruct, Filter,
        FieldCondition, MatchValue, FilterSelector,
    )
    QDRANT_OK = True
except ImportError:
    QDRANT_OK = False

# Variables d'état pour les embeddings
_embedder = None
_embedder_type = None
EMBED_OK = False

# Singleton QdrantClient — une seule instance réutilisée pour toutes les opérations
_qdrant_client: "QdrantClient | None" = None
_qdrant_url: str | None = None   # URL mémorisée pour détecter un changement de config


def _init_embedder():
    """Initialise l'embedder selon la configuration."""
    global _embedder, _embedder_type, EMBED_OK

    if Config.EMBEDDING_MODE == "api":
        # Mode API : utiliser OpenAI-compatible
        try:
            from openai import OpenAI
            _embedder = OpenAI(
                base_url=Config.EMBEDDING_API_BASE,
                api_key=Config.OPENAI_API_KEY or "none",
            )
            _embedder_type = "api"
            EMBED_OK = True
            _log.info(f"[RAG] Embeddings API initialisé : {Config.EMBEDDING_MODEL}")
        except ImportError:
            _log.error("[RAG] OpenAI non disponible pour embeddings API")
            EMBED_OK = False
    else:
        # Mode local : utiliser sentence-transformers
        try:
            from sentence_transformers import SentenceTransformer
            _embedder = SentenceTransformer(Config.EMBEDDING_MODEL, device='cpu')
            _embedder_type = "local"
            EMBED_OK = True
            _log.info(f"[RAG] Embeddings local initialisé : {Config.EMBEDDING_MODEL}")
        except ImportError:
            _log.error("[RAG] sentence-transformers non disponible")
            EMBED_OK = False


def _get_embeddings(texts: list[str]) -> list[list[float]]:
    """Génère les embeddings pour une liste de textes."""
    if not EMBED_OK or _embedder is None:
        return []

    if _embedder_type == "api":
        try:
            batch_size = 64
            all_embeddings = []
            for i in range(0, len(texts), batch_size):
                batch = texts[i : i + batch_size]
                response = _embedder.embeddings.create(
                    input=batch,
                    model=Config.EMBEDDING_MODEL,
                    encoding_format="float",
                )
                all_embeddings.extend(item.embedding for item in response.data)
            return all_embeddings
        except Exception as e:
            _log.error(f"[RAG] Erreur embeddings API : {e}")
            return []
    else:
        # Embeddings local avec sentence-transformers
        try:
            embeddings = _embedder.encode(texts, show_progress_bar=False)
            return embeddings.tolist()
        except Exception as e:
            _log.error(f"[RAG] Erreur embeddings local : {e}")
            return []


# Initialiser l'embedder au chargement du module
_init_embedder()


def _client() -> "QdrantClient":
    """Retourne le singleton QdrantClient, en le créant (ou recréant) si nécessaire."""
    global _qdrant_client, _qdrant_url
    current_url = Config.QDRANT_URL
    
    # Si on est déjà tombé en fallback local pendant cette session, on garde "local"
    if _qdrant_url == "local":
        current_url = "local"
        
    if _qdrant_client is None or _qdrant_url != current_url:
        if not current_url or current_url.lower() == "local":
            _qdrant_client = QdrantClient(path="data/qdrant_local")
            current_url = "local"
        else:
            try:
                _qdrant_client = QdrantClient(url=current_url)
                _qdrant_client.get_collections() # Test de connexion
            except Exception as e:
                _log.warning(f"[RAG] Serveur Qdrant inaccessible à {current_url} ({e}). Fallback local.")
                _qdrant_client = QdrantClient(path="data/qdrant_local")
                current_url = "local"
                
        _qdrant_url = current_url
        _log.info(f"[RAG] QdrantClient initialisé → {current_url}")
    return _qdrant_client


def reset_client():
    """Force la recréation du singleton au prochain appel (utile pour les tests)."""
    global _qdrant_client, _qdrant_url
    _qdrant_client = None
    _qdrant_url = None


def ensure_collection():
    if not QDRANT_OK:
        return False
    try:
        qc = _client()
        cols = {c.name: c for c in qc.get_collections().collections}

        if Config.QDRANT_COLLECTION in cols:
            # Vérifier que la dimension correspond
            info = qc.get_collection(Config.QDRANT_COLLECTION)
            existing_dim = info.config.params.vectors.size
            if existing_dim != Config.EMBEDDING_DIMENSION:
                _log.warning(
                    f"[RAG] Dimension mismatch : collection={existing_dim}, "
                    f"config={Config.EMBEDDING_DIMENSION}. Recréation…"
                )
                qc.delete_collection(Config.QDRANT_COLLECTION)
                # Recréer avec la bonne dimension
                qc.create_collection(
                    collection_name=Config.QDRANT_COLLECTION,
                    vectors_config=VectorParams(
                        size=Config.EMBEDDING_DIMENSION,
                        distance=Distance.COSINE,
                    ),
                )
                _log.info(f"[RAG] Collection recréée avec dim={Config.EMBEDDING_DIMENSION}")
        else:
            qc.create_collection(
                collection_name=Config.QDRANT_COLLECTION,
                vectors_config=VectorParams(
                    size=Config.EMBEDDING_DIMENSION,
                    distance=Distance.COSINE,
                ),
            )
            _log.info(f"[RAG] Collection créée avec dim={Config.EMBEDDING_DIMENSION}")

        return True
    except Exception as e:
        _log.warning(f"[RAG] Qdrant non disponible : {e}")
        return False


# ── Chunking hybride ───────────────────────────────────────────────────────
#
#   1. Détection du type de bloc (texte courant / code / tableau / liste)
#   2. Découpage adapté : phrases pour le texte, lignes pour le code/tableaux
#   3. Assemblage en chunks avec limite en tokens (estimation ou tiktoken)
#   4. Hard cap absolu : sous-découpage forcé si une unité dépasse la limite
#   5. Overlap mesuré en tokens, pas en nombre de phrases

# Ratio caractères → tokens pour l'estimation sans tiktoken.
# Texte : ~4 chars/token | Code dense : ~2.5 chars/token
# On prend 3.5 comme compromis conservateur (légèrement surestimé = plus sûr).
_CHARS_PER_TOKEN: float = 3.5


def _estimate_tokens(text: str) -> int:
    """
    Estime le nombre de tokens d'un texte.

    Utilise tiktoken (cl100k_base) si disponible pour une précision maximale,
    sinon fallback sur le ratio caractères/tokens.
    tiktoken est optionnel — pas de dépendance ajoutée au projet.
    """
    try:
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except ImportError:
        return max(1, int(len(text) / _CHARS_PER_TOKEN))


def _split_into_units(text: str) -> list[str]:
    """
    Découpe le texte en unités sémantiques minimales selon son contenu.

    Ordre de priorité :
      1. Blocs séparés par des lignes vides (paragraphes, blocs de code…)
      2. Au sein de chaque bloc :
         - Code / tableau / liste → découpage ligne par ligne
         - Texte courant          → découpage par phrases (ponctuation)
    """
    units: list[str] = []

    # Étape 1 : séparer par blocs (lignes vides multiples)
    paragraphs = re.split(r'\n{2,}', text.strip())

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        lines = para.splitlines()

        # Heuristique de détection code / tableau / liste
        is_structured = (
            # Indentation → code
            any(ln.startswith(('    ', '\t')) for ln in lines)
            # Tableau markdown
            or any(ln.strip().startswith('|') for ln in lines)
            # Bloc de code fencé
            or para.startswith('```')
            # Liste à puces / numérotée
            or any(re.match(r'^\s*[-*•]\s', ln) or re.match(r'^\s*\d+[.)]\s', ln)
                   for ln in lines)
            # Peu de ponctuation de fin de phrase → probablement du code
            or (len(lines) > 4 and sum(1 for ln in lines if re.search(r'[.!?]$', ln.strip()))
                < len(lines) * 0.2)
        )

        if is_structured:
            # Découpage ligne par ligne pour préserver la structure
            for line in lines:
                line = line.strip()
                if line:
                    units.append(line)
        else:
            # Découpage par phrases pour le texte courant
            sentences = re.split(r'(?<=[.!?])\s+', para)
            units.extend(s.strip() for s in sentences if s.strip())

    return units


def _chunk_text(
    text: str,
    max_tokens: int = 256,
    overlap_tokens: int = 32,
    hard_max_tokens: int = 512,
) -> list[str]:
    """
    Chunking hybride : unités sémantiques + limite en tokens.

    Paramètres :
        max_tokens       : taille cible d'un chunk (tokens estimés).
                           256 ≈ ~900 chars de texte FR.
        overlap_tokens   : chevauchement entre chunks consécutifs (tokens),
                           mesuré précisément plutôt qu'en nombre de phrases.
        hard_max_tokens  : limite absolue — toute unité dépassant ce seuil
                           est découpée de force, évitant la troncature
                           silencieuse par le modèle d'embedding.

    Garanties :
        - Aucun chunk ne dépasse hard_max_tokens (protection contre troncature)
        - Fonctionne sur du texte, du code, des tableaux et des contenus mixtes
        - Overlap stable en tokens quel que soit la longueur des phrases
        - Pas de dépendance externe obligatoire (tiktoken optionnel)
    """
    if not text or not text.strip():
        return []

    units = _split_into_units(text)
    if not units:
        return []

    # ── Sous-découpage des unités dépassant hard_max_tokens ────────────────
    chars_hard_max = int(hard_max_tokens * _CHARS_PER_TOKEN)
    chars_step     = int(max_tokens * _CHARS_PER_TOKEN)
    chars_overlap  = int(overlap_tokens * _CHARS_PER_TOKEN)

    safe_units: list[str] = []
    for unit in units:
        if len(unit) <= chars_hard_max:
            safe_units.append(unit)
        else:
            # Tranche forcée avec overlap en caractères
            pos = 0
            while pos < len(unit):
                safe_units.append(unit[pos : pos + chars_step])
                pos += chars_step - chars_overlap

    # ── Assemblage en chunks avec suivi des tokens ──────────────────────────
    chunks: list[str] = []
    current_units: list[str] = []
    current_tokens: int = 0

    def _flush() -> None:
        """Émet le chunk courant et prépare l'overlap pour le suivant."""
        nonlocal current_units, current_tokens
        if current_units:
            chunks.append(" ".join(current_units))
            # Conserver les dernières unités ≤ overlap_tokens
            kept: list[str] = []
            acc = 0
            for u in reversed(current_units):
                t = _estimate_tokens(u)
                if acc + t > overlap_tokens:
                    break
                kept.insert(0, u)
                acc += t
            current_units = kept
            current_tokens = acc

    for unit in safe_units:
        unit_tokens = _estimate_tokens(unit)

        # Une unité qui dépasse à elle seule max_tokens → chunk isolé
        if unit_tokens >= max_tokens:
            _flush()
            chunks.append(unit)
            current_units = []
            current_tokens = 0
            continue

        # Dépassement de la cible : émettre le chunk en cours avant d'ajouter
        if current_tokens + unit_tokens > max_tokens and current_units:
            _flush()

        current_units.append(unit)
        current_tokens += unit_tokens

    _flush()

    return [c for c in chunks if c.strip()]


def ingest_text(text: str, source: str = "manuel", conversation_id: str = None) -> int:
    """Découpe, embed et stocke dans Qdrant. Retourne le nombre de chunks."""
    if not QDRANT_OK or not EMBED_OK:
        return 0
    if not ensure_collection():
        return 0

    chunks = _chunk_text(text, max_tokens=256, overlap_tokens=32, hard_max_tokens=512)
    if not chunks:
        return 0

    embeddings = _get_embeddings(chunks)
    if not embeddings:
        return 0

    qc = _client()
    points = [
        PointStruct(
            id=str(uuid.uuid4()),
            vector=emb,
            payload={
                "text":            chunk,
                "source":          source,
                "conversation_id": conversation_id or "global",
            }
        )
        for chunk, emb in zip(chunks, embeddings)
    ]
    qc.upsert(collection_name=Config.QDRANT_COLLECTION, points=points)
    return len(chunks)


def ingest_file(path: str, conversation_id: str = None) -> int:
    """Ingère un fichier (txt, md, pdf)."""
    p = Path(path)
    if not p.exists():
        return 0

    text = ""
    if p.suffix.lower() == ".pdf":
        try:
            import fitz
            doc = fitz.open(str(p))
            text = "\n".join(page.get_text() for page in doc)
        except ImportError:
            return 0
    else:
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return 0

    return ingest_text(text, source=p.name, conversation_id=conversation_id)


def _make_scope_filter(conversation_id: str = None):
    """
    Construit le filtre Qdrant selon le scope :
    - conversation_id=None  → global uniquement (conversation_id == "global")
    - conversation_id=str   → cette conversation OU global (union des deux)

    Retourne None si aucun filtre ne doit être appliqué (collections externes).
    """
    global_cond = FieldCondition(key="conversation_id", match=MatchValue(value="global"))
    if not conversation_id:
        return Filter(must=[global_cond])
    conv_cond = FieldCondition(key="conversation_id", match=MatchValue(value=conversation_id))
    return Filter(should=[global_cond, conv_cond])


def search(query: str, top_k: int = 5, conversation_id: str = None, collection_name: str = None) -> list[dict]:
    """Recherche sémantique combinant docs globaux + docs de la conversation.

    Utilise query_points() (qdrant-client >= 1.7).
    """
    _log.debug(f"[RAG] search() — QDRANT_OK={QDRANT_OK} EMBED_OK={EMBED_OK} collection={collection_name!r} query={query[:80]!r}")

    if not QDRANT_OK or not EMBED_OK:
        _log.warning(f"[RAG] search() abandonnée — QDRANT_OK={QDRANT_OK} EMBED_OK={EMBED_OK}")
        return []

    # Utiliser la collection spécifiée ou celle par défaut
    if collection_name is None:
        collection_name = Config.QDRANT_COLLECTION
        _log.debug(f"[RAG] collection par défaut : {collection_name!r}")

    # Vérifier que la collection existe
    try:
        qc = _client()
        collections = {c.name for c in qc.get_collections().collections}
        _log.debug(f"[RAG] collections disponibles : {sorted(collections)}")
        if collection_name not in collections:
            _log.warning(f"[RAG] Collection '{collection_name}' n'existe pas")
            return []
    except Exception as e:
        _log.error(f"[RAG] Erreur lors de la vérification de la collection : {e}")
        return []

    embeddings = _get_embeddings([query])
    if not embeddings:
        _log.warning("[RAG] _get_embeddings() a retourné une liste vide")
        return []

    _log.debug(f"[RAG] embedding obtenu (dim={len(embeddings[0])}), lancement query_points")

    # Détecter si la collection utilise des vecteurs nommés (format multi-vecteur).
    # Dans ce cas, query_points() exige le paramètre `using=<nom>`.
    # On prend le premier nom de vecteur disponible dont la dimension correspond.
    #
    # Le SDK Qdrant peut retourner :
    #   - un VectorParams (vecteur unique, anonyme) → pas de `using` nécessaire
    #   - un dict-like {nom: VectorParams}          → `using=nom` obligatoire
    vector_name: str | None = None
    try:
        info = qc.get_collection(collection_name)
        vc = info.config.params.vectors
        _log.debug(f"[RAG] type(vectors)={type(vc).__name__!r} valeur={vc!r}")
        # Certaines versions du SDK exposent un objet qui se comporte comme un dict
        # (ex: qdrant_client.models.VectorsConfig) — on tente items() dans tous les cas.
        try:
            items = list(vc.items())   # lève AttributeError si vecteur unique
            dim = len(embeddings[0])
            matching = [n for n, p in items if getattr(p, "size", None) == dim]
            if matching:
                vector_name = matching[0]
                _log.debug(f"[RAG] vecteurs nommés — using={vector_name!r}")
            else:
                _log.warning(
                    f"[RAG] Aucun vecteur de dim={dim} dans {collection_name!r} "
                    f"(disponibles : {[n for n, _ in items]})"
                )
                return []
        except AttributeError:
            # Vecteur unique anonyme — pas de `using` nécessaire
            _log.debug(f"[RAG] vecteur unique anonyme dans {collection_name!r}")
    except Exception as e:
        _log.warning(f"[RAG] Impossible d'inspecter {collection_name!r} : {e}")

    try:
        kwargs = dict(
            collection_name=collection_name,
            query=embeddings[0],
            limit=top_k,
            with_payload=True,
        )
        if vector_name is not None:
            kwargs["using"] = vector_name
        # Appliquer le filtre de scope uniquement pour la collection interne Prométhée.
        # Les collections externes n'ont pas de champ conversation_id dans leur payload —
        # appliquer le filtre retournerait 0 résultat.
        if collection_name == Config.QDRANT_COLLECTION:
            kwargs["query_filter"] = _make_scope_filter(conversation_id)
        else:
            _log.debug(f"[RAG] collection externe {collection_name!r} — pas de filtre de scope")
        response = qc.query_points(**kwargs)
        results = [
            {
                "text":   p.payload.get("text", ""),
                "source": p.payload.get("source", ""),
                "scope":  p.payload.get("conversation_id", "global"),
                "score":  p.score,
            }
            for p in response.points
        ]
        _log.debug(f"[RAG] query_points → {len(results)} résultat(s)")
        return results
    except Exception as e:
        _log.error(f"[RAG] Erreur lors de la recherche dans '{collection_name}': {e}")
        return []


def list_sources(conversation_id: str = None) -> list[dict]:
    """Retourne les sources visibles depuis une conversation.

    Retourne les docs globaux + ceux de la conversation.
    Chaque entrée : {"source": str, "count": int, "scope": "global"|"conversation"}
    """
    if not QDRANT_OK or not EMBED_OK:
        return []
    if not ensure_collection():
        return []
    try:
        qc = _client()
        # Agrégation : source → (count, scope)
        sources: dict[str, dict] = {}
        offset = None
        while True:
            result, offset = qc.scroll(
                collection_name=Config.QDRANT_COLLECTION,
                scroll_filter=_make_scope_filter(conversation_id),
                limit=256,
                offset=offset,
                with_payload=["source", "conversation_id"],
                with_vectors=False,
            )
            for point in result:
                src   = point.payload.get("source", "inconnu")
                scope = "global" if point.payload.get("conversation_id") == "global" \
                        else "conversation"
                if src not in sources:
                    sources[src] = {"count": 0, "scope": scope}
                sources[src]["count"] += 1
            if offset is None:
                break
        return [
            {"source": s, "count": v["count"], "scope": v["scope"]}
            for s, v in sorted(sources.items())
        ]
    except Exception as e:
        _log.error(f"[RAG] Erreur list_sources : {e}")
        return []


def delete_by_source(source: str, conversation_id: str = None) -> int:
    """Supprime tous les chunks d'une source.

    Si conversation_id est fourni, ne supprime que les chunks de cette
    conversation (pas les chunks globaux du même nom).
    Passe conversation_id=None pour supprimer un doc global.
    """
    if not QDRANT_OK:
        return 0
    if not ensure_collection():
        return 0
    try:
        qc = _client()
        scope_value = "global" if conversation_id is None else conversation_id
        must = [
            FieldCondition(key="source",          match=MatchValue(value=source)),
            FieldCondition(key="conversation_id", match=MatchValue(value=scope_value)),
        ]
        count_before = qc.count(
            collection_name=Config.QDRANT_COLLECTION,
            count_filter=Filter(must=must),
            exact=True,
        ).count
        qc.delete(
            collection_name=Config.QDRANT_COLLECTION,
            points_selector=FilterSelector(filter=Filter(must=must)),
        )
        _log.info(f"[RAG] Supprimé {count_before} chunks — source='{source}' scope='{scope_value}'")
        return count_before
    except Exception as e:
        _log.error(f"[RAG] Erreur delete_by_source : {e}")
        return 0


def build_rag_context(query: str, conversation_id: str = None, collection_name: str = None) -> str:
    """Construit le contexte RAG (global + conversation) à injecter dans le prompt."""
    _log.debug(f"[RAG] build_rag_context() — collection={collection_name!r} conv={conversation_id!r}")
    hits = search(query, top_k=5, conversation_id=conversation_id, collection_name=collection_name)
    if not hits:
        _log.warning(f"[RAG] build_rag_context() — aucun résultat pour : {query[:80]!r}")
        return ""
    _log.debug(f"[RAG] build_rag_context() — {len(hits)} chunk(s) injectés dans le prompt")
    parts = ["### Contexte documentaire pertinent :\n"]
    for i, h in enumerate(hits, 1):
        tag = "🌐" if h["scope"] == "global" else "💬"
        parts.append(
            f"[{i}] {tag} ({h['source']}, score={h['score']:.2f})\n{h['text']}\n"
        )
    return "\n".join(parts)


def is_available() -> bool:
    return QDRANT_OK and EMBED_OK


def list_collections() -> list[str]:
    """Retourne la liste des noms de collections disponibles dans Qdrant."""
    if not QDRANT_OK:
        return []
    try:
        qc = _client()
        collections = qc.get_collections().collections
        return [c.name for c in collections]
    except Exception as e:
        _log.error(f"[RAG] Erreur lors de la récupération des collections : {e}")
        return []
