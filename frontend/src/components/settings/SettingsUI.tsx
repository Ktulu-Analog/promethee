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
 * SettingsUI.tsx — Primitives UI partagées entre les onglets du SettingsDialog
 *
 * Reproduit visuellement les QGroupBox, QFormLayout, QLineEdit, QComboBox
 * du dialogue Qt en utilisant les mêmes CSS custom properties.
 */

import React, { useState, useRef, useEffect } from "react";

// ── FormRow ───────────────────────────────────────────────────────────────

export function FormRow({
  label,
  children,
  hint,
}: {
  label: string;
  children: React.ReactNode;
  hint?: string;
}) {
  return (
    <div style={s.formRow}>
      <label style={s.formLabel}>{label}</label>
      <div style={s.formField}>
        {children}
        {hint && <span style={s.formHint}>{hint}</span>}
      </div>
    </div>
  );
}

// ── Group ─────────────────────────────────────────────────────────────────

export function Group({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <fieldset style={s.group}>
      <legend style={s.groupLegend}>{title}</legend>
      <div style={s.groupBody}>{children}</div>
    </fieldset>
  );
}

// ── TextInput ─────────────────────────────────────────────────────────────

export function TextInput({
  value,
  onChange,
  placeholder = "",
  password = false,
  mono = false,
  disabled = false,
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  password?: boolean;
  mono?: boolean;
  disabled?: boolean;
}) {
  return (
    <input
      type={password ? "password" : "text"}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      disabled={disabled}
      style={{
        ...s.input,
        fontFamily: mono ? "monospace" : "inherit",
        opacity: disabled ? 0.5 : 1,
      }}
    />
  );
}

// ── Select ────────────────────────────────────────────────────────────────

export function Select<T extends string>({
  value,
  onChange,
  options,
  disabled = false,
}: {
  value: T;
  onChange: (v: T) => void;
  options: { value: T; label: string }[];
  disabled?: boolean;
}) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value as T)}
      disabled={disabled}
      style={{ ...s.input, cursor: disabled ? "not-allowed" : "pointer", paddingRight: 28 }}
    >
      {options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  );
}

// ── ComboInput — select éditable + bouton refresh ─────────────────────────
// Équivalent de ComboBoxWithArrow (éditable) + QPushButton "🔄"

export function ComboInput({
  value,
  onChange,
  options,
  onRefresh,
  refreshing = false,
  placeholder = "(vide = modèle principal)",
  disabled = false,
}: {
  value: string;
  onChange: (v: string) => void;
  options: string[];
  onRefresh?: () => void;
  refreshing?: boolean;
  placeholder?: string;
  disabled?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [filter, setFilter] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  const dropRef = useRef<HTMLDivElement>(null);

  // Fermer le dropdown au clic extérieur
  useEffect(() => {
    function handle(e: MouseEvent) {
      if (!dropRef.current?.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", handle);
    return () => document.removeEventListener("mousedown", handle);
  }, []);

  const filtered = filter
    ? options.filter((o) => o.toLowerCase().includes(filter.toLowerCase()))
    : options;

  return (
    <div style={{ display: "flex", gap: 6, flex: 1 }}>
      <div ref={dropRef} style={{ position: "relative", flex: 1 }}>
        <input
          ref={inputRef}
          type="text"
          value={value}
          onChange={(e) => { onChange(e.target.value); setFilter(e.target.value); setOpen(true); }}
          onFocus={() => { setFilter(""); setOpen(options.length > 0); }}
          onBlur={() => setTimeout(() => setOpen(false), 150)}
          placeholder={placeholder}
          disabled={disabled}
          style={{ ...s.input, width: "100%", paddingRight: 24 }}
        />
        {/* Flèche */}
        <span style={s.dropArrow} onClick={() => { setOpen((v) => !v); inputRef.current?.focus(); }}>
          ▾
        </span>

        {open && options.length > 0 && (
          <div style={s.dropdown}>
            {filtered.slice(0, 30).map((opt) => (
              <div
                key={opt}
                style={{
                  ...s.dropItem,
                  background: opt === value ? "var(--sidebar-item-active-bg)" : undefined,
                }}
                onMouseDown={() => { onChange(opt); setOpen(false); setFilter(""); }}
              >
                {opt}
              </div>
            ))}
            {filtered.length === 0 && (
              <div style={s.dropEmpty}>Aucun résultat</div>
            )}
          </div>
        )}
      </div>

      {/* Bouton refresh */}
      {onRefresh && (
        <button
          onClick={onRefresh}
          disabled={refreshing || disabled}
          title="Actualiser la liste des modèles"
          style={s.refreshBtn}
        >
          {refreshing ? "⏳" : "🔄"}
        </button>
      )}
    </div>
  );
}

// ── Toggle ────────────────────────────────────────────────────────────────

export function Toggle({
  value,
  onChange,
  label,
}: {
  value: boolean;
  onChange: (v: boolean) => void;
  label: string;
}) {
  return (
    <label style={s.toggle}>
      <input
        type="checkbox"
        checked={value}
        onChange={(e) => onChange(e.target.checked)}
        style={{ accentColor: "var(--accent)", cursor: "pointer" }}
      />
      <span style={{ fontSize: 13, color: "var(--text-secondary)" }}>{label}</span>
    </label>
  );
}

// ── NumberInput ───────────────────────────────────────────────────────────

export function NumberInput({
  value,
  onChange,
  min,
  max,
  step = 1,
}: {
  value: number;
  onChange: (v: number) => void;
  min?: number;
  max?: number;
  step?: number;
}) {
  return (
    <input
      type="number"
      value={value}
      min={min}
      max={max}
      step={step}
      onChange={(e) => onChange(Number(e.target.value))}
      style={{ ...s.input, width: 100 }}
    />
  );
}

// ── StatusDot ─────────────────────────────────────────────────────────────

export function StatusDot({ ok, label }: { ok: boolean; label: string }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12 }}>
      <span
        style={{
          width: 8,
          height: 8,
          borderRadius: "50%",
          background: ok ? "var(--rag-badge-on)" : "var(--rag-badge-off)",
          display: "inline-block",
          flexShrink: 0,
        }}
      />
      <span style={{ color: ok ? "var(--rag-badge-on)" : "var(--text-muted)" }}>{label}</span>
    </div>
  );
}

// ── Hint ──────────────────────────────────────────────────────────────────

export function Hint({ children }: { children: React.ReactNode }) {
  return (
    <p style={{ margin: "0 0 8px", fontSize: 11, color: "var(--text-secondary)", lineHeight: 1.5 }}>
      {children}
    </p>
  );
}

// ── Styles ────────────────────────────────────────────────────────────────

export const s: Record<string, React.CSSProperties> = {
  formRow: {
    display: "grid",
    gridTemplateColumns: "140px 1fr",
    alignItems: "start",
    gap: "6px 12px",
    marginBottom: 10,
  },
  formLabel: {
    fontSize: 12,
    color: "var(--text-secondary)",
    paddingTop: 7,
    textAlign: "right",
    userSelect: "none",
  },
  formField: {
    display: "flex",
    flexDirection: "column",
    gap: 4,
  },
  formHint: {
    fontSize: 11,
    color: "var(--text-muted)",
    lineHeight: 1.4,
  },
  group: {
    border: "1px solid var(--input-border)",
    borderRadius: 8,
    padding: "10px 14px 12px",
    marginBottom: 12,
  },
  groupLegend: {
    fontSize: 12,
    fontWeight: 600,
    color: "var(--text-secondary)",
    padding: "0 6px",
  },
  groupBody: {
    marginTop: 8,
  },
  input: {
    display: "block",
    width: "100%",
    padding: "5px 9px",
    background: "var(--input-bg)",
    border: "1px solid var(--input-border)",
    borderRadius: 6,
    color: "var(--input-color)",
    fontSize: 13,
    outline: "none",
    boxSizing: "border-box",
    fontFamily: "inherit",
  },
  dropdown: {
    position: "absolute",
    top: "100%",
    left: 0,
    right: 0,
    zIndex: 200,
    background: "var(--menu-bg)",
    border: "1px solid var(--menu-border)",
    borderRadius: 6,
    boxShadow: "0 6px 20px rgba(0,0,0,0.25)",
    maxHeight: 240,
    overflowY: "auto",
    marginTop: 2,
  },
  dropItem: {
    padding: "6px 10px",
    fontSize: 13,
    cursor: "pointer",
    color: "var(--text-primary)",
    whiteSpace: "nowrap",
    overflow: "hidden",
    textOverflow: "ellipsis",
  },
  dropEmpty: {
    padding: "8px 10px",
    fontSize: 12,
    color: "var(--text-muted)",
    fontStyle: "italic",
  },
  dropArrow: {
    position: "absolute",
    right: 8,
    top: "50%",
    transform: "translateY(-50%)",
    fontSize: 10,
    color: "var(--text-muted)",
    cursor: "pointer",
    userSelect: "none",
  },
  refreshBtn: {
    flexShrink: 0,
    padding: "0 10px",
    height: 32,
    background: "var(--elevated-bg)",
    border: "1px solid var(--input-border)",
    borderRadius: 6,
    cursor: "pointer",
    fontSize: 15,
    color: "var(--text-primary)",
  },
  toggle: {
    display: "flex",
    alignItems: "center",
    gap: 8,
    cursor: "pointer",
    userSelect: "none",
  },
};
