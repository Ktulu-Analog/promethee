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
 * SidebarRail.tsx — Composants visuels du rail : RailBtn, NavItem, RecentConvBtn.
 */

import React, { useState } from "react";
import { Conversation } from "../../hooks/useConversationTree";

// ── RailBtn ───────────────────────────────────────────────────────────────────

export function RailBtn({
  icon, tip, onClick, active = false,
}: {
  icon: React.ReactNode;
  tip: string;
  onClick: () => void;
  active?: boolean;
}) {
  const [hovered, setHovered] = useState(false);
  const lit = hovered || active;

  return (
    <div
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        position: "relative",
        width: "100%",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        height: 36,
        flexShrink: 0,
        cursor: "pointer",
        background: lit
          ? "linear-gradient(90deg, transparent 0%, var(--accent-glow, rgba(99,102,241,0.10)) 20%, var(--accent-glow, rgba(99,102,241,0.10)) 80%, transparent 100%)"
          : "none",
        transition: "background 0.18s",
      }}
      onClick={onClick}
      title={tip}
    >
      <div
        style={{
          width: 32,
          height: 32,
          borderRadius: "50%",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          border: lit ? "1.5px solid var(--accent, #6366f1)" : "1.5px solid transparent",
          boxShadow: lit ? "0 0 8px 2px var(--accent-glow, rgba(99,102,241,0.30))" : "none",
          background: active ? "var(--sidebar-item-active-bg)" : "none",
          transition: "border-color 0.18s, box-shadow 0.18s, background 0.18s",
          flexShrink: 0,
        }}
      >
        {icon}
      </div>
    </div>
  );
}

// ── NavItem ───────────────────────────────────────────────────────────────────

export function NavItem({
  icon, label, onClick, active = false,
}: {
  icon: React.ReactNode;
  label: string;
  onClick: () => void;
  active?: boolean;
}) {
  const [hovered, setHovered] = useState(false);
  const lit = hovered || active;

  return (
    <div
      onClick={onClick}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        display: "flex",
        alignItems: "center",
        gap: 10,
        width: "100%",
        background: lit
          ? "linear-gradient(90deg, transparent 0%, var(--accent-glow) 20%, var(--accent-glow) 80%, transparent 100%)"
          : "none",
        borderRadius: 7,
        padding: "5px 8px",
        cursor: "pointer",
        color: active ? "var(--text-primary)" : "var(--text-secondary)",
        fontSize: 13,
        fontWeight: active ? 600 : 400,
        fontFamily: "inherit",
        userSelect: "none" as const,
        transition: "background 0.18s, color 0.18s",
      }}
    >
      <span style={{
        flexShrink: 0,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        width: 30,
        height: 30,
        borderRadius: "50%",
        border: lit ? "1.5px solid var(--accent)" : "1.5px solid transparent",
        boxShadow: lit ? "0 0 8px 2px var(--accent-glow)" : "none",
        background: active ? "var(--sidebar-item-active-bg)" : "none",
        transition: "border-color 0.18s, box-shadow 0.18s, background 0.18s",
      }}>
        {icon}
      </span>
      <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" as const }}>{label}</span>
    </div>
  );
}

// ── RecentConvBtn ─────────────────────────────────────────────────────────────

export function RecentConvBtn({
  conv, isActive, onClick,
}: {
  conv: Conversation;
  isActive: boolean;
  onClick: () => void;
}) {
  const initials = conv.title
    .replace(/^(re|fwd|fw):\s*/i, "")
    .trim()
    .slice(0, 2)
    .toUpperCase() || "…";

  return (
    <button
      title={conv.title}
      onClick={onClick}
      style={{
        width: 32,
        height: 32,
        borderRadius: 8,
        border: isActive
          ? "1.5px solid var(--accent)"
          : "1px solid var(--border)",
        background: isActive
          ? "var(--sidebar-item-active-bg)"
          : "var(--elevated-bg)",
        color: isActive ? "var(--accent)" : "var(--text-muted)",
        fontSize: 10,
        fontWeight: 700,
        cursor: "pointer",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        flexShrink: 0,
        letterSpacing: "0.03em",
        transition: "border-color 0.12s, background 0.12s, color 0.12s",
        fontFamily: "inherit",
        overflow: "hidden",
      }}
    >
      {initials}
    </button>
  );
}
