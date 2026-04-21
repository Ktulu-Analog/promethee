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
 * MetricsBar.tsx — Bandeau de métriques discret intégré à la chatTopBar
 *
 * Affiche en temps réel :
 *   - Indicateur d'état (dot vert, pulsant pendant la génération)
 *   - CO₂ estimé (gCO₂eq), vire à l'orange au-delà de 400 g
 *   - Tokens in / out (format compact : 12.4k)
 *   - Nombre d'appels LLM
 *
 * Chaque chip affiche une infobulle au hover avec le détail précis.
 *
 * Sources de données (par priorité) :
 *   1. Props `liveUsage` + `isGenerating` : mis à jour à chaque token par ChatPanel
 *   2. Polling GET /monitoring/{convId} toutes les POLL_MS ms (pour le CO₂, le
 *      coût et les appels LLM qui ne transitent pas par le WS)
 */

import React, { useEffect, useRef, useState, useCallback } from "react";
import { api } from "../../lib/api";

// ── Constantes ─────────────────────────────────────────────────────────────

const POLL_MS = 5_000;
const CO2_WARN_THRESHOLD = 400; // gCO₂eq — passe orange au-delà

// ── Types ──────────────────────────────────────────────────────────────────

interface MonitoringData {
  session: {
    prompt: number;
    completion: number;
    total: number;
    cost_eur: number;
    carbon_kgco2: number;
    llm_calls: number;
  };
  context_fill_pct: number;
}

export interface MetricsBarProps {
  convId: string | null;
  /** Titre de la conversation courante */
  convTitle?: string;
  /** Callbacks actions sur la conversation */
  onRenameConv?: (convId: string, newTitle: string) => Promise<void>;
  onStarConv?: (convId: string, starred: boolean) => Promise<void>;
  onMoveConv?: (convId: string, folderId: string | null) => Promise<void>;
  onClearConv?: () => void;
  /** Dossiers disponibles pour "Ajouter à un projet" */
  folders?: { id: string; name: string }[];
  /** true si la conversation est déjà en favoris */
  isStarred?: boolean;
  /** Tokens reçus en direct depuis le WS (mis à jour après chaque réponse) */
  livePrompt?: number;
  liveCompletion?: number;
  /** true pendant la génération → dot pulsant */
  isGenerating: boolean;
  /**
   * État du RAG lors du dernier envoi.
   * - idle  : RAG inactif ou pas encore utilisé
   * - ok    : contexte récupéré avec succès (chunks = nombre de passages injectés)
   * - warn  : erreur lors de la récupération du contexte
   */
  ragStatus?:
    | { kind: "idle" }
    | { kind: "ok"; chunks: number }
    | { kind: "warn"; error: string };
}

// ── Helpers ─────────────────────────────────────────────────────────────────

function fmtTok(n: number): string {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + "M";
  if (n >= 1_000)     return (n / 1_000).toFixed(1) + "k";
  return String(n);
}

function fmtCo2(kgco2: number): string {
  const g = kgco2 * 1000;
  if (g < 0.01) return "< 0.01";
  if (g < 10)   return g.toFixed(2);
  return g.toFixed(1);
}

function fmtCost(eur: number): string {
  if (eur < 0.001) return "< 0.001 €";
  return eur.toFixed(3) + " €";
}

/** Équivalence CO₂ en m de voiture (~120 gCO₂/km = 0.12 g/m) */
function fmtCarEquiv(kgco2: number): string {
  const g = kgco2 * 1000;
  const meters = Math.round(g / 0.12);
  if (meters < 1)    return "< 1 m";
  if (meters < 1000) return `${meters} m`;
  return `${(meters / 1000).toFixed(2)} km`;
}

// ── Sous-composants ─────────────────────────────────────────────────────────

// Dot d'état (vert, pulsant si génération active)
function StatusDot({ active }: { active: boolean }) {
  return (
    <span
      title={active ? "Génération en cours…" : "En attente"}
      style={{
        display: "inline-block",
        width: 7,
        height: 7,
        borderRadius: "50%",
        background: "var(--rag-badge-on)",
        flexShrink: 0,
        animation: active ? "mb-pulse 1.8s ease infinite" : "none",
        opacity: active ? 1 : 0.55,
      }}
    />
  );
}

// Séparateur vertical
function Sep() {
  return (
    <span
      style={{
        display: "inline-block",
        width: 1,
        height: 14,
        background: "var(--border)",
        margin: "0 4px",
        flexShrink: 0,
      }}
    />
  );
}

// Chip avec tooltip
function Chip({
  icon,
  children,
  tooltip,
  tooltipAlign = "center",
}: {
  icon: React.ReactNode;
  children: React.ReactNode;
  tooltip: React.ReactNode;
  tooltipAlign?: "center" | "left";
}) {
  const [hovered, setHovered] = useState(false);

  const tooltipPos: React.CSSProperties =
    tooltipAlign === "left"
      ? { left: 0, transform: "none" }
      : { left: "50%", transform: "translateX(-50%)" };

  const arrowPos: React.CSSProperties =
    tooltipAlign === "left"
      ? { left: 12, transform: "none" }
      : { left: "50%", transform: "translateX(-50%)" };

  return (
    <span
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        position: "relative",
        display: "inline-flex",
        alignItems: "center",
        gap: 4,
        padding: "2px 8px",
        borderRadius: 5,
        cursor: "default",
        background: hovered ? "var(--elevated-bg)" : "transparent",
        transition: "background 0.15s",
        userSelect: "none",
      }}
    >
      {/* Icône */}
      <span style={{ display: "flex", alignItems: "center", opacity: 0.6, flexShrink: 0 }}>
        {icon}
      </span>
      {/* Valeurs */}
      {children}
      {/* Tooltip */}
      {hovered && (
        <span
          style={{
            position: "absolute",
            top: "calc(100% + 8px)",
            ...tooltipPos,
            background: "var(--surface-bg)",
            border: "1px solid var(--border-active)",
            borderRadius: 8,
            padding: "8px 12px",
            fontSize: 12,
            color: "var(--text-primary)",
            whiteSpace: "nowrap",
            zIndex: 200,
            minWidth: 160,
            boxShadow: "0 4px 16px rgba(0,0,0,0.3)",
            pointerEvents: "none",
          }}
        >
          {/* Flèche vers le haut */}
          <span
            style={{
              position: "absolute",
              bottom: "100%",
              ...arrowPos,
              width: 0,
              height: 0,
              borderLeft: "5px solid transparent",
              borderRight: "5px solid transparent",
              borderBottom: "5px solid var(--border-active)",
            }}
          />
          {tooltip}
        </span>
      )}
    </span>
  );
}

// Ligne de tooltip
function TRow({ label, value }: { label: string; value: string }) {
  return (
    <span style={{ display: "flex", justifyContent: "space-between", gap: 16, lineHeight: "1.9" }}>
      <span style={{ color: "var(--text-muted)" }}>{label}</span>
      <span style={{ fontWeight: 500, fontVariantNumeric: "tabular-nums" }}>{value}</span>
    </span>
  );
}

// Valeur numérique compacte
function Val({ children, accent }: { children: React.ReactNode; accent?: boolean }) {
  return (
    <span
      style={{
        fontSize: 12,
        fontVariantNumeric: "tabular-nums",
        fontWeight: 500,
        color: accent ? "var(--rag-badge-on)" : "var(--text-primary)",
        transition: "color 0.3s",
      }}
    >
      {children}
    </span>
  );
}

function Unit({ children, style }: { children: React.ReactNode; style?: React.CSSProperties }) {
  return (
    <span style={{ fontSize: 10, color: "var(--text-muted)", fontWeight: 400, ...style }}>
      {children}
    </span>
  );
}

// ── Icônes SVG inline ───────────────────────────────────────────────────────

const IconLeaf = () => (
  <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
    <circle cx="6" cy="6" r="4.8" stroke="currentColor" strokeWidth="1.1" opacity="0.45" />
    <path d="M4 7.8C4 6.4 4.9 5 6 5s2 1.4 2 2.8" stroke="var(--rag-badge-on)" strokeWidth="1.1" strokeLinecap="round" />
    <circle cx="6" cy="3.6" r="0.75" fill="var(--rag-badge-on)" />
  </svg>
);

const IconTokens = () => (
  <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
    <rect x="1.5" y="2"   width="3.5" height="1.4" rx="0.5" fill="currentColor" opacity="0.35" />
    <rect x="1.5" y="5.3" width="9"   height="1.4" rx="0.5" fill="currentColor" opacity="0.6"  />
    <rect x="1.5" y="8.6" width="5.5" height="1.4" rx="0.5" fill="currentColor" opacity="0.35" />
  </svg>
);

const IconArrow = () => (
  <svg width="10" height="6" viewBox="0 0 10 6" fill="none" style={{ opacity: 0.35 }}>
    <path d="M1 3H9M6.5 1L9 3L6.5 5" stroke="currentColor" strokeWidth="1.1" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

const IconClock = () => (
  <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
    <circle cx="6" cy="6" r="4.5" stroke="currentColor" strokeWidth="1.1" opacity="0.5" />
    <path d="M6 3.5v2.8l1.8 1.4" stroke="currentColor" strokeWidth="1.1" strokeLinecap="round" />
  </svg>
);

const IconRagOk = () => (
  <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
    <circle cx="6" cy="6" r="4.5" stroke="currentColor" strokeWidth="1.1" />
    <path d="M3.8 6.1l1.5 1.5 2.9-3" stroke="currentColor" strokeWidth="1.15" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

const IconRagWarn = () => (
  <svg width="13" height="13" viewBox="0 0 13 13" fill="none">
    <path
      d="M6.5 1.5L11.8 10.5H1.2L6.5 1.5Z"
      stroke="currentColor" strokeWidth="1.2"
      strokeLinejoin="round" fill="none"
    />
    <line x1="6.5" y1="5" x2="6.5" y2="8" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
    <circle cx="6.5" cy="9.4" r="0.65" fill="currentColor" />
  </svg>
);

// ── ConvTitleMenu ────────────────────────────────────────────────────────────

export function ConvTitleMenu({
  convId,
  title,
  isStarred = false,
  folders = [],
  onRename,
  onStar,
  onMove,
  onClear,
}: {
  convId: string | null;
  title: string;
  isStarred?: boolean;
  folders?: { id: string; name: string }[];
  onRename?: (convId: string, newTitle: string) => Promise<void>;
  onStar?: (convId: string, starred: boolean) => Promise<void>;
  onMove?: (convId: string, folderId: string | null) => Promise<void>;
  onClear?: () => void;
}) {
  const [open, setOpen]         = useState(false);
  const [subOpen, setSubOpen]   = useState(false);
  const [renaming, setRenaming] = useState(false);
  const [renameVal, setRenameVal] = useState(title);
  const menuRef   = useRef<HTMLDivElement>(null);
  const inputRef  = useRef<HTMLInputElement>(null);
  const btnRef    = useRef<HTMLButtonElement>(null);

  // Sync rename value when title changes externally
  useEffect(() => { setRenameVal(title); }, [title]);

  // Fermer le menu au clic extérieur
  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node) &&
          btnRef.current && !btnRef.current.contains(e.target as Node)) {
        setOpen(false);
        setSubOpen(false);
        setRenaming(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  // Focus automatique sur l'input de renommage
  useEffect(() => {
    if (renaming) setTimeout(() => inputRef.current?.focus(), 30);
  }, [renaming]);

  const handleRename = async () => {
    if (!convId || !onRename || !renameVal.trim()) return;
    await onRename(convId, renameVal.trim());
    setRenaming(false);
    setOpen(false);
  };

  const handleStar = async () => {
    if (!convId || !onStar) return;
    await onStar(convId, !isStarred);
    setOpen(false);
  };

  const handleMove = async (folderId: string | null) => {
    if (!convId || !onMove) return;
    await onMove(convId, folderId);
    setSubOpen(false);
    setOpen(false);
  };

  const displayTitle = title.length > 48 ? title.slice(0, 46) + "…" : title;

  return (
    <span style={{ position: "relative", display: "inline-flex", alignItems: "center", maxWidth: 360 }}>
      {/* ── Bouton titre + flèche ── */}
      <button
        ref={btnRef}
        onClick={() => { setOpen((v) => !v); setRenaming(false); setSubOpen(false); }}
        title="Options de la conversation"
        style={{
          display: "inline-flex",
          alignItems: "center",
          gap: 5,
          background: "none",
          border: "none",
          cursor: "pointer",
          padding: "3px 7px",
          borderRadius: 6,
          fontFamily: "inherit",
          fontSize: 13,
          fontWeight: 500,
          color: "var(--text-primary)",
          maxWidth: 360,
          transition: "background 0.13s",
          ...(open ? { background: "var(--elevated-bg)" } : {}),
        }}
        onMouseEnter={e => { if (!open) (e.currentTarget as HTMLElement).style.background = "var(--elevated-bg)"; }}
        onMouseLeave={e => { if (!open) (e.currentTarget as HTMLElement).style.background = "none"; }}
      >
        <span style={{
          overflow: "hidden",
          whiteSpace: "nowrap",
          textOverflow: "ellipsis",
          maxWidth: 320,
        }}>
          {displayTitle || "Conversation"}
        </span>
        {/* Chevron ▾ */}
        <svg
          width="10" height="6" viewBox="0 0 10 6" fill="none"
          style={{ flexShrink: 0, opacity: 0.55, transition: "transform 0.15s", transform: open ? "rotate(180deg)" : "rotate(0deg)" }}
        >
          <path d="M1 1l4 4 4-4" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>

      {/* ── Menu déroulant ── */}
      {open && (
        <div
          ref={menuRef}
          style={{
            position: "absolute",
            top: "calc(100% + 6px)",
            left: "50%",
            transform: "translateX(-50%)",
            background: "var(--surface-bg)",
            border: "1px solid var(--border-active)",
            borderRadius: 10,
            boxShadow: "0 8px 32px rgba(0,0,0,0.32)",
            zIndex: 300,
            minWidth: 210,
            overflow: "visible",
            padding: "4px 0",
          }}
        >
          {/* ── Renommer ── */}
          {renaming ? (
            <div style={{ padding: "8px 12px", display: "flex", gap: 6 }}>
              <input
                ref={inputRef}
                value={renameVal}
                onChange={e => setRenameVal(e.target.value)}
                onKeyDown={e => {
                  if (e.key === "Enter") handleRename();
                  if (e.key === "Escape") { setRenaming(false); setRenameVal(title); }
                }}
                style={{
                  flex: 1,
                  padding: "5px 8px",
                  fontSize: 13,
                  borderRadius: 6,
                  border: "1px solid var(--border-active)",
                  background: "var(--input-bg)",
                  color: "var(--text-primary)",
                  fontFamily: "inherit",
                  outline: "none",
                }}
              />
              <button
                onClick={handleRename}
                style={{
                  padding: "5px 10px",
                  borderRadius: 6,
                  border: "none",
                  background: "var(--accent)",
                  color: "#fff",
                  fontSize: 12,
                  cursor: "pointer",
                  fontFamily: "inherit",
                  fontWeight: 600,
                }}
              >OK</button>
            </div>
          ) : (
            <>
              {/* Favoris */}
              <MenuItem
                icon={isStarred ? "★" : "☆"}
                label={isStarred ? "Retirer des favoris" : "Ajouter aux favoris"}
                onClick={handleStar}
                color={isStarred ? "var(--accent)" : undefined}
              />

              {/* Renommer */}
              <MenuItem
                icon="✏️"
                label="Renommer"
                onClick={() => setRenaming(true)}
              />

              {/* Ajouter à un projet */}
              <div style={{ position: "relative" }}
                onMouseEnter={() => setSubOpen(true)}
                onMouseLeave={() => setSubOpen(false)}
              >
                <MenuItem
                  icon="📁"
                  label="Ajouter à un projet"
                  arrow
                />
                {subOpen && (
                  <div style={{
                    position: "absolute",
                    top: 0,
                    left: "100%",
                    marginLeft: 4,
                    background: "var(--surface-bg)",
                    border: "1px solid var(--border-active)",
                    borderRadius: 10,
                    boxShadow: "0 8px 28px rgba(0,0,0,0.28)",
                    minWidth: 190,
                    padding: "4px 0",
                    zIndex: 301,
                    maxHeight: 260,
                    overflowY: "auto",
                  }}>
                    <MenuItem
                      icon="✕"
                      label="Retirer du projet"
                      onClick={() => handleMove(null)}
                      color="var(--text-muted)"
                    />
                    <div style={{ height: 1, background: "var(--border)", margin: "3px 0" }} />
                    {folders.length === 0 ? (
                      <span style={{ display: "block", padding: "8px 14px", fontSize: 12, color: "var(--text-muted)" }}>
                        Aucun projet disponible
                      </span>
                    ) : (
                      folders.map(f => (
                        <MenuItem
                          key={f.id}
                          icon="📂"
                          label={f.name}
                          onClick={() => handleMove(f.id)}
                        />
                      ))
                    )}
                  </div>
                )}
              </div>

              {/* Séparateur */}
              <div style={{ height: 1, background: "var(--border)", margin: "3px 0" }} />

              {/* Effacer */}
              <MenuItem
                icon="🗑"
                label="Effacer la conversation"
                onClick={() => { onClear?.(); setOpen(false); }}
                color="#e07878"
              />
            </>
          )}
        </div>
      )}
    </span>
  );
}

function MenuItem({
  icon, label, onClick, color, arrow,
}: {
  icon: string;
  label: string;
  onClick?: () => void;
  color?: string;
  arrow?: boolean;
}) {
  const [hov, setHov] = useState(false);
  return (
    <button
      onClick={onClick}
      onMouseEnter={() => setHov(true)}
      onMouseLeave={() => setHov(false)}
      style={{
        display: "flex",
        alignItems: "center",
        gap: 9,
        width: "100%",
        padding: "8px 14px",
        background: hov ? "var(--elevated-bg)" : "none",
        border: "none",
        cursor: "pointer",
        fontFamily: "inherit",
        fontSize: 13,
        color: color ?? "var(--text-primary)",
        textAlign: "left",
        transition: "background 0.1s",
      }}
    >
      <span style={{ fontSize: 14, lineHeight: 1, flexShrink: 0 }}>{icon}</span>
      <span style={{ flex: 1 }}>{label}</span>
      {arrow && (
        <svg width="8" height="12" viewBox="0 0 8 12" fill="none" style={{ opacity: 0.45, flexShrink: 0 }}>
          <path d="M2 2l4 4-4 4" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      )}
    </button>
  );
}

// ── Composant principal ─────────────────────────────────────────────────────

export function MetricsBar({
  convId,
  convTitle = "",
  onRenameConv,
  onStarConv,
  onMoveConv,
  onClearConv,
  folders = [],
  isStarred = false,
  livePrompt = 0,
  liveCompletion = 0,
  isGenerating,
  ragStatus = { kind: "idle" },
}: MetricsBarProps) {
  const [data, setData] = useState<MonitoringData | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchData = useCallback(async () => {
    if (!convId) return;
    try {
      const d = await api.get<MonitoringData>(`/monitoring/${convId}`);
      setData(d);
    } catch {
      // silencieux — l'affichage reste sur les dernières valeurs connues
    }
  }, [convId]);

  // Polling
  useEffect(() => {
    if (!convId) return;
    fetchData();
    timerRef.current = setInterval(fetchData, POLL_MS);
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [convId, fetchData]);

  // Rafraîchissement immédiat à la fin de chaque génération
  const prevGenerating = useRef(isGenerating);
  useEffect(() => {
    if (prevGenerating.current && !isGenerating) {
      // génération vient de se terminer
      fetchData();
    }
    prevGenerating.current = isGenerating;
  }, [isGenerating, fetchData]);

  // Valeurs affichées — priorité au live WS pendant la génération
  const promptTok  = isGenerating && livePrompt     > 0 ? livePrompt     : (data?.session.prompt     ?? 0);
  const compTok    = isGenerating && liveCompletion > 0 ? liveCompletion : (data?.session.completion ?? 0);
  const llmCalls   = data?.session.llm_calls   ?? 0;
  const kgco2      = data?.session.carbon_kgco2 ?? 0;
  const costEur    = data?.session.cost_eur     ?? 0;
  const ctxFill    = data?.context_fill_pct     ?? 0;
  const gCo2       = kgco2 * 1000;
  const co2Warn    = gCo2 >= CO2_WARN_THRESHOLD;

  // ── Styles globaux (animation) ─────────────────────────────────────────────
  // On injecte une fois la keyframe dans le head si elle n'existe pas encore
  useEffect(() => {
    const id = "mb-anim";
    if (document.getElementById(id)) return;
    const style = document.createElement("style");
    style.id = id;
    style.textContent = `
      @keyframes mb-pulse {
        0%, 100% { opacity: 1; transform: scale(1); }
        50%       { opacity: 0.4; transform: scale(0.8); }
      }
      @keyframes rag-blink {
        0%, 100% { opacity: 1; }
        50%       { opacity: 0.45; }
      }
    `;
    document.head.appendChild(style);
  }, []);

  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 0,
        fontSize: 12,
        flexShrink: 0,
      }}
    >
      {/* ── Métriques gauche ── */}
      <span style={{ display: "inline-flex", alignItems: "center", gap: 0, flexShrink: 0 }}>
        {/* Dot d'état */}
        <span style={{ display: "flex", alignItems: "center", padding: "0 8px 0 2px" }}>
          <StatusDot active={isGenerating} />
        </span>

        <Sep />

        {/* CO₂ */}
        <Chip
          icon={<IconLeaf />}
          tooltipAlign="left"
          tooltip={
            <span style={{ display: "flex", flexDirection: "column" }}>
              <TRow label="Conv. courante"  value={`${fmtCo2(kgco2)} gCO₂eq`} />
              <TRow label="Équiv. voiture"  value={fmtCarEquiv(kgco2)} />
              <TRow label="Coût estimé"     value={fmtCost(costEur)} />
            </span>
          }
        >
          <Val accent={!co2Warn}>
            <span style={{ color: co2Warn ? "var(--accent)" : "var(--rag-badge-on)" }}>
              {fmtCo2(kgco2)}
            </span>
          </Val>
          <Unit>gCO₂</Unit>
        </Chip>

        <Sep />

        {/* Tokens in → out */}
        <Chip
          icon={<IconTokens />}
          tooltip={
            <span style={{ display: "flex", flexDirection: "column" }}>
              <TRow label="Tokens in (prompt)"     value={promptTok.toLocaleString("fr-FR")} />
              <TRow label="Tokens out (complétion)" value={compTok.toLocaleString("fr-FR")} />
              <TRow label="Contexte rempli"         value={`${Math.round(ctxFill)} %`} />
            </span>
          }
        >
          <Val>{fmtTok(promptTok)}</Val>
          <span style={{ display: "inline-flex", alignItems: "center", margin: "0 2px" }}>
            <IconArrow />
          </span>
          <Val>{fmtTok(compTok)}</Val>
          <Unit style={{ marginLeft: 2 }}>tok</Unit>
        </Chip>

        <Sep />

        {/* Appels LLM */}
        <Chip
          icon={<IconClock />}
          tooltip={
            <span style={{ display: "flex", flexDirection: "column" }}>
              <TRow label="Appels LLM (conv.)"  value={String(llmCalls)} />
              <TRow label="Coût estimé"          value={fmtCost(costEur)} />
            </span>
          }
        >
          <Val>{llmCalls}</Val>
          <Unit>appels</Unit>
        </Chip>

        {/* RAG ok */}
        {ragStatus.kind === "ok" && (
          <>
            <Sep />
            <Chip
              icon={
                <span style={{ color: "var(--rag-badge-on)", display: "flex" }}>
                  <IconRagOk />
                </span>
              }
              tooltipAlign="left"
              tooltip={
                <span style={{ display: "flex", flexDirection: "column", gap: 4, whiteSpace: "normal" }}>
                  <span style={{ fontWeight: 600, color: "var(--rag-badge-on)" }}>
                    ✓ RAG actif
                  </span>
                  <span style={{ color: "var(--text-muted)", lineHeight: 1.5 }}>
                    {ragStatus.chunks > 0
                      ? `${ragStatus.chunks} passage${ragStatus.chunks > 1 ? "s" : ""} injecté${ragStatus.chunks > 1 ? "s" : ""} dans le contexte.`
                      : "Aucun passage pertinent trouvé pour ce message."}
                  </span>
                </span>
              }
            >
              <span style={{ fontSize: 12, fontWeight: 600, color: "var(--rag-badge-on)" }}>
                RAG
              </span>
              {ragStatus.chunks > 0 && (
                <Unit style={{ marginLeft: 1 }}>{ragStatus.chunks}</Unit>
              )}
            </Chip>
          </>
        )}

        {/* RAG warn */}
        {ragStatus.kind === "warn" && (
          <>
            <Sep />
            <Chip
              icon={
                <span style={{ color: "var(--accent)", animation: "rag-blink 2s ease infinite", display: "flex" }}>
                  <IconRagWarn />
                </span>
              }
              tooltipAlign="left"
              tooltip={
                <span style={{ display: "flex", flexDirection: "column", gap: 4, maxWidth: 260, whiteSpace: "normal" }}>
                  <span style={{ fontWeight: 600, color: "var(--accent)" }}>
                    ⚠ RAG hors service
                  </span>
                  <span style={{ color: "var(--text-muted)", lineHeight: 1.5 }}>
                    Le contexte documentaire n'a pas pu être récupéré. Le message a été envoyé sans données RAG.
                  </span>
                  {ragStatus.error && (
                    <span style={{
                      marginTop: 4,
                      padding: "4px 6px",
                      borderRadius: 4,
                      background: "var(--elevated-bg)",
                      fontFamily: "monospace",
                      fontSize: 11,
                      color: "var(--text-primary)",
                      wordBreak: "break-all",
                      whiteSpace: "pre-wrap",
                    }}>
                      {ragStatus.error}
                    </span>
                  )}
                </span>
              }
            >
              <span style={{ fontSize: 12, fontWeight: 600, color: "var(--accent)" }}>RAG KO</span>
            </Chip>
          </>
        )}
      </span>
    </span>
  );
}
