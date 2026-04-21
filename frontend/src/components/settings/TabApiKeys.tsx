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
 * TabApiKeys.tsx — Onglet « Mes clés API »
 *
 * Permet à chaque utilisateur de configurer ses propres clés API pour :
 *   - Albert (OpenAI-compatible : clé, base URL, modèle)
 *   - PISTE / Légifrance (client_id, client_secret)
 *   - PISTE / Judilibre (client_id, client_secret)
 *   - Grist (api_key, base_url)
 *   - IMAP/SMTP (host, user, password, etc.)
 *   - Embedding (api_base, model)
 *
 * Les valeurs ne sont jamais pré-remplies depuis le serveur (sécurité).
 * Un indicateur ✓ / ✗ montre si chaque clé est configurée.
 */

import React, { useState, useEffect, useCallback } from "react";
import { api } from "../../lib/api";

// ── Types ──────────────────────────────────────────────────────────────────

type ServiceStatus = Record<string, Record<string, boolean>>;

interface ServiceDef {
  id: string;
  label: string;
  icon: string;
  description: string;
  fields: { key: string; label: string; type?: string; placeholder?: string }[];
}

// ── Définition des services ────────────────────────────────────────────────

const SERVICES: ServiceDef[] = [
  {
    id: "albert",
    label: "Albert / LLM",
    icon: "🤖",
    description: "API OpenAI-compatible (Étalab Albert, OpenAI, etc.)",
    fields: [
      { key: "OPENAI_API_KEY",  label: "Clé API",    type: "password", placeholder: "sk-…" },
      { key: "OPENAI_API_BASE", label: "URL de base", placeholder: "https://albert.api.etalab.gouv.fr/v1" },
      { key: "OPENAI_MODEL",    label: "Modèle",      placeholder: "openai/gpt-oss-120b" },
    ],
  },
  {
    id: "legifrance",
    label: "Légifrance (PISTE)",
    icon: "⚖️",
    description: "Accès aux textes de loi via PISTE / DILA",
    fields: [
      { key: "LEGIFRANCE_CLIENT_ID",     label: "Client ID",     type: "password" },
      { key: "LEGIFRANCE_CLIENT_SECRET", label: "Client Secret", type: "password" },
      { key: "LEGIFRANCE_OAUTH_URL",     label: "OAuth URL",     placeholder: "https://oauth.piste.gouv.fr/api/oauth/token" },
      { key: "LEGIFRANCE_API_URL",       label: "API URL",       placeholder: "https://api.piste.gouv.fr/dila/legifrance/lf-engine-app" },
    ],
  },
  {
    id: "judilibre",
    label: "Judilibre (PISTE)",
    icon: "🏛️",
    description: "Accès aux décisions de justice via PISTE",
    fields: [
      { key: "JUDILIBRE_CLIENT_ID",     label: "Client ID",     type: "password" },
      { key: "JUDILIBRE_CLIENT_SECRET", label: "Client Secret", type: "password" },
    ],
  },
  {
    id: "grist",
    label: "Grist",
    icon: "📊",
    description: "Tableur collaboratif open-source",
    fields: [
      { key: "GRIST_API_KEY",  label: "Clé API",  type: "password" },
      { key: "GRIST_BASE_URL", label: "URL Grist", placeholder: "https://grist.numerique.gouv.fr" },
    ],
  },
  {
    id: "imap",
    label: "Messagerie IMAP",
    icon: "📧",
    description: "Lecture / envoi d'emails depuis l'agent",
    fields: [
      { key: "IMAP_HOST",     label: "Serveur IMAP",  placeholder: "imap.example.fr" },
      { key: "IMAP_PORT",     label: "Port IMAP",     placeholder: "993" },
      { key: "IMAP_USER",     label: "Utilisateur",   placeholder: "vous@example.fr" },
      { key: "IMAP_PASSWORD", label: "Mot de passe",  type: "password" },
      { key: "SMTP_HOST",     label: "Serveur SMTP",  placeholder: "smtp.example.fr" },
      { key: "SMTP_PORT",     label: "Port SMTP",     placeholder: "465" },
    ],
  },
  {
    id: "embedding",
    label: "Embeddings",
    icon: "🔢",
    description: "API d'embeddings (par défaut : même backend que Albert)",
    fields: [
      { key: "EMBEDDING_API_BASE", label: "URL de base", placeholder: "https://albert.api.etalab.gouv.fr/v1" },
      { key: "EMBEDDING_MODEL",    label: "Modèle",      placeholder: "BAAI/bge-m3" },
    ],
  },
];

// ── Composant ────────────────────────────────────────────────────────────────

export function TabApiKeys() {
  const [status, setStatus]       = useState<ServiceStatus>({});
  const [drafts, setDrafts]       = useState<Record<string, Record<string, string>>>({});
  const [plaintext, setPlaintext] = useState<Record<string, Record<string, string | null>>>({});
  const [saving, setSaving]       = useState<Record<string, boolean>>({});
  const [saved,  setSaved]        = useState<Record<string, boolean>>({});
  const [errors, setErrors]       = useState<Record<string, string>>({});
  const [loading, setLoading]     = useState(true);
  const [expanded, setExpanded]   = useState<string | null>(null);

  // Charger le statut initial
  useEffect(() => {
    Promise.all([
      api.get<ServiceStatus>("/auth/me/apikeys"),
      api.get<Record<string, Record<string, string | null>>>("/auth/me/apikeys/values"),
    ])
      .then(([s, v]) => { setStatus(s); setPlaintext(v); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);

  const toggleExpand = (id: string) =>
    setExpanded(e => e === id ? null : id);

  const setDraft = (service: string, key: string, value: string) => {
    setDrafts(d => ({
      ...d,
      [service]: { ...(d[service] ?? {}), [key]: value },
    }));
  };

  const handleSave = useCallback(async (serviceId: string) => {
    const draft = drafts[serviceId] ?? {};
    const keys = Object.entries(draft)
      .filter(([, v]) => v.trim() !== "")
      .map(([key_name, value]) => ({ key_name, value: value.trim() }));

    if (keys.length === 0) return;

    setSaving(s => ({ ...s, [serviceId]: true }));
    setErrors(e => ({ ...e, [serviceId]: "" }));
    try {
      await api.put("/auth/me/apikeys", { service: serviceId, keys });
      // Rafraîchir le statut et les valeurs en clair
      const [newStatus, newPlaintext] = await Promise.all([
        api.get<ServiceStatus>("/auth/me/apikeys"),
        api.get<Record<string, Record<string, string | null>>>("/auth/me/apikeys/values"),
      ]);
      setStatus(newStatus);
      setPlaintext(newPlaintext);
      setDrafts(d => ({ ...d, [serviceId]: {} }));
      setSaved(s => ({ ...s, [serviceId]: true }));
      setTimeout(() => setSaved(s => ({ ...s, [serviceId]: false })), 2500);
    } catch (e: any) {
      setErrors(err => ({ ...err, [serviceId]: e.message ?? "Erreur de sauvegarde." }));
    } finally {
      setSaving(s => ({ ...s, [serviceId]: false }));
    }
  }, [drafts]);

  if (loading) {
    return <div style={s.loading}>Chargement…</div>;
  }

  return (
    <div style={s.root}>
      <p style={s.intro}>
        Configurez vos propres clés API. Elles sont chiffrées et stockées
        séparément pour chaque utilisateur. Les valeurs existantes ne sont
        jamais affichées — saisissez une nouvelle valeur pour la remplacer.
      </p>

      {SERVICES.map(svc => {
        const svcStatus = status[svc.id] ?? {};
        const configuredCount = Object.values(svcStatus).filter(Boolean).length;
        const totalCount      = Object.values(svcStatus).length;
        const isExpanded      = expanded === svc.id;
        const allConfigured   = configuredCount === totalCount && totalCount > 0;

        return (
          <div key={svc.id} style={s.serviceCard}>
            {/* En-tête cliquable */}
            <button style={s.serviceHeader} onClick={() => toggleExpand(svc.id)}>
              <span style={s.serviceIcon}>{svc.icon}</span>
              <div style={s.serviceInfo}>
                <span style={s.serviceName}>{svc.label}</span>
                <span style={s.serviceDesc}>{svc.description}</span>
              </div>
              <div style={s.serviceRight}>
                <span style={{
                  ...s.badge,
                  ...(allConfigured ? s.badgeOk : configuredCount > 0 ? s.badgePartial : s.badgeNone),
                }}>
                  {configuredCount}/{totalCount}
                </span>
                <span style={s.chevron}>{isExpanded ? "▲" : "▼"}</span>
              </div>
            </button>

            {/* Formulaire dépliable */}
            {isExpanded && (
              <div style={s.serviceForm}>
                {svc.fields.map(field => {
                  const isSet      = svcStatus[field.key] === true;
                  const isSensitive = field.type === "password";
                  const savedValue = plaintext[svc.id]?.[field.key] ?? null;
                  // Placeholder : "••••••••" pour les secrets configurés, valeur réelle sinon
                  const placeholderText = isSensitive && isSet
                    ? "••••••••"
                    : (field.placeholder ?? "");
                  return (
                    <div key={field.key} style={s.row}>
                      <label style={s.fieldLabel}>
                        {field.label}
                        {isSet && <span style={s.checkmark}> ✓</span>}
                      </label>
                      <input
                        style={s.fieldInput}
                        type={field.type ?? "text"}
                        placeholder={placeholderText}
                        value={
                          drafts[svc.id]?.[field.key] !== undefined
                            ? drafts[svc.id][field.key]
                            : (!isSensitive && savedValue !== null ? savedValue : "")
                        }
                        onChange={e => setDraft(svc.id, field.key, e.target.value)}
                        autoComplete="off"
                      />
                    </div>
                  );
                })}

                {errors[svc.id] && (
                  <p style={s.error}>{errors[svc.id]}</p>
                )}

                <div style={s.actionRow}>
                  <button
                    style={{
                      ...s.saveBtn,
                      ...(saving[svc.id] ? s.saveBtnDisabled : {}),
                    }}
                    onClick={() => handleSave(svc.id)}
                    disabled={saving[svc.id]}
                  >
                    {saved[svc.id]
                      ? "✓ Enregistré"
                      : saving[svc.id]
                        ? "Enregistrement…"
                        : "Enregistrer"}
                  </button>
                </div>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

// ── Styles ────────────────────────────────────────────────────────────────────

const s: Record<string, React.CSSProperties> = {
  root: {
    display: "flex",
    flexDirection: "column",
    gap: 10,
    padding: "4px 0",
  },
  loading: {
    padding: 20,
    color: "var(--text-muted)",
    fontSize: 13,
    textAlign: "center",
  },
  intro: {
    margin: "0 0 8px",
    fontSize: 12,
    color: "var(--text-muted)",
    lineHeight: 1.6,
  },
  serviceCard: {
    border: "1px solid var(--border)",
    borderRadius: 8,
    overflow: "hidden",
  },
  serviceHeader: {
    width: "100%",
    display: "flex",
    alignItems: "center",
    gap: 10,
    padding: "10px 14px",
    background: "var(--elevated-bg)",
    border: "none",
    cursor: "pointer",
    textAlign: "left",
    color: "var(--text-primary)",
  },
  serviceIcon: {
    fontSize: 18,
    lineHeight: 1,
    flexShrink: 0,
  },
  serviceInfo: {
    flex: 1,
    display: "flex",
    flexDirection: "column",
    gap: 2,
  },
  serviceName: {
    fontSize: 13,
    fontWeight: 500,
    color: "var(--text-primary)",
  },
  serviceDesc: {
    fontSize: 11,
    color: "var(--text-muted)",
  },
  serviceRight: {
    display: "flex",
    alignItems: "center",
    gap: 8,
    flexShrink: 0,
  },
  badge: {
    fontSize: 11,
    fontWeight: 600,
    padding: "2px 8px",
    borderRadius: 10,
  },
  badgeOk: {
    background: "rgba(80,180,100,0.15)",
    color: "#5ab467",
  },
  badgePartial: {
    background: "rgba(212,129,61,0.15)",
    color: "var(--accent)",
  },
  badgeNone: {
    background: "var(--elevated-bg)",
    color: "var(--text-disabled)",
  },
  chevron: {
    fontSize: 10,
    color: "var(--text-muted)",
  },
  serviceForm: {
    padding: "14px 16px",
    background: "var(--surface-bg)",
    borderTop: "1px solid var(--border)",
    display: "flex",
    flexDirection: "column",
    gap: 10,
  },
  row: {
    display: "flex",
    flexDirection: "column",
    gap: 4,
  },
  fieldLabel: {
    fontSize: 11,
    color: "var(--text-secondary)",
    fontWeight: 500,
  },
  checkmark: {
    color: "#5ab467",
    fontWeight: 600,
  },
  fieldInput: {
    padding: "7px 10px",
    background: "var(--input-bg)",
    border: "1px solid var(--input-border)",
    borderRadius: 6,
    color: "var(--input-color)",
    fontSize: 13,
    outline: "none",
  },
  error: {
    margin: 0,
    fontSize: 11,
    color: "#e07878",
    padding: "6px 8px",
    background: "rgba(220,80,80,0.08)",
    borderRadius: 5,
    border: "1px solid rgba(220,80,80,0.2)",
  },
  actionRow: {
    display: "flex",
    justifyContent: "flex-end",
    paddingTop: 4,
  },
  saveBtn: {
    padding: "7px 18px",
    background: "var(--accent)",
    color: "#fff",
    border: "none",
    borderRadius: 6,
    fontSize: 13,
    fontWeight: 500,
    cursor: "pointer",
  },
  saveBtnDisabled: {
    opacity: 0.6,
    cursor: "not-allowed",
  },
};
