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
 * AdminPanel.tsx — Panneau de gestion des utilisateurs (admin only)
 *
 * Fonctionnalités :
 *   - Lister tous les utilisateurs
 *   - Créer un compte (utilisateur ou admin)
 *   - Réinitialiser le mot de passe
 *   - Accorder / révoquer les droits admin
 *   - Supprimer un compte
 *   - Afficher / modifier le quota VFS par utilisateur
 */

import React, { useState, useEffect, useCallback } from "react";
import { api } from "../../lib/api";

// ── Types ──────────────────────────────────────────────────────────────────

interface AdminUser {
  id: string;
  username: string;
  email: string;
  is_admin: boolean;
  created_at: string;
  vfs_quota_bytes: number;
}

interface VfsUsage {
  total_bytes: number;
  total_files: number;
  total_size: string;
  quota_limit_bytes: number;
  quota_limit: string;
  quota_used_pct: number;
  quota_exceeded: boolean;
}

interface Props {
  open: boolean;
  onClose: () => void;
  currentUserId: string;
}

type Modal =
  | { type: "create" }
  | { type: "reset"; user: AdminUser }
  | { type: "delete"; user: AdminUser }
  | { type: "quota"; user: AdminUser }
  | null;

// ── Helpers ────────────────────────────────────────────────────────────────

function fmtDate(iso: string) {
  try {
    return new Date(iso).toLocaleDateString("fr-FR", {
      day: "2-digit", month: "short", year: "numeric",
    });
  } catch {
    return iso;
  }
}

function fmtBytes(bytes: number): string {
  if (bytes === 0) return "0 o";
  const units = ["o", "Ko", "Mo", "Go", "To"];
  let v = bytes;
  let i = 0;
  while (v >= 1024 && i < units.length - 1) { v /= 1024; i++; }
  return `${v.toFixed(1)} ${units[i]}`;
}

function bytesFromInput(value: number, unit: "Mo" | "Go"): number {
  return unit === "Go" ? value * 1024 * 1024 * 1024 : value * 1024 * 1024;
}

// ── Barre de quota ─────────────────────────────────────────────────────────

function QuotaBar({ used, limit, pct }: { used: number; limit: number; pct: number }) {
  const color = pct >= 90 ? "#e07878" : pct >= 70 ? "#d4a03d" : "#5aaa7a";
  return (
    <div style={{ width: "100%", minWidth: 100 }}>
      <div style={{ height: 4, background: "rgba(255,255,255,0.07)", borderRadius: 3, overflow: "hidden" }}>
        <div style={{ height: "100%", width: `${Math.min(pct, 100)}%`, background: color, borderRadius: 3, transition: "width 0.3s" }} />
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", marginTop: 3, fontSize: 10, color: "var(--text-muted)" }}>
        <span style={{ color: pct >= 90 ? "#e07878" : "var(--text-muted)" }}>{fmtBytes(used)}</span>
        <span>{fmtBytes(limit)}</span>
      </div>
    </div>
  );
}

// ── Modal création ──────────────────────────────────────────────────────────

function CreateUserModal({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [isAdmin, setIsAdmin] = useState(false);
  const [quotaValue, setQuotaValue] = useState(500);
  const [quotaUnit, setQuotaUnit] = useState<"Mo" | "Go">("Mo");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await api.post("/admin/users", {
        username, email, password, is_admin: isAdmin,
        vfs_quota_bytes: bytesFromInput(quotaValue, quotaUnit),
      });
      onCreated();
      onClose();
    } catch (err: any) {
      setError(err.message ?? "Erreur lors de la création.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={s.overlay} onClick={onClose}>
      <div style={s.modal} onClick={e => e.stopPropagation()}>
        <h3 style={s.modalTitle}>Créer un utilisateur</h3>
        <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div style={s.formGroup}>
            <label style={s.label}>Identifiant</label>
            <input style={s.input} value={username} onChange={e => setUsername(e.target.value)}
              placeholder="nom_utilisateur" required minLength={3} maxLength={40} autoFocus />
          </div>
          <div style={s.formGroup}>
            <label style={s.label}>Email</label>
            <input style={s.input} type="email" value={email} onChange={e => setEmail(e.target.value)}
              placeholder="utilisateur@domaine.fr" required />
          </div>
          <div style={s.formGroup}>
            <label style={s.label}>Mot de passe</label>
            <input style={s.input} type="password" value={password} onChange={e => setPassword(e.target.value)}
              placeholder="Au moins 8 caractères" required minLength={8} />
          </div>
          <div style={s.formGroup}>
            <label style={s.label}>Quota VFS</label>
            <div style={{ display: "flex", gap: 6 }}>
              <input
                style={{ ...s.input, flex: 1 }}
                type="number" min={1} max={99999}
                value={quotaValue}
                onChange={e => setQuotaValue(Math.max(1, parseInt(e.target.value) || 1))}
              />
              <select
                value={quotaUnit}
                onChange={e => setQuotaUnit(e.target.value as "Mo" | "Go")}
                style={{ ...s.input, width: 70, cursor: "pointer" }}
              >
                <option value="Mo">Mo</option>
                <option value="Go">Go</option>
              </select>
            </div>
          </div>
          <label style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer", fontSize: 13, color: "var(--text-secondary)" }}>
            <input type="checkbox" checked={isAdmin} onChange={e => setIsAdmin(e.target.checked)}
              style={{ accentColor: "var(--accent)", width: 14, height: 14 }} />
            Compte administrateur
          </label>
          {error && <p style={s.errorMsg}>{error}</p>}
          <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 4 }}>
            <button type="button" onClick={onClose} style={s.btnSecondary}>Annuler</button>
            <button type="submit" disabled={loading} style={s.btnPrimary}>
              {loading ? "Création…" : "Créer"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ── Modal reset mdp ─────────────────────────────────────────────────────────

function ResetPasswordModal({ user, onClose, onDone }: { user: AdminUser; onClose: () => void; onDone: () => void }) {
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await api.post(`/admin/users/${user.id}/reset-password`, { new_password: password });
      onDone();
      onClose();
    } catch (err: any) {
      setError(err.message ?? "Erreur lors de la réinitialisation.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={s.overlay} onClick={onClose}>
      <div style={s.modal} onClick={e => e.stopPropagation()}>
        <h3 style={s.modalTitle}>Réinitialiser le mot de passe</h3>
        <p style={{ margin: "0 0 12px", fontSize: 13, color: "var(--text-secondary)" }}>
          Utilisateur : <strong style={{ color: "var(--text-primary)" }}>{user.username}</strong>
        </p>
        <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div style={s.formGroup}>
            <label style={s.label}>Nouveau mot de passe</label>
            <input style={s.input} type="password" value={password} onChange={e => setPassword(e.target.value)}
              placeholder="Au moins 8 caractères" required minLength={8} autoFocus />
          </div>
          {error && <p style={s.errorMsg}>{error}</p>}
          <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
            <button type="button" onClick={onClose} style={s.btnSecondary}>Annuler</button>
            <button type="submit" disabled={loading} style={s.btnPrimary}>
              {loading ? "Enregistrement…" : "Réinitialiser"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ── Modal suppression ───────────────────────────────────────────────────────

function DeleteUserModal({ user, onClose, onDeleted }: { user: AdminUser; onClose: () => void; onDeleted: () => void }) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleDelete() {
    setLoading(true);
    setError(null);
    try {
      await api.delete(`/admin/users/${user.id}`);
      onDeleted();
      onClose();
    } catch (err: any) {
      setError(err.message ?? "Erreur lors de la suppression.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={s.overlay} onClick={onClose}>
      <div style={s.modal} onClick={e => e.stopPropagation()}>
        <h3 style={{ ...s.modalTitle, color: "#e07878" }}>Supprimer l'utilisateur</h3>
        <p style={{ margin: "0 0 8px", fontSize: 13, color: "var(--text-secondary)" }}>
          Vous allez supprimer le compte <strong style={{ color: "var(--text-primary)" }}>{user.username}</strong> ({user.email}).
        </p>
        <p style={{ margin: "0 0 16px", fontSize: 12, color: "#e07878" }}>
          ⚠ Cette action est irréversible. Toutes les données de l'utilisateur seront supprimées.
        </p>
        {error && <p style={s.errorMsg}>{error}</p>}
        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
          <button onClick={onClose} style={s.btnSecondary}>Annuler</button>
          <button onClick={handleDelete} disabled={loading} style={{ ...s.btnPrimary, background: "#c0392b" }}>
            {loading ? "Suppression…" : "Supprimer"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Modal quota VFS ─────────────────────────────────────────────────────────

function SetQuotaModal({
  user,
  usage,
  onClose,
  onSaved,
}: {
  user: AdminUser;
  usage: VfsUsage | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  // Initialise depuis le quota actuel
  const initBytes = user.vfs_quota_bytes ?? 500 * 1024 * 1024;
  const initGo = initBytes >= 1024 * 1024 * 1024;
  const initValue = initGo
    ? Math.round(initBytes / (1024 * 1024 * 1024))
    : Math.round(initBytes / (1024 * 1024));

  const [quotaValue, setQuotaValue] = useState(initValue);
  const [quotaUnit, setQuotaUnit] = useState<"Mo" | "Go">(initGo ? "Go" : "Mo");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const newBytes = bytesFromInput(quotaValue, quotaUnit);
  const wouldExceed = usage ? newBytes < usage.total_bytes : false;

  async function handleSave() {
    setError(null);
    setLoading(true);
    try {
      await api.patch(`/admin/users/${user.id}/vfs-quota`, { quota_bytes: newBytes });
      onSaved();
      onClose();
    } catch (err: any) {
      setError(err.message ?? "Erreur lors de la mise à jour du quota.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={s.overlay} onClick={onClose}>
      <div style={s.modal} onClick={e => e.stopPropagation()}>
        <h3 style={s.modalTitle}>💾 Quota VFS — {user.username}</h3>

        {/* Utilisation actuelle */}
        {usage && (
          <div style={{ marginBottom: 16, padding: "10px 14px", background: "rgba(255,255,255,0.04)", borderRadius: 8, border: "1px solid var(--border)" }}>
            <div style={{ fontSize: 11, color: "var(--text-muted)", marginBottom: 6, textTransform: "uppercase", letterSpacing: "0.07em", fontWeight: 600 }}>
              Utilisation actuelle
            </div>
            <QuotaBar used={usage.total_bytes} limit={usage.quota_limit_bytes} pct={usage.quota_used_pct} />
            <div style={{ marginTop: 6, fontSize: 12, color: "var(--text-secondary)" }}>
              {usage.total_files} fichier{usage.total_files !== 1 ? "s" : ""} · {usage.total_size} utilisés sur {usage.quota_limit}
              {usage.quota_exceeded && (
                <span style={{ marginLeft: 8, color: "#e07878", fontWeight: 600 }}>⚠ Quota dépassé</span>
              )}
            </div>
          </div>
        )}

        {/* Nouveau quota */}
        <div style={s.formGroup}>
          <label style={s.label}>Nouveau quota</label>
          <div style={{ display: "flex", gap: 6 }}>
            <input
              style={{ ...s.input, flex: 1 }}
              type="number" min={1} max={99999}
              value={quotaValue}
              onChange={e => setQuotaValue(Math.max(1, parseInt(e.target.value) || 1))}
              autoFocus
            />
            <select
              value={quotaUnit}
              onChange={e => setQuotaUnit(e.target.value as "Mo" | "Go")}
              style={{ ...s.input, width: 70, cursor: "pointer" }}
            >
              <option value="Mo">Mo</option>
              <option value="Go">Go</option>
            </select>
          </div>
          <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 4 }}>
            = {fmtBytes(newBytes)}
          </div>
        </div>

        {wouldExceed && (
          <p style={{ margin: "8px 0 0", fontSize: 12, color: "#d4a03d" }}>
            ⚠ Le nouveau quota est inférieur à l'utilisation actuelle ({usage?.total_size}).
            Les fichiers existants ne seront pas supprimés mais l'utilisateur ne pourra plus écrire.
          </p>
        )}

        {error && <p style={{ ...s.errorMsg, marginTop: 8 }}>{error}</p>}

        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 16 }}>
          <button onClick={onClose} style={s.btnSecondary}>Annuler</button>
          <button onClick={handleSave} disabled={loading} style={s.btnPrimary}>
            {loading ? "Enregistrement…" : "Appliquer"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Composant principal ────────────────────────────────────────────────────

export function AdminPanel({ open, onClose, currentUserId }: Props) {
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [usages, setUsages] = useState<Record<string, VfsUsage>>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [modal, setModal] = useState<Modal>(null);
  const [toastMsg, setToastMsg] = useState<string | null>(null);

  const showToast = (msg: string) => {
    setToastMsg(msg);
    setTimeout(() => setToastMsg(null), 3000);
  };

  const fetchUsers = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.get<AdminUser[]>("/admin/users");
      setUsers(data);
      // Charger les usages VFS en parallèle (non-bloquant)
      const entries = await Promise.allSettled(
        data.filter(u => !u.is_admin).map(u =>
          api.get<VfsUsage>(`/admin/users/${u.id}/vfs-usage`)
            .then(usage => ({ id: u.id, usage }))
        )
      );
      const map: Record<string, VfsUsage> = {};
      entries.forEach(r => {
        if (r.status === "fulfilled") map[r.value.id] = r.value.usage;
      });
      setUsages(map);
    } catch (err: any) {
      setError(err.message ?? "Impossible de charger les utilisateurs.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (open) fetchUsers();
  }, [open, fetchUsers]);

  async function toggleAdmin(user: AdminUser) {
    const newVal = !user.is_admin;
    try {
      await api.patch(`/admin/users/${user.id}/admin`, { is_admin: newVal });
      showToast(`${user.username} est ${newVal ? "maintenant admin" : "repassé utilisateur"}.`);
      fetchUsers();
    } catch (err: any) {
      setError(err.message ?? "Erreur lors de la mise à jour.");
    }
  }

  if (!open) return null;

  return (
    <div style={s.backdrop} onClick={onClose}>
      <div style={s.panel} onClick={e => e.stopPropagation()}>

        {/* Header */}
        <div style={s.header}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <span style={{ fontSize: 18 }}>🛡</span>
            <h2 style={s.title}>Administration</h2>
          </div>
          <button onClick={onClose} style={s.closeBtn} title="Fermer">✕</button>
        </div>

        {/* Actions */}
        <div style={s.toolbar}>
          <span style={{ fontSize: 13, color: "var(--text-secondary)" }}>
            {users.length} compte{users.length !== 1 ? "s" : ""}
          </span>
          <button onClick={() => setModal({ type: "create" })} style={s.btnPrimary}>
            + Nouvel utilisateur
          </button>
        </div>

        {/* Erreur globale */}
        {error && (
          <div style={s.errorBanner}>
            <span>⚠</span> {error}
          </div>
        )}

        {/* Liste */}
        <div style={s.tableWrap}>
          {loading ? (
            <div style={s.emptyState}>Chargement…</div>
          ) : users.length === 0 ? (
            <div style={s.emptyState}>Aucun utilisateur trouvé.</div>
          ) : (
            <table style={s.table}>
              <thead>
                <tr>
                  {["Utilisateur", "Email", "Rôle", "Stockage VFS", "Créé le", "Actions"].map(h => (
                    <th key={h} style={s.th}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {users.map(u => {
                  const usage = usages[u.id];
                  return (
                    <tr key={u.id} style={s.tr}>
                      <td style={s.td}>
                        <span style={{ fontWeight: 600, color: "var(--text-primary)" }}>{u.username}</span>
                        {u.id === currentUserId && (
                          <span style={s.meBadge}>vous</span>
                        )}
                      </td>
                      <td style={{ ...s.td, color: "var(--text-secondary)", fontSize: 12 }}>{u.email}</td>
                      <td style={s.td}>
                        <span style={u.is_admin ? s.badgeAdmin : s.badgeUser}>
                          {u.is_admin ? "🛡 Admin" : "👤 Utilisateur"}
                        </span>
                      </td>

                      {/* Colonne Stockage VFS */}
                      <td style={{ ...s.td, minWidth: 160 }}>
                        {u.is_admin ? (
                          <span style={{ fontSize: 11, color: "var(--text-muted)" }}>—</span>
                        ) : usage ? (
                          <QuotaBar
                            used={usage.total_bytes}
                            limit={usage.quota_limit_bytes}
                            pct={usage.quota_used_pct}
                          />
                        ) : (
                          <div style={{ fontSize: 11, color: "var(--text-muted)" }}>
                            <span>— / {fmtBytes(u.vfs_quota_bytes)}</span>
                          </div>
                        )}
                      </td>

                      <td style={{ ...s.td, color: "var(--text-secondary)", fontSize: 12 }}>
                        {fmtDate(u.created_at)}
                      </td>
                      <td style={s.td}>
                        <div style={{ display: "flex", gap: 6 }}>
                          {/* Toggle admin */}
                          <button
                            onClick={() => toggleAdmin(u)}
                            disabled={u.id === currentUserId && u.is_admin}
                            style={s.btnAction}
                            title={u.is_admin ? "Révoquer les droits admin" : "Accorder les droits admin"}
                          >
                            {u.is_admin ? "↓ User" : "↑ Admin"}
                          </button>
                          {/* Reset mdp */}
                          <button
                            onClick={() => setModal({ type: "reset", user: u })}
                            style={s.btnAction}
                            title="Réinitialiser le mot de passe"
                          >
                            🔑
                          </button>
                          {/* Quota VFS (non-admin seulement) */}
                          {!u.is_admin && (
                            <button
                              onClick={() => setModal({ type: "quota", user: u })}
                              style={s.btnAction}
                              title="Modifier le quota VFS"
                            >
                              💾
                            </button>
                          )}
                          {/* Supprimer */}
                          <button
                            onClick={() => setModal({ type: "delete", user: u })}
                            disabled={u.id === currentUserId}
                            style={{ ...s.btnAction, color: "#e07878" }}
                            title={u.id === currentUserId ? "Vous ne pouvez pas vous supprimer" : "Supprimer"}
                          >
                            🗑
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>

        {/* Toast */}
        {toastMsg && (
          <div style={s.toast}>{toastMsg}</div>
        )}
      </div>

      {/* Modals */}
      {modal?.type === "create" && (
        <CreateUserModal
          onClose={() => setModal(null)}
          onCreated={() => { fetchUsers(); showToast("Compte créé avec succès."); }}
        />
      )}
      {modal?.type === "reset" && (
        <ResetPasswordModal
          user={modal.user}
          onClose={() => setModal(null)}
          onDone={() => showToast("Mot de passe réinitialisé.")}
        />
      )}
      {modal?.type === "delete" && (
        <DeleteUserModal
          user={modal.user}
          onClose={() => setModal(null)}
          onDeleted={() => { fetchUsers(); showToast("Compte supprimé."); }}
        />
      )}
      {modal?.type === "quota" && (
        <SetQuotaModal
          user={modal.user}
          usage={usages[modal.user.id] ?? null}
          onClose={() => setModal(null)}
          onSaved={() => { fetchUsers(); showToast(`Quota de ${modal.user.username} mis à jour.`); }}
        />
      )}
    </div>
  );
}

// ── Styles ─────────────────────────────────────────────────────────────────

const s: Record<string, React.CSSProperties> = {
  backdrop: {
    position: "fixed", inset: 0, zIndex: 1000,
    background: "rgba(0,0,0,0.55)", backdropFilter: "blur(4px)",
    display: "flex", alignItems: "center", justifyContent: "center",
  },
  panel: {
    background: "var(--surface-bg)",
    border: "1px solid var(--border)",
    borderRadius: 14,
    width: "min(1000px, 96vw)",
    maxHeight: "85vh",
    display: "flex", flexDirection: "column",
    overflow: "hidden",
    boxShadow: "0 24px 64px rgba(0,0,0,0.5)",
  },
  header: {
    display: "flex", alignItems: "center", justifyContent: "space-between",
    padding: "18px 24px 14px",
    borderBottom: "1px solid var(--border)",
  },
  title: {
    margin: 0, fontSize: 18, fontWeight: 700, color: "var(--text-primary)",
  },
  closeBtn: {
    background: "none", border: "none", color: "var(--text-muted)",
    fontSize: 16, cursor: "pointer", padding: "4px 8px", borderRadius: 6,
  },
  toolbar: {
    display: "flex", alignItems: "center", justifyContent: "space-between",
    padding: "12px 24px",
    borderBottom: "1px solid var(--border)",
  },
  tableWrap: {
    flex: 1, overflowY: "auto", padding: "0 0 12px",
  },
  table: {
    width: "100%", borderCollapse: "collapse",
  },
  th: {
    padding: "10px 16px", textAlign: "left",
    fontSize: 11, fontWeight: 600, letterSpacing: "0.07em",
    color: "var(--text-muted)", textTransform: "uppercase",
    borderBottom: "1px solid var(--border)",
    position: "sticky", top: 0, background: "var(--surface-bg)",
  },
  tr: {
    borderBottom: "1px solid var(--border-subtle, rgba(255,255,255,0.04))",
  },
  td: {
    padding: "10px 16px", fontSize: 13,
    color: "var(--text-secondary)",
    verticalAlign: "middle",
  },
  meBadge: {
    marginLeft: 6, fontSize: 10, padding: "1px 6px",
    background: "rgba(122,175,212,0.15)", color: "#7aafd4",
    borderRadius: 10, fontWeight: 600,
  },
  badgeAdmin: {
    display: "inline-block", padding: "2px 10px", borderRadius: 10, fontSize: 11,
    background: "rgba(212,129,61,0.15)", color: "#d4813d", fontWeight: 600,
  },
  badgeUser: {
    display: "inline-block", padding: "2px 10px", borderRadius: 10, fontSize: 11,
    background: "rgba(255,255,255,0.06)", color: "var(--text-muted)", fontWeight: 500,
  },
  btnAction: {
    background: "rgba(255,255,255,0.05)", border: "1px solid var(--border)",
    borderRadius: 6, color: "var(--text-secondary)",
    fontSize: 11, padding: "3px 8px", cursor: "pointer",
  },
  btnPrimary: {
    background: "var(--accent, #d4813d)", color: "#fff",
    border: "none", borderRadius: 7, padding: "7px 16px",
    fontSize: 13, fontWeight: 600, cursor: "pointer",
  },
  btnSecondary: {
    background: "rgba(255,255,255,0.06)", color: "var(--text-secondary)",
    border: "1px solid var(--border)", borderRadius: 7, padding: "7px 16px",
    fontSize: 13, cursor: "pointer",
  },
  emptyState: {
    padding: 40, textAlign: "center", color: "var(--text-muted)", fontSize: 13,
  },
  errorBanner: {
    margin: "0 24px 0", padding: "10px 14px", borderRadius: 8,
    background: "rgba(200,60,60,0.08)", border: "1px solid rgba(200,60,60,0.2)",
    color: "#e07878", fontSize: 13, display: "flex", gap: 8,
  },
  errorMsg: {
    margin: 0, fontSize: 12, color: "#e07878",
  },
  toast: {
    position: "absolute", bottom: 20, left: "50%", transform: "translateX(-50%)",
    background: "var(--surface-bg)", border: "1px solid var(--border)",
    borderRadius: 8, padding: "8px 18px", fontSize: 13,
    color: "var(--text-primary)", boxShadow: "0 4px 16px rgba(0,0,0,0.3)",
    whiteSpace: "nowrap",
  },
  // Modals
  overlay: {
    position: "fixed", inset: 0, zIndex: 1100,
    background: "rgba(0,0,0,0.5)",
    display: "flex", alignItems: "center", justifyContent: "center",
  },
  modal: {
    background: "var(--surface-bg)", border: "1px solid var(--border)",
    borderRadius: 12, padding: "24px 28px", width: "min(440px, 92vw)",
    boxShadow: "0 16px 48px rgba(0,0,0,0.5)",
  },
  modalTitle: {
    margin: "0 0 16px", fontSize: 16, fontWeight: 700, color: "var(--text-primary)",
  },
  formGroup: {
    display: "flex", flexDirection: "column", gap: 5,
  },
  label: {
    fontSize: 11, fontWeight: 600, color: "var(--text-muted)",
    letterSpacing: "0.07em", textTransform: "uppercase",
  },
  input: {
    padding: "9px 12px", background: "var(--input-bg, rgba(255,255,255,0.05))",
    border: "1px solid var(--input-border, rgba(255,255,255,0.12))",
    borderRadius: 7, color: "var(--input-color, #e4e2ec)", fontSize: 13, outline: "none",
  },
};
