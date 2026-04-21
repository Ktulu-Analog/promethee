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
 * VfsPanel.tsx — Explorateur du système de fichiers virtuel
 *
 * Fonctionnalités :
 *   - Navigation arborescente (breadcrumb + liste)
 *   - Icônes grandes et colorées selon type MIME / extension
 *   - Renommer, supprimer, créer dossier
 *   - Déplacer via menu contextuel (modale arborescence) ET drag & drop
 *   - Uploader des fichiers (drag & drop ou sélecteur)
 *   - Télécharger un fichier
 *   - Affichage quota
 *   - Recherche dans le dossier courant
 *   - Menu contextuel (clic droit)
 *   - Détection fichiers orphelins MinIO
 */

import React, {
  useState,
  useEffect,
  useRef,
  useCallback,
  KeyboardEvent,
} from "react";
import { createPortal } from "react-dom";
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

interface VfsEntry {
  name: string;
  path: string;
  type: "file" | "dir";
  size?: string;
  size_bytes?: number;
  mime_type?: string;
  created_at?: string;
  updated_at?: string;
}

interface VfsQuota {
  total_files: number;
  total_bytes: number;
  total_size: string;
  quota_limit_bytes: number;
  quota_limit: string;
  quota_used_pct: number;
  quota_exceeded: boolean;
  backend: string;
}

interface CtxMenu {
  x: number;
  y: number;
  entry: VfsEntry;
}

interface DragState {
  path: string;
  name: string;
}

// ── Helpers ────────────────────────────────────────────────────────────────

function formatDate(iso?: string): string {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleDateString("fr-FR", {
      day: "2-digit", month: "2-digit", year: "numeric",
      hour: "2-digit", minute: "2-digit",
    });
  } catch { return iso; }
}

function joinPath(...parts: string[]): string {
  return "/" + parts.map((p) => p.replace(/^\/+|\/+$/g, "")).filter(Boolean).join("/");
}

function parentPath(path: string): string {
  const parts = path.split("/").filter(Boolean);
  if (parts.length === 0) return "/";
  return "/" + parts.slice(0, -1).join("/");
}

function getExt(name: string): string {
  return name.split(".").pop()?.toLowerCase() ?? "";
}

// ── Couleur & label par type de fichier ───────────────────────────────────

function fileStyle(mime: string | undefined, name: string): { color: string; label: string } {
  const ext = getExt(name);
  const m = mime ?? "";
  if (m.startsWith("image/") || ["png","jpg","jpeg","gif","webp","svg","bmp","ico"].includes(ext))
    return { color: "#7ab8e0", label: "IMG" };
  if (m === "application/pdf" || ext === "pdf")
    return { color: "#e07070", label: "PDF" };
  if (["doc","docx","odt","rtf"].includes(ext))
    return { color: "#7aafd4", label: "DOC" };
  if (["xls","xlsx","ods","csv"].includes(ext))
    return { color: "#5aaa7a", label: "XLS" };
  if (["ppt","pptx"].includes(ext))
    return { color: "#e08f4a", label: "PPT" };
  if (m.startsWith("audio/") || ["mp3","wav","ogg","flac","aac","m4a"].includes(ext))
    return { color: "#b07ae0", label: "SON" };
  if (m.startsWith("video/") || ["mp4","avi","mkv","mov","webm"].includes(ext))
    return { color: "#e07aaa", label: "VID" };
  if (["py","js","ts","tsx","jsx","json","html","css","sh","rs","go","java","c","cpp","h","yml","yaml","toml"].includes(ext))
    return { color: "#d4a03d", label: ext.toUpperCase().slice(0,3) };
  if (["zip","tar","gz","7z","rar","bz2"].includes(ext))
    return { color: "#a0aa5a", label: "ZIP" };
  if (["md","txt","log"].includes(ext))
    return { color: "#8a9ab0", label: "TXT" };
  return { color: "#6a6a78", label: ext ? ext.toUpperCase().slice(0,3) : "FIL" };
}

// ── Icône fichier grande ───────────────────────────────────────────────────

function FileIconLarge({ mime, name, size = 52 }: { mime?: string; name: string; size?: number }) {
  const { color, label } = fileStyle(mime, name);
  const ext = getExt(name);
  const s = size;

  if ((mime ?? "").startsWith("image/") || ["png","jpg","jpeg","gif","webp","svg","bmp"].includes(ext)) {
    return (
      <svg viewBox="0 0 52 52" width={s} height={s} style={{ display: "block", flexShrink: 0 }}>
        <rect x="2" y="2" width="48" height="48" rx="6" fill={color} fillOpacity=".13" stroke={color} strokeWidth="1.8"/>
        <rect x="8" y="10" width="36" height="26" rx="3" fill={color} fillOpacity=".18" stroke={color} strokeWidth="1.5"/>
        <circle cx="17" cy="19" r="4" fill={color} fillOpacity=".7"/>
        <polyline points="8,36 18,25 25,31 34,21 44,36" fill="none" stroke={color} strokeWidth="2" strokeLinejoin="round"/>
        <text x="26" y="47" textAnchor="middle" fontSize="7" fill={color} fontFamily="monospace" fontWeight="700">{label}</text>
      </svg>
    );
  }
  if ((mime ?? "").startsWith("audio/") || ["mp3","wav","ogg","flac","aac","m4a"].includes(ext)) {
    return (
      <svg viewBox="0 0 52 52" width={s} height={s} style={{ display: "block", flexShrink: 0 }}>
        <rect x="2" y="2" width="48" height="48" rx="6" fill={color} fillOpacity=".13" stroke={color} strokeWidth="1.8"/>
        <circle cx="18" cy="35" r="7" fill="none" stroke={color} strokeWidth="2"/>
        <circle cx="18" cy="35" r="3" fill={color} fillOpacity=".5"/>
        <path d="M25 35V16l16-4v19" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round"/>
        <circle cx="41" cy="31" r="7" fill="none" stroke={color} strokeWidth="2"/>
        <circle cx="41" cy="31" r="3" fill={color} fillOpacity=".5"/>
      </svg>
    );
  }
  if ((mime ?? "").startsWith("video/") || ["mp4","avi","mkv","mov","webm"].includes(ext)) {
    return (
      <svg viewBox="0 0 52 52" width={s} height={s} style={{ display: "block", flexShrink: 0 }}>
        <rect x="2" y="2" width="48" height="48" rx="6" fill={color} fillOpacity=".13" stroke={color} strokeWidth="1.8"/>
        <rect x="6" y="14" width="32" height="24" rx="3" fill="none" stroke={color} strokeWidth="1.8"/>
        <polyline points="38,20 46,16 46,36 38,32" fill={color} fillOpacity=".3" stroke={color} strokeWidth="1.8" strokeLinejoin="round"/>
        <polygon points="16,20 16,32 28,26" fill={color} fillOpacity=".6"/>
      </svg>
    );
  }
  if (["zip","tar","gz","7z","rar","bz2"].includes(ext)) {
    return (
      <svg viewBox="0 0 52 52" width={s} height={s} style={{ display: "block", flexShrink: 0 }}>
        <rect x="2" y="2" width="48" height="48" rx="6" fill={color} fillOpacity=".13" stroke={color} strokeWidth="1.8"/>
        <rect x="16" y="6" width="12" height="7" rx="2" fill={color} fillOpacity=".3" stroke={color} strokeWidth="1.5"/>
        <rect x="16" y="13" width="12" height="7" rx="0" fill="none" stroke={color} strokeWidth="1.5" strokeDasharray="3 2"/>
        <rect x="16" y="20" width="12" height="7" rx="0" fill={color} fillOpacity=".15" stroke={color} strokeWidth="1.5"/>
        <rect x="16" y="27" width="12" height="7" rx="0" fill="none" stroke={color} strokeWidth="1.5" strokeDasharray="3 2"/>
        <rect x="14" y="34" width="16" height="10" rx="3" fill={color} fillOpacity=".4" stroke={color} strokeWidth="1.8"/>
        <text x="22" y="42" textAnchor="middle" fontSize="6" fill={color} fontFamily="monospace" fontWeight="700">ZIP</text>
      </svg>
    );
  }
  // Document générique
  return (
    <svg viewBox="0 0 52 52" width={s} height={s} style={{ display: "block", flexShrink: 0 }}>
      <path d="M8 4 H36 L46 14 V48 H8 Z" fill={color} fillOpacity=".13" stroke={color} strokeWidth="1.8" strokeLinejoin="round"/>
      <path d="M36 4 V14 H46" fill="none" stroke={color} strokeWidth="1.8" strokeLinejoin="round"/>
      <line x1="14" y1="22" x2="38" y2="22" stroke={color} strokeWidth="2" strokeLinecap="round"/>
      <line x1="14" y1="28" x2="38" y2="28" stroke={color} strokeWidth="2" strokeLinecap="round"/>
      <line x1="14" y1="34" x2="28" y2="34" stroke={color} strokeWidth="2" strokeLinecap="round"/>
      <rect x="10" y="40" width="20" height="8" rx="2" fill={color} fillOpacity=".25"/>
      <text x="20" y="47" textAnchor="middle" fontSize="6" fill={color} fontFamily="monospace" fontWeight="700">{label}</text>
    </svg>
  );
}

// ── Icône fichier petite ───────────────────────────────────────────────────

function FileIconSmall({ mime, name, size = 16 }: { mime?: string; name: string; size?: number }) {
  const { color } = fileStyle(mime, name);
  return (
    <svg viewBox="0 0 16 16" width={size} height={size} style={{ display: "block", flexShrink: 0 }}>
      <path d="M3 1h7l3 3v11H3V1z" stroke={color} strokeWidth="1.3" fill={color} fillOpacity=".12" strokeLinejoin="round"/>
      <path d="M10 1v3h3" stroke={color} strokeWidth="1.2" fill="none"/>
      <line x1="5" y1="8" x2="11" y2="8" stroke={color} strokeWidth="1.2" strokeLinecap="round"/>
      <line x1="5" y1="11" x2="9" y2="11" stroke={color} strokeWidth="1.2" strokeLinecap="round"/>
    </svg>
  );
}

// ── Icône dossier grande ───────────────────────────────────────────────────

function FolderIconLarge({ open = false, size = 52 }: { open?: boolean; size?: number }) {
  const color = "#d4813d";
  return (
    <svg viewBox="0 0 52 52" width={size} height={size} style={{ display: "block", flexShrink: 0 }}>
      <path
        d="M4 14C4 11.8 5.8 10 8 10H20L24 16H44C46.2 16 48 17.8 48 20V40C48 42.2 46.2 44 44 44H8C5.8 44 4 42.2 4 40V14Z"
        fill={color} fillOpacity={open ? 0.35 : 0.18}
        stroke={color} strokeWidth="1.8" strokeLinejoin="round"
      />
      {open && <path d="M14 44L10 28H42L38 44Z" fill={color} fillOpacity="0.15"/>}
    </svg>
  );
}

// ── Icône dossier petite ───────────────────────────────────────────────────

function FolderIconSmall({ open = false, size = 16 }: { open?: boolean; size?: number }) {
  const color = "#d4813d";
  return (
    <svg viewBox="0 0 16 16" width={size} height={size} style={{ display: "block", flexShrink: 0 }}>
      <path
        d="M1 4.5C1 3.7 1.7 3 2.5 3H6l1.5 2H13.5C14.3 5 15 5.7 15 6.5V12.5C15 13.3 14.3 14 13.5 14H2.5C1.7 14 1 13.3 1 12.5V4.5Z"
        stroke={color} strokeWidth="1.3" fill={open ? color : "none"} fillOpacity={open ? 0.22 : 0} strokeLinejoin="round"
      />
    </svg>
  );
}

// ── Modale "Déplacer vers…" ───────────────────────────────────────────────

interface MoveModalProps {
  srcPath: string;
  srcName: string;
  onConfirm: (dstDir: string) => void;
  onCancel: () => void;
}

function MoveModal({ srcPath, srcName, onConfirm, onCancel }: MoveModalProps) {
  const [browsePath, setBrowsePath] = useState("/");
  const [dirs, setDirs] = useState<VfsEntry[]>([]);
  const [loading, setLoading] = useState(false);

  const loadDirs = useCallback(async (path: string) => {
    setLoading(true);
    try {
      const r = await authFetch(`${BASE}/vfs/list?path=${encodeURIComponent(path)}`);
      if (!r.ok) return;
      const data = await r.json();
      setDirs((data.entries ?? []).filter((e: VfsEntry) => e.type === "dir" && e.path !== srcPath));
    } finally {
      setLoading(false);
    }
  }, [srcPath]);

  useEffect(() => { loadDirs(browsePath); }, [browsePath, loadDirs]);

  const crumbs: Array<{ label: string; path: string }> = [{ label: "🏠", path: "/" }];
  const parts = browsePath.split("/").filter(Boolean);
  let acc = "";
  for (const p of parts) { acc += "/" + p; crumbs.push({ label: p, path: acc }); }

  const srcParent = parentPath(srcPath);
  const isSameLocation = browsePath === srcParent;

  return (
    <div
      style={{ position: "fixed", inset: 0, zIndex: 700, background: "rgba(0,0,0,0.55)", display: "flex", alignItems: "center", justifyContent: "center" }}
      onMouseDown={(e) => { if (e.target === e.currentTarget) onCancel(); }}
    >
      <div style={{ width: 380, maxHeight: "70vh", background: "var(--elevated-bg)", border: "1px solid var(--border)", borderRadius: 12, boxShadow: "0 12px 48px rgba(0,0,0,0.5)", display: "flex", flexDirection: "column", overflow: "hidden" }}>
        {/* En-tête */}
        <div style={{ padding: "14px 16px 10px", borderBottom: "1px solid var(--border)", flexShrink: 0 }}>
          <div style={{ fontWeight: 700, fontSize: 13, color: "var(--text-primary)", marginBottom: 6 }}>
            Déplacer « {srcName} »
          </div>
          <div style={{ display: "flex", gap: 3, flexWrap: "wrap", alignItems: "center" }}>
            {crumbs.map((c, i) => (
              <React.Fragment key={c.path}>
                {i > 0 && <span style={{ color: "var(--text-disabled)", fontSize: 11 }}>/</span>}
                <button onClick={() => setBrowsePath(c.path)} style={{ background: "none", border: "none", cursor: "pointer", color: i === crumbs.length - 1 ? "var(--text-primary)" : "var(--accent)", fontSize: 11, padding: "1px 2px", fontWeight: i === crumbs.length - 1 ? 700 : 400 }}>
                  {c.label}
                </button>
              </React.Fragment>
            ))}
          </div>
        </div>

        {/* Liste dossiers */}
        <div style={{ flex: 1, overflowY: "auto", padding: "6px 0" }}>
          {browsePath !== "/" && (
            <DirRow label="⬆ Dossier parent" muted onClick={() => setBrowsePath(parentPath(browsePath))} />
          )}
          {loading && <div style={{ padding: 16, textAlign: "center", color: "var(--text-muted)", fontSize: 12 }}><LoadingDots /></div>}
          {!loading && dirs.length === 0 && (
            <div style={{ padding: "20px 16px", textAlign: "center", color: "var(--text-disabled)", fontSize: 12 }}>Aucun sous-dossier</div>
          )}
          {dirs.map((d) => (
            <DirRow key={d.path} label={d.name} hasChildren onClick={() => setBrowsePath(d.path)} />
          ))}
        </div>

        {/* Footer */}
        <div style={{ padding: "10px 16px", borderTop: "1px solid var(--border)", display: "flex", gap: 8, justifyContent: "flex-end", background: "var(--surface-bg)", flexShrink: 0 }}>
          <div style={{ flex: 1, fontSize: 11, color: "var(--text-muted)", alignSelf: "center", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            → {browsePath}
          </div>
          <button onClick={onCancel} style={{ background: "none", border: "1px solid var(--border)", borderRadius: 6, color: "var(--text-muted)", fontSize: 12, padding: "5px 14px", cursor: "pointer" }}>
            Annuler
          </button>
          <button
            onClick={() => onConfirm(browsePath)}
            disabled={isSameLocation}
            style={{ background: isSameLocation ? "var(--border)" : "var(--accent)", border: "none", borderRadius: 6, color: isSameLocation ? "var(--text-disabled)" : "#fff", fontSize: 12, padding: "5px 14px", cursor: isSameLocation ? "not-allowed" : "pointer", fontWeight: 600 }}
          >
            Déplacer ici
          </button>
        </div>
      </div>
    </div>
  );
}

function DirRow({ label, muted = false, hasChildren = false, onClick }: { label: string; muted?: boolean; hasChildren?: boolean; onClick: () => void }) {
  const [hovered, setHovered] = useState(false);
  return (
    <div
      onMouseEnter={() => setHovered(true)} onMouseLeave={() => setHovered(false)}
      onClick={onClick}
      style={{ display: "flex", alignItems: "center", gap: 10, padding: "7px 16px", cursor: "pointer", background: hovered ? "var(--sidebar-item-hover-bg)" : "transparent", transition: "background 0.1s" }}
    >
      {!muted && <FolderIconSmall size={15} />}
      <span style={{ flex: 1, fontSize: 12, color: muted ? "var(--text-muted)" : "var(--text-secondary)" }}>{label}</span>
      {hasChildren && (
        <svg viewBox="0 0 16 16" width={11} height={11}><polyline points="5,3 11,8 5,13" fill="none" stroke="var(--text-muted)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></svg>
      )}
    </div>
  );
}

// ── Composant principal ────────────────────────────────────────────────────

export interface VfsPanelProps {
  onClose: () => void;
  embedded?: boolean;
}

export function VfsPanel({ onClose, embedded = false }: VfsPanelProps) {
  const [currentPath, setCurrentPath] = useState("/");
  const [entries, setEntries] = useState<VfsEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [quota, setQuota] = useState<VfsQuota | null>(null);
  const [orphans, setOrphans] = useState<Set<string>>(new Set());
  const [search, setSearch] = useState("");
  const [searchRecursive, setSearchRecursive] = useState(false);
  const [searchResults, setSearchResults] = useState<VfsEntry[]>([]);
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchTruncated, setSearchTruncated] = useState(false);
  const searchDebounce = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [ctxMenu, setCtxMenu] = useState<CtxMenu | null>(null);
  const [renamingPath, setRenamingPath] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const [newFolderMode, setNewFolderMode] = useState(false);
  const [newFolderName, setNewFolderName] = useState("");
  const [dragging, setDragging] = useState<DragState | null>(null);
  const [dragOverPath, setDragOverPath] = useState<string | null>(null);
  const [dragOverPanel, setDragOverPanel] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [sortBy, setSortBy] = useState<"name" | "size" | "date">("name");
  const [sortAsc, setSortAsc] = useState(true);
  const [viewMode, setViewMode] = useState<"list" | "grid">("grid");
  const [moveModal, setMoveModal] = useState<{ path: string; name: string } | null>(null);
  const [confirmModal, setConfirmModal] = useState<{ message: string; onConfirm: () => void } | null>(null);
  const [tooltip, setTooltip] = useState<TooltipState | null>(null);
  const tooltipTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);

  // ── Chargement ────────────────────────────────────────────────────────

  const loadDir = useCallback(async (path: string) => {
    setLoading(true);
    setError(null);
    setSelected(new Set());
    setOrphans(new Set());
    try {
      const r = await authFetch(`${BASE}/vfs/list?path=${encodeURIComponent(path)}`);
      if (!r.ok) throw new Error(await r.text());
      const data = await r.json();
      setEntries(data.entries ?? []);
      authFetch(`${BASE}/vfs/check?path=${encodeURIComponent(path)}`)
        .then(r2 => r2.ok ? r2.json() : null)
        .then(data2 => { if (data2?.orphans?.length) setOrphans(new Set(data2.orphans as string[])); })
        .catch(() => {});
    } catch (e: any) {
      setError(e.message ?? "Erreur lors du chargement");
    } finally {
      setLoading(false);
    }
  }, []);

  const loadQuota = useCallback(async () => {
    try {
      const r = await authFetch(`${BASE}/vfs/quota`);
      if (r.ok) setQuota(await r.json());
    } catch {}
  }, []);

  useEffect(() => { loadDir(currentPath); }, [currentPath, loadDir]);
  useEffect(() => { loadQuota(); }, [loadQuota]);

  // ── Navigation ────────────────────────────────────────────────────────

  function navigate(path: string) {
    if (tooltipTimer.current) clearTimeout(tooltipTimer.current);
    setTooltip(null);
    setSearch("");
    setSearchRecursive(false);
    setSearchResults([]);
    setSearchTruncated(false);
    setNewFolderMode(false);
    setCurrentPath(path);
  }

  function breadcrumbParts(): Array<{ label: string; path: string }> {
    const parts = currentPath.split("/").filter(Boolean);
    const crumbs: Array<{ label: string; path: string }> = [{ label: "🏠", path: "/" }];
    let acc = "";
    for (const p of parts) { acc += "/" + p; crumbs.push({ label: p, path: acc }); }
    return crumbs;
  }

  // ── Recherche récursive ───────────────────────────────────────────────

  const doRecursiveSearch = useCallback(async (term: string) => {
    if (!term.trim()) {
      setSearchRecursive(false);
      setSearchResults([]);
      setSearchTruncated(false);
      return;
    }
    setSearchRecursive(true);
    setSearchLoading(true);
    setSearchTruncated(false);
    try {
      const r = await authFetch(
        `${BASE}/vfs/search?q=${encodeURIComponent(term)}&path=${encodeURIComponent(currentPath)}`
      );
      if (!r.ok) throw new Error(await r.text());
      const data = await r.json();
      setSearchResults(data.results ?? []);
      setSearchTruncated(data.truncated ?? false);
    } catch (e: any) {
      console.error("Recursive search error:", e);
    } finally {
      setSearchLoading(false);
    }
  }, [currentPath]);

  // ── Tri & filtre ──────────────────────────────────────────────────────

  const displayEntries = searchRecursive ? searchResults : entries;

  const filtered = displayEntries
    .filter((e) => !searchRecursive && search
      ? e.name.toLowerCase().includes(search.toLowerCase())
      : true)
    .sort((a, b) => {
      if (a.type !== b.type) return a.type === "dir" ? -1 : 1;
      let cmp = 0;
      if (sortBy === "name") cmp = a.name.localeCompare(b.name, "fr");
      else if (sortBy === "size") cmp = (a.size_bytes ?? 0) - (b.size_bytes ?? 0);
      else cmp = (a.updated_at ?? "").localeCompare(b.updated_at ?? "");
      return sortAsc ? cmp : -cmp;
    });

  // ── Actions ───────────────────────────────────────────────────────────

  async function handleDelete(path: string) {
    setConfirmModal({
      message: `Supprimer "${path.split("/").pop()}" ?`,
      onConfirm: async () => {
        setConfirmModal(null);
        try {
          const r = await authFetch(`${BASE}/vfs/delete?path=${encodeURIComponent(path)}`, { method: "DELETE" });
          if (!r.ok) throw new Error(await r.text());
          await loadDir(currentPath); await loadQuota();
        } catch (e: any) { alert("Erreur : " + e.message); }
      },
    });
  }

  async function handleDownload(path: string, name: string) {
    try {
      const r = await authFetch(`${BASE}/vfs/download?path=${encodeURIComponent(path)}`);
      if (!r.ok) { alert(`Erreur (${r.status}) :\n${await r.text().catch(() => "")}`); return; }
      const blob = await r.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = name;
      document.body.appendChild(a); a.click(); document.body.removeChild(a);
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (e: any) { alert(`Erreur : ${e.message}`); }
  }

  async function handleRename(oldPath: string, newName: string) {
    if (!newName.trim()) return;
    const newPath = joinPath(parentPath(oldPath), newName.trim());
    try {
      const r = await authFetch(`${BASE}/vfs/move?src=${encodeURIComponent(oldPath)}&dst=${encodeURIComponent(newPath)}`, { method: "POST" });
      if (!r.ok) throw new Error(await r.text());
      await loadDir(currentPath);
    } catch (e: any) { alert("Erreur : " + e.message); }
    setRenamingPath(null);
  }

  async function handleMkdir(name: string) {
    if (!name.trim()) { setNewFolderMode(false); return; }
    try {
      const r = await authFetch(`${BASE}/vfs/mkdir?path=${encodeURIComponent(joinPath(currentPath, name.trim()))}`, { method: "POST" });
      if (!r.ok) throw new Error(await r.text());
      await loadDir(currentPath);
    } catch (e: any) { alert("Erreur : " + e.message); }
    setNewFolderMode(false); setNewFolderName("");
  }

  async function handleMove(srcPath: string, dstDirPath: string) {
    const name = srcPath.split("/").pop() ?? "fichier";
    const newPath = joinPath(dstDirPath, name);
    if (newPath === srcPath) return;
    try {
      const r = await authFetch(`${BASE}/vfs/move?src=${encodeURIComponent(srcPath)}&dst=${encodeURIComponent(newPath)}`, { method: "POST" });
      if (!r.ok) throw new Error(await r.text());
      await loadDir(currentPath);
    } catch (e: any) { alert("Erreur déplacement : " + e.message); }
  }

  async function handleUpload(files: FileList | File[]) {
    for (const file of Array.from(files)) {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("vfs_path", joinPath(currentPath, file.name));
      try { await authFetch(`${BASE}/upload/file`, { method: "POST", body: formData }); }
      catch (e: any) { console.error("Upload error:", e); }
    }
    await loadDir(currentPath); await loadQuota();
  }

  // ── Drag & Drop OS ────────────────────────────────────────────────────

  function handleDragOver(e: React.DragEvent) {
    if (e.dataTransfer.types.includes("Files")) { e.preventDefault(); setDragOverPanel(true); }
  }
  function handleDragLeave() { setDragOverPanel(false); }
  function handleDrop(e: React.DragEvent) {
    e.preventDefault(); setDragOverPanel(false);
    if (e.dataTransfer.files.length) handleUpload(e.dataTransfer.files);
  }

  // ── Drag & Drop interne ───────────────────────────────────────────────

  function handleEntryDragStart(e: React.DragEvent, entry: VfsEntry) {
    e.dataTransfer.effectAllowed = "move";
    setDragging({ path: entry.path, name: entry.name });
  }
  function handleEntryDragOver(e: React.DragEvent, entry: VfsEntry) {
    if (!dragging || entry.type !== "dir" || dragging.path === entry.path) return;
    e.preventDefault(); setDragOverPath(entry.path);
  }
  function handleEntryDrop(e: React.DragEvent, entry: VfsEntry) {
    e.preventDefault();
    if (!dragging || entry.type !== "dir") return;
    handleMove(dragging.path, entry.path);
    setDragging(null); setDragOverPath(null);
  }
  function handleEntryDragEnd() { setDragging(null); setDragOverPath(null); }

  function toggleSelect(path: string, multi: boolean) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (!multi) next.clear();
      if (next.has(path)) next.delete(path); else next.add(path);
      return next;
    });
  }

  function handleCtxMenu(e: React.MouseEvent, entry: VfsEntry) {
    e.preventDefault(); e.stopPropagation();
    setCtxMenu({ x: e.clientX, y: e.clientY, entry });
  }

  function handleHover(entry: VfsEntry, x: number, y: number) {
    // Si le tooltip est déjà affiché pour cette même entrée, ne pas relancer le timer
    if (tooltip?.entry.path === entry.path) return;
    if (tooltipTimer.current) clearTimeout(tooltipTimer.current);
    tooltipTimer.current = setTimeout(() => {
      setTooltip({ entry, x, y });
    }, 600);
  }

  function handleHoverEnd() {
    if (tooltipTimer.current) clearTimeout(tooltipTimer.current);
    setTooltip(null);
  }

  useEffect(() => {
    function close() { if (ctxMenu) setCtxMenu(null); }
    window.addEventListener("mousedown", close);
    return () => window.removeEventListener("mousedown", close);
  }, [ctxMenu]);

  // ── Rendu ─────────────────────────────────────────────────────────────

  const crumbs = breadcrumbParts();

  return (
    <div
      ref={panelRef}
      style={{
        display: "flex", flexDirection: "column", height: "100%",
        background: embedded ? "transparent" : "var(--surface-bg)",
        color: "var(--text-primary)",
        fontFamily: "'SF Mono', 'JetBrains Mono', 'Fira Code', monospace",
        fontSize: 12, position: "relative", userSelect: "none",
        ...(dragOverPanel ? { outline: "2px dashed var(--accent)", outlineOffset: -4 } : {}),
      }}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      {/* ── En-tête ── */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "12px 14px 10px", borderBottom: "1px solid var(--border)", flexShrink: 0 }}>
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" width={16} height={16} style={{ flexShrink: 0 }}>
          <path d="M1 3.5C1 2.7 1.7 2 2.5 2H6L7.5 4H13.5C14.3 4 15 4.7 15 5.5V12.5C15 13.3 14.3 14 13.5 14H2.5C1.7 14 1 13.3 1 12.5V3.5Z"
            stroke="var(--accent)" strokeWidth="1.3" fill="var(--accent)" fillOpacity="0.15" strokeLinejoin="round"/>
          <circle cx="12" cy="10" r="2.5" fill="var(--accent)" fillOpacity="0.3" stroke="var(--accent)" strokeWidth="1.2"/>
          <line x1="12" y1="8.5" x2="12" y2="11.5" stroke="var(--accent)" strokeWidth="1.3" strokeLinecap="round"/>
          <line x1="10.5" y1="10" x2="13.5" y2="10" stroke="var(--accent)" strokeWidth="1.3" strokeLinecap="round"/>
        </svg>
        <span style={{ fontWeight: 700, fontSize: 12, color: "var(--text-secondary)", letterSpacing: "0.04em", textTransform: "uppercase" }}>Fichiers</span>
        <div style={{ flex: 1 }} />
        <button onClick={() => setViewMode("list")} title="Vue liste" style={{ ...st.iconBtn, opacity: viewMode === "list" ? 1 : 0.4 }}>
          <svg viewBox="0 0 16 16" width={13} height={13}><line x1="3" y1="4" x2="13" y2="4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/><line x1="3" y1="8" x2="13" y2="8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/><line x1="3" y1="12" x2="13" y2="12" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/></svg>
        </button>
        <button onClick={() => setViewMode("grid")} title="Vue grille" style={{ ...st.iconBtn, opacity: viewMode === "grid" ? 1 : 0.4 }}>
          <svg viewBox="0 0 16 16" width={13} height={13}><rect x="2" y="2" width="5" height="5" rx="1" stroke="currentColor" strokeWidth="1.4" fill="none"/><rect x="9" y="2" width="5" height="5" rx="1" stroke="currentColor" strokeWidth="1.4" fill="none"/><rect x="2" y="9" width="5" height="5" rx="1" stroke="currentColor" strokeWidth="1.4" fill="none"/><rect x="9" y="9" width="5" height="5" rx="1" stroke="currentColor" strokeWidth="1.4" fill="none"/></svg>
        </button>
        <button onClick={onClose} title="Fermer" style={st.iconBtn}>
          <svg viewBox="0 0 16 16" width={14} height={14}><line x1="3" y1="3" x2="13" y2="13" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"/><line x1="13" y1="3" x2="3" y2="13" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"/></svg>
        </button>
      </div>

      {/* ── Breadcrumb ── */}
      <div style={{ display: "flex", alignItems: "center", gap: 2, padding: "8px 14px 4px", flexShrink: 0, flexWrap: "wrap" }}>
        {currentPath !== "/" && (
          <button onClick={() => navigate(parentPath(currentPath))} title="Dossier parent" style={{ ...st.iconBtn, marginRight: 4 }}>
            <svg viewBox="0 0 16 16" width={13} height={13}><polyline points="10,3 4,8 10,13" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"/></svg>
          </button>
        )}
        {crumbs.map((c, i) => (
          <React.Fragment key={c.path}>
            {i > 0 && <span style={{ color: "var(--text-disabled)", fontSize: 10 }}>/</span>}
            <button onClick={() => navigate(c.path)} style={{ ...st.crumbBtn, color: i === crumbs.length - 1 ? "var(--text-primary)" : "var(--text-muted)", fontWeight: i === crumbs.length - 1 ? 600 : 400 }}>
              {c.label}
            </button>
          </React.Fragment>
        ))}
      </div>

      {/* ── Barre d'outils ── */}
      <div style={{ display: "flex", alignItems: "center", gap: 6, padding: "4px 14px 8px", flexShrink: 0 }}>
        <div style={{ flex: 1, position: "relative" }}>
          <svg viewBox="0 0 16 16" width={11} height={11} style={{ position: "absolute", left: 7, top: "50%", transform: "translateY(-50%)", pointerEvents: "none" }}>
            <circle cx="6.5" cy="6.5" r="4" stroke="var(--text-muted)" strokeWidth="1.4" fill="none"/>
            <line x1="10" y1="10" x2="13" y2="13" stroke="var(--text-muted)" strokeWidth="1.5" strokeLinecap="round"/>
          </svg>
          <input
            value={search}
            onChange={(e) => {
              const v = e.target.value;
              setSearch(v);
              if (searchDebounce.current) clearTimeout(searchDebounce.current);
              if (!v.trim()) {
                setSearchRecursive(false);
                setSearchResults([]);
                setSearchTruncated(false);
                return;
              }
              searchDebounce.current = setTimeout(() => doRecursiveSearch(v), 300);
            }}
            onKeyDown={(e) => { if (e.key === "Escape") {
              setSearch(""); setSearchRecursive(false); setSearchResults([]); setSearchTruncated(false);
            }}}
            placeholder="Rechercher (récursif)…"
            style={{ ...st.searchInput, paddingLeft: 24, paddingRight: searchLoading ? 28 : 8 }}
          />
          {searchLoading && (
            <span style={{ position: "absolute", right: 7, top: "50%", transform: "translateY(-50%)" }}>
              <LoadingDots />
            </span>
          )}
          {search && !searchLoading && (
            <button
              onClick={() => { setSearch(""); setSearchRecursive(false); setSearchResults([]); setSearchTruncated(false); }}
              style={{ position: "absolute", right: 5, top: "50%", transform: "translateY(-50%)", background: "none", border: "none", cursor: "pointer", color: "var(--text-muted)", padding: 2, display: "flex", alignItems: "center" }}
              title="Effacer la recherche"
            >
              <svg viewBox="0 0 16 16" width={10} height={10}><line x1="3" y1="3" x2="13" y2="13" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"/><line x1="13" y1="3" x2="3" y2="13" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"/></svg>
            </button>
          )}
        </div>
        <button onClick={() => { setNewFolderMode(true); setNewFolderName(""); }} title="Nouveau dossier" style={st.toolBtn}>
          <svg viewBox="0 0 16 16" width={13} height={13}><path d="M1 4C1 3.4 1.4 3 2 3H5.5L7 5H14C14.6 5 15 5.4 15 6V13C15 13.6 14.6 14 14 14H2C1.4 14 1 13.6 1 13V4Z" stroke="currentColor" strokeWidth="1.3" fill="none"/><line x1="8" y1="8" x2="8" y2="12" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"/><line x1="6" y1="10" x2="10" y2="10" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"/></svg>
        </button>
        <button onClick={() => fileInputRef.current?.click()} title="Uploader" style={st.toolBtn}>
          <svg viewBox="0 0 16 16" width={13} height={13}><line x1="8" y1="2" x2="8" y2="10" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/><polyline points="5,5 8,2 11,5" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinecap="round" strokeLinejoin="round"/><line x1="3" y1="13" x2="13" y2="13" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/></svg>
        </button>
        <button onClick={() => loadDir(currentPath)} title="Rafraîchir" style={st.toolBtn}>
          <svg viewBox="0 0 16 16" width={13} height={13}><path d="M13 8A5 5 0 1 1 8 3" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinecap="round"/><polyline points="8,1 11,3 8,5" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinecap="round" strokeLinejoin="round"/></svg>
        </button>
        <input ref={fileInputRef} type="file" multiple style={{ display: "none" }} onChange={(e) => e.target.files && handleUpload(e.target.files)} />
      </div>

      {/* ── En-tête colonnes (vue liste) ── */}
      {viewMode === "list" && (
        <div style={{ display: "flex", alignItems: "center", padding: "3px 14px", borderBottom: "1px solid var(--border)", flexShrink: 0, gap: 4 }}>
          <div style={{ flex: 1 }}>
            <button onClick={() => { setSortBy("name"); setSortAsc(v => sortBy === "name" ? !v : true); }} style={st.sortBtn}>Nom {sortBy === "name" ? (sortAsc ? "↑" : "↓") : ""}</button>
          </div>
          <div style={{ width: 70 }}>
            <button onClick={() => { setSortBy("size"); setSortAsc(v => sortBy === "size" ? !v : true); }} style={st.sortBtn}>Taille {sortBy === "size" ? (sortAsc ? "↑" : "↓") : ""}</button>
          </div>
          <div style={{ width: 120 }}>
            <button onClick={() => { setSortBy("date"); setSortAsc(v => sortBy === "date" ? !v : true); }} style={st.sortBtn}>Modifié {sortBy === "date" ? (sortAsc ? "↑" : "↓") : ""}</button>
          </div>
          <div style={{ width: 66 }} />
        </div>
      )}

      {/* ── Contenu ── */}
      <div style={{ flex: 1, overflowY: "auto", padding: viewMode === "grid" ? "12px" : "4px 0" }}>
        {loading && !searchRecursive && <div style={{ textAlign: "center", padding: 40, color: "var(--text-muted)" }}><LoadingDots /></div>}
        {error && <div style={{ padding: 16, color: "#e07070", fontSize: 12 }}>{error}</div>}

        {/* Bannière mode recherche récursive */}
        {searchRecursive && !searchLoading && (
          <div style={{ margin: viewMode === "grid" ? "0 0 10px" : "0 0 4px", padding: "6px 14px", background: "var(--elevated-bg)", borderBottom: "1px solid var(--border)", display: "flex", alignItems: "center", gap: 8, flexShrink: 0 }}>
            <svg viewBox="0 0 16 16" width={11} height={11} style={{ flexShrink: 0 }}>
              <circle cx="6.5" cy="6.5" r="4" stroke="var(--accent)" strokeWidth="1.5" fill="none"/>
              <line x1="10" y1="10" x2="13" y2="13" stroke="var(--accent)" strokeWidth="1.6" strokeLinecap="round"/>
            </svg>
            <span style={{ fontSize: 11, color: "var(--text-muted)", flex: 1 }}>
              {filtered.length} résultat{filtered.length !== 1 ? "s" : ""} pour <strong style={{ color: "var(--text-secondary)" }}>« {search} »</strong>
              {searchTruncated && <span style={{ color: "#e07070" }}> (limité à 200)</span>}
              {currentPath !== "/" && <span> dans <code style={{ fontSize: 10, color: "var(--text-muted)" }}>{currentPath}</code></span>}
            </span>
            <button
              onClick={() => { setSearch(""); setSearchRecursive(false); setSearchResults([]); setSearchTruncated(false); }}
              style={{ background: "none", border: "none", cursor: "pointer", fontSize: 10, color: "var(--accent)", padding: 0 }}
            >
              Fermer
            </button>
          </div>
        )}

        {!loading && !searchLoading && !error && filtered.length === 0 && (
          <div style={{ textAlign: "center", padding: 48, color: "var(--text-disabled)" }}>
            {search ? "Aucun résultat" : "Dossier vide"}
            {!search && <div style={{ marginTop: 8, fontSize: 11 }}>Glissez des fichiers ici ou cliquez sur ↑</div>}
          </div>
        )}

        {/* Nouveau dossier inline */}
        {newFolderMode && (
          <div style={{ ...st.entry, background: "var(--elevated-bg)", padding: "6px 14px", marginBottom: 2 }}>
            <FolderIconSmall size={15} />
            <input autoFocus value={newFolderName} onChange={(e) => setNewFolderName(e.target.value)}
              placeholder="Nom du dossier" style={{ ...st.inlineInput, flex: 1 }}
              onKeyDown={(e: KeyboardEvent<HTMLInputElement>) => {
                if (e.key === "Enter") handleMkdir(newFolderName);
                if (e.key === "Escape") { setNewFolderMode(false); setNewFolderName(""); }
              }}
              onBlur={() => { if (newFolderName.trim()) handleMkdir(newFolderName); else setNewFolderMode(false); }}
            />
            <span style={{ fontSize: 10, color: "var(--text-muted)" }}>↵ valider</span>
          </div>
        )}

        {/* Vue liste */}
        {viewMode === "list" && filtered.map((entry) => (
          <EntryRow
            key={entry.path} entry={entry}
            selected={selected.has(entry.path)} isOrphan={orphans.has(entry.path)}
            renamingPath={renamingPath} renameValue={renameValue} dragOverPath={dragOverPath}
            showPath={searchRecursive}
            onNavigate={navigate} onSelect={toggleSelect} onCtxMenu={handleCtxMenu}
            onRenameStart={(p, n) => { setRenamingPath(p); setRenameValue(n); }}
            onRenameCommit={handleRename} onRenameChange={setRenameValue} onRenameCancel={() => setRenamingPath(null)}
            onDelete={handleDelete} onDownload={handleDownload}
            onMove={(p, n) => setMoveModal({ path: p, name: n })}
            onHover={handleHover} onHoverEnd={handleHoverEnd}
            onDragStart={handleEntryDragStart} onDragOver={handleEntryDragOver}
            onDrop={handleEntryDrop} onDragEnd={handleEntryDragEnd}
          />
        ))}

        {/* Vue grille */}
        {viewMode === "grid" && (
          <div style={{ display: "flex", flexWrap: "wrap", gap: 10 }}>
            {filtered.map((entry) => (
              <EntryCard
                key={entry.path} entry={entry}
                selected={selected.has(entry.path)} isOrphan={orphans.has(entry.path)}
                dragOverPath={dragOverPath}
                showPath={searchRecursive}
                onNavigate={navigate} onSelect={toggleSelect} onCtxMenu={handleCtxMenu}
                onHover={handleHover} onHoverEnd={handleHoverEnd}
                onDragStart={handleEntryDragStart} onDragOver={handleEntryDragOver}
                onDrop={handleEntryDrop} onDragEnd={handleEntryDragEnd}
              />
            ))}
          </div>
        )}
      </div>

      {/* ── Bannière orphelins ── */}
      {orphans.size > 0 && (
        <div style={{ padding: "8px 14px", borderTop: "1px solid rgba(224,112,112,0.3)", background: "rgba(224,112,112,0.07)", flexShrink: 0, display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontSize: 11, color: "#e07070", flex: 1 }}>⚠ {orphans.size} fichier{orphans.size > 1 ? "s" : ""} sans contenu MinIO</span>
          <button
            onClick={() => {
              setConfirmModal({
                message: `Supprimer les ${orphans.size} entrée(s) orpheline(s) ?`,
                onConfirm: async () => {
                  setConfirmModal(null);
                  for (const p of orphans) await authFetch(`${BASE}/vfs/delete?path=${encodeURIComponent(p)}`, { method: "DELETE" }).catch(() => {});
                  setOrphans(new Set()); await loadDir(currentPath); await loadQuota();
                },
              });
            }}
            style={{ background: "rgba(224,112,112,0.15)", border: "1px solid rgba(224,112,112,0.4)", borderRadius: 4, color: "#e07070", fontSize: 10, padding: "3px 8px", cursor: "pointer" }}
          >
            Nettoyer
          </button>
        </div>
      )}

      {/* ── Quota ── */}
      {quota && (
        <div style={{ padding: "8px 14px 10px", borderTop: "1px solid var(--border)", flexShrink: 0 }}>
          {/* Barre de progression */}
          {quota.quota_limit_bytes > 0 && (
            <div style={{ marginBottom: 5 }}>
              <div style={{ height: 3, background: "rgba(255,255,255,0.07)", borderRadius: 3, overflow: "hidden" }}>
                <div style={{
                  height: "100%",
                  width: `${Math.min(quota.quota_used_pct, 100)}%`,
                  background: quota.quota_exceeded ? "#e07878" : quota.quota_used_pct >= 80 ? "#d4a03d" : "#5aaa7a",
                  borderRadius: 3,
                  transition: "width 0.4s",
                }} />
              </div>
            </div>
          )}
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", color: "var(--text-muted)", fontSize: 10 }}>
            <span>
              {quota.total_files} fichier{quota.total_files > 1 ? "s" : ""}
              {quota.quota_exceeded && (
                <span style={{ marginLeft: 6, color: "#e07878", fontWeight: 700 }}>⚠ quota dépassé</span>
              )}
              {!quota.quota_exceeded && quota.quota_used_pct >= 80 && (
                <span style={{ marginLeft: 6, color: "#d4a03d" }}>⚠ {quota.quota_used_pct.toFixed(0)}% utilisé</span>
              )}
            </span>
            <span style={{ color: quota.quota_exceeded ? "#e07878" : "#5aaa7a" }}>
              {quota.total_size}
              {quota.quota_limit_bytes > 0 && (
                <span style={{ color: "var(--text-muted)" }}> / {quota.quota_limit}</span>
              )}
            </span>
          </div>
        </div>
      )}

      {/* ── Menu contextuel ── */}
      {ctxMenu && (
        <div
          style={{ position: "fixed", top: ctxMenu.y, left: ctxMenu.x, zIndex: 600, background: "var(--elevated-bg)", border: "1px solid var(--border)", borderRadius: 8, padding: "4px 0", boxShadow: "0 8px 32px rgba(0,0,0,0.4)", minWidth: 175 }}
          onMouseDown={(e) => e.stopPropagation()}
        >
          {ctxMenu.entry.type === "file" && (
            <CtxItem
              icon={<svg viewBox="0 0 16 16" width={12} height={12}><line x1="8" y1="2" x2="8" y2="10" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/><polyline points="5,7 8,10 11,7" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinecap="round" strokeLinejoin="round"/><line x1="3" y1="13" x2="13" y2="13" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/></svg>}
              label="Télécharger"
              onClick={() => { handleDownload(ctxMenu.entry.path, ctxMenu.entry.name); setCtxMenu(null); }}
            />
          )}
          <CtxItem
            icon={<svg viewBox="0 0 16 16" width={12} height={12}><path d="M11 2l3 3-8 8H3v-3L11 2z" stroke="currentColor" strokeWidth="1.4" fill="none" strokeLinejoin="round"/></svg>}
            label="Renommer"
            onClick={() => { setRenamingPath(ctxMenu.entry.path); setRenameValue(ctxMenu.entry.name); setCtxMenu(null); }}
          />
          <CtxItem
            icon={<svg viewBox="0 0 16 16" width={12} height={12}><path d="M2 8h9M8 4l4 4-4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" fill="none"/><rect x="12" y="2" width="2" height="12" rx="1" fill="currentColor" opacity=".4"/></svg>}
            label="Déplacer vers…"
            onClick={() => { setMoveModal({ path: ctxMenu.entry.path, name: ctxMenu.entry.name }); setCtxMenu(null); }}
          />
          <div style={{ height: 1, background: "var(--border)", margin: "4px 0" }} />
          <CtxItem
            icon={<svg viewBox="0 0 16 16" width={12} height={12}><path d="M2 4h12M5 4V2h6v2M6 7v5M10 7v5M3 4l1 9h8l1-9" stroke="#e07070" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" fill="none"/></svg>}
            label="Supprimer" danger
            onClick={() => { handleDelete(ctxMenu.entry.path); setCtxMenu(null); }}
          />
        </div>
      )}

      {/* ── Overlay drop OS ── */}
      {dragOverPanel && (
        <div style={{ position: "absolute", inset: 0, zIndex: 500, background: "rgba(212,129,61,0.08)", display: "flex", alignItems: "center", justifyContent: "center", border: "2px dashed var(--accent)", borderRadius: 8, pointerEvents: "none" }}>
          <div style={{ textAlign: "center", color: "var(--accent)" }}>
            <div style={{ fontSize: 32, marginBottom: 8 }}>↓</div>
            <div style={{ fontSize: 13, fontWeight: 600 }}>Déposer ici</div>
            <div style={{ fontSize: 11, opacity: 0.7 }}>{currentPath}</div>
          </div>
        </div>
      )}

      {/* ── Modale déplacement ── */}
      {moveModal && (
        <MoveModal
          srcPath={moveModal.path}
          srcName={moveModal.name}
          onConfirm={async (dstDir) => { setMoveModal(null); await handleMove(moveModal.path, dstDir); }}
          onCancel={() => setMoveModal(null)}
        />
      )}

      {/* ── Modale confirmation suppression ── */}
      {confirmModal && (
        <div
          style={{ position: "fixed", inset: 0, zIndex: 800, background: "rgba(0,0,0,0.55)", display: "flex", alignItems: "center", justifyContent: "center" }}
          onMouseDown={(e) => { if (e.target === e.currentTarget) setConfirmModal(null); }}
        >
          <div style={{ width: 340, background: "var(--elevated-bg)", border: "1px solid var(--border)", borderRadius: 12, boxShadow: "0 12px 48px rgba(0,0,0,0.5)", padding: "24px 24px 20px", display: "flex", flexDirection: "column", gap: 20 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
              <span style={{ fontSize: 22, lineHeight: 1 }}>🗑️</span>
              <span style={{ fontSize: 14, color: "var(--text-primary)", fontWeight: 600 }}>Confirmation</span>
            </div>
            <p style={{ margin: 0, fontSize: 13, color: "var(--text-secondary)", lineHeight: 1.5 }}>{confirmModal.message}</p>
            <div style={{ display: "flex", gap: 10, justifyContent: "flex-end" }}>
              <button
                onClick={() => setConfirmModal(null)}
                style={{ padding: "7px 16px", borderRadius: 8, border: "1px solid var(--border)", background: "transparent", color: "var(--text-secondary)", fontSize: 13, cursor: "pointer" }}
              >
                Annuler
              </button>
              <button
                onClick={confirmModal.onConfirm}
                style={{ padding: "7px 16px", borderRadius: 8, border: "1px solid rgba(224,112,112,0.5)", background: "rgba(224,112,112,0.15)", color: "#e07070", fontSize: 13, fontWeight: 600, cursor: "pointer" }}
              >
                Supprimer
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Tooltip infos fichier (portal) ── */}
      {tooltip && createPortal(
        <FileTooltip entry={tooltip.entry} x={tooltip.x} y={tooltip.y} />,
        document.body
      )}
    </div>
  );
}

// ── EntryRow ───────────────────────────────────────────────────────────────

interface EntryRowProps {
  entry: VfsEntry;
  selected: boolean;
  isOrphan: boolean;
  renamingPath: string | null;
  renameValue: string;
  dragOverPath: string | null;
  showPath?: boolean;
  onNavigate: (path: string) => void;
  onSelect: (path: string, multi: boolean) => void;
  onCtxMenu: (e: React.MouseEvent, entry: VfsEntry) => void;
  onRenameStart: (path: string, name: string) => void;
  onRenameCommit: (path: string, name: string) => void;
  onRenameChange: (v: string) => void;
  onRenameCancel: () => void;
  onDelete: (path: string) => void;
  onDownload: (path: string, name: string) => void;
  onMove: (path: string, name: string) => void;
  onHover: (entry: VfsEntry, x: number, y: number) => void;
  onHoverEnd: () => void;
  onDragStart: (e: React.DragEvent, entry: VfsEntry) => void;
  onDragOver: (e: React.DragEvent, entry: VfsEntry) => void;
  onDrop: (e: React.DragEvent, entry: VfsEntry) => void;
  onDragEnd: () => void;
}

function EntryRow({
  entry, selected, isOrphan, renamingPath, renameValue, dragOverPath,
  showPath = false,
  onNavigate, onSelect, onCtxMenu,
  onRenameStart, onRenameCommit, onRenameChange, onRenameCancel,
  onDelete, onDownload, onMove, onHover, onHoverEnd,
  onDragStart, onDragOver, onDrop, onDragEnd,
}: EntryRowProps) {
  const isRenaming = renamingPath === entry.path;
  const isDragTarget = dragOverPath === entry.path && entry.type === "dir";
  const [hovered, setHovered] = useState(false);

  const parentDir = parentPath(entry.path);

  return (
    <div
      draggable
      onDragStart={(e) => onDragStart(e, entry)}
      onDragOver={(e) => onDragOver(e, entry)}
      onDrop={(e) => onDrop(e, entry)}
      onDragEnd={onDragEnd}
      onMouseEnter={(e) => { setHovered(true); onHover(entry, e.clientX, e.clientY); }}
      onMouseMove={(e) => onHover(entry, e.clientX, e.clientY)}
      onMouseLeave={() => { setHovered(false); onHoverEnd(); }}
      onContextMenu={(e) => onCtxMenu(e, entry)}
      onClick={(e) => {
        if (entry.type === "dir") onNavigate(entry.path);
        else onSelect(entry.path, e.metaKey || e.ctrlKey);
      }}
      onDoubleClick={() => { if (entry.type === "file") onDownload(entry.path, entry.name); }}
      style={{
        ...st.entry,
        background: isDragTarget ? "rgba(212,129,61,0.12)" : selected ? "var(--sidebar-item-active-bg)" : hovered ? "var(--sidebar-item-hover-bg)" : "transparent",
        outline: isDragTarget ? "1px solid var(--accent)" : "none",
        cursor: entry.type === "dir" ? "pointer" : "default",
      }}
    >
      <div style={{ flexShrink: 0 }}>
        {entry.type === "dir" ? <FolderIconSmall open={isDragTarget} size={16} /> : <FileIconSmall mime={entry.mime_type} name={entry.name} size={16} />}
      </div>
      <div style={{ flex: 1, overflow: "hidden" }}>
        {isRenaming ? (
          <input autoFocus value={renameValue} onChange={(e) => onRenameChange(e.target.value)}
            style={st.inlineInput} onClick={(e) => e.stopPropagation()}
            onKeyDown={(e: KeyboardEvent<HTMLInputElement>) => {
              e.stopPropagation();
              if (e.key === "Enter") onRenameCommit(entry.path, renameValue);
              if (e.key === "Escape") onRenameCancel();
            }}
            onBlur={() => onRenameCommit(entry.path, renameValue)}
          />
        ) : (
          <div style={{ display: "flex", flexDirection: "column", overflow: "hidden" }}>
            <span style={{ fontSize: 12, color: isOrphan ? "#e07070" : entry.type === "dir" ? "var(--text-primary)" : "var(--text-secondary)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", display: "flex", alignItems: "center", gap: 5 }}>
              {entry.name}
              {isOrphan && <span title="Contenu absent de MinIO" style={{ fontSize: 9, fontWeight: 700, color: "#e07070", background: "rgba(224,112,112,0.12)", border: "1px solid rgba(224,112,112,0.3)", borderRadius: 3, padding: "1px 4px", flexShrink: 0 }}>⚠ orphelin</span>}
            </span>
            {showPath && (
              <button
                onClick={(e) => { e.stopPropagation(); onNavigate(parentDir); }}
                title={`Ouvrir ${parentDir}`}
                style={{ background: "none", border: "none", padding: 0, cursor: "pointer", textAlign: "left", fontSize: 9, color: "var(--text-muted)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", fontFamily: "'SF Mono','JetBrains Mono',monospace" }}
              >
                {parentDir}
              </button>
            )}
          </div>
        )}
      </div>
      <div style={{ width: 70, textAlign: "right", color: "var(--text-muted)", fontSize: 10, flexShrink: 0 }}>
        {entry.type === "file" && entry.size ? entry.size : ""}
      </div>
      <div style={{ width: 120, textAlign: "right", color: "var(--text-disabled)", fontSize: 10, flexShrink: 0 }}>
        {formatDate(entry.updated_at)}
      </div>
      <div style={{ width: 66, display: "flex", gap: 2, justifyContent: "flex-end", flexShrink: 0, opacity: hovered ? 1 : 0, transition: "opacity 0.15s" }}>
        <button onClick={(e) => { e.stopPropagation(); onRenameStart(entry.path, entry.name); }} title="Renommer" style={st.rowActionBtn}>
          <svg viewBox="0 0 16 16" width={11} height={11}><path d="M11 2l3 3-8 8H3v-3L11 2z" stroke="currentColor" strokeWidth="1.4" fill="none" strokeLinejoin="round"/></svg>
        </button>
        <button onClick={(e) => { e.stopPropagation(); onMove(entry.path, entry.name); }} title="Déplacer" style={st.rowActionBtn}>
          <svg viewBox="0 0 16 16" width={11} height={11}><path d="M2 8h9M8 4l4 4-4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" fill="none"/></svg>
        </button>
        {entry.type === "file" && (
          <button onClick={(e) => { e.stopPropagation(); onDownload(entry.path, entry.name); }} title="Télécharger" style={st.rowActionBtn}>
            <svg viewBox="0 0 16 16" width={11} height={11}><line x1="8" y1="2" x2="8" y2="10" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/><polyline points="5,7 8,10 11,7" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinecap="round" strokeLinejoin="round"/></svg>
          </button>
        )}
        <button onClick={(e) => { e.stopPropagation(); onDelete(entry.path); }} title="Supprimer" style={{ ...st.rowActionBtn, color: "#e07070" }}>
          <svg viewBox="0 0 16 16" width={11} height={11}><path d="M2 4h12M5 4V2h6v2M6 7v5M10 7v5M3 4l1 9h8l1-9" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" fill="none"/></svg>
        </button>
      </div>
    </div>
  );
}

// ── EntryCard (vue grille) ─────────────────────────────────────────────────

interface EntryCardProps {
  entry: VfsEntry;
  selected: boolean;
  isOrphan: boolean;
  dragOverPath: string | null;
  showPath?: boolean;
  onNavigate: (path: string) => void;
  onSelect: (path: string, multi: boolean) => void;
  onCtxMenu: (e: React.MouseEvent, entry: VfsEntry) => void;
  onHover: (entry: VfsEntry, x: number, y: number) => void;
  onHoverEnd: () => void;
  onDragStart: (e: React.DragEvent, entry: VfsEntry) => void;
  onDragOver: (e: React.DragEvent, entry: VfsEntry) => void;
  onDrop: (e: React.DragEvent, entry: VfsEntry) => void;
  onDragEnd: () => void;
}

function EntryCard({ entry, selected, isOrphan, dragOverPath, showPath = false, onNavigate, onSelect, onCtxMenu, onHover, onHoverEnd, onDragStart, onDragOver, onDrop, onDragEnd }: EntryCardProps) {
  const [hovered, setHovered] = useState(false);
  const isDragTarget = dragOverPath === entry.path && entry.type === "dir";
  const parentDir = parentPath(entry.path);

  return (
    <div
      draggable
      onDragStart={(e) => onDragStart(e, entry)}
      onDragOver={(e) => onDragOver(e, entry)}
      onDrop={(e) => onDrop(e, entry)}
      onDragEnd={onDragEnd}
      onMouseEnter={(e) => { setHovered(true); onHover(entry, e.clientX, e.clientY); }}
      onMouseMove={(e) => onHover(entry, e.clientX, e.clientY)}
      onMouseLeave={() => { setHovered(false); onHoverEnd(); }}
      onContextMenu={(e) => onCtxMenu(e, entry)}
      onClick={(e) => {
        if (entry.type === "dir") onNavigate(entry.path);
        else onSelect(entry.path, e.metaKey || e.ctrlKey);
      }}
      style={{
        width: 110, padding: "14px 8px 10px",
        display: "flex", flexDirection: "column", alignItems: "center", gap: 8,
        border: `1px solid ${isDragTarget ? "var(--accent)" : isOrphan ? "rgba(224,112,112,0.4)" : selected ? "var(--accent)" : hovered ? "var(--border-active)" : "transparent"}`,
        borderRadius: 10,
        background: isDragTarget ? "rgba(212,129,61,0.12)" : isOrphan ? "rgba(224,112,112,0.06)" : selected ? "var(--sidebar-item-active-bg)" : hovered ? "var(--sidebar-item-hover-bg)" : "transparent",
        cursor: entry.type === "dir" ? "pointer" : "default",
        transition: "background 0.1s, border-color 0.1s",
        position: "relative",
      }}
    >
      {isOrphan && <span title="Contenu absent de MinIO" style={{ position: "absolute", top: 5, right: 6, fontSize: 10, color: "#e07070", fontWeight: 700 }}>⚠</span>}
      {isDragTarget && <div style={{ position: "absolute", inset: 0, borderRadius: 10, border: "2px dashed var(--accent)", pointerEvents: "none" }} />}
      {entry.type === "dir"
        ? <FolderIconLarge open={hovered || isDragTarget} size={52} />
        : <FileIconLarge mime={entry.mime_type} name={entry.name} size={52} />}
      <span style={{ fontSize: 11, color: isOrphan ? "#e07070" : "var(--text-secondary)", textAlign: "center", lineHeight: 1.3, wordBreak: "break-word", maxWidth: "100%", display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" }}>
        {entry.name}
      </span>
      {entry.type === "file" && entry.size && (
        <span style={{ fontSize: 9, color: "var(--text-disabled)" }}>{entry.size}</span>
      )}
      {showPath && (
        <button
          onClick={(e) => { e.stopPropagation(); onNavigate(parentDir); }}
          title={`Ouvrir ${parentDir}`}
          style={{ background: "none", border: "none", padding: 0, cursor: "pointer", fontSize: 9, color: "var(--accent)", maxWidth: "100%", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", fontFamily: "'SF Mono','JetBrains Mono',monospace" }}
        >
          {parentDir}
        </button>
      )}
    </div>
  );
}

// ── Helpers UI ─────────────────────────────────────────────────────────────

function CtxItem({ icon, label, onClick, danger = false }: { icon: React.ReactNode; label: string; onClick: () => void; danger?: boolean }) {
  const [hovered, setHovered] = useState(false);
  return (
    <button
      onMouseEnter={() => setHovered(true)} onMouseLeave={() => setHovered(false)}
      onClick={onClick}
      style={{ display: "flex", alignItems: "center", gap: 8, width: "100%", padding: "7px 14px", background: hovered ? "var(--sidebar-item-hover-bg)" : "transparent", border: "none", cursor: "pointer", color: danger ? "#e07070" : "var(--text-secondary)", fontSize: 12, textAlign: "left" }}
    >
      {icon}{label}
    </button>
  );
}

// ── Tooltip infos fichier ─────────────────────────────────────────────────

interface TooltipState {
  entry: VfsEntry;
  x: number;
  y: number;
}

function FileTooltip({ entry, x, y }: TooltipState) {
  const ref = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState({ left: x + 16, top: y });

  useEffect(() => {
    if (!ref.current) return;
    const rect = ref.current.getBoundingClientRect();
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    let left = x + 16;
    let top = y;
    if (left + rect.width > vw - 12) left = x - rect.width - 8;
    if (top + rect.height > vh - 12) top = vh - rect.height - 12;
    if (top < 8) top = 8;
    setPos({ left, top });
  }, [x, y]);

  const ext = getExt(entry.name);
  const { color, label } = fileStyle(entry.mime_type, entry.name);
  const isDir = entry.type === "dir";

  return (
    <div
      ref={ref}
      style={{
        position: "fixed",
        left: pos.left,
        top: pos.top,
        zIndex: 9000,
        pointerEvents: "none",
        width: 220,
        background: "var(--elevated-bg)",
        border: "1px solid var(--border-active)",
        borderRadius: 10,
        boxShadow: "0 8px 32px rgba(0,0,0,0.45)",
        overflow: "hidden",
        animation: "tooltipIn 0.12s ease-out",
      }}
    >
      <style>{`@keyframes tooltipIn { from { opacity:0; transform:translateY(4px) } to { opacity:1; transform:translateY(0) } }`}</style>

      {/* Bandeau coloré en haut */}
      <div style={{
        height: 4,
        background: isDir ? "#d4813d" : color,
        opacity: 0.7,
      }} />

      {/* Icône + nom */}
      <div style={{ padding: "10px 12px 8px", display: "flex", alignItems: "flex-start", gap: 10 }}>
        <div style={{ flexShrink: 0, marginTop: 1 }}>
          {isDir
            ? <FolderIconSmall size={20} />
            : <FileIconSmall mime={entry.mime_type} name={entry.name} size={20} />}
        </div>
        <div style={{ flex: 1, overflow: "hidden" }}>
          <div style={{
            fontSize: 12, fontWeight: 600,
            color: "var(--text-primary)",
            wordBreak: "break-word", lineHeight: 1.35,
          }}>
            {entry.name}
          </div>
          {!isDir && ext && (
            <div style={{
              display: "inline-block", marginTop: 4,
              fontSize: 9, fontWeight: 700,
              color, background: `${color}22`,
              border: `1px solid ${color}44`,
              borderRadius: 3, padding: "1px 5px",
              letterSpacing: "0.04em",
            }}>
              {label}
            </div>
          )}
        </div>
      </div>

      {/* Séparateur */}
      <div style={{ height: 1, background: "var(--border)", margin: "0 12px" }} />

      {/* Métadonnées */}
      <div style={{ padding: "8px 12px 10px", display: "flex", flexDirection: "column", gap: 5 }}>
        <TooltipRow icon="📁" label="Chemin" value={entry.path} mono />
        {!isDir && entry.size && (
          <TooltipRow icon="⚖️" label="Taille" value={entry.size} />
        )}
        {!isDir && entry.mime_type && (
          <TooltipRow icon="🔖" label="Type" value={entry.mime_type} mono small />
        )}
        {entry.created_at && (
          <TooltipRow icon="🕐" label="Créé" value={formatDate(entry.created_at)} />
        )}
        {entry.updated_at && (
          <TooltipRow icon="✏️" label="Modifié" value={formatDate(entry.updated_at)} />
        )}
      </div>
    </div>
  );
}

function TooltipRow({ icon, label, value, mono = false, small = false }: {
  icon: string; label: string; value: string; mono?: boolean; small?: boolean;
}) {
  return (
    <div style={{ display: "flex", gap: 6, alignItems: "flex-start" }}>
      <span style={{ fontSize: 10, flexShrink: 0, lineHeight: "16px" }}>{icon}</span>
      <span style={{ fontSize: 10, color: "var(--text-muted)", flexShrink: 0, lineHeight: "16px", minWidth: 44 }}>{label}</span>
      <span style={{
        fontSize: small ? 9 : 10,
        color: "var(--text-secondary)",
        fontFamily: mono ? "'SF Mono','JetBrains Mono',monospace" : "inherit",
        wordBreak: "break-all", lineHeight: "16px", flex: 1,
      }}>
        {value}
      </span>
    </div>
  );
}

function LoadingDots() {
  return (
    <span style={{ display: "inline-flex", gap: 4 }}>
      {[0, 1, 2].map((i) => (
        <span key={i} style={{ width: 5, height: 5, borderRadius: "50%", background: "var(--text-muted)", display: "inline-block", animation: "vfsDot 1.2s ease-in-out infinite", animationDelay: `${i * 0.2}s` }} />
      ))}
      <style>{`@keyframes vfsDot { 0%,80%,100%{opacity:0.2} 40%{opacity:1} }`}</style>
    </span>
  );
}

// ── Styles ─────────────────────────────────────────────────────────────────

const st = {
  iconBtn: { background: "none", border: "none", cursor: "pointer", color: "var(--text-muted)", padding: 4, borderRadius: 4, display: "flex", alignItems: "center", justifyContent: "center" } as React.CSSProperties,
  toolBtn: { background: "var(--elevated-bg)", border: "1px solid var(--border)", borderRadius: 5, cursor: "pointer", color: "var(--text-secondary)", padding: "4px 7px", display: "flex", alignItems: "center", gap: 4, fontSize: 11 } as React.CSSProperties,
  crumbBtn: { background: "none", border: "none", cursor: "pointer", fontSize: 11, padding: "1px 3px", borderRadius: 3 } as React.CSSProperties,
  sortBtn: { background: "none", border: "none", cursor: "pointer", fontSize: 10, color: "var(--text-muted)", padding: "1px 0", fontFamily: "inherit" } as React.CSSProperties,
  entry: { display: "flex", alignItems: "center", gap: 8, padding: "5px 14px", minHeight: 30, transition: "background 0.1s" } as React.CSSProperties,
  inlineInput: { background: "var(--input-bg)", border: "1px solid var(--accent)", borderRadius: 4, color: "var(--text-primary)", fontSize: 12, padding: "2px 6px", outline: "none", width: "100%", fontFamily: "inherit" } as React.CSSProperties,
  rowActionBtn: { background: "none", border: "none", cursor: "pointer", color: "var(--text-muted)", padding: "2px 3px", borderRadius: 3, display: "flex", alignItems: "center" } as React.CSSProperties,
  searchInput: { width: "100%", background: "var(--input-bg)", border: "1px solid var(--border)", borderRadius: 5, color: "var(--text-primary)", fontSize: 11, padding: "4px 8px", outline: "none", boxSizing: "border-box" as const, fontFamily: "inherit" } as React.CSSProperties,
} as const;
