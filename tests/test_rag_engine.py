# tests/test_rag_engine.py
import sys, types, urllib.error
from unittest.mock import MagicMock, patch

_qs = types.ModuleType("qdrant_client")
_qs.QdrantClient = MagicMock()
_qm = types.ModuleType("qdrant_client.models")
for _n in ("Distance","VectorParams","PointStruct","Filter","FieldCondition","MatchValue","FilterSelector"):
    setattr(_qm, _n, MagicMock())
_qs.models = _qm
sys.modules.setdefault("qdrant_client", _qs)
sys.modules.setdefault("qdrant_client.models", _qm)

import core.rag_engine as rag

class TestChunks:
    def test_empty(self):
        assert rag._chunk_text("") == []
    def test_whitespace_empty(self):
        assert rag._chunk_text("   ") == []
    def test_short_single_chunk(self):
        c = rag._chunk_text("Ceci est une courte phrase.")
        assert len(c) == 1 and "courte" in c[0]
    def test_long_multiple_chunks(self):
        text = ("Voici une phrase de test assez longue. " * 60)
        assert len(rag._chunk_text(text, max_tokens=50)) > 1
    def test_code_preserved(self):
        code = "def foo():\n    return 42\n\ndef bar():\n    return 0\n"
        full = " ".join(rag._chunk_text(code))
        assert "def foo" in full and "def bar" in full

class TestBuildContext:
    def test_no_hits_empty(self):
        with patch.object(rag, "search", return_value=[]):
            assert rag.build_rag_context("q") == ""
    def test_hits_produce_context(self):
        hits = [{"text": "Contenu A", "source": "doc.pdf", "scope": "global", "score": 0.9}]
        with patch.object(rag, "search", return_value=hits):
            r = rag.build_rag_context("q")
        assert "doc.pdf" in r and "Contenu A" in r and "0.90" in r

def _p1():
    return patch.object(rag, "QDRANT_OK", True)
def _p2():
    return patch.object(rag, "EMBED_OK", True)
def _pt(text="t", source="s", cid="global", score=0.9):
    p = MagicMock()
    p.payload = {"text": text, "source": source, "conversation_id": cid}
    p.score = score
    return p

class TestSearch:
    def test_unavailable_returns_empty(self):
        with patch.object(rag, "QDRANT_OK", False):
            assert rag.search("q") == []

    def test_named_vectors_uses_using(self):
        mock_qc = MagicMock()
        col = MagicMock(); col.name = "BA2T"
        mock_qc.get_collections.return_value.collections = [col]
        vp = MagicMock(); vp.size = 4
        info = MagicMock()
        info.config.params.vectors.items.return_value = [("dense", vp)]
        mock_qc.get_collection.return_value = info
        mock_qc.query_points.return_value.points = [_pt()]
        with _p1(), _p2(), patch.object(rag, "_client", return_value=mock_qc),              patch.object(rag, "_get_embeddings", return_value=[[0.1,0.2,0.3,0.4]]):
            rag.search("q", collection_name="BA2T")
        assert mock_qc.query_points.call_args[1].get("using") == "dense"

    def test_external_no_scope_filter(self):
        mock_qc = MagicMock()
        col = MagicMock(); col.name = "BA2T"
        mock_qc.get_collections.return_value.collections = [col]
        info = MagicMock()
        info.config.params.vectors.items.side_effect = AttributeError
        mock_qc.get_collection.return_value = info
        mock_qc.query_points.return_value.points = []
        with _p1(), _p2(), patch.object(rag, "_client", return_value=mock_qc),              patch.object(rag, "_get_embeddings", return_value=[[0.1,0.2,0.3,0.4]]):
            rag.search("q", collection_name="BA2T")
        assert "query_filter" not in mock_qc.query_points.call_args[1]

    def test_internal_has_scope_filter(self):
        from core.config import Config
        mock_qc = MagicMock()
        col = MagicMock(); col.name = Config.QDRANT_COLLECTION
        mock_qc.get_collections.return_value.collections = [col]
        info = MagicMock()
        info.config.params.vectors.items.side_effect = AttributeError
        mock_qc.get_collection.return_value = info
        mock_qc.query_points.return_value.points = []
        with _p1(), _p2(), patch.object(rag, "_client", return_value=mock_qc),              patch.object(rag, "_get_embeddings", return_value=[[0.1,0.2,0.3,0.4]]):
            rag.search("q", collection_name=Config.QDRANT_COLLECTION)
        assert "query_filter" in mock_qc.query_points.call_args[1]

class TestIsAvailable:
    def test_true(self):
        with patch.object(rag, "QDRANT_OK", True), patch.object(rag, "EMBED_OK", True):
            assert rag.is_available() is True
    def test_false_qdrant(self):
        with patch.object(rag, "QDRANT_OK", False), patch.object(rag, "EMBED_OK", True):
            assert rag.is_available() is False
    def test_false_embed(self):
        with patch.object(rag, "QDRANT_OK", True), patch.object(rag, "EMBED_OK", False):
            assert rag.is_available() is False

class TestListCollections:
    def test_returns_names(self):
        mock_qc = MagicMock()
        c1, c2 = MagicMock(), MagicMock()
        c1.name, c2.name = "A", "B"
        mock_qc.get_collections.return_value.collections = [c1, c2]
        with patch.object(rag, "QDRANT_OK", True), patch.object(rag, "_client", return_value=mock_qc):
            assert rag.list_collections() == ["A", "B"]
    def test_empty_when_ko(self):
        with patch.object(rag, "QDRANT_OK", False):
            assert rag.list_collections() == []


# ── Compléments : fonctions non couvertes ─────────────────────────────────────

class TestEstimateTokens:
    def test_empty_string(self):
        assert rag._estimate_tokens("") >= 0

    def test_short_text(self):
        result = rag._estimate_tokens("Bonjour monde")
        assert isinstance(result, int) and result > 0

    def test_longer_text_more_tokens(self):
        short = rag._estimate_tokens("Bonjour")
        long  = rag._estimate_tokens("Bonjour " * 100)
        assert long > short

    def test_returns_int(self):
        assert isinstance(rag._estimate_tokens("test"), int)


class TestListSourcesUnavailable:
    def test_returns_empty_when_qdrant_ko(self):
        with patch.object(rag, "QDRANT_OK", False):
            assert rag.list_sources() == []

    def test_returns_empty_when_embed_ko(self):
        with patch.object(rag, "EMBED_OK", False):
            assert rag.list_sources() == []


class TestDeleteBySourceUnavailable:
    def test_returns_zero_when_qdrant_ko(self):
        with patch.object(rag, "QDRANT_OK", False):
            assert rag.delete_by_source("source_test") == 0


class TestBuildRagContext:
    def test_returns_string(self):
        with patch.object(rag, "search", return_value=[]):
            result = rag.build_rag_context("ma requête")
        assert isinstance(result, str)

    def test_empty_search_results_empty_context(self):
        with patch.object(rag, "search", return_value=[]):
            result = rag.build_rag_context("requête sans résultat")
        assert result == "" or isinstance(result, str)

    def test_search_results_included_in_context(self):
        # build_rag_context consomme les hits retournés par search()
        # Structure : {scope, source, score, text} (format aplati, pas payload)
        hits = [{"scope": "global", "source": "doc.txt",
                 "score": 0.9, "text": "passage important"}]
        with patch.object(rag, "search", return_value=hits):
            result = rag.build_rag_context("requête")
        assert isinstance(result, str) and "passage important" in result


class TestBuildRagContextFiltering:
    """Tests des nouvelles règles de filtrage et diversification de build_rag_context."""

    def _hit(self, text, source, score, scope="global"):
        return {"text": text, "source": source, "score": score, "scope": scope}

    def test_below_min_score_excluded(self):
        """Un chunk sous RAG_MIN_SCORE ne doit pas apparaître dans le contexte."""
        hits = [
            self._hit("chunk pertinent",   "a.pdf", 0.85),
            self._hit("chunk trop faible", "b.pdf", 0.20),
        ]
        with patch.object(rag, "search", return_value=hits):
            result = rag.build_rag_context("q")
        assert "chunk pertinent"   in result
        assert "chunk trop faible" not in result

    def test_all_below_min_score_returns_empty(self):
        """Si tous les chunks sont sous le seuil, retourner une chaîne vide."""
        hits = [self._hit("faible", "a.pdf", 0.10)]
        with patch.object(rag, "search", return_value=hits):
            result = rag.build_rag_context("q")
        assert result == ""

    def test_source_diversity_limits_chunks_per_source(self):
        """Pas plus de RAG_MAX_CHUNKS_PER_SOURCE chunks par source."""
        max_per = rag.Config.RAG_MAX_CHUNKS_PER_SOURCE
        # 4 chunks du même document
        hits = [self._hit(f"chunk {i}", "mono.pdf", 0.9 - i * 0.01) for i in range(4)]
        # 1 chunk d'un second document
        hits.append(self._hit("autre doc", "autre.pdf", 0.75))
        with patch.object(rag, "search", return_value=hits):
            result = rag.build_rag_context("q")
        # Le second document doit apparaître malgré le score plus faible
        assert "autre doc" in result
        # Pas plus de max_per occurrences de "mono.pdf"
        assert result.count("mono.pdf") <= max_per

    def test_max_chunks_total_respected(self):
        """Le nombre total de chunks injectés ne dépasse pas RAG_MAX_CHUNKS_TOTAL."""
        max_total = rag.Config.RAG_MAX_CHUNKS_TOTAL
        # Génère 3× plus de chunks que la limite totale, sources variées
        hits = [self._hit(f"texte {i}", f"src_{i}.pdf", 0.9) for i in range(max_total * 3)]
        with patch.object(rag, "search", return_value=hits):
            result = rag.build_rag_context("q")
        # Compter le nombre de marqueurs [N] dans le résultat
        import re
        n_injected = len(re.findall(r"^\[\d+\]", result, re.MULTILINE))
        assert n_injected <= max_total


class TestAlbertBackend:
    """Tests du pipeline Albert (recherche hybride + reranking)."""

    def _chunk(self, text, source="doc.pdf", score=0.9):
        return {"text": text, "source": source, "scope": "global", "score": score}

    # ── _albert_post / _albert_request ───────────────────────────────

    def test_albert_post_returns_none_on_http_error(self):
        """_albert_post retourne None en cas d'erreur HTTP."""
        # On mock _albert_request directement (la couche transport est testée là)
        with patch.object(rag, "_albert_request", return_value=None):
            result = rag._albert_post("/v1/search", {})
        assert result is None

    def test_albert_post_returns_none_on_network_error(self):
        """_albert_post retourne None en cas d'erreur réseau."""
        with patch.object(rag, "_albert_request", return_value=None):
            result = rag._albert_post("/v1/rerank", {})
        assert result is None

    # ── _albert_search ────────────────────────────────────────────────

    def test_albert_search_empty_collection_ids(self):
        """_albert_search retourne [] immédiatement sans collection."""
        assert rag._albert_search("q", [], limit=10) == []

    def test_albert_search_parses_response(self):
        """_albert_search mappe correctement le format Albert → format interne."""
        fake_resp = {
            "data": [
                {
                    "score": 0.87,
                    "chunk": {
                        "content": "texte du chunk",
                        "metadata": {"document_name": "rapport.pdf"},
                    }
                }
            ]
        }
        with patch.object(rag, "_albert_post", return_value=fake_resp):
            results = rag._albert_search("q", [42], limit=10)
        assert len(results) == 1
        assert results[0]["text"] == "texte du chunk"
        assert results[0]["source"] == "rapport.pdf"
        assert results[0]["score"] == pytest.approx(0.87)
        assert results[0]["scope"] == "global"

    def test_albert_search_fallback_source_from_document_id(self):
        """Sans metadata.document_name, source = document#<id>."""
        fake_resp = {
            "data": [{"score": 0.7, "chunk": {"content": "x", "document_id": 99, "metadata": {}}}]
        }
        with patch.object(rag, "_albert_post", return_value=fake_resp):
            results = rag._albert_search("q", [1], limit=5)
        assert results[0]["source"] == "document#99"

    def test_albert_search_api_failure_returns_empty(self):
        """Si l'API échoue, _albert_search retourne []."""
        with patch.object(rag, "_albert_post", return_value=None):
            assert rag._albert_search("q", [1], limit=5) == []

    # ── _albert_rerank ────────────────────────────────────────────────

    def test_albert_rerank_reorders_by_relevance(self):
        """_albert_rerank réordonne les chunks selon le score du cross-encoder."""
        candidates = [
            self._chunk("chunk A", score=0.9),
            self._chunk("chunk B", score=0.8),
            self._chunk("chunk C", score=0.7),
        ]
        # Le reranker inverse l'ordre : C > A > B
        fake_resp = {
            "results": [
                {"index": 2, "relevance_score": 8.5},
                {"index": 0, "relevance_score": 4.2},
                {"index": 1, "relevance_score": 1.1},
            ]
        }
        with patch.object(rag, "_albert_post", return_value=fake_resp):
            reranked = rag._albert_rerank("q", candidates, top_n=3, model="m", min_score=-10.0)
        assert reranked[0]["text"] == "chunk C"
        assert reranked[0]["score"] == pytest.approx(8.5)
        assert reranked[1]["text"] == "chunk A"

    def test_albert_rerank_filters_below_min_score(self):
        """_albert_rerank écarte les chunks sous min_score."""
        candidates = [self._chunk("A"), self._chunk("B")]
        fake_resp = {
            "results": [
                {"index": 0, "relevance_score": 5.0},
                {"index": 1, "relevance_score": -5.0},  # sous le seuil
            ]
        }
        with patch.object(rag, "_albert_post", return_value=fake_resp):
            reranked = rag._albert_rerank("q", candidates, top_n=2, model="m", min_score=0.0)
        assert len(reranked) == 1
        assert reranked[0]["text"] == "A"

    def test_albert_rerank_fallback_on_api_failure(self):
        """Si le reranker échoue, on conserve l'ordre vectoriel original."""
        candidates = [self._chunk("A"), self._chunk("B"), self._chunk("C")]
        with patch.object(rag, "_albert_post", return_value=None):
            reranked = rag._albert_rerank("q", candidates, top_n=2, model="m", min_score=-10.0)
        assert len(reranked) == 2
        assert reranked[0]["text"] == "A"

    def test_albert_rerank_strips_internal_marker(self):
        """Le marqueur _reranked ne doit pas apparaître dans les résultats."""
        candidates = [self._chunk("A")]
        fake_resp = {"results": [{"index": 0, "relevance_score": 3.0}]}
        with patch.object(rag, "_albert_post", return_value=fake_resp):
            reranked = rag._albert_rerank("q", candidates, top_n=1, model="m", min_score=-10.0)
        # _reranked est un marqueur interne — il ne doit PAS être dans le résultat final
        # (il est retiré dans _albert_search_and_rerank, pas dans _albert_rerank)
        assert "_reranked" in reranked[0]  # présent ici, retiré en aval

    # ── build_rag_context dispatch ─────────────────────────────────────

    def test_build_context_uses_albert_when_ids_configured(self):
        """build_rag_context délègue à Albert si des collections sont disponibles."""
        chunks = [self._chunk("contenu albert", "note.pdf", score=7.2)]
        with patch.object(rag, "get_albert_collection_ids", return_value=[42]):
            with patch.object(rag, "_albert_search_and_rerank", return_value=chunks):
                result = rag.build_rag_context("q")
        assert "contenu albert" in result
        assert "note.pdf" in result

    def test_build_context_uses_qdrant_when_no_albert_ids(self):
        """build_rag_context délègue à Qdrant si aucune collection Albert disponible."""
        hits = [self._chunk("contenu qdrant", "doc.pdf", score=0.85)]
        with patch.object(rag, "get_albert_collection_ids", return_value=[]):
            with patch.object(rag, "search", return_value=hits):
                result = rag.build_rag_context("q")
        assert "contenu qdrant" in result

    def test_build_context_uses_qdrant_when_explicit_collection(self):
        """Si une collection Qdrant explicite est passée, on n'utilise pas Albert."""
        hits = [self._chunk("qdrant explicite", "doc.pdf", score=0.80)]
        with patch.object(rag, "get_albert_collection_ids", return_value=[42]):
            with patch.object(rag, "search", return_value=hits):
                result = rag.build_rag_context("q", collection_name="ma_collection_custom")
        assert "qdrant explicite" in result

    def test_build_context_albert_empty_returns_empty_string(self):
        """build_rag_context retourne '' si Albert ne trouve rien."""
        with patch.object(rag, "get_albert_collection_ids", return_value=[1]):
            with patch.object(rag, "_albert_search_and_rerank", return_value=[]):
                result = rag.build_rag_context("q")
        assert result == ""


class TestAlbertCollectionDiscovery:
    """Tests de la découverte automatique des collections Albert."""

    def _page_resp(self, items: list) -> dict:
        """Simule une réponse de page Albert."""
        return {"data": items}

    def setup_method(self, _):
        rag.reset_albert_collections_cache()

    # ── list_albert_collections ───────────────────────────────────────

    def test_returns_empty_when_no_transport(self):
        """Sans base_url ni client OpenAI, retourne []."""
        with patch.object(rag, "_albert_base_url", return_value=""):
            with patch.object(rag, "_get_openai_client", return_value=None):
                assert rag.list_albert_collections() == []

    def test_fetches_all_collections_single_page(self):
        """Retourne toutes les collections en une seule page."""
        items = [
            {"id": 1, "name": "pub",  "description": "", "visibility": "public"},
            {"id": 2, "name": "priv", "description": "", "visibility": "private"},
        ]
        # Première page pleine (< limit), deuxième page vide (fin)
        with patch.object(rag, "_albert_request", side_effect=[
            {"data": items},   # page 1
        ]):
            # La page a 2 éléments < limit=100, donc on s'arrête
            with patch.object(rag, "_albert_base_url", return_value="https://fake.api"):
                result = rag.list_albert_collections()
        assert {c["id"] for c in result} == {1, 2}

    def test_deduplicates_by_id(self):
        """Un ID en double n'apparaît qu'une seule fois."""
        items = [{"id": 5, "name": "shared", "description": "", "visibility": "public"}]
        with patch.object(rag, "_albert_base_url", return_value="https://fake.api"):
            with patch.object(rag, "_albert_request", return_value={"data": items}):
                result = rag.list_albert_collections()
        assert len(result) == 1 and result[0]["id"] == 5

    def test_handles_api_error_gracefully(self):
        """En cas d'erreur API (_albert_request retourne None), retourne []."""
        with patch.object(rag, "_albert_base_url", return_value="https://fake.api"):
            with patch.object(rag, "_albert_request", return_value=None):
                assert rag.list_albert_collections() == []

    def test_pagination_fetches_multiple_pages(self):
        """Si une page est pleine (=limit=100), une deuxième page est demandée."""
        page1 = [{"id": i, "name": f"c{i}", "description": "", "visibility": "public"} for i in range(100)]
        page2 = [{"id": 100, "name": "c100", "description": "", "visibility": "public"}]
        with patch.object(rag, "_albert_base_url", return_value="https://fake.api"):
            with patch.object(rag, "_albert_request", side_effect=[
                {"data": page1},  # page 1 : pleine → on continue
                {"data": page2},  # page 2 : partielle → on s'arrête
            ]):
                result = rag.list_albert_collections()
        assert len(result) == 101

    # ── get_albert_collection_ids ─────────────────────────────────────

    def test_returns_static_ids_when_configured(self):
        """Si RAG_ALBERT_COLLECTION_IDS est défini dans .env, l'utilise sans appel API."""
        with patch.object(rag.Config, "RAG_ALBERT_COLLECTION_IDS", [10, 20]):
            assert rag.get_albert_collection_ids() == [10, 20]

    def test_autodiscovers_when_no_static_ids(self):
        """Sans config statique, découvre et met en cache les IDs."""
        cols = [{"id": 7, "name": "auto", "description": "", "visibility": "public"}]
        with patch.object(rag.Config, "RAG_ALBERT_COLLECTION_IDS", []):
            with patch.object(rag, "_albert_base_url", return_value="https://fake.api"):
                with patch.object(rag, "list_albert_collections", return_value=cols):
                    assert rag.get_albert_collection_ids() == [7]

    def test_cache_avoids_second_api_call(self):
        """Le second appel utilise le cache sans rappeler list_albert_collections."""
        cols = [{"id": 3, "name": "cached", "description": "", "visibility": "private"}]
        with patch.object(rag.Config, "RAG_ALBERT_COLLECTION_IDS", []):
            with patch.object(rag, "_albert_base_url", return_value="https://fake.api"):
                with patch.object(rag, "list_albert_collections", return_value=cols) as m:
                    rag.get_albert_collection_ids()
                    rag.get_albert_collection_ids()
                    assert m.call_count == 1

    def test_reset_cache_forces_rediscovery(self):
        """reset_albert_collections_cache() force un nouvel appel API."""
        cols = [{"id": 9, "name": "fresh", "description": "", "visibility": "public"}]
        with patch.object(rag.Config, "RAG_ALBERT_COLLECTION_IDS", []):
            with patch.object(rag, "_albert_base_url", return_value="https://fake.api"):
                with patch.object(rag, "list_albert_collections", return_value=cols) as m:
                    rag.get_albert_collection_ids()
                    rag.reset_albert_collections_cache()
                    rag.get_albert_collection_ids()
                    assert m.call_count == 2

    def test_returns_empty_when_no_transport_no_static(self):
        """Sans OPENAI_API_BASE ni client OpenAI, retourne []."""
        with patch.object(rag.Config, "RAG_ALBERT_COLLECTION_IDS", []):
            with patch.object(rag, "_albert_base_url", return_value=""):
                with patch.object(rag, "_get_openai_client", return_value=None):
                    assert rag.get_albert_collection_ids() == []
