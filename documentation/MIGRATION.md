# Guide d'activation des améliorations RAG

## Fichiers modifiés
- `core/rag_engine.py` — moteur RAG (HyDE + chunking contextuel + seuil adaptatif)
- `core/config.py` — 8 nouveaux paramètres `.env`

---

## 1. Seuil de score adaptatif (actif par défaut)

Remplace le seuil fixe `RAG_MIN_SCORE` par un seuil calculé dynamiquement
à partir de la distribution des scores retournés par Qdrant.

**Aucune action requise** — activé dès le déploiement des fichiers.

Paramètres `.env` optionnels :
```env
RAG_ADAPTIVE_THRESHOLD=ON      # ON (défaut) / OFF pour revenir au comportement historique
RAG_ADAPTIVE_SIGMA=1.0         # 0.5=permissif | 1.0=équilibré | 1.5=strict
```

---

## 2. HyDE — Hypothetical Document Embedding (désactivé par défaut)

Génère un court document hypothétique avant l'embedding de la requête.
Coût : **1 appel LLM supplémentaire par requête RAG** (~0.3–1s de latence).

**Activation** :
```env
RAG_HYDE_ENABLED=ON
RAG_HYDE_MAX_TOKENS=200        # Longueur du document hypothétique (défaut : 200)
```

> Recommandé si vos utilisateurs posent des questions courtes ou conversationnelles
> sur un corpus technique (documentation, textes juridiques, notes internes).

---

## 3. Chunking contextuel (désactivé par défaut — nécessite réingestion)

Enrichit chaque chunk avec un préfixe contextuel LLM lors de l'ingestion.
Améliore fortement les chunks hors-contexte (tableaux, listes, sous-sections).

### ⚠️ Réingestion obligatoire

Les documents déjà indexés dans Qdrant ne bénéficieront pas du contexte.
Il faut supprimer et réindexer.

**Étapes :**

```bash
# 1. Activer dans .env
RAG_CONTEXTUAL_CHUNKING=ON
RAG_CONTEXTUAL_PREFIX_MAX_TOKENS=100    # Longueur du préfixe (défaut : 100)
RAG_CONTEXTUAL_DOC_MAX_CHARS=10000      # Tronc. doc. parent envoyé au LLM (défaut : 10000)

# 2. Supprimer la collection existante (ATTENTION : irréversible)
#    Via le panneau RAG de l'interface, ou via l'API Qdrant :
#    curl -X DELETE http://localhost:6333/collections/<votre_collection>

# 3. Réindexer vos documents
python3 promethee/scripts/ingest3.py /chemin/vers/vos/docs
```

> **Coût** : environ 1 appel LLM par chunk (~20–50 chunks par document de 10 pages).
> Pour 100 documents : prévoir 30–60 min selon la vitesse du LLM configuré.

### Nouveau champ Qdrant

Les chunks ingérés avec cette option stockent un champ supplémentaire :
```json
{
  "text": "...texte du chunk...",
  "source": "mon_doc.pdf",
  "context_prefix": "Ce passage décrit la procédure de résiliation en section 4.2.",
  "conversation_id": "global"
}
```

---

## Résumé des variables `.env` ajoutées

| Variable | Défaut | Description |
|---|---|---|
| `RAG_HYDE_ENABLED` | `OFF` | Active HyDE (1 appel LLM / requête) |
| `RAG_HYDE_MAX_TOKENS` | `200` | Tokens max pour le doc. hypothétique |
| `RAG_CONTEXTUAL_CHUNKING` | `OFF` | Active le chunking contextuel (réingestion requise) |
| `RAG_CONTEXTUAL_PREFIX_MAX_TOKENS` | `100` | Tokens max du préfixe contextuel |
| `RAG_CONTEXTUAL_DOC_MAX_CHARS` | `10000` | Taille max du doc. parent envoyé au LLM |
| `RAG_ADAPTIVE_THRESHOLD` | `ON` | Active le seuil adaptatif |
| `RAG_ADAPTIVE_SIGMA` | `1.0` | Facteur σ du seuil adaptatif |
