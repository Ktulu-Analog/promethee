/**
 * ============================================================================
 * Prométhée — Assistant IA avancé
 * ============================================================================
 * Auteur  : Pierre COUGET ktulu.analog@gmail.com
 * Licence : GNU Affero General Public License v3.0 (AGPL-3.0)
 *           https://www.gnu.org/licenses/agpl-3.0.html
 * Année   : 2026
 * ----------------------------------------------------------------------------
 * Ce fichier fait partie du projet Prométhée.
 * Vous pouvez le redistribuer et/ou le modifier selon les termes de la
 * licence AGPL-3.0 publiée par la Free Software Foundation.
 * ============================================================================
 *
 *
 * RagPanel.tsx — Panneau RAG droit
 *
 * Portage complet de ui/panels/rag_panel.py (PyQt6 → React).
 *
 * Fonctionnalités :
 *   - Statut Qdrant (GET /rag/status)
 *   - Sélection de collection (Qdrant 💾 + Albert ⚡) via GET /rag/collections + /rag/albert/collections
 *   - Ingestion fichiers pour la conversation courante (POST /rag/ingest/stream SSE)
 *   - Ingestion texte libre (POST /rag/ingest)
 *   - Liste des sources indexées (GET /rag/sources)
 *   - Suppression de source avec confirmation (DELETE /rag/sources)
 *   - Légende scope : 🌐 collection / 💬 conversation
 *
 * Props :
 *   convId            — ID de la conversation active (null si aucune)
 *   onClose           — Ferme le panneau
 *   onCollectionChange — Notifie App du changement de collection (pour le chat)
 */

import React, { useState, useEffect, useRef, useCallback } from "react";
import { getToken } from "../../hooks/useAuth";

const BASE = (import.meta as any).env?.VITE_API_URL ?? "http://localhost:8000";

function authFetch(url: string, options: RequestInit = {}): Promise<Response> {
  const token = getToken();
  const headers: Record<string, string> = {
    ...(options.headers as Record<string, string> ?? {}),
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  return fetch(url, { ...options, headers });
}

// ── Types API ──────────────────────────────────────────────────────────────

interface RagStatus {
  available: boolean;
}

interface RagCollection {
  name: string;
  is_own: boolean;
}

interface AlbertCollection {
  id: string;
  name: string;
  visibility?: string;
}

interface CollectionOption {
  label: string;
  value: string; // Qdrant name ou "albert:<id>"
}

interface RagSource {
  source: string;
  chunks: number;
  scope: "global" | "conv";
  score_avg?: number;
}

// ── Props ──────────────────────────────────────────────────────────────────

export interface RagPanelProps {
  convId: string | null;
  onClose: () => void;
  onCollectionChange?: (collectionName: string | null) => void;
  /** Collection initialement sélectionnée (persistée depuis le parent pour survivre aux fermetures) */
  initialCollection?: string | null;
  /** Quand true : pas de borderLeft, background transparent, s'adapte au FloatingPanel */
  embedded?: boolean;
}

// ── Helpers ───────────────────────────────────────────────────────────────

/** Collection mémoire long terme : jamais visible par l'utilisateur */
function isMemoryCollection(name: string): boolean {
  return name.startsWith("promethee_memory_");
}

/** Collection propre à l'utilisateur : affichée avec ses documents */
function isOwnCollection(name: string): boolean {
  return name.startsWith("promethee_") && !isMemoryCollection(name);
}

// ── Composant principal ───────────────────────────────────────────────────

export function RagPanel({ convId, onClose, onCollectionChange, initialCollection = null, embedded = false }: RagPanelProps) {
  const [status, setStatus] = useState<"ok" | "off" | "unknown">("unknown");
  const [collections, setCollections] = useState<CollectionOption[]>([]);
  const [selectedCollection, setSelectedCollection] = useState<string | null>(initialCollection);
  const [collectionInfo, setCollectionInfo] = useState("Aucune collection sélectionnée");
  const [sources, setSources] = useState<RagSource[]>([]);
  const [loadingSources, setLoadingSources] = useState(false);

  // Ingestion fichiers
  const [ingesting, setIngesting] = useState(false);
  const [ingestProgress, setIngestProgress] = useState<{ done: number; total: number } | null>(null);
  const [ingestMsg, setIngestMsg] = useState<{ text: string; ok: boolean } | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Ingestion texte
  const [showTextInput, setShowTextInput] = useState(false);
  const [textInput, setTextInput] = useState("");
  const [ingestingText, setIngestingText] = useState(false);

  // Source sélectionnée pour suppression
  const [selectedSource, setSelectedSource] = useState<RagSource | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<RagSource | null>(null);

  // ── Init ─────────────────────────────────────────────────────────────────

  useEffect(() => {
    fetchStatus();
    fetchCollections();
  }, []);

  useEffect(() => {
    if (selectedCollection !== null) {
      fetchSources();
    }
  }, [convId, selectedCollection]);

  // ── API calls ─────────────────────────────────────────────────────────────

  async function fetchStatus() {
    try {
      const res = await authFetch(`${BASE}/rag/status`);
      const data: RagStatus = await res.json();
      setStatus(data.available ? "ok" : "off");
    } catch {
      setStatus("off");
    }
  }

  async function fetchCollections() {
    const items: CollectionOption[] = [];

    // Qdrant
    try {
      const res = await authFetch(`${BASE}/rag/collections`);
      if (res.ok) {
        const cols: RagCollection[] = await res.json();
        for (const col of cols) {
          // Masquer la collection mémoire long terme
          if (isMemoryCollection(col.name)) continue;
          const label = col.is_own ? `💾 ${col.name} ★` : `💾 ${col.name}`;
          items.push({ label, value: col.name });
        }
      }
    } catch {}

    // Albert
    try {
      const res = await authFetch(`${BASE}/rag/albert/collections`);
      if (res.ok) {
        const cols: AlbertCollection[] = await res.json();
        for (const col of cols) {
          const vis = col.visibility === "public" ? "🌐" : "🔒";
          items.push({ label: `⚡${vis} ${col.name}`, value: `albert:${col.id}` });
        }
      }
    } catch {}

    setCollections(items);

    // Sélectionner la collection par défaut UNIQUEMENT si aucune n'est déjà sélectionnée
    // ou si la collection sélectionnée n'existe plus dans la liste.
    // Cela évite d'écraser le choix de l'utilisateur lors d'un rechargement de la liste.
    setSelectedCollection((current) => {
      if (current !== null && items.some((c) => c.value === current)) {
        // La sélection courante est valide : conserver le choix existant
        const opt = items.find((c) => c.value === current)!;
        updateCollectionInfo(opt);
        return current;
      }
      // Pas de sélection valide : sélectionner la collection propre par défaut
      if (items.length === 0) return null;
      const own = items.find((c) => c.label.includes("★"));
      const def = own ?? items[0];
      updateCollectionInfo(def);
      onCollectionChange?.(def.value);
      return def.value;
    });
  }

  async function fetchSources() {
    if (!selectedCollection) return;

    // Pour les collections non-propres (ex: immenses collections partagées),
    // on n'affiche pas la liste des documents pour éviter les requêtes lentes.
    if (!selectedCollection.startsWith("albert:") && !isOwnCollection(selectedCollection)) {
      setSources([]);
      return;
    }

    setLoadingSources(true);
    try {
      const params = new URLSearchParams();
      if (convId) params.set("conv_id", convId);
      if (selectedCollection) params.set("collection_name", selectedCollection);
      const res = await authFetch(`${BASE}/rag/sources?${params}`);
      if (res.ok) {
        const data = await res.json();
        // Normalise scope field
        const normalized: RagSource[] = data.map((s: any) => ({
          source: s.source,
          chunks: s.chunks ?? s.count ?? 0,
          scope: s.scope ?? "global",
          score_avg: s.score_avg,
        }));
        setSources(normalized);
      }
    } catch {}
    setLoadingSources(false);
  }

  // ── Collection change ─────────────────────────────────────────────────────

  function handleCollectionChange(value: string) {
    setSelectedCollection(value);
    const opt = collections.find((c) => c.value === value);
    if (opt) updateCollectionInfo(opt);
    onCollectionChange?.(value);
    setSelectedSource(null);
  }

  function updateCollectionInfo(opt: CollectionOption) {
    if (opt.value.startsWith("albert:")) {
      const name = opt.label.replace(/^⚡[🌐🔒] /, "");
      setCollectionInfo(`⚡ Albert — ${name}  (hybride BGE-M3 + reranking)`);
    } else {
      setCollectionInfo(`💾 Qdrant — ${opt.value}`);
    }
  }

  // ── Ingestion fichiers (SSE) ──────────────────────────────────────────────

  async function handleFileSelect(e: React.ChangeEvent<HTMLInputElement>) {
    const files = e.target.files;
    if (!files || files.length === 0) return;
    e.target.value = ""; // reset input

    setIngesting(true);
    setIngestProgress({ done: 0, total: files.length });
    setIngestMsg(null);

    const formData = new FormData();
    for (const f of Array.from(files)) {
      formData.append("files", f);
    }
    if (convId) formData.append("conv_id", convId);

    try {
      const res = await authFetch(`${BASE}/rag/ingest/stream`, {
        method: "POST",
        body: formData,
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail ?? res.statusText);
      }

      // Lire le SSE
      const reader = res.body!.getReader();
      const decoder = new TextDecoder();
      let totalChunks = 0;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        const text = decoder.decode(value);
        for (const line of text.split("\n")) {
          if (!line.startsWith("data: ")) continue;
          try {
            const evt = JSON.parse(line.slice(6));
            if (evt.done === true) break;
            if (evt.error) {
              setIngestMsg({ text: `Erreur : ${evt.error}`, ok: false });
            } else {
              totalChunks += evt.chunks ?? 0;
              setIngestProgress({ done: evt.done, total: evt.total });
            }
          } catch {}
        }
      }

      setIngestMsg({ text: `✅ ${totalChunks} chunks indexés`, ok: true });
      fetchSources();
    } catch (err: any) {
      setIngestMsg({ text: `Erreur : ${err.message}`, ok: false });
    } finally {
      setIngesting(false);
      setIngestProgress(null);
    }
  }

  // ── Ingestion texte ───────────────────────────────────────────────────────

  async function handleIngestText() {
    const text = textInput.trim();
    if (!text) return;
    setIngestingText(true);
    setIngestMsg(null);

    const formData = new FormData();
    const blob = new Blob([text], { type: "text/plain" });
    formData.append("file", blob, "texte libre.txt");
    if (convId) formData.append("conv_id", convId);

    try {
      const res = await authFetch(`${BASE}/rag/ingest`, {
        method: "POST",
        body: formData,
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail ?? res.statusText);
      }
      const data = await res.json();
      setIngestMsg({ text: `✅ ${data.chunks} chunks indexés (conversation)`, ok: true });
      setTextInput("");
      setShowTextInput(false);
      fetchSources();
    } catch (err: any) {
      setIngestMsg({ text: `Erreur : ${err.message}`, ok: false });
    } finally {
      setIngestingText(false);
    }
  }

  // ── Suppression ───────────────────────────────────────────────────────────

  async function handleDeleteConfirm() {
    if (!confirmDelete) return;
    const src = confirmDelete;
    setConfirmDelete(null);
    setSelectedSource(null);

    const params = new URLSearchParams({ source: src.source });
    if (convId && src.scope !== "global") params.set("conv_id", convId);
    if (selectedCollection) params.set("collection_name", selectedCollection);

    try {
      await authFetch(`${BASE}/rag/sources?${params}`, {
        method: "DELETE",
      });
      setIngestMsg({ text: `🗑 '${src.source}' supprimé`, ok: true });
      fetchSources();
    } catch (err: any) {
      setIngestMsg({ text: `Erreur suppression : ${err.message}`, ok: false });
    }
  }

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div style={{ ...s.panel, ...(embedded ? s.panelEmbedded : {}) }}>
      {/* ── En-tête ────────────────────────────────────────────────────── */}
      <div style={s.header}>
        <span style={s.headerIcon}>📚</span>
        <span style={s.headerTitle}>Base documentaire</span>
        <div style={{ flex: 1 }} />
        <button style={s.closeBtn} onClick={onClose} title="Fermer">×</button>
      </div>

      {/* ── Statut Qdrant ──────────────────────────────────────────────── */}
      <div style={s.statusRow}>
        <span
          style={{
            ...s.statusDot,
            background: status === "ok" ? "var(--rag-badge-on)" : "var(--rag-badge-off)",
          }}
        />
        <span style={{ color: status === "ok" ? "var(--rag-badge-on)" : "var(--text-muted)", fontSize: 11, fontWeight: 600 }}>
          {status === "ok" ? "Qdrant connecté" : status === "off" ? "RAG désactivé" : "…"}
        </span>
      </div>

      <div style={s.divider} />

      {/* ── Collections ────────────────────────────────────────────────── */}
      <SectionLabel>🗂 Collections</SectionLabel>

      <div style={s.collectionRow}>
        <select
          value={selectedCollection ?? ""}
          onChange={(e) => handleCollectionChange(e.target.value)}
          style={s.select}
          disabled={collections.length === 0}
        >
          {collections.length === 0 && (
            <option value="">Aucune collection disponible</option>
          )}
          {collections.map((c) => (
            <option key={c.value} value={c.value}>{c.label}</option>
          ))}
        </select>

        <button
          style={s.iconBtn}
          onClick={() => { fetchCollections(); fetchSources(); }}
          title="Actualiser la liste des collections"
        >
          🔄
        </button>
      </div>

      <div style={s.collectionInfo}>{collectionInfo}</div>

      <div style={s.divider} />

      {/* ── Cette conversation ─────────────────────────────────────────── */}
      <SectionLabel>💬 Cette conversation</SectionLabel>

      <div style={s.btnRow}>
        <button
          style={{ ...s.toolBtn, opacity: ingesting ? 0.6 : 1 }}
          disabled={ingesting || status !== "ok"}
          onClick={() => fileInputRef.current?.click()}
          title="Indexer des fichiers pour cette conversation"
        >
          📄 Fichiers
        </button>
        <button
          style={{ ...s.toolBtn, background: showTextInput ? "var(--elevated-bg)" : undefined }}
          disabled={ingesting || status !== "ok"}
          onClick={() => {
            setShowTextInput((v) => !v);
            setIngestMsg(null);
          }}
          title="Indexer du texte pour cette conversation"
        >
          ✏️ Texte
        </button>
      </div>

      {/* Input fichier caché */}
      <input
        ref={fileInputRef}
        type="file"
        multiple
        accept=".txt,.md,.pdf,.csv,.py,.js,.json,.ts,.tsx,.html,.xml,.yaml,.yml"
        style={{ display: "none" }}
        onChange={handleFileSelect}
      />

      {/* Zone texte libre */}
      {showTextInput && (
        <div style={s.textZone}>
          <div style={s.textScopeLbl}>💬 Indexer pour cette conversation</div>
          <textarea
            value={textInput}
            onChange={(e) => setTextInput(e.target.value)}
            placeholder="Collez du texte à indexer…"
            style={s.textarea}
            rows={5}
          />
          <button
            style={{ ...s.sendBtn, opacity: ingestingText ? 0.6 : 1 }}
            onClick={handleIngestText}
            disabled={ingestingText || !textInput.trim()}
          >
            {ingestingText ? "Indexation…" : "Indexer →"}
          </button>
        </div>
      )}

      {/* Barre de progression */}
      {ingesting && ingestProgress && (
        <div style={s.progressWrap}>
          <div
            style={{
              ...s.progressBar,
              width: `${Math.round((ingestProgress.done / ingestProgress.total) * 100)}%`,
            }}
          />
          <span style={s.progressLabel}>
            {ingestProgress.done} / {ingestProgress.total}
          </span>
        </div>
      )}

      {/* Message de statut */}
      {ingestMsg && (
        <div style={{ ...s.ingestMsg, color: ingestMsg.ok ? "var(--rag-badge-on)" : "#e07878" }}>
          {ingestMsg.text}
        </div>
      )}

      <div style={s.divider} />

      {/* ── Documents indexés ──────────────────────────────────────────── */}
      <div style={s.docHeader}>
        <SectionLabel>Documents indexés</SectionLabel>
        <div style={{ flex: 1 }} />
        <button
          style={{
            ...s.iconBtn,
            opacity: selectedSource ? 1 : 0.4,
            cursor: selectedSource ? "pointer" : "not-allowed",
          }}
          disabled={!selectedSource}
          onClick={() => selectedSource && setConfirmDelete(selectedSource)}
          title="Supprimer le document sélectionné"
        >
          🗑️
        </button>
      </div>

      <div style={s.docList}>
        {loadingSources && (
          <div style={s.hint}>Chargement…</div>
        )}
        {!loadingSources && selectedCollection && !selectedCollection.startsWith("albert:") && !isOwnCollection(selectedCollection) && (
          <div style={s.hint}>Liste non disponible pour les collections partagées.</div>
        )}
        {!loadingSources && sources.length === 0 && (!selectedCollection || selectedCollection.startsWith("albert:") || isOwnCollection(selectedCollection)) && (
          <div style={s.hint}>Aucun document indexé</div>
        )}
        {sources.map((src) => (
          <div
            key={`${src.source}__${src.scope}`}
            style={{
              ...s.docItem,
              background: selectedSource?.source === src.source && selectedSource?.scope === src.scope
                ? "var(--sidebar-item-active-bg)"
                : undefined,
            }}
            onClick={() =>
              setSelectedSource(
                selectedSource?.source === src.source && selectedSource?.scope === src.scope
                  ? null
                  : src
              )
            }
            title={`${src.scope === "global" ? `Collection : ${selectedCollection}` : "Cette conversation"}\n${src.source} — ${src.chunks} chunk(s)`}
          >
            <span style={s.docBadge}>{src.scope === "global" ? "🌐" : "💬"}</span>
            <span style={s.docName}>{src.source}</span>
            <span style={s.docCount}>{src.chunks}</span>
          </div>
        ))}
      </div>

      <div style={s.divider} />

      {/* ── Légende ────────────────────────────────────────────────────── */}
      <div style={s.legend}>
        <span style={s.legendItem}>🌐 Collection</span>
        <span style={s.legendItem}>💬 Conversation</span>
      </div>

      {/* ── Dialogue confirmation suppression ──────────────────────────── */}
      {confirmDelete && (
        <ConfirmDialog
          source={confirmDelete.source}
          scope={confirmDelete.scope}
          onConfirm={handleDeleteConfirm}
          onCancel={() => setConfirmDelete(null)}
        />
      )}
    </div>
  );
}

// ── SectionLabel ──────────────────────────────────────────────────────────

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div style={{
      fontSize: 11,
      fontWeight: 600,
      color: "var(--text-muted)",
      textTransform: "uppercase",
      letterSpacing: "0.06em",
      padding: "0 14px 4px",
    }}>
      {children}
    </div>
  );
}

// ── ConfirmDialog ─────────────────────────────────────────────────────────

function ConfirmDialog({
  source, scope, onConfirm, onCancel,
}: {
  source: string;
  scope: string;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const scopeLabel = scope === "global" ? "la collection" : "cette conversation";
  return (
    <div style={s.overlay}>
      <div style={s.dialog}>
        <div style={s.dialogTitle}>Confirmer la suppression</div>
        <div style={s.dialogBody}>
          Supprimer <strong style={{ color: "var(--text-primary)" }}>{source}</strong>
          {" "}de <strong style={{ color: "var(--text-primary)" }}>{scopeLabel}</strong> ?
        </div>
        <div style={s.dialogBtns}>
          <button style={s.cancelBtn} onClick={onCancel}>Annuler</button>
          <button style={s.deleteBtn} onClick={onConfirm}>Supprimer</button>
        </div>
      </div>
    </div>
  );
}

// ── Styles ────────────────────────────────────────────────────────────────

const s: Record<string, React.CSSProperties> = {
  panel: {
    width: 280,
    background: "var(--surface-bg)",
    borderLeft: "1px solid var(--border)",
    display: "flex",
    flexDirection: "column",
    height: "100%",
    overflow: "hidden",
    flexShrink: 0,
    fontSize: 13,
    color: "var(--text-primary)",
  },
  panelEmbedded: {
    width: "100%",
    borderLeft: "none",
    background: "transparent",
    height: "100%",
  },
  header: {
    display: "flex",
    alignItems: "center",
    gap: 6,
    padding: "10px 14px",
    borderBottom: "1px solid var(--border)",
    flexShrink: 0,
  },
  headerIcon: {
    fontSize: 16,
  },
  headerTitle: {
    fontWeight: 600,
    fontSize: 13,
    color: "var(--text-secondary)",
  },
  closeBtn: {
    background: "none",
    border: "none",
    cursor: "pointer",
    color: "var(--text-muted)",
    fontSize: 18,
    lineHeight: 1,
    padding: "0 2px",
    display: "flex",
    alignItems: "center",
  },
  statusRow: {
    display: "flex",
    alignItems: "center",
    gap: 6,
    padding: "8px 14px 6px",
  },
  statusDot: {
    width: 8,
    height: 8,
    borderRadius: "50%",
    flexShrink: 0,
    display: "inline-block",
  },
  divider: {
    height: 1,
    background: "var(--border)",
    margin: "8px 0",
    flexShrink: 0,
  },
  collectionRow: {
    display: "flex",
    gap: 6,
    padding: "4px 14px 6px",
    alignItems: "center",
  },
  select: {
    flex: 1,
    minWidth: 0,
    padding: "5px 8px",
    background: "var(--input-bg)",
    border: "1px solid var(--input-border)",
    borderRadius: 6,
    color: "var(--input-color)",
    fontSize: 12,
    outline: "none",
    cursor: "pointer",
    overflow: "hidden",
    textOverflow: "ellipsis",
  },
  iconBtn: {
    flexShrink: 0,
    width: 32,
    height: 32,
    background: "var(--elevated-bg)",
    border: "1px solid var(--input-border)",
    borderRadius: 6,
    cursor: "pointer",
    fontSize: 14,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
  },
  collectionInfo: {
    padding: "0 14px 6px",
    fontSize: 10,
    color: "var(--text-muted)",
    lineHeight: 1.5,
    wordBreak: "break-all",
  },
  btnRow: {
    display: "flex",
    gap: 6,
    padding: "4px 14px 8px",
  },
  toolBtn: {
    flex: 1,
    padding: "6px 8px",
    background: "var(--elevated-bg)",
    border: "1px solid var(--input-border)",
    borderRadius: 6,
    color: "var(--text-primary)",
    fontSize: 12,
    cursor: "pointer",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    gap: 4,
    fontFamily: "inherit",
  },
  textZone: {
    margin: "0 14px 8px",
    display: "flex",
    flexDirection: "column",
    gap: 6,
  },
  textScopeLbl: {
    fontSize: 10,
    color: "var(--text-muted)",
  },
  textarea: {
    background: "var(--input-bg)",
    border: "1px solid var(--input-border)",
    borderRadius: 6,
    color: "var(--input-color)",
    fontSize: 12,
    padding: "6px 8px",
    resize: "vertical",
    outline: "none",
    fontFamily: "inherit",
    minHeight: 80,
  },
  sendBtn: {
    padding: "6px 12px",
    background: "var(--accent)",
    border: "none",
    borderRadius: 6,
    color: "#fff",
    fontSize: 12,
    fontWeight: 600,
    cursor: "pointer",
    alignSelf: "flex-end",
    fontFamily: "inherit",
  },
  progressWrap: {
    margin: "0 14px 6px",
    position: "relative",
    height: 6,
    background: "var(--elevated-bg)",
    borderRadius: 3,
    overflow: "hidden",
  },
  progressBar: {
    position: "absolute",
    left: 0,
    top: 0,
    height: "100%",
    background: "var(--accent)",
    borderRadius: 3,
    transition: "width 0.2s",
  },
  progressLabel: {
    position: "absolute",
    right: 0,
    top: 8,
    fontSize: 10,
    color: "var(--text-muted)",
  },
  ingestMsg: {
    margin: "0 14px 6px",
    fontSize: 11,
    lineHeight: 1.5,
  },
  docHeader: {
    display: "flex",
    alignItems: "center",
    paddingRight: 10,
  },
  docList: {
    flex: 1,
    overflowY: "auto",
    overflowX: "hidden",
    padding: "2px 6px 6px",
    minHeight: 40,
  },
  docItem: {
    display: "flex",
    alignItems: "center",
    gap: 6,
    padding: "5px 8px",
    borderRadius: 5,
    cursor: "pointer",
    userSelect: "none",
    transition: "background 0.1s",
  },
  docBadge: {
    fontSize: 12,
    flexShrink: 0,
  },
  docName: {
    flex: 1,
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
    fontSize: 12,
    color: "var(--text-primary)",
  },
  docCount: {
    fontSize: 10,
    color: "var(--text-muted)",
    flexShrink: 0,
    background: "var(--elevated-bg)",
    border: "1px solid var(--border)",
    borderRadius: 4,
    padding: "1px 5px",
  },
  hint: {
    padding: "10px 8px",
    fontSize: 12,
    color: "var(--text-muted)",
    fontStyle: "italic",
  },
  legend: {
    display: "flex",
    gap: 14,
    padding: "6px 14px 10px",
    flexShrink: 0,
  },
  legendItem: {
    fontSize: 10,
    color: "var(--text-muted)",
  },
  // Confirm dialog
  overlay: {
    position: "absolute",
    inset: 0,
    background: "rgba(0,0,0,0.5)",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    zIndex: 100,
  },
  dialog: {
    background: "var(--surface-bg)",
    border: "1px solid var(--border)",
    borderRadius: 10,
    padding: "20px 22px",
    width: 240,
    boxShadow: "0 8px 32px rgba(0,0,0,0.35)",
    display: "flex",
    flexDirection: "column",
    gap: 12,
  },
  dialogTitle: {
    fontWeight: 600,
    fontSize: 13,
    color: "var(--text-primary)",
  },
  dialogBody: {
    fontSize: 12,
    color: "var(--text-secondary)",
    lineHeight: 1.5,
  },
  dialogBtns: {
    display: "flex",
    gap: 8,
    justifyContent: "flex-end",
  },
  cancelBtn: {
    padding: "6px 14px",
    background: "var(--elevated-bg)",
    border: "1px solid var(--input-border)",
    borderRadius: 6,
    color: "var(--text-primary)",
    fontSize: 12,
    cursor: "pointer",
    fontFamily: "inherit",
  },
  deleteBtn: {
    padding: "6px 14px",
    background: "#b74040",
    border: "none",
    borderRadius: 6,
    color: "#fff",
    fontSize: 12,
    fontWeight: 600,
    cursor: "pointer",
    fontFamily: "inherit",
  },
};
