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
 * ProfilesPanel.tsx — Panneau latéral Profils & Skills
 *
 * Affiché dans la sidebar (panneau flottant) quand l'utilisateur clique
 * sur l'icône Profils dans le rail.
 *
 * Fonctionnalités :
 *   ─ Liste des profils avec sélection du profil actif
 *   ─ Créer / Éditer / Supprimer un profil
 *   ─ Gérer les skills (créer / éditer / supprimer)
 */

import React, { useState, useEffect, useRef } from "react";
import { api } from "../../lib/api";

// ── Types ────────────────────────────────────────────────────────────────────

export interface Profile {
  name: string;
  prompt: string;
  tool_families?: { enabled: string[]; disabled: string[] };
  pinned_skills?: string[];
  is_personal?: boolean;
}

export interface Skill {
  slug: string;
  name: string;
  description?: string;
  tags?: string[];
  version?: string;
  size?: number;
}

interface ToolFamily {
  family: string;
  label: string;
  icon: string;
  enabled: boolean;
}

export interface ProfilesPanelProps {
  currentProfile: Profile | null;
  onProfileChange: (profile: Profile | null) => void;
  onClose: () => void;
  embedded?: boolean;
  isAdmin?: boolean;
}

// ── Composant principal ───────────────────────────────────────────────────────

export function ProfilesPanel({
  currentProfile,
  onProfileChange,
  onClose,
  embedded = false,
  isAdmin = false,
}: ProfilesPanelProps) {
  const [tab, setTab] = useState<"profiles" | "skills">("profiles");
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [personalProfiles, setPersonalProfiles] = useState<Profile[]>([]);
  const [showProfileEditor, setShowProfileEditor] = useState(false);
  const [editingProfile, setEditingProfile] = useState<Profile | null>(null);
  const [editingPersonal, setEditingPersonal] = useState(false);

  useEffect(() => {
    fetchProfiles();
    fetchPersonalProfiles();
  }, []);

  async function fetchProfiles() {
    try {
      const data = await api.get<Profile[]>("/profiles");
      setProfiles(data);
      if (!currentProfile && data.length > 0) {
        const noRole = data.find((p) => p.name === "Aucun rôle") ?? data[0];
        onProfileChange(noRole);
      }
    } catch {}
  }

  async function fetchPersonalProfiles() {
    try {
      const data = await api.get<Profile[]>("/personal-profiles");
      setPersonalProfiles(data.map((p) => ({ ...p, is_personal: true })));
    } catch {}
  }

  async function handleProfileSave(profile: Profile, isNew: boolean, isPersonal: boolean) {
    try {
      const base = isPersonal ? "/personal-profiles" : "/profiles";
      if (isNew) {
        await api.post(base, profile);
        if (isPersonal) await fetchPersonalProfiles();
        else await fetchProfiles();
      } else {
        await api.patch(`${base}/${encodeURIComponent(profile.name)}`, {
          prompt: profile.prompt,
          tool_families: profile.tool_families,
          pinned_skills: profile.pinned_skills,
        });
        if (isPersonal) await fetchPersonalProfiles();
        else await fetchProfiles();
      }
      // Correction : récupérer le profil complet depuis l'API après sauvegarde
      // pour garantir que onProfileChange reçoit un objet frais avec les
      // tool_families à jour, évitant que ToolsPanel calcule ses overrides
      // depuis un objet stale (référence ancienne avant PATCH).
      try {
        const freshBase = isPersonal ? "/personal-profiles" : "/profiles";
        const fresh = await api.get<Profile>(`${freshBase}/${encodeURIComponent(profile.name)}`);
        onProfileChange({ ...fresh, is_personal: isPersonal });
      } catch {
        // Fallback : utiliser l'objet local si le refetch échoue
        onProfileChange({ ...profile, is_personal: isPersonal });
      }
    } catch {}
    setShowProfileEditor(false);
    setEditingProfile(null);
  }

  async function handleProfileDelete(name: string, isPersonal: boolean) {
    if (!window.confirm(`Supprimer le profil "${name}" ?`)) return;
    try {
      const base = isPersonal ? "/personal-profiles" : "/profiles";
      await api.delete(`${base}/${encodeURIComponent(name)}`);
      if (isPersonal) await fetchPersonalProfiles();
      else await fetchProfiles();
      const noRole = profiles.find((p) => p.name === "Aucun rôle");
      onProfileChange(noRole ?? null);
    } catch {}
  }

  return (
    <div style={p.root}>
      {/* En-tête */}
      <div style={p.header}>
        <span style={p.title}>Profils & Skills</span>
        {embedded && (
          <button style={p.closeBtn} onClick={onClose} title="Fermer">×</button>
        )}
      </div>

      {/* Onglets */}
      <div style={p.tabs}>
        <button
          style={{ ...p.tab, ...(tab === "profiles" ? p.tabActive : {}) }}
          onClick={() => setTab("profiles")}
        >
          👤 Profils
        </button>
        <button
          style={{ ...p.tab, ...(tab === "skills" ? p.tabActive : {}) }}
          onClick={() => setTab("skills")}
        >
          📚 Skills
        </button>
      </div>

      {/* Contenu */}
      {tab === "profiles" && (
        <ProfilesTab
          profiles={profiles}
          personalProfiles={personalProfiles}
          currentProfile={currentProfile}
          onSelect={(profile) => { onProfileChange(profile); }}
          onEdit={(profile, isPersonal) => { setEditingProfile(profile); setEditingPersonal(isPersonal); setShowProfileEditor(true); }}
          onDelete={handleProfileDelete}
          onNew={(isPersonal) => { setEditingProfile(null); setEditingPersonal(isPersonal); setShowProfileEditor(true); }}
          isAdmin={isAdmin}
        />
      )}

      {tab === "skills" && (
        <SkillsTab onRefreshNeeded={fetchProfiles} isAdmin={isAdmin} />
      )}

      {/* Modal éditeur de profil */}
      {showProfileEditor && (
        <ProfileEditorModal
          profile={editingProfile}
          isPersonal={editingPersonal}
          onSave={handleProfileSave}
          onClose={() => { setShowProfileEditor(false); setEditingProfile(null); }}
        />
      )}
    </div>
  );
}

// ── Onglet Profils ────────────────────────────────────────────────────────────

function ProfilesTab({
  profiles, personalProfiles, currentProfile, onSelect, onEdit, onDelete, onNew, isAdmin,
}: {
  profiles: Profile[];
  personalProfiles: Profile[];
  currentProfile: Profile | null;
  onSelect: (p: Profile) => void;
  onEdit: (p: Profile, isPersonal: boolean) => void;
  onDelete: (name: string, isPersonal: boolean) => void;
  onNew: (isPersonal: boolean) => void;
  isAdmin: boolean;
}) {
  return (
    <div style={p.tabContent}>
      {/* Boutons d'ajout */}
      <div style={{ display: "flex", gap: 6, margin: "10px 10px 4px", flexShrink: 0 }}>
        {isAdmin && (
          <button style={{ ...p.newBtn, margin: 0, flex: 1 }} onClick={() => onNew(false)}>
            ➕ Ajouter un profil système
          </button>
        )}
        <button style={{ ...p.newBtn, margin: 0, flex: 1 }} onClick={() => onNew(true)}>
          ➕ Ajouter un profil personnel
        </button>
      </div>

      {/* Profils personnels */}
      {personalProfiles.length > 0 && (
        <>
          <div style={p.sectionLabel}>Mes profils personnels</div>
          <div style={p.profileList}>
            {personalProfiles.map((prof) => {
              const isActive = !!(currentProfile?.name === prof.name && currentProfile?.is_personal);
              return (
                <ProfileItem
                  key={`personal:${prof.name}`}
                  prof={prof}
                  isActive={isActive}
                  canEdit={true}
                  onSelect={() => onSelect(prof)}
                  onEdit={() => onEdit(prof, true)}
                  onDelete={() => onDelete(prof.name, true)}
                  badge="personnel"
                />
              );
            })}
          </div>
        </>
      )}

      {/* Séparateur si les deux sections sont présentes */}
      {personalProfiles.length > 0 && profiles.length > 0 && (
        <div style={p.sectionLabel}>Profils système</div>
      )}

      {/* Profils système */}
      <div style={p.profileList}>
        {profiles.length === 0 && (
          <div style={p.empty}>Aucun profil disponible.</div>
        )}
        {profiles.map((prof) => {
          const isActive = !!(currentProfile?.name === prof.name && !currentProfile?.is_personal);
          const isDefault = prof.name === "Aucun rôle";
          return (
            <ProfileItem
              key={`system:${prof.name}`}
              prof={prof}
              isActive={isActive}
              canEdit={isAdmin && !isDefault}
              onSelect={() => onSelect(prof)}
              onEdit={() => onEdit(prof, false)}
              onDelete={() => onDelete(prof.name, false)}
            />
          );
        })}
      </div>

      {currentProfile && currentProfile.prompt && (
        <div style={p.promptPreview}>
          <div style={p.promptPreviewLabel}>Prompt actif :</div>
          <div style={p.promptPreviewText}>
            {currentProfile.prompt.slice(0, 200)}
            {currentProfile.prompt.length > 200 ? "…" : ""}
          </div>
        </div>
      )}
    </div>
  );
}

function ProfileItem({
  prof, isActive, canEdit, onSelect, onEdit, onDelete, badge,
}: {
  prof: Profile;
  isActive: boolean;
  canEdit: boolean;
  onSelect: () => void;
  onEdit: () => void;
  onDelete: () => void;
  badge?: string;
}) {
  return (
    <div
      style={{
        ...p.profileItem,
        ...(isActive ? p.profileItemActive : {}),
      }}
    >
      <button
        style={p.profileSelectBtn}
        onClick={onSelect}
        title={prof.prompt ? prof.prompt.slice(0, 120) + "…" : "Profil vide"}
      >
        <span style={p.profileIcon}>{isActive ? "✅" : prof.is_personal ? "🧑" : "👤"}</span>
        <span style={p.profileName}>{prof.name}</span>
        {isActive && <span style={p.profileActiveBadge}>actif</span>}
        {badge && !isActive && (
          <span style={{ ...p.profileActiveBadge, color: "var(--text-muted)", background: "var(--elevated-bg)", borderColor: "var(--border)" }}>
            {badge}
          </span>
        )}
      </button>
      {canEdit && (
        <div style={p.profileActions}>
          <button style={p.profileActionBtn} onClick={onEdit} title="Éditer ce profil">✏️</button>
          <button
            style={{ ...p.profileActionBtn, color: "#e07878" }}
            onClick={onDelete}
            title="Supprimer ce profil"
          >🗑️</button>
        </div>
      )}
    </div>
  );
}

// ── Onglet Skills ─────────────────────────────────────────────────────────────

function SkillsTab({ onRefreshNeeded, isAdmin }: { onRefreshNeeded: () => void; isAdmin: boolean }) {
  const [skills, setSkills] = useState<Skill[]>([]);
  const [selectedSlug, setSelectedSlug] = useState<string | null>(null);
  const [preview, setPreview] = useState("");
  const [editingSkill, setEditingSkill] = useState<{ slug: string; content: string } | null>(null);
  const [showEditor, setShowEditor] = useState(false);

  useEffect(() => { refreshSkills(); }, []);

  async function refreshSkills(selectSlug?: string) {
    try {
      const data = await api.get<Skill[]>("/skills");
      setSkills(data);
      const sel = selectSlug ?? (data[0]?.slug ?? null);
      setSelectedSlug(sel);
      if (sel) loadPreview(sel);
    } catch {}
  }

  async function loadPreview(slug: string) {
    try {
      const data = await api.get<{ slug: string; content: string }>(`/skills/${slug}`);
      setPreview(data.content ?? "");
    } catch { setPreview(""); }
  }

  async function handleEditSkill() {
    if (!selectedSlug) return;
    const data = await api.get<{ slug: string; content: string }>(`/skills/${selectedSlug}`);
    setEditingSkill({ slug: selectedSlug, content: data.content ?? "" });
    setShowEditor(true);
  }

  async function handleDeleteSkill() {
    if (!selectedSlug) return;
    const sk = skills.find((s) => s.slug === selectedSlug);
    if (!window.confirm(`Supprimer le skill « ${sk?.name ?? selectedSlug} » ?`)) return;
    await api.delete(`/skills/${selectedSlug}`);
    await refreshSkills();
    onRefreshNeeded();
  }

  async function handleSkillSave(slug: string, content: string, isNew: boolean) {
    if (isNew) {
      await api.post("/skills", { slug, content });
    } else {
      await api.put(`/skills/${slug}`, { slug, content });
    }
    setShowEditor(false);
    setEditingSkill(null);
    await refreshSkills(slug);
    onRefreshNeeded();
  }

  return (
    <div style={p.tabContent}>
      <p style={p.skillHint}>
        Les skills sont des guides Markdown injectés dans le prompt système. Épinglez-les dans un profil.
      </p>

      <div style={p.skillList}>
        {skills.length === 0 && (
          <div style={p.empty}>Aucun skill. Créez-en un !</div>
        )}
        {skills.map((sk) => (
          <div
            key={sk.slug}
            style={{
              ...p.skillItem,
              ...(sk.slug === selectedSlug ? p.skillItemActive : {}),
            }}
            onClick={() => { setSelectedSlug(sk.slug); loadPreview(sk.slug); }}
          >
            <div style={p.skillName}>{sk.name}</div>
            {sk.description && (
              <div style={p.skillDesc}>
                {sk.description.slice(0, 50)}{sk.description.length > 50 ? "…" : ""}
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Aperçu */}
      {selectedSlug && preview && (
        <div style={p.skillPreview}>
          <pre style={p.skillPreviewPre}>{preview.slice(0, 300)}{preview.length > 300 ? "\n…" : ""}</pre>
        </div>
      )}

      {/* Actions */}
      <div style={p.skillActions}>
        {isAdmin && (
          <button
            style={p.newBtn}
            onClick={() => { setEditingSkill(null); setShowEditor(true); }}
          >
            ➕ Nouveau
          </button>
        )}
        {isAdmin && (
          <button
            style={{ ...p.actionBtn, opacity: selectedSlug ? 1 : 0.4 }}
            disabled={!selectedSlug}
            onClick={handleEditSkill}
          >
            ✏️ Éditer
          </button>
        )}
        {isAdmin && (
          <button
            style={{ ...p.actionBtn, color: "#e07878", opacity: selectedSlug ? 1 : 0.4 }}
            disabled={!selectedSlug}
            onClick={handleDeleteSkill}
          >
            🗑️
          </button>
        )}
      </div>

      {showEditor && (
        <SkillEditorModal
          slug={editingSkill?.slug ?? null}
          content={editingSkill?.content ?? ""}
          onSave={handleSkillSave}
          onClose={() => { setShowEditor(false); setEditingSkill(null); }}
        />
      )}
    </div>
  );
}

// ── ProfileEditorModal ────────────────────────────────────────────────────────

function ProfileEditorModal({
  profile,
  isPersonal,
  onSave,
  onClose,
}: {
  profile: Profile | null;
  isPersonal: boolean;
  onSave: (p: Profile, isNew: boolean, isPersonal: boolean) => void;
  onClose: () => void;
}) {
  const isNew = !profile;
  const isReadOnly = profile?.name === "Aucun rôle";

  const [name, setName] = useState(isNew ? "" : profile?.name ?? "");
  const [prompt, setPrompt] = useState(profile?.prompt ?? "");
  const [families, setFamilies] = useState<ToolFamily[]>([]);
  const [familyStates, setFamilyStates] = useState<Record<string, "enabled" | "disabled" | "neutral">>({});
  const [skills, setSkills] = useState<Skill[]>([]);
  const [pinnedSkills, setPinnedSkills] = useState<Set<string>>(new Set(profile?.pinned_skills ?? []));
  const [error, setError] = useState("");

  useEffect(() => {
    api.get<ToolFamily[]>("/tools/families")
      .then((data) => {
        setFamilies(data);
        const states: Record<string, "enabled" | "disabled" | "neutral"> = {};
        const enabled = new Set(profile?.tool_families?.enabled ?? []);
        const disabled = new Set(profile?.tool_families?.disabled ?? []);
        for (const f of data) {
          if (enabled.has(f.family)) states[f.family] = "enabled";
          else if (disabled.has(f.family)) states[f.family] = "disabled";
          else states[f.family] = "neutral";
        }
        setFamilyStates(states);
      })
      .catch(() => {});

    api.get<Skill[]>("/skills")
      .then((data) => setSkills(data))
      .catch(() => {});
  }, []);

  function cycleFamilyState(family: string) {
    setFamilyStates((prev) => {
      const cur = prev[family] ?? "neutral";
      const next = cur === "neutral" ? "enabled" : cur === "enabled" ? "disabled" : "neutral";
      return { ...prev, [family]: next };
    });
  }

  function toggleSkill(slug: string) {
    setPinnedSkills((prev) => {
      const next = new Set(prev);
      next.has(slug) ? next.delete(slug) : next.add(slug);
      return next;
    });
  }

  function handleSave() {
    const trimName = name.trim();
    if (!trimName) { setError("Le nom du profil est requis."); return; }
    if (trimName === "Aucun rôle" && isNew) { setError("Ce nom est réservé."); return; }

    const enabled: string[] = [];
    const disabled: string[] = [];
    for (const [fam, state] of Object.entries(familyStates)) {
      if (state === "enabled") enabled.push(fam);
      if (state === "disabled") disabled.push(fam);
    }

    onSave({
      name: trimName,
      prompt,
      tool_families: { enabled, disabled },
      pinned_skills: Array.from(pinnedSkills),
      is_personal: isPersonal,
    }, isNew, isPersonal);
  }

  function familyStateLabel(state: "enabled" | "disabled" | "neutral") {
    if (state === "enabled") return { icon: "✅", title: "Forcé actif" };
    if (state === "disabled") return { icon: "❌", title: "Forcé inactif" };
    return { icon: "➖", title: "Indéterminé" };
  }

  return (
    <div style={m.overlay}>
      <div style={m.modal}>
        <div style={m.header}>
          <span style={m.headerTitle}>
            {isNew
              ? isPersonal ? "👤 Nouveau profil personnel" : "✨ Nouveau profil"
              : `✏️ Éditer : ${profile?.name}${isPersonal ? " (personnel)" : ""}`}
          </span>
          <button style={m.closeBtn} onClick={onClose}>×</button>
        </div>

        <div style={m.body}>
          {!isReadOnly && (
            <div style={m.formRow}>
              <label style={m.label}>Nom du profil</label>
              <input
                value={name}
                onChange={(e) => { setName(e.target.value); setError(""); }}
                placeholder="Ex : Assistant juridique"
                disabled={!isNew}
                style={{ ...m.input, opacity: !isNew ? 0.6 : 1 }}
              />
            </div>
          )}

          <div style={m.formRow}>
            <label style={m.label}>Prompt système</label>
            <textarea
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder={"Définissez le rôle, les règles et le comportement…\n\nExemple :\nRôle : Tu es un expert en…\n\nRègles :\n- Règle 1"}
              style={m.textarea}
              rows={8}
            />
          </div>

          <fieldset style={m.fieldset}>
            <legend style={m.legend}>🛠️ Outils activés par ce profil</legend>
            <p style={m.hint}>✅ Forcé actif · ❌ Forcé inactif · ➖ Indéterminé</p>
            <div style={m.familyGrid}>
              {families.length === 0 && (
                <span style={{ color: "var(--text-muted)", fontSize: 12 }}>Aucune famille disponible</span>
              )}
              {families.map((fam) => {
                const state = familyStates[fam.family] ?? "neutral";
                const { icon, title } = familyStateLabel(state);
                return (
                  <div
                    key={fam.family}
                    style={{
                      ...m.familyItem,
                      background: state === "enabled"
                        ? "rgba(90, 170, 122, 0.12)"
                        : state === "disabled"
                          ? "rgba(224, 120, 120, 0.1)"
                          : undefined,
                    }}
                    onClick={() => cycleFamilyState(fam.family)}
                    title={title}
                  >
                    <span style={m.familyIcon}>{icon}</span>
                    <span>{fam.icon} {fam.label}</span>
                  </div>
                );
              })}
            </div>
          </fieldset>

          <fieldset style={m.fieldset}>
            <legend style={m.legend}>📚 Skills épinglés</legend>
            <p style={m.hint}>Coché = injecté automatiquement dans le prompt système.</p>
            {skills.length === 0 ? (
              <p style={{ color: "var(--text-muted)", fontSize: 12 }}>
                Aucun skill. Créez-en via l'onglet Skills.
              </p>
            ) : (
              <div style={m.skillList}>
                {skills.map((sk) => (
                  <label key={sk.slug} style={m.skillRow}>
                    <input
                      type="checkbox"
                      checked={pinnedSkills.has(sk.slug)}
                      onChange={() => toggleSkill(sk.slug)}
                      style={{ accentColor: "var(--accent)", cursor: "pointer" }}
                    />
                    <span style={m.skillName}>{sk.name}</span>
                    {sk.description && (
                      <span style={m.skillDesc}>
                        {" — "}{sk.description.slice(0, 60)}{sk.description.length > 60 ? "…" : ""}
                      </span>
                    )}
                  </label>
                ))}
              </div>
            )}
          </fieldset>

          {error && <p style={m.error}>{error}</p>}
        </div>

        <div style={m.footer}>
          <button style={m.cancelBtn} onClick={onClose}>Annuler</button>
          <button style={m.saveBtn} onClick={handleSave}>
            {isNew ? "Créer" : "Sauvegarder"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── SkillEditorModal ──────────────────────────────────────────────────────────

function SkillEditorModal({
  slug, content, onSave, onClose,
}: {
  slug: string | null;
  content: string;
  onSave: (slug: string, content: string, isNew: boolean) => void;
  onClose: () => void;
}) {
  const isNew = !slug;

  function parseFm(raw: string) {
    const match = raw.match(/^---\s*\n([\s\S]*?)\n---\s*\n/);
    if (!match) return { name: "", description: "", tags: "", version: "1.0", body: raw };
    try {
      const lines = match[1].split("\n");
      const fm: Record<string, string> = {};
      for (const line of lines) {
        const [k, ...rest] = line.split(":");
        if (k && rest.length) fm[k.trim()] = rest.join(":").trim();
      }
      return {
        name: fm.name ?? "",
        description: fm.description ?? "",
        tags: fm.tags?.replace(/[\[\]]/g, "") ?? "",
        version: fm.version ?? "1.0",
        body: raw.slice(match[0].length).trimStart(),
      };
    } catch {
      return { name: "", description: "", tags: "", version: "1.0", body: raw };
    }
  }

  const parsed = parseFm(content);

  const [skillName, setSkillName] = useState(parsed.name);
  const [skillSlug, setSkillSlug] = useState(slug ?? "");
  const [description, setDescription] = useState(parsed.description);
  const [tags, setTags] = useState(parsed.tags);
  const [version, setVersion] = useState(parsed.version);
  const [body, setBody] = useState(parsed.body);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!isNew) return;
    const s = skillName
      .normalize("NFD").replace(/[\u0300-\u036f]/g, "")
      .replace(/[^a-zA-Z0-9]+/g, "_")
      .replace(/^_|_$/g, "")
      .toLowerCase();
    setSkillSlug(s);
  }, [skillName, isNew]);

  function buildContent() {
    const tagList = tags.split(",").map((t) => t.trim()).filter(Boolean);
    return [
      "---",
      skillName ? `name: ${skillName}` : null,
      description ? `description: ${description}` : null,
      tagList.length ? `tags: [${tagList.join(", ")}]` : null,
      `version: ${version || "1.0"}`,
      "---",
      "",
      body,
    ].filter((l) => l !== null).join("\n");
  }

  function handleSave() {
    if (!skillSlug.trim()) { setError("Le slug est requis."); return; }
    if (!/^[a-zA-Z0-9_-]+$/.test(skillSlug)) {
      setError("Le slug ne peut contenir que des lettres, chiffres, tirets et underscores.");
      return;
    }
    if (!skillName.trim()) { setError("Le nom affiché est requis."); return; }
    if (!body.trim()) { setError("Le contenu est vide."); return; }
    onSave(skillSlug.trim(), buildContent(), isNew);
  }

  return (
    <div style={{ ...m.overlay, zIndex: 310 }}>
      <div style={{ ...m.modal, width: 740 }}>
        <div style={m.header}>
          <span style={m.headerTitle}>
            {isNew ? "✨ Nouveau skill" : `✏️ Éditer : ${slug}`}
          </span>
          <button style={m.closeBtn} onClick={onClose}>×</button>
        </div>

        <div style={m.body}>
          <fieldset style={m.fieldset}>
            <legend style={m.legend}>📋 Métadonnées</legend>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "8px 14px" }}>
              <div>
                <label style={m.label}>Nom affiché</label>
                <input value={skillName} onChange={(e) => setSkillName(e.target.value)} placeholder="Ex : Conventions de nommage" style={m.input} />
              </div>
              <div>
                <label style={m.label}>Slug (nom de fichier)</label>
                <input
                  value={skillSlug}
                  onChange={(e) => isNew && setSkillSlug(e.target.value)}
                  placeholder="conventions_nommage"
                  disabled={!isNew}
                  style={{ ...m.input, opacity: !isNew ? 0.6 : 1 }}
                />
              </div>
              <div>
                <label style={m.label}>Description courte</label>
                <input value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Résumé affiché dans la liste" style={m.input} />
              </div>
              <div>
                <label style={m.label}>Tags (virgule)</label>
                <input value={tags} onChange={(e) => setTags(e.target.value)} placeholder="nommage, fichiers" style={m.input} />
              </div>
            </div>
          </fieldset>

          <div style={m.formRow}>
            <label style={m.label}>Contenu Markdown</label>
            <textarea
              value={body}
              onChange={(e) => setBody(e.target.value)}
              placeholder={"# Titre du skill\n\n## Section 1\n\nVos conventions ici…"}
              style={{ ...m.textarea, fontFamily: "'Courier New', monospace", fontSize: 12, minHeight: 220 }}
              rows={12}
            />
          </div>

          {error && <p style={m.error}>{error}</p>}
        </div>

        <div style={m.footer}>
          <button style={m.cancelBtn} onClick={onClose}>Annuler</button>
          <button style={m.saveBtn} onClick={handleSave}>
            {isNew ? "Créer" : "Sauvegarder"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Styles panel ──────────────────────────────────────────────────────────────

const p: Record<string, React.CSSProperties> = {
  root: {
    display: "flex",
    flexDirection: "column",
    height: "100%",
    overflow: "hidden",
  },
  header: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    padding: "12px 14px 8px",
    borderBottom: "1px solid var(--sidebar-border)",
    flexShrink: 0,
  },
  title: {
    fontSize: 13,
    fontWeight: 600,
    color: "var(--text-secondary)",
    letterSpacing: "0.01em",
  },
  closeBtn: {
    background: "none",
    border: "none",
    cursor: "pointer",
    color: "var(--text-muted)",
    fontSize: 18,
    lineHeight: 1,
    padding: "0 2px",
  },
  tabs: {
    display: "flex",
    borderBottom: "1px solid var(--sidebar-border)",
    flexShrink: 0,
  },
  tab: {
    flex: 1,
    padding: "8px 6px",
    background: "none",
    border: "none",
    borderBottom: "2px solid transparent",
    cursor: "pointer",
    fontSize: 12,
    fontWeight: 500,
    color: "var(--text-muted)",
    fontFamily: "inherit",
    transition: "color 0.12s, border-color 0.12s",
  },
  tabActive: {
    color: "var(--accent)",
    borderBottomColor: "var(--accent)",
  },
  tabContent: {
    flex: 1,
    overflowY: "auto",
    display: "flex",
    flexDirection: "column",
    gap: 0,
  },
  newBtn: {
    display: "flex",
    alignItems: "center",
    gap: 6,
    margin: "10px 10px 6px",
    padding: "7px 12px",
    background: "none",
    border: "1px solid var(--border)",
    borderRadius: 7,
    color: "var(--text-primary)",
    fontSize: 12,
    cursor: "pointer",
    fontWeight: 500,
    fontFamily: "inherit",
    flexShrink: 0,
  },
  profileList: {
    display: "flex",
    flexDirection: "column",
    padding: "0 6px",
    gap: 2,
  },
  profileItem: {
    display: "flex",
    alignItems: "center",
    borderRadius: 6,
    overflow: "hidden",
    transition: "background 0.1s",
  },
  profileItemActive: {
    background: "var(--sidebar-item-active-bg)",
  },
  profileSelectBtn: {
    flex: 1,
    display: "flex",
    alignItems: "center",
    gap: 7,
    padding: "7px 8px",
    background: "none",
    border: "none",
    cursor: "pointer",
    fontSize: 13,
    color: "var(--text-secondary)",
    fontFamily: "inherit",
    textAlign: "left",
    minWidth: 0,
  },
  profileIcon: {
    fontSize: 13,
    flexShrink: 0,
  },
  profileName: {
    flex: 1,
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
  },
  profileActiveBadge: {
    fontSize: 10,
    color: "var(--accent)",
    background: "rgba(212,129,61,0.12)",
    border: "1px solid var(--accent)",
    borderRadius: 4,
    padding: "1px 5px",
    flexShrink: 0,
  },
  profileActions: {
    display: "flex",
    gap: 2,
    padding: "0 4px",
    flexShrink: 0,
  },
  profileActionBtn: {
    background: "none",
    border: "none",
    cursor: "pointer",
    fontSize: 13,
    padding: "4px",
    borderRadius: 4,
    color: "var(--text-muted)",
    fontFamily: "inherit",
    lineHeight: 1,
  },
  promptPreview: {
    margin: "10px 10px 6px",
    padding: "8px 10px",
    background: "var(--elevated-bg)",
    border: "1px solid var(--border)",
    borderRadius: 6,
    flexShrink: 0,
  },
  promptPreviewLabel: {
    fontSize: 10,
    color: "var(--text-muted)",
    fontWeight: 600,
    marginBottom: 4,
    textTransform: "uppercase",
    letterSpacing: "0.05em",
  },
  promptPreviewText: {
    fontSize: 11,
    color: "var(--text-secondary)",
    lineHeight: 1.5,
    whiteSpace: "pre-wrap",
    wordBreak: "break-word",
  },
  empty: {
    padding: "16px 12px",
    color: "var(--text-muted)",
    fontSize: 12,
    fontStyle: "italic",
    textAlign: "center",
  },
  sectionLabel: {
    padding: "6px 14px 2px",
    fontSize: 10,
    fontWeight: 700,
    color: "var(--text-muted)",
    textTransform: "uppercase" as const,
    letterSpacing: "0.06em",
    flexShrink: 0,
  },
  skillHint: {
    margin: "8px 10px 4px",
    fontSize: 11,
    color: "var(--text-muted)",
    lineHeight: 1.5,
    flexShrink: 0,
  },
  skillList: {
    display: "flex",
    flexDirection: "column",
    padding: "0 6px",
    gap: 2,
    maxHeight: 200,
    overflowY: "auto",
    flexShrink: 0,
  },
  skillItem: {
    padding: "6px 8px",
    borderRadius: 5,
    cursor: "pointer",
    fontSize: 12,
    color: "var(--text-secondary)",
    transition: "background 0.1s",
  },
  skillItemActive: {
    background: "var(--sidebar-item-active-bg)",
    color: "var(--text-primary)",
  },
  skillName: {
    fontWeight: 600,
    fontSize: 12,
  },
  skillDesc: {
    fontSize: 11,
    color: "var(--text-muted)",
    marginTop: 1,
  },
  skillPreview: {
    margin: "6px 10px",
    padding: "8px",
    background: "var(--elevated-bg)",
    border: "1px solid var(--border)",
    borderRadius: 6,
    maxHeight: 120,
    overflow: "auto",
    flexShrink: 0,
  },
  skillPreviewPre: {
    margin: 0,
    fontSize: 10,
    lineHeight: 1.5,
    color: "var(--text-secondary)",
    fontFamily: "'Courier New', monospace",
    whiteSpace: "pre-wrap",
    wordBreak: "break-word",
  },
  skillActions: {
    display: "flex",
    gap: 6,
    padding: "8px 10px",
    borderTop: "1px solid var(--border)",
    flexShrink: 0,
    marginTop: "auto",
  },
  actionBtn: {
    padding: "5px 10px",
    background: "var(--elevated-bg)",
    border: "1px solid var(--border)",
    borderRadius: 6,
    color: "var(--text-muted)",
    fontSize: 12,
    cursor: "pointer",
    fontFamily: "inherit",
  },
};

// ── Styles modals ─────────────────────────────────────────────────────────────

const m: Record<string, React.CSSProperties> = {
  overlay: {
    position: "fixed",
    inset: 0,
    background: "rgba(0,0,0,0.6)",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    zIndex: 300,
  },
  modal: {
    background: "var(--surface-bg)",
    border: "1px solid var(--border)",
    borderRadius: 12,
    width: 720,
    maxWidth: "95vw",
    maxHeight: "88vh",
    display: "flex",
    flexDirection: "column",
    boxShadow: "0 20px 60px rgba(0,0,0,0.5)",
    overflow: "hidden",
  },
  header: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    padding: "14px 20px",
    borderBottom: "1px solid var(--border)",
    flexShrink: 0,
  },
  headerTitle: {
    fontWeight: 700,
    fontSize: 15,
    color: "var(--text-primary)",
  },
  closeBtn: {
    background: "none",
    border: "none",
    cursor: "pointer",
    color: "var(--text-muted)",
    fontSize: 20,
    lineHeight: 1,
    padding: "0 4px",
  },
  body: {
    padding: "16px 20px",
    overflowY: "auto",
    flex: 1,
    display: "flex",
    flexDirection: "column",
    gap: 14,
  },
  footer: {
    display: "flex",
    justifyContent: "flex-end",
    gap: 10,
    padding: "12px 20px",
    borderTop: "1px solid var(--border)",
    flexShrink: 0,
  },
  formRow: {
    display: "flex",
    flexDirection: "column",
    gap: 5,
  },
  label: {
    fontSize: 12,
    color: "var(--text-secondary)",
    fontWeight: 500,
  },
  input: {
    width: "100%",
    padding: "6px 10px",
    background: "var(--input-bg)",
    border: "1px solid var(--input-border)",
    borderRadius: 6,
    color: "var(--input-color)",
    fontSize: 13,
    outline: "none",
    boxSizing: "border-box",
    fontFamily: "inherit",
  },
  textarea: {
    width: "100%",
    padding: "8px 10px",
    background: "var(--input-bg)",
    border: "1px solid var(--input-border)",
    borderRadius: 6,
    color: "var(--input-color)",
    fontSize: 13,
    outline: "none",
    resize: "vertical",
    fontFamily: "inherit",
    lineHeight: 1.5,
    boxSizing: "border-box",
    minHeight: 140,
  },
  fieldset: {
    border: "1px solid var(--input-border)",
    borderRadius: 8,
    padding: "10px 14px 12px",
    margin: 0,
  },
  legend: {
    fontSize: 12,
    fontWeight: 700,
    color: "var(--text-secondary)",
    padding: "0 6px",
  },
  hint: {
    margin: "4px 0 10px",
    fontSize: 11,
    color: "var(--text-muted)",
    lineHeight: 1.5,
  },
  familyGrid: {
    display: "grid",
    gridTemplateColumns: "1fr 1fr",
    gap: "4px 10px",
  },
  familyItem: {
    display: "flex",
    alignItems: "center",
    gap: 8,
    padding: "5px 8px",
    borderRadius: 5,
    cursor: "pointer",
    fontSize: 12,
    color: "var(--text-primary)",
    border: "1px solid transparent",
    userSelect: "none",
    transition: "background 0.12s",
  },
  familyIcon: {
    fontSize: 14,
    width: 16,
    textAlign: "center",
    flexShrink: 0,
  },
  skillList: {
    display: "flex",
    flexDirection: "column",
    gap: 4,
    maxHeight: 140,
    overflowY: "auto",
  },
  skillRow: {
    display: "flex",
    alignItems: "baseline",
    gap: 7,
    cursor: "pointer",
    padding: "3px 2px",
    fontSize: 12,
    color: "var(--text-primary)",
    userSelect: "none",
  },
  skillName: {
    fontWeight: 500,
  },
  skillDesc: {
    color: "var(--text-muted)",
    fontSize: 11,
  },
  error: {
    margin: 0,
    fontSize: 12,
    color: "#e07878",
  },
  cancelBtn: {
    padding: "7px 16px",
    background: "var(--elevated-bg)",
    border: "1px solid var(--input-border)",
    borderRadius: 7,
    color: "var(--text-primary)",
    fontSize: 13,
    cursor: "pointer",
    fontFamily: "inherit",
  },
  saveBtn: {
    padding: "7px 18px",
    background: "var(--accent)",
    border: "none",
    borderRadius: 7,
    color: "#fff",
    fontSize: 13,
    fontWeight: 700,
    cursor: "pointer",
    fontFamily: "inherit",
  },
};
