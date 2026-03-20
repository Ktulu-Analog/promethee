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

Deux backends de recherche coexistent :

  • Backend Qdrant (mode historique) — recherche vectorielle dense via qdrant-client.
    Actif quand aucune collection Albert n'est configurée (RAG_ALBERT_COLLECTION_IDS vide).

  • Backend Albert (mode amélioré) — recherche hybride dense+sparse (BGE-M3) via
    l'API Albert /v1/search, suivie d'un reranking cross-encoder (BGE-Reranker-v2-M3)
    via /v1/rerank. Actif quand RAG_ALBERT_COLLECTION_IDS contient au moins un ID.

build_rag_context() choisit automatiquement le backend selon la configuration.
Les deux backends produisent le même format de sortie : liste de dicts
  {"text": str, "source": str, "scope": str, "score": float}
"""
import logging
import uuid
import re
from pathlib import Path
from typing import Optional
from .config import Config, get_safe_user_id

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


# ══════════════════════════════════════════════════════════════════════════════
#  Backend Albert — recherche hybride BGE-M3 + reranking BGE-Reranker-v2-M3
# ══════════════════════════════════════════════════════════════════════════════
#
#  L'API Albert (OpenGateLLM) expose :
#    POST /v1/search  — recherche hybride/sémantique/lexicale dans des collections
#                       Albert gérées côté serveur (IDs entiers).
#    POST /v1/rerank  — cross-encoder BGE-Reranker-v2-M3 pour scorer des paires
#                       (query, passage) et produire un classement affiné.
#
#  Flux complet :
#    1. /v1/search(method=hybrid, collection_ids=[…], limit=RAG_TOP_K)
#       → candidats bruts triés par score RRF (dense BGE-M3 + sparse BM25)
#    2. /v1/rerank(query, documents=[chunk.text for chunk in candidats], top_n=RAG_MAX_CHUNKS_TOTAL)
#       → scores logit du cross-encoder, réordonnancement, filtre RAG_RERANK_MIN_SCORE
#    3. Diversification par source (RAG_MAX_CHUNKS_PER_SOURCE) + plafond total
#
#  En cas d'erreur Albert (réseau, auth…), on logue et on retourne [].
#  Le fallback vers Qdrant n'est PAS automatique pour ne pas masquer les erreurs.

import urllib.request
import urllib.error
import json as _json


def _albert_base_url() -> str:
    """Retourne l'URL de base de l'API Albert, sans le suffixe /v1.

    OPENAI_API_BASE est typiquement "https://albert.api.etalab.gouv.fr/v1".
    Les endpoints non-standard (/v1/search, /v1/rerank, /v1/collections) sont
    appelés via le client OpenAI qui ajoute lui-même le préfixe /v1.
    On retire donc le /v1 final pour éviter le doublon /v1/v1/…
    """
    base = Config.OPENAI_API_BASE.rstrip("/")
    if base.endswith("/v1"):
        base = base[:-3]
    return base


def _get_openai_client():
    """Retourne le client OpenAI disponible (embedder en mode API).

    Utilisé pour les appels non-standard via ._client.request().
    Retourne None si le client n'est pas initialisé ou pas en mode API.
    """
    if _embedder_type == "api" and _embedder is not None:
        return _embedder
    # Tentative de création à la volée si les credentials sont disponibles
    base = _albert_base_url()
    key  = Config.OPENAI_API_KEY
    if base and key:
        try:
            from openai import OpenAI
            return OpenAI(base_url=base + "/v1", api_key=key)
        except Exception:
            pass
    return None


def _albert_request(method: str, path: str, **kwargs) -> dict | None:
    """
    Effectue une requête HTTP sur l'API Albert.

    Stratégie de transport (par ordre de préférence) :
      1. Client OpenAI (._client.request) — utilise la session httpx configurée,
         gère auth et base_url automatiquement. C'est la méthode que l'autre appli
         utilise et qui fonctionne.
      2. urllib (stdlib) — fallback si le client OpenAI n'est pas disponible.
         Construit l'URL manuellement depuis _albert_base_url() (sans /v1).

    Parameters
    ----------
    method  : "GET" ou "POST"
    path    : chemin relatif sans base, ex: "/v1/collections" ou "/v1/search"
    kwargs  : params= pour GET, json= pour POST
    """
    # ── Stratégie 1 : client OpenAI ._client.request() ──────────────
    oa_client = _get_openai_client()
    if oa_client is not None:
        try:
            # ._client est le httpx.Client sous-jacent du SDK OpenAI.
            # Il utilise base_url + path, où base_url = https://host/v1/
            # et path ne doit PAS commencer par /v1 pour éviter le doublon.
            # On retire donc le préfixe /v1 du path.
            rel_path = path.lstrip("/")
            if rel_path.startswith("v1/"):
                rel_path = rel_path[3:]

            headers = {"Authorization": f"Bearer {Config.OPENAI_API_KEY}"}

            if method == "GET":
                resp = oa_client._client.request(
                    method="GET",
                    url=rel_path,
                    params=kwargs.get("params", {}),
                    headers=headers,
                )
            else:
                resp = oa_client._client.request(
                    method="POST",
                    url=rel_path,
                    json=kwargs.get("json", {}),
                    headers=headers,
                )

            if resp.status_code != 200:
                body = resp.text[:300] if hasattr(resp, "text") else ""
                _log.error("[Albert] HTTP %d sur %s : %s", resp.status_code, path, body)
                return None

            return resp.json()

        except Exception as e:
            _log.warning("[Albert] client OpenAI échoué (%s), fallback urllib", e)
            # on continue vers le fallback

    # ── Stratégie 2 : urllib (fallback) ─────────────────────────────
    base = _albert_base_url()
    if not base:
        return None

    url = f"{base}{path}"  # base est sans /v1, path contient /v1/...
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {Config.OPENAI_API_KEY}",
    }

    try:
        if method == "GET":
            params = kwargs.get("params", {})
            if params:
                from urllib.parse import urlencode
                url = f"{url}?{urlencode(params)}"
            req = urllib.request.Request(url, headers=headers, method="GET")
        else:
            data = _json.dumps(kwargs.get("json", {})).encode("utf-8")
            req = urllib.request.Request(url, data=data, headers=headers, method="POST")

        with urllib.request.urlopen(req, timeout=30) as resp:
            return _json.loads(resp.read().decode("utf-8"))

    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", errors="replace")[:300]
        except Exception:
            pass
        _log.error("[Albert] urllib HTTP %d sur %s : %s", e.code, path, body)
        return None
    except Exception as e:
        _log.error("[Albert] urllib erreur réseau sur %s : %s", path, e)
        return None


def _albert_post(endpoint: str, payload: dict) -> dict | None:
    """POST JSON sur l'API Albert. Conservé pour compatibilité."""
    return _albert_request("POST", endpoint, json=payload)


def _albert_get(path: str, params: dict | None = None) -> dict | None:
    """GET sur l'API Albert."""
    return _albert_request("GET", path, params=params or {})


def _albert_search(
    query: str,
    collection_ids: list[int],
    limit: int,
    method: str = "hybrid",
    rff_k: int = 60,
) -> list[dict]:
    """
    Appelle POST /v1/search et retourne les chunks sous le format interne
    {"text": str, "source": str, "scope": str, "score": float}.

    Parameters
    ----------
    query          : question de l'utilisateur (brute ou reformulée)
    collection_ids : IDs entiers des collections Albert à interroger
    limit          : nombre maximum de candidats à récupérer (RAG_TOP_K)
    method         : "hybrid" | "semantic" | "lexical"
    rff_k          : constante RRF pour le mode hybrid (recommandé : 10–100)
    """
    if not collection_ids:
        return []

    payload = {
        "query":          query,
        "collection_ids": collection_ids,
        "limit":          limit,
        "method":         method,
        "rff_k":          rff_k,
        "score_threshold": 0.0,   # pas de pré-filtre ici : on laisse le reranker décider
    }
    _log.debug(
        "[Albert] search — method=%s collections=%s limit=%d query=%r",
        method, collection_ids, limit, query[:80],
    )

    resp = _albert_post("/v1/search", payload)
    if resp is None:
        return []

    results = []
    for item in resp.get("data", []):
        chunk = item.get("chunk", {})
        text  = chunk.get("content", "") or chunk.get("text", "")
        # "metadata" peut contenir un champ "document_name" ou "source"
        meta   = chunk.get("metadata") or {}
        source = (
            meta.get("document_name")
            or meta.get("source")
            or meta.get("filename")
            or chunk.get("document_id", "albert")
        )
        # Convertir l'ID entier en str lisible si pas d'autre nom disponible
        if isinstance(source, int):
            source = f"document#{source}"
        results.append({
            "text":   str(text),
            "source": str(source),
            "scope":  "global",          # collections Albert = scope global
            "score":  float(item.get("score", 0.0)),
        })

    _log.debug("[Albert] search → %d candidat(s)", len(results))
    return results


def _albert_rerank(
    query: str,
    candidates: list[dict],
    top_n: int,
    model: str,
    min_score: float,
) -> list[dict]:
    """
    Appelle POST /v1/rerank sur les candidats et retourne la liste
    réordonnée + filtrée, en conservant le format interne des chunks.

    Le reranker BGE-Reranker-v2-M3 produit des scores logit (non bornés).
    Valeurs typiques : négatif = hors-sujet, > 0 = pertinent, > 5 = très pertinent.

    Parameters
    ----------
    query      : question de l'utilisateur
    candidates : chunks au format interne {"text", "source", "scope", "score"}
    top_n      : nombre de chunks à retourner après reranking
    model      : ID du modèle reranker (ex: "BAAI/bge-reranker-v2-m3")
    min_score  : score logit minimal pour conserver un chunk
    """
    if not candidates:
        return []

    texts = [c["text"] for c in candidates]
    payload = {
        "query":     query,
        "documents": texts,
        "model":     model,
        "top_n":     top_n,
    }
    _log.debug(
        "[Albert] rerank — model=%s top_n=%d n_docs=%d",
        model, top_n, len(texts),
    )

    resp = _albert_post("/v1/rerank", payload)
    if resp is None:
        # Fallback gracieux : conserver les candidats dans l'ordre original
        _log.warning("[Albert] rerank échoué — conservation de l'ordre vectoriel")
        return candidates[:top_n]

    reranked = []
    for result in resp.get("results", []):
        idx   = result.get("index", -1)
        score = float(result.get("relevance_score", 0.0))
        if idx < 0 or idx >= len(candidates):
            continue
        if score < min_score:
            _log.debug(
                "[Albert] chunk #%d écarté par reranker (score=%.3f < min=%.3f)",
                idx, score, min_score,
            )
            continue
        chunk = dict(candidates[idx])
        chunk["score"] = score          # remplacer le score vectoriel par le score cross-encoder
        chunk["_reranked"] = True       # marqueur interne, retiré avant injection dans le prompt
        reranked.append(chunk)

    _log.debug("[Albert] rerank → %d chunk(s) retenus", len(reranked))
    return reranked



def _diversify_chunks(
    candidates: list[dict],
    max_per_source: int,
    max_total: int,
    strip_keys: frozenset = frozenset(),
) -> list[dict]:
    """
    Diversification par source + plafond total.

    Sélectionne les chunks en limitant la représentation de chaque source
    à max_per_source entrées et le total à max_total entrées.

    Parameters
    ----------
    candidates : list[dict]
        Chunks candidats au format interne {text, source, scope, score, …}.
    max_per_source : int
        Nombre maximal de chunks conservés pour une même source.
    max_total : int
        Nombre total maximal de chunks retournés.
    strip_keys : frozenset
        Clés internes à retirer de chaque chunk avant de le servir
        (ex : {"_reranked"} pour le backend Albert).

    Returns
    -------
    list[dict]
        Chunks sélectionnés, sans les clés internes demandées.
    """
    per_source: dict[str, int] = {}
    selected: list[dict] = []
    for chunk in candidates:
        src   = chunk["source"]
        count = per_source.get(src, 0)
        if count < max_per_source:
            clean = {k: v for k, v in chunk.items() if k not in strip_keys}
            selected.append(clean)
            per_source[src] = count + 1
        if len(selected) >= max_total:
            break
    return selected


def _albert_search_and_rerank(query: str, force_collection_ids: list[int] | None = None) -> list[dict]:
    """
    Pipeline complet Albert pour une requête :
      1. Recherche hybride BGE-M3 (dense + sparse, RRF)
      2. Reranking BGE-Reranker-v2-M3
      3. Diversification par source + plafond total

    Parameters
    ----------
    query               : question de l'utilisateur
    force_collection_ids: si fourni, utilise ces IDs au lieu de get_albert_collection_ids()
                          (permet de cibler une seule collection sélectionnée dans le panneau)

    Retourne les chunks au format interne, prêts pour build_rag_context().
    """
    collection_ids = force_collection_ids if force_collection_ids is not None else get_albert_collection_ids()
    if not collection_ids:
        return []

    # ── HyDE : reformulation de la requête avant recherche ────────────
    # Le document hypothétique est utilisé pour la recherche vectorielle dense.
    # Le reranker cross-encoder reçoit toujours la requête originale (plus précis
    # pour scorer la pertinence réelle vis-à-vis de l'intention de l'utilisateur).
    search_query = _hyde_expand_query(query)

    # ── Étape 1 : recherche hybride ────────────────────────────────────
    candidates = _albert_search(
        query=search_query,
        collection_ids=collection_ids,
        limit=Config.RAG_TOP_K,
        method=Config.RAG_SEARCH_METHOD,
        rff_k=Config.RAG_RFF_K,
    )
    if not candidates:
        return []

    # ── Étape 2 : reranking ────────────────────────────────────────────
    if Config.RAG_RERANK_ENABLED:
        candidates = _albert_rerank(
            query=query,
            candidates=candidates,
            top_n=Config.RAG_MAX_CHUNKS_TOTAL * 2,  # marge avant diversification
            model=Config.RAG_RERANK_MODEL,
            min_score=Config.RAG_RERANK_MIN_SCORE,
        )

    # ── Étape 3 : diversification par source + plafond total ──────────
    selected = _diversify_chunks(
        candidates,
        max_per_source=Config.RAG_MAX_CHUNKS_PER_SOURCE,
        max_total=Config.RAG_MAX_CHUNKS_TOTAL,
        strip_keys=frozenset({"_reranked"}),
    )
    _log.debug(
        "[Albert] pipeline complet → %d chunk(s) retenus, %d source(s) distincte(s)",
        len(selected), len({c["source"] for c in selected}),
    )
    return selected


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
            _log.info("[RAG] Embeddings API initialisé : %s", Config.EMBEDDING_MODEL)
        except ImportError:
            _log.error("[RAG] OpenAI non disponible pour embeddings API")
            EMBED_OK = False
    else:
        # Mode local : utiliser sentence-transformers
        try:
            from sentence_transformers import SentenceTransformer
            _embedder = SentenceTransformer(Config.EMBEDDING_MODEL)
            _embedder_type = "local"
            EMBED_OK = True
            _log.info("[RAG] Embeddings local initialisé : %s", Config.EMBEDDING_MODEL)
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
            _log.error("[RAG] Erreur embeddings API : %s", e)
            return []
    else:
        # Embeddings local avec sentence-transformers
        try:
            embeddings = _embedder.encode(texts, show_progress_bar=False)
            return embeddings.tolist()
        except Exception as e:
            _log.error("[RAG] Erreur embeddings local : %s", e)
            return []


# Initialiser l'embedder au chargement du module
_init_embedder()


# ══════════════════════════════════════════════════════════════════════════════
#  HyDE — Hypothetical Document Embedding
# ══════════════════════════════════════════════════════════════════════════════
#
#  Principe : au lieu d'embedder la requête brute de l'utilisateur (courte,
#  conversationnelle), on demande au LLM de rédiger un court document
#  hypothétique qui *répondrait* à cette requête.
#  Ce document synthétique est sémantiquement plus proche des chunks indexés
#  (qui sont des extraits de documents) → meilleure précision de retrieval.
#
#  Référence : Gao et al., 2022 — "Precise Zero-Shot Dense Retrieval without
#  Relevance Labels" (HyDE). Implémentation adaptée au contexte Prométhée :
#  on utilise le LLM déjà configuré (OpenAI-compatible ou Ollama).
#
#  Activation : RAG_HYDE_ENABLED=ON dans .env
#  Coût       : 1 appel LLM supplémentaire par requête RAG (latence +0.3–1s)


def _hyde_generate(query: str) -> str:
    """Génère un document hypothétique pour la requête via le LLM configuré.

    Retourne le texte généré, ou la requête originale en cas d'échec
    (dégradation gracieuse : le RAG continue de fonctionner normalement).

    Utilise le modèle assigné à la famille 'rag_tools' depuis l'onglet Outils
    des paramètres. Si aucun modèle n'est assigné, utilise le modèle principal.
    """
    prompt = (
        "Rédige un court extrait de document (3 à 5 phrases) qui répondrait "
        "directement à la question suivante. Ne donne que le contenu du document, "
        "sans introduction ni formule de politesse.\n\n"
        f"Question : {query}"
    )

    try:
        from core.llm_clients import build_family_client
        client, model = build_family_client("rag_tools")
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=Config.RAG_HYDE_MAX_TOKENS,
            temperature=0.3,
        )
        doc = resp.choices[0].message.content.strip()
        if doc:
            _log.debug("[HyDE] document hypothétique généré (%d chars) via %s", len(doc), model)
            return doc
    except Exception as e:
        _log.warning("[HyDE] Échec LLM : %s — fallback requête brute", e)

    # Dégradation gracieuse
    _log.debug("[HyDE] aucun LLM disponible — utilisation de la requête brute")
    return query


def _hyde_expand_query(query: str) -> str:
    """Retourne le texte à embedder selon que HyDE est activé ou non.

    Point d'entrée unique utilisé par search() et _albert_search_and_rerank().
    Si RAG_HYDE_ENABLED=OFF, retourne la requête brute sans appel LLM.
    """
    if not Config.RAG_HYDE_ENABLED:
        return query
    return _hyde_generate(query)


# ══════════════════════════════════════════════════════════════════════════════
#  Chunking contextuel — Anthropic Contextual Retrieval
# ══════════════════════════════════════════════════════════════════════════════
#
#  Principe : avant d'embedder chaque chunk, le LLM génère un court préfixe
#  contextuel qui replace ce chunk dans son document parent.
#  Exemple : "Ce passage décrit la procédure de résiliation d'un contrat
#  d'assurance vie dans la section 4.2 des conditions générales."
#
#  Ce préfixe est concaténé au début du chunk avant l'embedding ET stocké
#  dans le payload Qdrant (champ "context_prefix") pour traçabilité.
#
#  Référence : Anthropic, "Contextual Retrieval" (2024).
#  https://www.anthropic.com/news/contextual-retrieval
#
#  Activation : RAG_CONTEXTUAL_CHUNKING=ON dans .env
#  Coût       : 1 appel LLM par chunk à l'ingestion (batch possible)
#  Important  : nécessite une réingestion des documents existants.


def _contextual_prefix_batch(
    document: str,
    chunks: list[str],
) -> list[str]:
    """Génère un préfixe contextuel pour chaque chunk via le LLM.

    Envoie un seul appel LLM par chunk (pas de vrai batching côté API,
    mais la boucle est courte pour les corpus documentaires typiques).

    Retourne une liste de préfixes de même longueur que `chunks`.
    En cas d'échec pour un chunk individuel, retourne une chaîne vide
    pour ce chunk (le texte brut est toujours embedé).
    """
    doc_excerpt = document[: Config.RAG_CONTEXTUAL_DOC_MAX_CHARS]
    prefixes: list[str] = []

    for i, chunk in enumerate(chunks):
        system_prompt = (
            "Tu es un assistant qui aide à contextualiser des extraits de documents. "
            "Réponds uniquement avec le contexte demandé, sans introduction."
        )
        user_prompt = (
            "<document>\n"
            f"{doc_excerpt}\n"
            "</document>\n\n"
            "Voici l'extrait à contextualiser :\n"
            "<chunk>\n"
            f"{chunk}\n"
            "</chunk>\n\n"
            "Génère une courte phrase (max 2 phrases) qui situe cet extrait dans "
            "le document : de quoi parle-t-il globalement, dans quel contexte "
            "apparaît-il ? Ne répète pas le contenu de l'extrait."
        )

        prefix = ""

        # Résoudre le client et le modèle via le registre de familles.
        # Utilise le modèle assigné à 'rag_tools' depuis l'onglet Outils,
        # ou RAG_INGESTION_MODEL, ou le modèle principal en dernier recours.
        try:
            from core.llm_clients import build_family_client
            client, model = build_family_client("rag_tools")
            # Surcharge par RAG_INGESTION_MODEL si explicitement défini
            if Config.RAG_INGESTION_MODEL:
                model = Config.RAG_INGESTION_MODEL
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": user_prompt},
                ],
                max_tokens=Config.RAG_CONTEXTUAL_PREFIX_MAX_TOKENS,
                temperature=0.1,
            )
            prefix = resp.choices[0].message.content.strip()
        except Exception as e:
            _log.warning("[CTX] chunk %d/%d — échec LLM : %s", i + 1, len(chunks), e)

        prefixes.append(prefix)

    success = sum(1 for p in prefixes if p)
    _log.debug("[CTX] %d/%d préfixes contextuels générés", success, len(chunks))
    return prefixes


def _client() -> "QdrantClient":
    """Retourne le singleton QdrantClient, en le créant (ou recréant) si nécessaire.

    La connexion est réutilisée entre tous les appels RAG au sein du même
    processus. Si l'URL de configuration change (rare, mais possible lors
    d'un rechargement de .env à chaud), le client est recréé automatiquement.
    """
    global _qdrant_client, _qdrant_url
    current_url = Config.QDRANT_URL
    if _qdrant_client is None or _qdrant_url != current_url:
        _qdrant_client = QdrantClient(url=current_url)
        _qdrant_url = current_url
        _log.info("[RAG] QdrantClient initialisé → %s", current_url)
    return _qdrant_client


def reset_client():
    """Force la recréation du singleton au prochain appel (utile pour les tests)."""
    global _qdrant_client, _qdrant_url
    _qdrant_client = None
    _qdrant_url = None


def ensure_collection(collection_name: str = None):
    """Crée la collection Qdrant si elle n'existe pas, et vérifie la dimension.

    Parameters
    ----------
    collection_name : str, optional
        Nom de la collection à vérifier/créer. Défaut : Config.QDRANT_COLLECTION.
    """
    if not QDRANT_OK:
        return False
    target = collection_name or Config.QDRANT_COLLECTION
    try:
        qc = _client()
        cols = {c.name: c for c in qc.get_collections().collections}

        if target in cols:
            # Vérifier que la dimension correspond
            info = qc.get_collection(target)
            existing_dim = info.config.params.vectors.size
            if existing_dim != Config.EMBEDDING_DIMENSION:
                _log.warning(
                    f"[RAG] Dimension mismatch : collection={existing_dim}, "
                    f"config={Config.EMBEDDING_DIMENSION}. Recréation…"
                )
                qc.delete_collection(target)
                # Recréer avec la bonne dimension
                qc.create_collection(
                    collection_name=target,
                    vectors_config=VectorParams(
                        size=Config.EMBEDDING_DIMENSION,
                        distance=Distance.COSINE,
                    ),
                )
                _log.info("[RAG] Collection '%s' recréée avec dim=%s", target, Config.EMBEDDING_DIMENSION)
        else:
            qc.create_collection(
                collection_name=target,
                vectors_config=VectorParams(
                    size=Config.EMBEDDING_DIMENSION,
                    distance=Distance.COSINE,
                ),
            )
            _log.info("[RAG] Collection '%s' créée avec dim=%s", target, Config.EMBEDDING_DIMENSION)

        return True
    except Exception as e:
        _log.warning("[RAG] Qdrant non disponible : %s", e)
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


def ingest_text(text: str, source: str = "manuel", conversation_id: str = None,
                collection_name: str = None, extra_payload: dict = None) -> int:
    """Découpe, embed et stocke dans Qdrant. Retourne le nombre de chunks.

    Parameters
    ----------
    text : str
        Texte à ingérer.
    source : str
        Identifiant de la source (nom de fichier, URL, "memory:<conv_id>"…).
    conversation_id : str, optional
        Scope de la conversation (None → "global").
    collection_name : str, optional
        Collection Qdrant cible. Défaut : Config.QDRANT_COLLECTION.
        La collection doit appartenir à l'utilisateur courant (_is_own_collection).
    extra_payload : dict, optional
        Champs supplémentaires ajoutés au payload de chaque point Qdrant.
        Utilisé par LongTermMemory pour marquer les chunks consolidés
        (_consolidated=True) et éviter leur inclusion dans les cycles suivants.
    """
    if not QDRANT_OK or not EMBED_OK:
        return 0

    target = collection_name or Config.QDRANT_COLLECTION

    # Protection : on n'écrit jamais dans une collection d'un autre utilisateur
    if not _is_own_collection(target):
        _log.warning("[RAG] ingest_text refusé : collection '%s' non autorisée", target)
        return 0

    if not ensure_collection(target):
        return 0

    chunks = _chunk_text(text, max_tokens=256, overlap_tokens=32, hard_max_tokens=512)
    if not chunks:
        return 0

    # ── Chunking contextuel (Anthropic Contextual Retrieval) ──────────────
    # Si activé, enrichit chaque chunk avec un préfixe contextuel LLM avant
    # l'embedding. Le texte embedé = "préfixe\n\nchunk" mais on stocke les
    # deux séparément dans le payload pour traçabilité et débogage.
    context_prefixes: list[str] = []
    if Config.RAG_CONTEXTUAL_CHUNKING:
        _log.info("[CTX] génération des préfixes contextuels pour %d chunks (source=%r)…", len(chunks), source)
        context_prefixes = _contextual_prefix_batch(text, chunks)
    else:
        context_prefixes = [""] * len(chunks)

    # Textes à embedder : "préfixe\n\nchunk" si préfixe disponible, sinon chunk brut
    texts_to_embed = [
        f"{prefix}\n\n{chunk}" if prefix else chunk
        for prefix, chunk in zip(context_prefixes, chunks)
    ]

    embeddings = _get_embeddings(texts_to_embed)
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
                # Préfixe contextuel stocké pour traçabilité (vide si CTX désactivé)
                **({"context_prefix": prefix} if prefix else {}),
                **(extra_payload or {}),
            }
        )
        for chunk, emb, prefix in zip(chunks, embeddings, context_prefixes)
    ]
    qc.upsert(collection_name=target, points=points)
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


def _is_own_collection(collection_name: str) -> bool:
    """Vérifie que la collection appartient à l'utilisateur courant.

    Une collection est considérée comme appartenant à l'utilisateur si :
      - c'est sa collection RAG documentaire (Config.QDRANT_COLLECTION), ou
      - c'est sa collection LTM (Config.LTM_COLLECTION), ou
      - son nom est exactement "promethee_<user_id>" ou
        "promethee_memory_<user_id>" (nommage automatique).

    Les collections d'autres utilisateurs (promethee_marie quand on est pierre)
    et les collections externes (sans préfixe promethee_) sont refusées.
    """
    # Correspondance directe avec les collections configurées
    if collection_name in (Config.QDRANT_COLLECTION, Config.LTM_COLLECTION):
        return True

    # Reconstruire les deux noms attendus depuis le user_id.
    # get_safe_user_id() est la source unique de vérité (définie dans config.py) ;
    # on évite ainsi de dupliquer ici la logique de résolution RAG_USER_ID / getuser().
    safe = get_safe_user_id()
    return collection_name in (f"promethee_{safe}", f"promethee_memory_{safe}")


def search(query: str, top_k: int = 5, conversation_id: str = None, collection_name: str = None) -> list[dict]:
    """Recherche sémantique combinant docs globaux + docs de la conversation.

    Utilise query_points() (qdrant-client >= 1.7).
    """
    _log.debug("[RAG] search() — QDRANT_OK=%s EMBED_OK=%s collection=%r query=%r", QDRANT_OK, EMBED_OK, collection_name, query[:80])

    if not QDRANT_OK or not EMBED_OK:
        _log.warning("[RAG] search() abandonnée — QDRANT_OK=%s EMBED_OK=%s", QDRANT_OK, EMBED_OK)
        return []

    # Utiliser la collection spécifiée ou celle par défaut
    if collection_name is None:
        collection_name = Config.QDRANT_COLLECTION
        _log.debug("[RAG] collection par défaut : %r", collection_name)

    # Vérifier que la collection appartient à l'utilisateur courant.
    # Les collections internes d'autres utilisateurs sont refusées en lecture.
    # Les collections externes (sans préfixe promethee_) sont autorisées en lecture seule
    # car elles peuvent être des sources documentaires partagées intentionnellement.
    if collection_name.startswith("promethee_") and not _is_own_collection(collection_name):
        _log.warning("[RAG] search refusé : collection '%s' appartient à un autre utilisateur", collection_name)
        return []

    # Vérifier que la collection existe
    try:
        qc = _client()
        collections = {c.name for c in qc.get_collections().collections}
        _log.debug("[RAG] collections disponibles : %s", sorted(collections))
        if collection_name not in collections:
            _log.warning("[RAG] Collection '%s' n'existe pas", collection_name)
            return []
    except Exception as e:
        _log.error("[RAG] Erreur lors de la vérification de la collection : %s", e)
        return []

    embeddings = _get_embeddings([_hyde_expand_query(query)])
    if not embeddings:
        _log.warning("[RAG] _get_embeddings() a retourné une liste vide")
        return []

    _log.debug("[RAG] embedding obtenu (dim=%s), lancement query_points", len(embeddings[0]))

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
        _log.debug("[RAG] type(vectors)=%r valeur=%r", type(vc).__name__, vc)
        # Certaines versions du SDK exposent un objet qui se comporte comme un dict
        # (ex: qdrant_client.models.VectorsConfig) — on tente items() dans tous les cas.
        try:
            items = list(vc.items())   # lève AttributeError si vecteur unique
            dim = len(embeddings[0])
            matching = [n for n, p in items if getattr(p, "size", None) == dim]
            if matching:
                vector_name = matching[0]
                _log.debug("[RAG] vecteurs nommés — using=%r", vector_name)
            else:
                _log.warning(
                    f"[RAG] Aucun vecteur de dim={dim} dans {collection_name!r} "
                    f"(disponibles : {[n for n, _ in items]})"
                )
                return []
        except AttributeError:
            # Vecteur unique anonyme — pas de `using` nécessaire
            _log.debug("[RAG] vecteur unique anonyme dans %r", collection_name)
    except Exception as e:
        _log.warning("[RAG] Impossible d'inspecter %r : %s", collection_name, e)

    try:
        kwargs = dict(
            collection_name=collection_name,
            query=embeddings[0],
            limit=top_k,
            with_payload=True,
        )
        if vector_name is not None:
            kwargs["using"] = vector_name
        # Appliquer le filtre de scope uniquement pour les collections internes Prométhée.
        # Les collections externes n'ont pas de champ conversation_id dans leur payload —
        # appliquer le filtre retournerait 0 résultat.
        # Une collection est considérée interne si elle porte le préfixe "promethee_"
        # (nommage automatique multi-postes) ou si c'est explicitement la collection
        # configurée (QDRANT_COLLECTION forcé via .env).
        is_internal = (
            collection_name.startswith("promethee_")
            or collection_name == Config.QDRANT_COLLECTION
        )
        if is_internal:
            kwargs["query_filter"] = _make_scope_filter(conversation_id)
        else:
            _log.debug("[RAG] collection externe %r — pas de filtre de scope", collection_name)
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
        _log.debug("[RAG] query_points → %s résultat(s)", len(results))
        return results
    except Exception as e:
        _log.error("[RAG] Erreur lors de la recherche dans '%s': %s", collection_name, e)
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
        _log.error("[RAG] Erreur list_sources : %s", e)
        return []


def delete_by_source(source: str, conversation_id: str = None,
                     collection_name: str = None) -> int:
    """Supprime tous les chunks d'une source.

    Si conversation_id est fourni, ne supprime que les chunks de cette
    conversation (pas les chunks globaux du même nom).
    Passe conversation_id=None pour supprimer un doc global.

    Parameters
    ----------
    collection_name : str, optional
        Collection cible. Défaut : Config.QDRANT_COLLECTION.
        Doit appartenir à l'utilisateur courant.
    """
    if not QDRANT_OK:
        return 0
    target = collection_name or Config.QDRANT_COLLECTION
    if not ensure_collection(target):
        return 0
    if not _is_own_collection(target):
        _log.warning("[RAG] delete_by_source refusé : collection '%s' non autorisée", target)
        return 0
    try:
        qc = _client()
        scope_value = "global" if conversation_id is None else conversation_id
        must = [
            FieldCondition(key="source",          match=MatchValue(value=source)),
            FieldCondition(key="conversation_id", match=MatchValue(value=scope_value)),
        ]
        count_before = qc.count(
            collection_name=target,
            count_filter=Filter(must=must),
            exact=True,
        ).count
        qc.delete(
            collection_name=target,
            points_selector=FilterSelector(filter=Filter(must=must)),
        )
        _log.info("[RAG] Supprimé %s chunks — source='%s' scope='%s' collection='%s'", count_before, source, scope_value, target)
        return count_before
    except Exception as e:
        _log.error("[RAG] Erreur delete_by_source : %s", e)
        return 0


def build_rag_context(query: str, conversation_id: str = None, collection_name: str = None) -> str:
    """Construit le contexte RAG à injecter dans le prompt système.

    Sélection automatique du backend :

    • Backend Albert  — activé si :
        - collection_name est "albert:<ID>" (sélection explicite dans le panneau), OU
        - collection_name est None ou vaut la collection Qdrant par défaut,
          ET des collections Albert sont disponibles (config ou auto-découverte).
      Pipeline : recherche hybride BGE-M3 (dense+sparse, RRF) → reranking
      BGE-Reranker-v2-M3 → diversification par source → plafond total.

    • Backend Qdrant  — actif dans tous les autres cas (comportement historique).
      Pipeline : recherche vectorielle dense → filtre par score cosinus →
      diversification par source → plafond total.
    """
    _log.debug(
        "[RAG] build_rag_context() — collection=%r conv=%r",
        collection_name, conversation_id,
    )

    # ── Sélection explicite d'une collection Albert depuis le panneau ──
    # La valeur "albert:<ID>" est injectée par RagPanel._on_collection_index_changed.
    if collection_name and collection_name.startswith("albert:"):
        try:
            col_id = int(collection_name.split(":", 1)[1])
        except ValueError:
            col_id = None
        if col_id is not None:
            return _build_rag_context_albert(query, force_collection_ids=[col_id])
        # ID invalide → fallback Qdrant
        return _build_rag_context_qdrant(query, conversation_id, None)

    # ── Dispatch automatique ──────────────────────────────────────────
    # On utilise Albert si des collections sont disponibles (config ou auto-découverte)
    # et que l'utilisateur n'a pas sélectionné une collection Qdrant explicite.
    use_albert = bool(get_albert_collection_ids()) and (
        collection_name is None
        or collection_name == Config.QDRANT_COLLECTION
    )

    if use_albert:
        return _build_rag_context_albert(query)
    else:
        return _build_rag_context_qdrant(query, conversation_id, collection_name)



def _format_chunks_as_context(
    chunks: list[dict],
    title: str = "### Contexte documentaire pertinent :\n",
    scope_tags: bool = False,
    default_tag: str = "🌐",
    score_decimals: int = 2,
) -> str:
    """
    Formate une liste de chunks en bloc de contexte prêt à injecter dans le prompt.

    Parameters
    ----------
    chunks : list[dict]
        Chunks au format interne {text, source, scope, score}.
    title : str
        En-tête du bloc (première ligne).
    scope_tags : bool
        Si True, utilise 🌐 pour les chunks globaux et 💬 pour les chunks
        de conversation (backend Qdrant). Si False, utilise default_tag.
    default_tag : str
        Emoji utilisé quand scope_tags=False (ex : "🌐" pour Albert).
    score_decimals : int
        Précision d'affichage du score (2 pour Qdrant, 3 pour Albert).

    Returns
    -------
    str
        Bloc Markdown prêt à insérer dans le prompt système.
        Chaîne vide si chunks est vide.
    """
    if not chunks:
        return ""
    fmt  = f"{{:.{score_decimals}f}}"
    parts = [title]
    for i, h in enumerate(chunks, 1):
        if scope_tags:
            tag = "🌐" if h.get("scope") == "global" else "💬"
        else:
            tag = default_tag
        score = fmt.format(h["score"])
        parts.append(f"[{i}] {tag} ({h['source']}, score={score})\n{h['text']}\n")
    return "\n".join(parts)


def _build_rag_context_albert(query: str, force_collection_ids: list[int] | None = None) -> str:
    """Build RAG context via le backend Albert (hybride + reranking)."""
    selected = _albert_search_and_rerank(query, force_collection_ids=force_collection_ids)
    if not selected:
        _log.warning("[RAG/Albert] aucun chunk retenu pour : %r", query[:80])
        return ""

    method = Config.RAG_SEARCH_METHOD
    rerank = "→ reranké" if Config.RAG_RERANK_ENABLED else ""
    title  = f"### Contexte documentaire pertinent ({method}{rerank}) :\n"
    _log.debug("[RAG/Albert] %d chunk(s) injectés dans le prompt", len(selected))
    return _format_chunks_as_context(selected, title=title, score_decimals=3)


def _build_rag_context_qdrant(
    query: str,
    conversation_id: str = None,
    collection_name: str = None,
) -> str:
    """Build RAG context via le backend Qdrant (vectoriel dense, comportement historique).

    Stratégie de sélection des chunks :
      1. Récupère RAG_TOP_K candidats depuis Qdrant (filet large).
      2. Filtre les chunks sous le seuil de score RAG_MIN_SCORE (trop peu pertinents).
      3. Limite à RAG_MAX_CHUNKS_PER_SOURCE chunks par document source
         pour éviter qu'un seul document monopolise le contexte.
      4. Retient au maximum RAG_MAX_CHUNKS_TOTAL chunks au total.
    """
    top_k       = Config.RAG_TOP_K
    min_score   = Config.RAG_MIN_SCORE
    max_per_src = Config.RAG_MAX_CHUNKS_PER_SOURCE
    max_total   = Config.RAG_MAX_CHUNKS_TOTAL

    candidates = search(query, top_k=top_k, conversation_id=conversation_id, collection_name=collection_name)
    if not candidates:
        _log.warning("[RAG/Qdrant] aucun résultat pour : %r", query[:80])
        return ""

    # ── Seuil de score adaptatif ───────────────────────────────────────
    # Calcule un seuil dynamique à partir de la distribution des scores
    # retournés, ce qui évite d'utiliser un seuil fixe inadapté à la
    # densité du corpus ou à la difficulté de la requête.
    #
    # Formule : threshold = max(RAG_MIN_SCORE, mean(scores) - σ × std(scores))
    #
    #   σ faible (0.5) → filtre permissif, garde plus de chunks
    #   σ moyen  (1.0) → équilibre précision/rappel (recommandé)
    #   σ élevé  (1.5) → filtre strict, garde seulement les meilleurs
    #
    # Le seuil calculé ne peut jamais descendre sous RAG_MIN_SCORE, ce qui
    # garantit un niveau de qualité minimal même si le corpus est bruité.
    effective_min_score = min_score
    if Config.RAG_ADAPTIVE_THRESHOLD and len(candidates) >= 2:
        scores = [h["score"] for h in candidates]
        mean_s = sum(scores) / len(scores)
        variance = sum((s - mean_s) ** 2 for s in scores) / len(scores)
        std_s = variance ** 0.5
        adaptive = mean_s - Config.RAG_ADAPTIVE_SIGMA * std_s
        effective_min_score = max(min_score, adaptive)
        _log.debug(
            "[RAG/Qdrant] seuil adaptatif : mean=%.3f std=%.3f σ=%.1f "
            "→ adaptive=%.3f effective=%.3f (RAG_MIN_SCORE=%.3f)",
            mean_s, std_s, Config.RAG_ADAPTIVE_SIGMA,
            adaptive, effective_min_score, min_score,
        )

    # ── Filtre par score minimum ───────────────────────────────────────
    above_threshold = [h for h in candidates if h["score"] >= effective_min_score]
    n_dropped = len(candidates) - len(above_threshold)
    if n_dropped:
        _log.debug(
            "[RAG/Qdrant] %d chunk(s) écarté(s) sous seuil=%.3f%s",
            n_dropped, effective_min_score,
            " (adaptatif)" if Config.RAG_ADAPTIVE_THRESHOLD else " (fixe)",
        )

    # ── Diversification par source ─────────────────────────────────────
    selected = _diversify_chunks(
        above_threshold,
        max_per_source=max_per_src,
        max_total=max_total,
    )
    _log.debug(
        "[RAG/Qdrant] %d chunk(s) retenus sur %d candidats (%d source(s))",
        len(selected), len(candidates), len({c["source"] for c in selected}),
    )

    if not selected:
        _log.warning(
            "[RAG/Qdrant] aucun chunk retenu après filtrage (seuil=%.3f%s, top_k=%d)",
            effective_min_score,
            " adaptatif" if Config.RAG_ADAPTIVE_THRESHOLD else " fixe",
            top_k,
        )
        return ""

    return _format_chunks_as_context(selected, scope_tags=True)


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
        _log.error("[RAG] Erreur lors de la récupération des collections : %s", e)
        return []


def list_albert_collections() -> list[dict]:
    """Retourne la liste des collections accessibles sur le serveur Albert.

    Récupère toutes les collections en une seule passe paginée (sans filtre
    de visibilité), exactement comme le fait l'autre appli qui fonctionne.
    Le serveur Albert retourne uniquement ce que l'API key courante peut voir
    (collections publiques + collections privées de l'utilisateur) — pas besoin
    de deux appels séparés.

    Chaque entrée : {"id": int, "name": str, "description": str, "visibility": str}
    Retourne [] si l'API Albert n'est pas configurée ou inaccessible.
    """
    base = _albert_base_url()
    oa   = _get_openai_client()
    if not base and oa is None:
        return []

    seen_ids: set[int] = set()
    result:   list[dict] = []
    offset = 0
    limit  = 100

    while True:
        data = _albert_get("/v1/collections", params={
            "limit":  limit,
            "offset": offset,
        })

        if data is None:
            _log.warning("[Albert] list_collections : appel API échoué à offset=%d", offset)
            break

        page = data.get("data", [])
        if not page:
            break  # dernière page

        for item in page:
            col_id = item.get("id")
            if col_id is None or col_id in seen_ids:
                continue
            seen_ids.add(col_id)
            result.append({
                "id":          col_id,
                "name":        item.get("name", f"collection#{col_id}"),
                "description": item.get("description", "") or "",
                "visibility":  item.get("visibility", "unknown"),
            })

        if len(page) < limit:
            break  # dernière page reçue
        offset += limit

    _log.debug("[Albert] list_collections → %d collection(s)", len(result))
    return result


# ── Cache des IDs Albert — résolution automatique au premier appel ────────────
#
# RAG_ALBERT_COLLECTION_IDS dans .env reste supporté pour forcer une liste
# précise. Si la variable est absente ou vide, on découvre automatiquement
# toutes les collections accessibles (publiques + privées de l'utilisateur).
#
# Le cache est invalidé si la clé API change (redémarrage implicite),
# ou explicitement via reset_albert_collections_cache().

_albert_collections_cache: list[int] | None = None


def reset_albert_collections_cache() -> None:
    """Force la redécouverte des collections Albert au prochain appel."""
    global _albert_collections_cache
    _albert_collections_cache = None
    _log.debug("[Albert] cache collections invalidé")


def get_albert_collection_ids() -> list[int]:
    """Retourne les IDs de collections Albert à interroger.

    Priorité :
      1. RAG_ALBERT_COLLECTION_IDS dans .env  — liste fixe, respectée telle quelle.
      2. Auto-découverte via GET /v1/collections (public + private) — mise en cache.
         Le cache est conservé pendant toute la durée de vie du processus ;
         appeler reset_albert_collections_cache() pour forcer un rechargement.

    Retourne [] si l'API Albert n'est pas configurée (OPENAI_API_BASE vide).
    """
    global _albert_collections_cache

    # Priorité 1 : liste explicite dans .env
    if Config.RAG_ALBERT_COLLECTION_IDS:
        return Config.RAG_ALBERT_COLLECTION_IDS

    # Priorité 2 : auto-découverte avec cache
    if not _albert_base_url() and _get_openai_client() is None:
        return []

    if _albert_collections_cache is None:
        cols = list_albert_collections()
        _albert_collections_cache = [c["id"] for c in cols]
        if _albert_collections_cache:
            names = [f"{c['name']}(#{c['id']})" for c in cols]
            _log.info(
                "[Albert] %d collection(s) découverte(s) automatiquement : %s",
                len(names), ", ".join(names),
            )
        else:
            _log.warning("[Albert] aucune collection trouvée sur le serveur")

    return _albert_collections_cache
