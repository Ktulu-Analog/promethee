/**
 * ============================================================================
 * Prométhée — Assistant IA avancé
 * ============================================================================
 * Auteur  : Pierre COUGET
 * Licence : GNU Affero General Public License v3.0 (AGPL-3.0)
 *           https://www.gnu.org/licenses/agpl-3.0.html
 * Année   : 2026
 * ----------------------------------------------------------------------------
 * Ce fichier fait partie du projet Prométhée.
 * Vous pouvez le redistribuer et/ou le modifier selon les termes de la
 * licence AGPL-3.0 publiée par la Free Software Foundation.
 * ============================================================================
 *
 * IngestPanel.tsx — Panneau d'ingestion de répertoires dans Qdrant (admin only)
 *
 * Fonctionnalités :
 *   - Statut Qdrant + config embedding (GET /admin/ingest/status)
 *   - Gestion des collections : lister, créer, supprimer
 *   - Ingestion de répertoire complet avec progression SSE
 *   - Upload direct d'un fichier vers une collection
 *   - Gestion des sources : lister, supprimer
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

// ── Types ──────────────────────────────────────────────────────────────────

interface IngestStatus {
  qdrant_available: boolean;
  qdrant_url: string;
  embedding_model: string;
  embedding_dimension: number;
  embedding_api_base: string;
  contextual_chunking_env: boolean;
  rag_engine_ok: boolean;
  ocr_available: boolean;
  ocr_lang: string;
}

interface Collection {
  name: string;
  vectors_count: number;
}

interface Source {
  source: string;
  chunks: number;
}

interface ProgressEvent {
  done: number | true;
  total?: number;
  filename?: string;
  chunks?: number;
  status?: "ok" | "skipped" | "error";
  error?: string;
  total_chunks?: number;
  success?: number;
  errors?: number;
}

interface Props {
  onClose: () => void;
  embedded?: boolean;
  isAdmin?: boolean;
}

// ── Styles ──────────────────────────────────────────────────────────────────

const s = {
  container: {
    display: "flex",
    flexDirection: "column" as const,
    height: "100%",
    background: "var(--panel-bg, var(--surface-bg))",
    color: "var(--text-primary)",
    fontFamily: "var(--font-sans, system-ui)",
    fontSize: 13,
    overflow: "hidden",
  },
  header: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    padding: "14px 16px 10px",
    borderBottom: "1px solid var(--border)",
    flexShrink: 0,
  },
  headerTitle: {
    fontWeight: 700,
    fontSize: 15,
    display: "flex",
    alignItems: "center",
    gap: 8,
  },
  closeBtn: {
    background: "none",
    border: "none",
    color: "var(--text-muted)",
    cursor: "pointer",
    fontSize: 18,
    lineHeight: 1,
    padding: "2px 6px",
    borderRadius: 4,
  },
  body: {
    flex: 1,
    overflowY: "auto" as const,
    padding: "12px 16px",
    display: "flex",
    flexDirection: "column" as const,
    gap: 16,
  },
  section: {
    display: "flex",
    flexDirection: "column" as const,
    gap: 8,
  },
  sectionTitle: {
    fontWeight: 600,
    fontSize: 12,
    textTransform: "uppercase" as const,
    letterSpacing: "0.06em",
    color: "var(--text-muted)",
    paddingBottom: 4,
    borderBottom: "1px solid var(--border)",
  },
  statusRow: {
    display: "flex",
    alignItems: "center",
    gap: 8,
    fontSize: 12,
    color: "var(--text-secondary)",
  },
  dot: (ok: boolean) => ({
    width: 8,
    height: 8,
    borderRadius: "50%",
    background: ok ? "var(--success, #4caf50)" : "var(--error, #f44336)",
    flexShrink: 0,
  }),
  badge: (ok: boolean) => ({
    display: "inline-block",
    padding: "1px 6px",
    borderRadius: 10,
    fontSize: 11,
    fontWeight: 600,
    background: ok ? "rgba(76,175,80,0.15)" : "rgba(244,67,54,0.15)",
    color: ok ? "var(--success, #4caf50)" : "var(--error, #f44336)",
  }),
  input: {
    width: "100%",
    background: "var(--input-bg, var(--surface-bg))",
    border: "1px solid var(--border)",
    borderRadius: 6,
    padding: "7px 10px",
    color: "var(--text-primary)",
    fontSize: 13,
    outline: "none",
    boxSizing: "border-box" as const,
  },
  select: {
    width: "100%",
    background: "var(--input-bg, var(--surface-bg))",
    border: "1px solid var(--border)",
    borderRadius: 6,
    padding: "7px 10px",
    color: "var(--text-primary)",
    fontSize: 13,
    outline: "none",
    cursor: "pointer",
  },
  row: {
    display: "flex",
    gap: 8,
    alignItems: "center",
  },
  btn: (variant: "primary" | "secondary" | "danger" = "secondary") => ({
    padding: "7px 14px",
    borderRadius: 6,
    cursor: "pointer",
    fontSize: 12,
    fontWeight: 600,
    background:
      variant === "primary" ? "var(--accent)" :
      variant === "danger"  ? "rgba(244,67,54,0.15)" :
      "var(--surface-bg)",
    color:
      variant === "primary" ? "white" :
      variant === "danger"  ? "var(--error, #f44336)" :
      "var(--text-secondary)",
    border:
      variant === "primary"   ? "none" :
      variant === "danger"    ? "1px solid rgba(244,67,54,0.3)" :
      "1px solid var(--border)",
    whiteSpace: "nowrap" as const,
    flexShrink: 0,
  }),
  btnDisabled: {
    opacity: 0.45,
    cursor: "not-allowed",
    pointerEvents: "none" as const,
  },
  progressBox: {
    background: "var(--surface-bg)",
    border: "1px solid var(--border)",
    borderRadius: 8,
    padding: "10px 12px",
    display: "flex",
    flexDirection: "column" as const,
    gap: 6,
  },
  progressBar: (pct: number) => ({
    height: 6,
    borderRadius: 3,
    background: "var(--border)",
    overflow: "hidden" as const,
    position: "relative" as const,
  }),
  progressFill: (pct: number) => ({
    height: "100%",
    width: `${pct}%`,
    borderRadius: 3,
    background: "var(--accent)",
    transition: "width 0.3s ease",
  }),
  logBox: {
    background: "var(--surface-bg)",
    border: "1px solid var(--border)",
    borderRadius: 6,
    padding: "8px 10px",
    maxHeight: 180,
    overflowY: "auto" as const,
    fontFamily: "var(--font-mono, monospace)",
    fontSize: 11,
    color: "var(--text-secondary)",
    display: "flex",
    flexDirection: "column" as const,
    gap: 2,
  },
  logLine: (status?: string) => ({
    color:
      status === "ok"      ? "var(--success, #4caf50)" :
      status === "error"   ? "var(--error, #f44336)" :
      status === "skipped" ? "var(--text-muted)" :
      "var(--text-secondary)",
  }),
  collectionRow: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    padding: "6px 10px",
    borderRadius: 6,
    background: "var(--surface-bg)",
    border: "1px solid var(--border)",
    gap: 8,
  },
  collectionName: {
    fontWeight: 500,
    color: "var(--text-primary)",
    flex: 1,
    minWidth: 0,
    overflow: "hidden",
    textOverflow: "ellipsis" as const,
    whiteSpace: "nowrap" as const,
  },
  collectionCount: {
    color: "var(--text-muted)",
    fontSize: 11,
    flexShrink: 0,
  },
  sourceRow: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    padding: "5px 10px",
    borderRadius: 6,
    background: "var(--surface-bg)",
    border: "1px solid var(--border)",
    gap: 8,
  },
  sourceName: {
    flex: 1,
    overflow: "hidden",
    textOverflow: "ellipsis" as const,
    whiteSpace: "nowrap" as const,
    fontSize: 12,
    color: "var(--text-primary)",
  },
  sourceCount: {
    color: "var(--text-muted)",
    fontSize: 11,
    flexShrink: 0,
  },
  toggle: (active: boolean) => ({
    width: 14,
    height: 14,
    borderRadius: 3,
    border: "1px solid var(--border)",
    background: active ? "var(--accent)" : "transparent",
    cursor: "pointer",
    flexShrink: 0,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    fontSize: 10,
    color: "white",
  }),
  error: {
    background: "rgba(244,67,54,0.08)",
    border: "1px solid rgba(244,67,54,0.25)",
    borderRadius: 6,
    padding: "8px 10px",
    color: "var(--error, #f44336)",
    fontSize: 12,
  },
  labelRow: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
  },
  label: {
    fontSize: 12,
    color: "var(--text-muted)",
    fontWeight: 500,
  },
  tabBar: {
    display: "flex",
    gap: 4,
    borderBottom: "1px solid var(--border)",
    paddingBottom: 0,
    marginBottom: 4,
  },
  tab: (active: boolean) => ({
    padding: "6px 12px",
    background: "none",
    border: "none",
    borderBottom: active ? "2px solid var(--accent)" : "2px solid transparent",
    color: active ? "var(--accent)" : "var(--text-muted)",
    fontWeight: active ? 600 : 400,
    fontSize: 12,
    cursor: "pointer",
    marginBottom: -1,
  }),
  hint: {
    fontSize: 11,
    color: "var(--text-muted)",
    fontStyle: "italic" as const,
  },
  // Modale de confirmation
  modalOverlay: {
    position: "fixed" as const,
    inset: 0,
    background: "rgba(0,0,0,0.55)",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    zIndex: 200,
  },
  modalBox: {
    background: "var(--surface-bg)",
    border: "1px solid var(--border)",
    borderRadius: 10,
    padding: "22px 24px",
    width: 320,
    maxWidth: "90vw",
    boxShadow: "0 8px 40px rgba(0,0,0,0.4)",
    display: "flex",
    flexDirection: "column" as const,
    gap: 14,
  },
  modalTitle: {
    fontWeight: 700,
    fontSize: 14,
    color: "var(--text-primary)",
  },
  modalBody: {
    fontSize: 13,
    color: "var(--text-secondary)",
    lineHeight: 1.55,
  },
  modalBtns: {
    display: "flex",
    gap: 8,
    justifyContent: "flex-end",
  },
};

// ── Composant principal ────────────────────────────────────────────────────

export function IngestPanel({ onClose, embedded, isAdmin = false }: Props) {
  // ── État général ─────────────────────────────────────────────────────────
  const [tab, setTab] = useState<"run" | "collections" | "sources">("run");
  const [status, setStatus]         = useState<IngestStatus | null>(null);
  const [statusLoading, setStatusLoading] = useState(true);
  const [collections, setCollections] = useState<Collection[]>([]);
  const [collLoading, setCollLoading] = useState(false);
  const [error, setError]           = useState<string | null>(null);

  // ── Onglet "Ingérer" ─────────────────────────────────────────────────────
  const [directory, setDirectory]   = useState("");
  const [targetCol, setTargetCol]   = useState("");
  const [recursive, setRecursive]   = useState(true);
  const [useCtx, setUseCtx]         = useState(false);
  const [running, setRunning]       = useState(false);
  const [progress, setProgress]     = useState<ProgressEvent[]>([]);
  const [done, setDone]             = useState(false);
  const logRef = useRef<HTMLDivElement>(null);

  // ── Onglet "Collections" ─────────────────────────────────────────────────
  const [newColName, setNewColName] = useState("");
  const [creating, setCreating]     = useState(false);

  // ── Onglet "Sources" ────────────────────────────────────────────────────
  const [sourcesCol, setSourcesCol] = useState("");
  const [sources, setSources]       = useState<Source[]>([]);
  const [sourcesLoading, setSourcesLoading] = useState(false);

  // ── Upload fichier ───────────────────────────────────────────────────────
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploading, setUploading]   = useState(false);
  const fileInputRef    = useRef<HTMLInputElement>(null);
  const dirInputRef     = useRef<HTMLInputElement>(null);

  // ── Mode d'ingestion : "local" (sélecteur dossier) ou "server" (chemin texte)
  const [ingestMode, setIngestMode]         = useState<"local" | "server">("local");
  const [localFiles, setLocalFiles]         = useState<File[]>([]);
  const [localDirName, setLocalDirName]     = useState<string>("");
  const [uploadingDir, setUploadingDir]     = useState(false);

  // ── État mode non-admin ──────────────────────────────────────────────────
  const [personalCollection, setPersonalCollection] = useState<string>("");
  const [personalVectors, setPersonalVectors]       = useState<number>(0);
  const [clearing, setClearing]                     = useState(false);

  // Modale de confirmation (suppression source / vidage collection)
  const [confirm, setConfirm] = useState<{
    title: string; body: string; danger?: boolean; onConfirm: () => void;
  } | null>(null);

  // ── Chargement initial ────────────────────────────────────────────────────
  const loadStatus = useCallback(async () => {
    setStatusLoading(true);
    try {
      const endpoint = isAdmin ? `${BASE}/admin/ingest/status` : `${BASE}/admin/ingest/personal/status`;
      const r = await authFetch(endpoint);
      if (r.ok) {
        const data = await r.json();
        setStatus(data);
        if (!isAdmin && data.personal_collection) {
          setPersonalCollection(data.personal_collection);
          setPersonalVectors(data.personal_vectors_count ?? 0);
          setTargetCol(data.personal_collection);
        }
      } else setError("Impossible de charger le statut.");
    } catch (e: any) {
      setError(e.message);
    } finally {
      setStatusLoading(false);
    }
  }, []);

  const loadCollections = useCallback(async () => {
    if (!isAdmin) return;  // non-admin : pas de liste de collections
    setCollLoading(true);
    try {
      const r = await authFetch(`${BASE}/admin/ingest/collections`);
      if (r.ok) {
        const cols: Collection[] = await r.json();
        setCollections(cols);
        if (!targetCol && cols.length > 0) setTargetCol(cols[0].name);
        if (!sourcesCol && cols.length > 0) setSourcesCol(cols[0].name);
      }
    } catch {}
    finally { setCollLoading(false); }
  }, [isAdmin, targetCol, sourcesCol]);

  useEffect(() => {
    loadStatus();
    loadCollections();
    // Non-admin : charger les sources dès le montage (pas de useEffect tab au montage)
    if (!isAdmin) loadSources();
  }, []);

  // Recharge les collections à chaque activation de l'onglet Collections
  useEffect(() => {
    if (tab === "collections" && isAdmin) {
      loadCollections();
    }
  }, [tab]);

  // Auto-scroll du log
  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [progress]);


  // ── Ingestion répertoire ──────────────────────────────────────────────────
  async function handleRun() {
    if (!directory.trim() || !targetCol) return;
    setError(null);
    setRunning(true);
    setDone(false);
    setProgress([]);

    try {
      const body = JSON.stringify({
        directory: directory.trim(),
        collection: targetCol,
        recursive,
        use_contextual_chunking: useCtx,
      });
      const r = await authFetch(`${BASE}/admin/ingest/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body,
      });

      if (!r.ok) {
        const j = await r.json().catch(() => ({}));
        setError(j.detail ?? `Erreur ${r.status}`);
        setRunning(false);
        return;
      }

      const reader = r.body!.getReader();
      const decoder = new TextDecoder();
      let buf = "";

      while (true) {
        const { value, done: streamDone } = await reader.read();
        if (streamDone) break;
        buf += decoder.decode(value, { stream: true });
        const lines = buf.split("\n");
        buf = lines.pop() ?? "";
        for (const line of lines) {
          if (!line.startsWith("data:")) continue;
          try {
            const ev: ProgressEvent = JSON.parse(line.slice(5).trim());
            setProgress(prev => [...prev, ev]);
            if (ev.done === true) {
              setDone(true);
              loadCollections();
            }
          } catch {}
        }
      }
    } catch (e: any) {
      setError(e.message);
    } finally {
      setRunning(false);
    }
  }

  // ── Upload fichier ────────────────────────────────────────────────────────
  async function handleUpload() {
    if (!uploadFile || !targetCol) return;
    setUploading(true);
    setError(null);
    try {
      const form = new FormData();
      form.append("file", uploadFile);
      const uploadUrl = isAdmin
        ? `${BASE}/admin/ingest/file?collection=${encodeURIComponent(targetCol)}&use_contextual_chunking=${useCtx}`
        : `${BASE}/admin/ingest/personal/file?use_contextual_chunking=${useCtx}`;
      const r = await authFetch(uploadUrl, { method: "POST", body: form });
      if (!r.ok) {
        const j = await r.json().catch(() => ({}));
        setError(j.detail ?? `Erreur ${r.status}`);
      } else {
        const j = await r.json();
        setProgress(prev => [...prev, {
          done: 1, total: 1, filename: j.filename,
          chunks: j.chunks, status: j.chunks > 0 ? "ok" : "skipped",
        }]);
        setUploadFile(null);
        if (fileInputRef.current) fileInputRef.current.value = "";
        loadCollections();
      }
    } catch (e: any) {
      setError(e.message);
    } finally {
      setUploading(false);
    }
  }

  // ── Upload dossier local (webkitdirectory) ──────────────────────────────────
  async function handleUploadDir() {
    if (!localFiles.length || !targetCol) return;
    setUploadingDir(true);
    setError(null);
    setDone(false);
    setProgress([]);

    const total = localFiles.length;
    let success = 0;
    let errors  = 0;
    let totalChunks = 0;

    for (let i = 0; i < localFiles.length; i++) {
      const file = localFiles[i];
      setProgress(prev => [...prev, {
        done: i + 1, total,
        filename: file.webkitRelativePath || file.name,
        chunks: 0,
        status: undefined,
      }]);
      try {
        const form = new FormData();
        form.append("file", file);
        const uploadEndpoint = isAdmin
          ? `${BASE}/admin/ingest/file?collection=${encodeURIComponent(targetCol)}&use_contextual_chunking=${useCtx}`
          : `${BASE}/admin/ingest/personal/file?use_contextual_chunking=${useCtx}`;
        const r = await authFetch(uploadEndpoint, { method: "POST", body: form });
        const j = r.ok ? await r.json() : null;
        const chunks = j?.chunks ?? 0;
        const st = r.ok ? (chunks > 0 ? "ok" : "skipped") : "error";
        if (st === "ok") { success++; totalChunks += chunks; }
        else errors++;
        setProgress(prev => {
          const next = [...prev];
          next[i] = { done: i + 1, total, filename: file.webkitRelativePath || file.name, chunks, status: st };
          return next;
        });
      } catch (e: any) {
        errors++;
        setProgress(prev => {
          const next = [...prev];
          next[i] = { done: i + 1, total, filename: file.webkitRelativePath || file.name, chunks: 0, status: "error", error: e.message };
          return next;
        });
      }
    }

    setProgress(prev => [...prev, {
      done: true as const,
      total,
      total_chunks: totalChunks,
      success,
      errors,
    }]);
    setDone(true);
    loadCollections();
    setUploadingDir(false);
  }

  // ── Création de collection ────────────────────────────────────────────────
  async function handleCreateCollection() {
    if (!newColName.trim()) return;
    setCreating(true);
    setError(null);
    try {
      const r = await authFetch(`${BASE}/admin/ingest/collections`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: newColName.trim() }),
      });
      if (!r.ok) {
        const j = await r.json().catch(() => ({}));
        setError(j.detail ?? `Erreur ${r.status}`);
      } else {
        setNewColName("");
        await loadCollections();
      }
    } catch (e: any) {
      setError(e.message);
    } finally {
      setCreating(false);
    }
  }

  // ── Suppression de collection ─────────────────────────────────────────────
  async function handleDeleteCollection(name: string) {
    if (!window.confirm(`Supprimer la collection « ${name} » et tous ses vecteurs ?`)) return;
    setError(null);
    try {
      const r = await authFetch(`${BASE}/admin/ingest/collections/${encodeURIComponent(name)}`, { method: "DELETE" });
      if (!r.ok) {
        const j = await r.json().catch(() => ({}));
        setError(j.detail ?? `Erreur ${r.status}`);
      } else {
        await loadCollections();
      }
    } catch (e: any) {
      setError(e.message);
    }
  }

  // ── Sources ────────────────────────────────────────────────────────────────
  // useCallback pour pouvoir le référencer de façon stable dans les useEffect
  const loadSources = useCallback(async () => {
    // Admin : nécessite une collection cible sélectionnée
    if (isAdmin && !sourcesCol) return;
    setSourcesLoading(true);
    setSources([]);
    try {
      const sourcesUrl = isAdmin
        ? `${BASE}/admin/ingest/sources?collection=${encodeURIComponent(sourcesCol)}`
        : `${BASE}/admin/ingest/personal/sources`;
      const r = await authFetch(sourcesUrl);
      if (r.ok) setSources(await r.json());
      else setError("Impossible de charger les sources.");
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSourcesLoading(false);
    }
  }, [isAdmin, sourcesCol]);

  // Chargement automatique à l'activation de l'onglet Sources
  useEffect(() => {
    if (tab === "sources") loadSources();
  }, [tab, loadSources]);

  function handleDeleteSource(source: string) {
    setConfirm({
      title: "Supprimer le document",
      body: `Retirer « ${source} » de la collection ? Cette action est irréversible.`,
      danger: true,
      onConfirm: async () => {
        setConfirm(null);
        try {
          const deleteUrl = isAdmin
            ? `${BASE}/admin/ingest/sources?collection=${encodeURIComponent(sourcesCol)}&source=${encodeURIComponent(source)}`
            : `${BASE}/admin/ingest/personal/sources?source=${encodeURIComponent(source)}`;
          const r = await authFetch(deleteUrl, { method: "DELETE" });
          if (!r.ok) {
            const j = await r.json().catch(() => ({}));
            setError(j.detail ?? `Erreur ${r.status}`);
          } else {
            setSources(prev => prev.filter(s => s.source !== source));
            setPersonalVectors(prev => prev - (sources.find(s => s.source === source)?.chunks ?? 0));
          }
        } catch (e: any) { setError(e.message); }
      },
    });
  }

  function handleClearCollection() {
    const label = isAdmin ? `la collection « ${sourcesCol} »` : "votre collection personnelle";
    setConfirm({
      title: "Vider la collection",
      body: `Supprimer TOUS les documents indexés de ${label} ? Cette action est irréversible.`,
      danger: true,
      onConfirm: async () => {
        setConfirm(null);
        setClearing(true);
        try {
          const url = isAdmin
            ? `${BASE}/admin/ingest/collections/${encodeURIComponent(sourcesCol)}/clear`
            : `${BASE}/admin/ingest/personal/collection`;
          const r = await authFetch(url, { method: "DELETE" });
          if (!r.ok) {
            const j = await r.json().catch(() => ({}));
            setError(j.detail ?? `Erreur ${r.status}`);
          } else {
            setSources([]);
            setPersonalVectors(0);
          }
        } catch (e: any) { setError(e.message); }
        finally { setClearing(false); }
      },
    });
  }

  // ── Calcul progression ────────────────────────────────────────────────────
  const lastFinal = progress.filter(p => p.done === true).pop();
  const lastStep  = progress.filter(p => typeof p.done === "number").pop() as ProgressEvent | undefined;
  const total     = lastStep?.total ?? 0;
  const current   = typeof lastStep?.done === "number" ? lastStep.done : 0;
  const pct       = total > 0 ? Math.round((current / total) * 100) : 0;

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <div style={s.container}>
      {/* Header */}
      <div style={s.header}>
        <div style={s.headerTitle}>
          <span>🗄️</span>
          <span>Ingestion Qdrant</span>
          {status && (
            <span style={s.badge(status.qdrant_available)}>
              {status.qdrant_available ? "Qdrant ✓" : "Qdrant ✗"}
            </span>
          )}
          {!isAdmin && (
            <span style={{ fontSize: 11, color: "var(--text-muted)", marginLeft: 4 }}>
              — Ma collection
            </span>
          )}
        </div>
        <button style={s.closeBtn} onClick={onClose} title="Fermer">✕</button>
      </div>

      <div style={s.body}>
        {/* Statut rapide */}
        {status && (
          <div style={s.section}>
            <div style={s.sectionTitle}>Configuration</div>
            <div style={s.statusRow}>
              <span style={s.dot(status.qdrant_available)} />
              <span>{status.qdrant_url}</span>
            </div>
            <div style={s.statusRow}>
              <span style={{ color: "var(--text-muted)" }}>Modèle embedding :</span>
              <span style={{ fontFamily: "var(--font-mono, monospace)", fontSize: 11 }}>{status.embedding_model}</span>
              <span style={{ color: "var(--text-muted)" }}>dim={status.embedding_dimension}</span>
            </div>
            <div style={s.statusRow}>
              <span style={s.dot(status.ocr_available)} />
              <span>OCR Tesseract {status.ocr_available ? `(${status.ocr_lang})` : "(non disponible)"}</span>
              <span style={{ marginLeft: "auto" }}>
                <span style={s.dot(status.rag_engine_ok)} />
                <span style={{ marginLeft: 4 }}>rag_engine</span>
              </span>
            </div>
          </div>
        )}

        {/* Modale de confirmation générique */}
        {confirm && (
          <div style={s.modalOverlay}>
            <div style={s.modalBox}>
              <div style={s.modalTitle}>{confirm.title}</div>
              <div style={s.modalBody}>{confirm.body}</div>
              <div style={s.modalBtns}>
                <button style={s.btn()} onClick={() => setConfirm(null)}>Annuler</button>
                <button
                  style={s.btn(confirm.danger ? "danger" : "primary")}
                  onClick={confirm.onConfirm}
                >
                  Confirmer
                </button>
              </div>
            </div>
          </div>
        )}

        {error && <div style={s.error}>⚠ {error}</div>}

        {/* Onglets */}
        <div style={s.tabBar}>
          {(isAdmin ? ["run", "collections", "sources"] as const : ["run", "sources"] as const).map(t => (
            <button key={t} style={s.tab(tab === t)} onClick={() => { setTab(t); setError(null); }}>
              {t === "run" ? "📥 Ingérer" : t === "collections" ? "🗂 Collections" : "📄 Mes sources"}
            </button>
          ))}
        </div>

        {/* ── Onglet Ingérer ── */}
        {tab === "run" && (
          <>
            <div style={s.section}>
              <div style={s.sectionTitle}>Collection cible</div>
              {isAdmin ? (
                <>
                  {collLoading
                    ? <div style={s.hint}>Chargement…</div>
                    : collections.length > 0
                      ? <select style={s.select} value={targetCol} onChange={e => setTargetCol(e.target.value)}>
                          {collections.map(c => (
                            <option key={c.name} value={c.name}>{c.name} ({c.vectors_count.toLocaleString()} vecteurs)</option>
                          ))}
                        </select>
                      : <div style={s.hint}>Aucune collection — créez-en une dans l'onglet Collections.</div>
                  }
                  <div style={{ ...s.row, marginTop: 2 }}>
                    <input
                      style={{ ...s.input, flex: 1 }}
                      placeholder="ou saisir un nouveau nom…"
                      value={targetCol}
                      onChange={e => setTargetCol(e.target.value)}
                    />
                  </div>
                </>
              ) : (
                <div style={{
                  display: "flex", alignItems: "center", gap: 10,
                  background: "var(--surface-bg)", border: "1px solid var(--border)",
                  borderRadius: 8, padding: "10px 14px",
                }}>
                  <span style={{ fontSize: 18 }}>🗄️</span>
                  <div>
                    <div style={{ fontWeight: 600, fontSize: 13, color: "var(--text-primary)", fontFamily: "var(--font-mono, monospace)" }}>
                      {personalCollection || "…"}
                    </div>
                    <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 2 }}>
                      {personalVectors.toLocaleString()} vecteurs indexés
                    </div>
                  </div>
                </div>
              )}
            </div>

            <div style={s.section}>
              <div style={s.sectionTitle}>Source à indexer</div>

              {/* Sélecteur de mode — Serveur réservé aux admins */}
              {isAdmin && (
              <div style={{ display: "flex", gap: 0, borderRadius: 6, overflow: "hidden", border: "1px solid var(--border)", alignSelf: "flex-start" }}>
                {(["local", "server"] as const).map(m => (
                  <button
                    key={m}
                    style={{
                      padding: "5px 14px", border: "none", cursor: "pointer", fontSize: 12, fontWeight: 600,
                      background: ingestMode === m ? "var(--accent)" : "transparent",
                      color: ingestMode === m ? "white" : "var(--text-muted)",
                      transition: "background 0.15s",
                    }}
                    onClick={() => { setIngestMode(m); setProgress([]); setDone(false); setError(null); }}
                  >
                    {m === "local" ? "💻 Poste local" : "🖥 Serveur"}
                  </button>
                ))}
              </div>
              )}

              {/* ── Mode LOCAL : sélecteur de dossier ── */}
              {ingestMode === "local" && (
                <>
                  {/* Zone de drop / sélection */}
                  <div
                    style={{
                      border: "2px dashed var(--border)",
                      borderRadius: 8,
                      padding: "20px 16px",
                      textAlign: "center" as const,
                      cursor: "pointer",
                      background: localFiles.length ? "rgba(var(--accent-rgb, 180,130,60),0.06)" : "transparent",
                      transition: "background 0.2s",
                    }}
                    onClick={() => dirInputRef.current?.click()}
                    onDragOver={e => e.preventDefault()}
                    onDrop={e => {
                      e.preventDefault();
                      const items = e.dataTransfer.items;
                      if (!items) return;
                      // La gestion drag&drop de dossier est limitée au navigateur,
                      // on redirige vers le clic pour la compatibilité maximale
                      dirInputRef.current?.click();
                    }}
                  >
                    <input
                      ref={dirInputRef}
                      type="file"
                      style={{ display: "none" }}
                      // @ts-ignore — attribut non-standard supporté par Chrome/Edge/Firefox
                      webkitdirectory=""
                      multiple
                      onChange={e => {
                        const files = Array.from(e.target.files ?? []).filter(f => {
                          const ext = f.name.split('.').pop()?.toLowerCase() ?? '';
                          return [
                            'txt','md','markdown','rst','py','js','jsx','ts','tsx',
                            'json','yaml','yml','xml','csv','tsv','pdf','docx','doc','html','htm'
                          ].includes(ext);
                        });
                        setLocalFiles(files);
                        setLocalDirName(files[0]?.webkitRelativePath?.split('/')[0] ?? "");
                        setProgress([]);
                        setDone(false);
                      }}
                    />
                    {localFiles.length === 0 ? (
                      <>
                        <div style={{ fontSize: 28, marginBottom: 6 }}>📁</div>
                        <div style={{ fontSize: 13, color: "var(--text-secondary)", fontWeight: 500 }}>
                          Cliquer pour sélectionner un dossier
                        </div>
                        <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 4 }}>
                          Tous les fichiers supportés seront indexés
                        </div>
                      </>
                    ) : (
                      <>
                        <div style={{ fontSize: 22, marginBottom: 4 }}>📂</div>
                        <div style={{ fontSize: 13, color: "var(--accent)", fontWeight: 600 }}>
                          {localDirName}
                        </div>
                        <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 3 }}>
                          {localFiles.length} fichier{localFiles.length > 1 ? "s" : ""} sélectionné{localFiles.length > 1 ? "s" : ""}
                          {" · "}
                          <span
                            style={{ color: "var(--accent)", cursor: "pointer", textDecoration: "underline" }}
                            onClick={e => { e.stopPropagation(); setLocalFiles([]); setLocalDirName(""); if (dirInputRef.current) dirInputRef.current.value = ""; }}
                          >
                            Changer
                          </span>
                        </div>
                      </>
                    )}
                  </div>

                  {/* Options + bouton lancer — chunking contextuel réservé aux admins */}
                  {isAdmin && (
                  <div style={s.row}>
                    <button style={s.toggle(useCtx)} onClick={() => setUseCtx(v => !v)}>
                      {useCtx ? "✓" : ""}
                    </button>
                    <span style={s.label}>Chunking contextuel {status?.contextual_chunking_env ? "(env: ON)" : "(env: OFF)"}</span>
                  </div>
                  )}
                  <button
                    style={{
                      ...s.btn("primary"),
                      ...(uploadingDir || !localFiles.length || !targetCol ? s.btnDisabled : {}),
                    }}
                    onClick={handleUploadDir}
                    disabled={uploadingDir || !localFiles.length || !targetCol}
                  >
                    {uploadingDir
                      ? `⏳ Envoi en cours… (${progress.filter(p => typeof p.done === "number").length}/${localFiles.length})`
                      : `▶ Indexer ${localFiles.length || ""} fichier${localFiles.length > 1 ? "s" : ""}`}
                  </button>

                  {/* Upload fichier unique */}
                  <div style={{ borderTop: "1px solid var(--border)", paddingTop: 8, marginTop: 4 }}>
                    <div style={{ ...s.label, marginBottom: 6 }}>Ou un fichier seul :</div>
                    <div style={s.row}>
                      <input
                        ref={fileInputRef}
                        type="file"
                        style={{ flex: 1, fontSize: 12, color: "var(--text-secondary)" }}
                        onChange={e => setUploadFile(e.target.files?.[0] ?? null)}
                        disabled={uploading}
                      />
                      <button
                        style={{ ...s.btn("secondary"), ...(uploading || !uploadFile || !targetCol ? s.btnDisabled : {}) }}
                        onClick={handleUpload}
                        disabled={uploading || !uploadFile || !targetCol}
                      >
                        {uploading ? "⏳" : "Envoyer"}
                      </button>
                    </div>
                  </div>
                </>
              )}

              {/* ── Mode SERVEUR : chemin texte — admin uniquement ── */}
              {ingestMode === "server" && isAdmin && (
                <>
                  <input
                    style={s.input}
                    placeholder="/chemin/absolu/vers/dossier"
                    value={directory}
                    onChange={e => setDirectory(e.target.value)}
                    disabled={running}
                  />
                  <div style={s.row}>
                    <button style={s.toggle(recursive)} onClick={() => setRecursive(v => !v)}>
                      {recursive ? "✓" : ""}
                    </button>
                    <span style={s.label}>Scanner les sous-répertoires</span>
                    <button style={{ ...s.toggle(useCtx), marginLeft: 12 }} onClick={() => setUseCtx(v => !v)}>
                      {useCtx ? "✓" : ""}
                    </button>
                    <span style={s.label}>Chunking contextuel {status?.contextual_chunking_env ? "(env: ON)" : "(env: OFF)"}</span>
                  </div>
                  <button
                    style={{
                      ...s.btn("primary"),
                      ...(running || !directory.trim() || !targetCol ? s.btnDisabled : {}),
                    }}
                    onClick={handleRun}
                    disabled={running || !directory.trim() || !targetCol}
                  >
                    {running ? "⏳ Ingestion en cours…" : "▶ Lancer l'ingestion"}
                  </button>
                </>
              )}
            </div>

            {/* Progression */}
            {progress.length > 0 && (
              <div style={s.section}>
                <div style={s.sectionTitle}>
                  Progression {total > 0 && `— ${current}/${total} fichiers (${pct}%)`}
                  {done && lastFinal && (
                    <span style={{ marginLeft: 8, color: "var(--success, #4caf50)", fontSize: 11 }}>
                      ✓ {lastFinal.success} indexés · {lastFinal.total_chunks?.toLocaleString()} chunks · {lastFinal.errors} ignorés
                    </span>
                  )}
                </div>
                {total > 0 && (
                  <div style={s.progressBar(pct)}>
                    <div style={s.progressFill(pct)} />
                  </div>
                )}
                <div style={s.logBox} ref={logRef}>
                  {progress.filter(p => typeof p.done === "number").map((ev, i) => (
                    <div key={i} style={s.logLine(ev.status)}>
                      {ev.status === "ok"      ? "✓" :
                       ev.status === "error"   ? "✗" :
                       ev.status === "skipped" ? "–" : "•"}
                      {" "}{ev.filename}
                      {ev.status === "ok"    && ` — ${ev.chunks} chunks`}
                      {ev.status === "error" && ` — ${ev.error}`}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </>
        )}

        {/* ── Onglet Collections ── */}
        {tab === "collections" && (
          <>
            <div style={s.section}>
              <div style={s.sectionTitle}>Créer une collection</div>
              <div style={s.row}>
                <input
                  style={{ ...s.input, flex: 1 }}
                  placeholder="nom-de-la-collection"
                  value={newColName}
                  onChange={e => setNewColName(e.target.value)}
                  onKeyDown={e => e.key === "Enter" && handleCreateCollection()}
                />
                <button
                  style={{
                    ...s.btn("primary"),
                    ...(creating || !newColName.trim() ? s.btnDisabled : {}),
                  }}
                  onClick={handleCreateCollection}
                  disabled={creating || !newColName.trim()}
                >
                  Créer
                </button>
              </div>
              <div style={s.hint}>Dimension : {status?.embedding_dimension ?? "…"} (depuis EMBEDDING_DIMENSION)</div>
            </div>

            <div style={s.section}>
              <div style={{ ...s.labelRow }}>
                <div style={s.sectionTitle}>Collections existantes ({collections.length})</div>
                <button style={{ ...s.btn(), fontSize: 11 }} onClick={loadCollections}>↻ Rafraîchir</button>
              </div>
              {collLoading && <div style={s.hint}>Chargement…</div>}
              {!collLoading && collections.length === 0 && <div style={s.hint}>Aucune collection.</div>}
              {collections.map(c => (
                <div key={c.name} style={s.collectionRow}>
                  <span style={s.collectionName} title={c.name}>{c.name}</span>
                  <span style={s.collectionCount}>{c.vectors_count.toLocaleString()} vect.</span>
                  <button
                    style={s.btn("danger")}
                    onClick={() => handleDeleteCollection(c.name)}
                  >
                    Supprimer
                  </button>
                </div>
              ))}
            </div>
          </>
        )}

        {/* ── Onglet Sources ── */}
        {tab === "sources" && (
          <>
            {isAdmin ? (
            <div style={s.section}>
              <div style={s.sectionTitle}>Collection</div>
              <div style={s.row}>
                <select
                  style={{ ...s.select, flex: 1 }}
                  value={sourcesCol}
                  onChange={e => { setSourcesCol(e.target.value); setSources([]); }}
                >
                  {collections.map(c => (
                    <option key={c.name} value={c.name}>{c.name}</option>
                  ))}
                </select>
                <button
                  style={{ ...s.btn(), ...(sourcesLoading || !sourcesCol ? s.btnDisabled : {}) }}
                  onClick={loadSources}
                  disabled={sourcesLoading || !sourcesCol}
                >
                  {sourcesLoading ? "…" : "Charger"}
                </button>
              </div>
            </div>
            ) : (
            <div style={s.section}>
              <div style={{ ...s.labelRow }}>
                <div style={s.sectionTitle}>Ma collection personnelle</div>
                <button style={{ ...s.btn(), fontSize: 11 }} onClick={loadSources} disabled={sourcesLoading}>
                  {sourcesLoading ? "…" : "↻ Rafraîchir"}
                </button>
              </div>
              <div style={{ ...s.hint, marginBottom: 4 }}>
                {personalCollection && <span style={{ fontFamily: "var(--font-mono, monospace)", color: "var(--accent)" }}>{personalCollection}</span>}
                {" — "}{personalVectors.toLocaleString()} vecteurs indexés
              </div>
              {sources.length > 0 && (
                <button
                  style={{ ...s.btn("danger"), alignSelf: "flex-start", ...(clearing ? s.btnDisabled : {}) }}
                  onClick={handleClearCollection}
                  disabled={clearing}
                  title="Supprimer tous les documents de votre collection personnelle"
                >
                  {clearing ? "Vidage…" : "🗑 Vider la collection"}
                </button>
              )}
            </div>
            )}

            {sources.length > 0 && (
              <div style={s.section}>
                <div style={s.sectionTitle}>Documents indexés ({sources.length})</div>
                {sources.map(src => (
                  <div key={src.source} style={s.sourceRow}>
                    <span style={s.sourceName} title={src.source}>{src.source}</span>
                    <span style={s.sourceCount}>{src.chunks} chunks</span>
                    <button
                      style={s.btn("danger")}
                      onClick={() => handleDeleteSource(src.source)}
                      title={`Supprimer « ${src.source} »`}
                    >
                      ✕
                    </button>
                  </div>
                ))}
              </div>
            )}
            {sources.length === 0 && !sourcesLoading && (
              <div style={s.hint}>Aucun document indexé dans votre collection.</div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
