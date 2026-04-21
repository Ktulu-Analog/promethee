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
 * ToolsPanel.tsx — Panneau d'outils agent (sidebar droite)
 *
 * Portage complet de ui/panels/tools_panel.py (PyQt6 → React).
 *
 * Fonctionnalités :
 *   - Liste des familles d'outils (GET /tools/families)
 *   - Toggle activer/désactiver une famille (PATCH /tools/families/{family})
 *   - Collapse/expand par famille
 *   - Tooltip au survol d'un outil ou d'un en-tête de famille
 *   - Nom barré quand la famille est désactivée
 *
 * Props :
 *   onClose — Ferme le panneau
 */

import React, { useState, useEffect, useRef, useCallback, useMemo } from "react";
import { api } from "../../lib/api";

// ── Types profil ───────────────────────────────────────────────────────────

interface Profile {
  name: string;
  prompt: string;
  tool_families?: { enabled: string[]; disabled: string[] };
}

// ── Types API ──────────────────────────────────────────────────────────────

interface ToolOut {
  name: string;
  description: string;
  icon: string;
  family: string;
  family_label: string;
  family_icon: string;
  enabled: boolean;
}

interface FamilyOut {
  family: string;
  label: string;
  icon: string;
  enabled: boolean;
  tool_count: number;
  model_backend: string;
  model_name: string;
  model_base_url: string;
}

// ── Props ──────────────────────────────────────────────────────────────────

export interface ToolsPanelProps {
  onClose: () => void;
  /** Quand true : pas de borderLeft, background transparent, s'adapte au FloatingPanel */
  embedded?: boolean;
  /** Profil courant — ses tool_families surchargent l'état global des familles */
  currentProfile?: Profile | null;
}

// ── Tooltip flottant ───────────────────────────────────────────────────────

interface TooltipState {
  visible: boolean;
  title: string;
  body: string;
  x: number;
  y: number;
}

// ── FamilyToggle ───────────────────────────────────────────────────────────

function FamilyToggle({
  enabled,
  onToggle,
}: {
  enabled: boolean;
  onToggle: (v: boolean) => void;
}) {
  return (
    <button
      onClick={(e) => {
        e.stopPropagation();
        onToggle(!enabled);
      }}
      title={enabled ? "Désactiver la famille" : "Activer la famille"}
      style={{
        ...s.toggle,
        background: enabled ? "#4CAF50" : "#555",
      }}
    >
      <span
        style={{
          ...s.toggleThumb,
          transform: enabled ? "translateX(16px)" : "translateX(0)",
        }}
      />
    </button>
  );
}

// ── ToolCard ───────────────────────────────────────────────────────────────

function ToolCard({
  tool,
  strikethrough,
  onMouseEnter,
  onMouseLeave,
}: {
  tool: ToolOut;
  strikethrough: boolean;
  onMouseEnter: (e: React.MouseEvent, tool: ToolOut) => void;
  onMouseLeave: () => void;
}) {
  const [hovered, setHovered] = useState(false);

  return (
    <div
      style={{
        ...s.toolCard,
        borderColor: hovered ? "var(--accent)" : "var(--border)",
      }}
      onMouseEnter={(e) => {
        setHovered(true);
        onMouseEnter(e, tool);
      }}
      onMouseLeave={() => {
        setHovered(false);
        onMouseLeave();
      }}
    >
      <span style={s.toolIcon}>{tool.icon}</span>
      <span
        style={{
          ...s.toolName,
          color: strikethrough ? "var(--text-muted)" : "var(--text-primary)",
          textDecoration: strikethrough ? "line-through" : "none",
        }}
      >
        {tool.name}
      </span>
    </div>
  );
}

// ── FamilyGroup ────────────────────────────────────────────────────────────

function FamilyGroup({
  family,
  tools,
  onToggle,
  onToolHover,
  onFamilyHover,
  onHoverEnd,
}: {
  family: FamilyOut;
  tools: ToolOut[];
  onToggle: (familyKey: string, enabled: boolean) => void;
  onToolHover: (e: React.MouseEvent, tool: ToolOut) => void;
  onFamilyHover: (e: React.MouseEvent, family: FamilyOut, toolCount: number) => void;
  onHoverEnd: () => void;
}) {
  const [collapsed, setCollapsed] = useState(true);

  return (
    <div style={s.familyGroup}>
      {/* En-tête famille */}
      <div
        style={s.familyHeader}
        onMouseEnter={(e) => onFamilyHover(e, family, tools.length)}
        onMouseLeave={onHoverEnd}
      >
        {/* Chevron collapse */}
        <button
          style={s.chevron}
          onClick={() => setCollapsed((v) => !v)}
          title={collapsed ? "Déplier" : "Replier"}
        >
          {collapsed ? "▶" : "▼"}
        </button>

        {/* Toggle ON/OFF */}
        <FamilyToggle
          enabled={family.enabled}
          onToggle={(v) => onToggle(family.family, v)}
        />

        {/* Icône + label */}
        <span style={s.familyIcon}>{family.icon}</span>
        <span
          style={{
            ...s.familyLabel,
            opacity: family.enabled ? 1 : 0.5,
          }}
        >
          {family.label}
        </span>

        {/* Nombre d'outils */}
        <span style={s.familyCount}>{tools.length}</span>
      </div>

      {/* Liste des outils */}
      {!collapsed && (
        <div style={s.toolList}>
          {tools.map((tool) => (
            <ToolCard
              key={tool.name}
              tool={tool}
              strikethrough={!family.enabled}
              onMouseEnter={onToolHover}
              onMouseLeave={onHoverEnd}
            />
          ))}
        </div>
      )}
    </div>
  );
}

// ── Composant principal ────────────────────────────────────────────────────

export function ToolsPanel({ onClose, embedded = false, currentProfile }: ToolsPanelProps) {
  const [baseFamilies, setBaseFamilies] = useState<FamilyOut[]>([]);
  const [toolsByFamily, setToolsByFamily] = useState<Record<string, ToolOut[]>>({});
  const [loading, setLoading] = useState(true);

  // Overrides manuels de l'utilisateur : { [familyKey]: boolean }
  // Réinitialisés à chaque changement de profil.
  const [userOverrides, setUserOverrides] = useState<Record<string, boolean>>({});

  // Ref sur le nom du profil précédent pour détecter les vrais changements
  const prevProfileNameRef = useRef<string | null | undefined>(undefined);

  // Tooltip
  const [tooltip, setTooltip] = useState<TooltipState>({
    visible: false,
    title: "",
    body: "",
    x: 0,
    y: 0,
  });
  const hoverTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pendingTooltipRef = useRef<TooltipState | null>(null);

  // ── Chargement données ───────────────────────────────────────────────────

  useEffect(() => {
    loadData();
  }, []);

  async function loadData() {
    setLoading(true);
    try {
      const [fams, tools] = await Promise.all([
        api.get<FamilyOut[]>("/tools/families"),
        api.get<ToolOut[]>("/tools"),
      ]);

      const byFamily: Record<string, ToolOut[]> = {};
      for (const t of tools) {
        if (!byFamily[t.family]) byFamily[t.family] = [];
        byFamily[t.family].push(t);
      }

      setBaseFamilies(fams);
      setToolsByFamily(byFamily);
    } catch (err) {
      console.error("ToolsPanel: erreur chargement", err);
    } finally {
      setLoading(false);
    }
  }

  // ── Reset overrides au changement de profil ──────────────────────────────

  useEffect(() => {
    const incomingName = currentProfile?.name ?? null;
    if (incomingName === prevProfileNameRef.current) return;
    prevProfileNameRef.current = incomingName;
    // Nouveau profil → on efface les overrides manuels
    setUserOverrides({});
  }, [currentProfile]);

  // ── État effectif des familles (profil + overrides utilisateur) ──────────

  const families = useMemo<FamilyOut[]>(() => {
    const tf = currentProfile?.tool_families;
    return baseFamilies.map((f) => {
      // 1. Override manuel de l'utilisateur (priorité maximale)
      if (f.family in userOverrides) {
        return { ...f, enabled: userOverrides[f.family] };
      }
      // 2. Override du profil
      if (tf) {
        if (tf.enabled?.includes(f.family)) return { ...f, enabled: true };
        if (tf.disabled?.includes(f.family)) return { ...f, enabled: false };
      }
      // 3. État global
      return f;
    });
  }, [baseFamilies, currentProfile, userOverrides]);

  // ── Toggle famille ───────────────────────────────────────────────────────

  async function handleToggle(familyKey: string, enabled: boolean) {
    // Enregistrer l'override utilisateur (survit au re-render, reset au changement profil)
    setUserOverrides((prev) => ({ ...prev, [familyKey]: enabled }));
    try {
      await api.patch(`/tools/families/${familyKey}`, { enabled });
      // Mettre aussi à jour baseFamilies pour cohérence si le profil est retiré
      setBaseFamilies((prev) =>
        prev.map((f) => (f.family === familyKey ? { ...f, enabled } : f))
      );
    } catch (err) {
      console.error("ToolsPanel: erreur toggle", err);
      // Rollback override
      setUserOverrides((prev) => {
        const next = { ...prev };
        delete next[familyKey];
        return next;
      });
    }
  }

  // ── Tooltip ──────────────────────────────────────────────────────────────

  const scheduleTooltip = useCallback(
    (e: React.MouseEvent, title: string, body: string) => {
      if (hoverTimerRef.current) clearTimeout(hoverTimerRef.current);

      // Positionner à gauche du panneau
      const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
      const pending: TooltipState = {
        visible: true,
        title,
        body,
        x: rect.right + 10, // infobulle à droite
        y: rect.top,
      };
      pendingTooltipRef.current = pending;

      hoverTimerRef.current = setTimeout(() => {
        if (pendingTooltipRef.current) {
          setTooltip(pendingTooltipRef.current);
        }
      }, 400);
    },
    []
  );

  const hideTooltip = useCallback(() => {
    if (hoverTimerRef.current) clearTimeout(hoverTimerRef.current);
    pendingTooltipRef.current = null;
    setTooltip((t) => ({ ...t, visible: false }));
  }, []);

  const handleToolHover = useCallback(
    (e: React.MouseEvent, tool: ToolOut) => {
      scheduleTooltip(e, `${tool.icon}  ${tool.name}`, tool.description);
    },
    [scheduleTooltip]
  );

  const handleFamilyHover = useCallback(
    (e: React.MouseEvent, family: FamilyOut, toolCount: number) => {
      const status = family.enabled ? "activée" : "désactivée";
      const plural = toolCount > 1 ? "s" : "";
      scheduleTooltip(
        e,
        `${family.icon}  ${family.label}`,
        `${toolCount} outil${plural}  ·  famille ${status}`
      );
    },
    [scheduleTooltip]
  );

  // ── Render ────────────────────────────────────────────────────────────────

  const enabledCount = families.filter((f) => f.enabled).length;
  const totalTools = Object.values(toolsByFamily).reduce((n, ts) => n + ts.length, 0);
  const hasUserOverrides = Object.keys(userOverrides).length > 0;
  const profileName = currentProfile?.name && currentProfile.name !== "Aucun rôle"
    ? currentProfile.name : null;

  return (
    <div style={{ ...s.panel, ...(embedded ? s.panelEmbedded : {}) }}>
      {/* ── En-tête ────────────────────────────────────────────────────── */}
      <div style={s.header}>
        <span style={s.headerIcon}>🛠️</span>
        <span style={s.headerTitle}>Outils Agent</span>
        <div style={{ flex: 1 }} />
        <button style={s.closeBtn} onClick={onClose} title="Fermer">×</button>
      </div>

      {/* ── Profil actif ────────────────────────────────────────────────── */}
      {profileName && (
        <div style={s.profileBadge}>
          <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0 }}>
            <circle cx="12" cy="8" r="4"/><path d="M4 20c0-4 3.6-7 8-7s8 3 8 7"/>
          </svg>
          <span>{profileName}</span>
          {hasUserOverrides && (
            <span style={s.overrideDot} title="Modifications manuelles actives">●</span>
          )}
        </div>
      )}

      {/* ── Hint ───────────────────────────────────────────────────────── */}
      <div style={s.hint}>
        Activez le mode Agent dans la zone de saisie.
      </div>

      <div style={s.divider} />

      {/* ── Compteurs ──────────────────────────────────────────────────── */}
      <div style={s.stats}>
        <span style={s.statBadge}>{enabledCount}/{families.length} familles</span>
        <span style={s.statBadge}>{totalTools} outils</span>
        {hasUserOverrides && (
          <span
            style={{ ...s.statBadge, ...s.statBadgeOverride }}
            title="Cliquez sur un toggle pour réinitialiser au prochain changement de profil"
          >
            ✎ modifié
          </span>
        )}
      </div>

      <SectionLabel>Familles d'outils</SectionLabel>

      {/* ── Liste des familles ──────────────────────────────────────────── */}
      <div style={s.scrollArea}>
        {loading && (
          <div style={s.loading}>Chargement…</div>
        )}
        {!loading && families.length === 0 && (
          <div style={s.loading}>Aucun outil disponible</div>
        )}
        {families.map((family) => {
          const tools = toolsByFamily[family.family] ?? [];
          if (tools.length === 0) return null;
          return (
            <FamilyGroup
              key={family.family}
              family={family}
              tools={tools}
              onToggle={handleToggle}
              onToolHover={handleToolHover}
              onFamilyHover={handleFamilyHover}
              onHoverEnd={hideTooltip}
            />
          );
        })}
        <div style={{ height: 8 }} />
      </div>

      <div style={s.divider} />

      {/* ── Pied de page ───────────────────────────────────────────────── */}
      <div style={s.footer}>
        Les outils s'exécutent<br />localement sur votre machine.
      </div>

      {/* ── Tooltip flottant ───────────────────────────────────────────── */}
      {tooltip.visible && (
        <div
          style={{
            ...s.tooltip,
            left: Math.max(8, tooltip.x),
            top: tooltip.y,
          }}
        >
          <div style={s.tooltipTitle}>{tooltip.title}</div>
          <div style={s.tooltipBody}>{tooltip.body}</div>
        </div>
      )}
    </div>
  );
}

// ── SectionLabel ───────────────────────────────────────────────────────────

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

// ── Styles ─────────────────────────────────────────────────────────────────

const s: Record<string, React.CSSProperties> = {
  panel: {
    width: "100%",
    background: "var(--surface-bg)",
    borderLeft: "1px solid var(--border)",
    display: "flex",
    flexDirection: "column",
    height: "100%",
    overflow: "hidden",
    flexShrink: 0,
    fontSize: 13,
    color: "var(--text-primary)",
    position: "relative",
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
  hint: {
    padding: "8px 14px 6px",
    fontSize: 11,
    color: "var(--tools-badge-idle)",
    lineHeight: 1.5,
    flexShrink: 0,
  },
  profileBadge: {
    display: "flex",
    alignItems: "center",
    gap: 5,
    padding: "4px 14px 0",
    fontSize: 11,
    color: "var(--accent)",
    fontWeight: 600,
    flexShrink: 0,
  },
  overrideDot: {
    color: "var(--text-muted)",
    fontSize: 8,
    marginLeft: 2,
    opacity: 0.7,
  },
  statBadgeOverride: {
    color: "var(--accent)",
    borderColor: "var(--accent)",
    opacity: 0.8,
  },
  divider: {
    height: 1,
    background: "var(--border)",
    margin: "6px 0",
    flexShrink: 0,
  },
  stats: {
    display: "flex",
    gap: 6,
    padding: "2px 14px 8px",
    flexShrink: 0,
  },
  statBadge: {
    fontSize: 10,
    color: "var(--text-muted)",
    background: "var(--elevated-bg)",
    border: "1px solid var(--border)",
    borderRadius: 4,
    padding: "2px 7px",
  },
  scrollArea: {
    flex: 1,
    overflowY: "auto",
    overflowX: "hidden",
    padding: "4px 10px 0",
    minHeight: 0,
  },
  loading: {
    padding: "16px 8px",
    fontSize: 12,
    color: "var(--text-muted)",
    fontStyle: "italic",
    textAlign: "center",
  },
  footer: {
    padding: "8px 14px 12px",
    fontSize: 10,
    color: "var(--text-muted)",
    textAlign: "center",
    lineHeight: 1.6,
    flexShrink: 0,
  },

  // Famille
  familyGroup: {
    marginBottom: 10,
  },
  familyHeader: {
    display: "flex",
    alignItems: "center",
    gap: 6,
    padding: "6px 10px",
    background: "var(--elevated-bg)",
    border: "1px solid var(--border)",
    borderRadius: 8,
    cursor: "default",
    userSelect: "none",
    marginBottom: 4,
  },
  chevron: {
    background: "transparent",
    border: "none",
    color: "var(--text-muted)",
    fontSize: 9,
    cursor: "pointer",
    padding: "0 2px",
    width: 16,
    height: 16,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    flexShrink: 0,
    fontFamily: "inherit",
  },
  familyIcon: {
    fontSize: 13,
    flexShrink: 0,
  },
  familyLabel: {
    flex: 1,
    fontSize: 12,
    fontWeight: 700,
    color: "var(--text-primary)",
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
  },
  familyCount: {
    fontSize: 10,
    color: "var(--text-muted)",
    background: "var(--surface-bg)",
    border: "1px solid var(--border)",
    borderRadius: 4,
    padding: "1px 5px",
    flexShrink: 0,
  },

  // Toggle
  toggle: {
    position: "relative",
    width: 36,
    height: 20,
    borderRadius: 10,
    border: "none",
    cursor: "pointer",
    padding: 0,
    flexShrink: 0,
    transition: "background 0.2s",
  },
  toggleThumb: {
    position: "absolute",
    top: 2,
    left: 2,
    width: 16,
    height: 16,
    borderRadius: "50%",
    background: "#fff",
    transition: "transform 0.2s",
    display: "block",
  },

  // Outil
  toolList: {
    paddingLeft: 4,
    paddingRight: 4,
    paddingTop: 4,
    paddingBottom: 6,
    display: "grid",
    gridTemplateColumns: "repeat(3, 1fr)",
    gap: 4,
  },
  toolCard: {
    display: "flex",
    alignItems: "center",
    gap: 6,
    padding: "6px 8px",
    background: "var(--elevated-bg)",
    border: "1px solid var(--border)",
    borderRadius: 7,
    cursor: "default",
    transition: "border-color 0.15s",
    userSelect: "none",
    minWidth: 0,
  },
  toolIcon: {
    fontSize: 16,
    width: 24,
    flexShrink: 0,
    textAlign: "center",
  },
  toolName: {
    fontSize: 11,
    fontWeight: 600,
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
    minWidth: 0,
    flex: 1,
  },

  // Tooltip
  tooltip: {
    position: "fixed",
    background: "var(--surface-bg)",
    border: "1px solid var(--border-active)",
    borderRadius: 8,
    padding: "10px 12px",
    maxWidth: 280,
    zIndex: 9999,
    pointerEvents: "none",
    boxShadow: "0 4px 20px rgba(0,0,0,0.4)",
  },
  tooltipTitle: {
    fontSize: 12,
    fontWeight: 700,
    color: "var(--text-primary)",
    marginBottom: 4,
    whiteSpace: "nowrap",
  },
  tooltipBody: {
    fontSize: 11,
    color: "var(--text-muted)",
    lineHeight: 1.5,
    wordBreak: "break-word",
  },
};
