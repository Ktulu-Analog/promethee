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
 */

import React, {
  useState,
  useRef,
  useCallback,
  useEffect,
  useMemo,
} from "react";
import {
  DndContext,
  DragEndEvent,
  DragStartEvent,
  PointerSensor,
  useSensor,
  useSensors,
  DragOverlay,
  closestCenter,
} from "@dnd-kit/core";
import { useConversationTree, filterTree, ConvTree, Folder, Conversation } from "../../hooks/useConversationTree";
import {
  IconHamburger, IconFolder, IconChat,
  IconTools,
  IconPlus, IconProfiles, IconVfs, IconIngest,
} from "../ui/icons";
import { useTheme } from "../../lib/useTheme";
import { ToolsPanel } from "../tools/ToolsPanel";
import { ProfilesPanel } from "../profiles/ProfilesPanel";
import { VfsPanel } from "../vfs/VfsPanel";
import { ProjectsPanel, setDesc as setProjDesc } from "../projects/ProjectsPanel";
import { IngestPanel } from "../admin/IngestPanel";
import type { Profile } from "../profiles/ProfilesPanel";

import { s } from "./sidebarStyles";
import { ConfirmModal } from "./ConfirmModal";
import { SidebarFooter } from "./SidebarFooter";
import { RailBtn, NavItem } from "./SidebarRail";
import { ConvItem } from "./ConvItem";
import { DiscussionsPanel } from "./DiscussionsPanel";

// ── Types ─────────────────────────────────────────────────────────────────────

export interface ConvSidePanelProps {
  activeConvId: string | null;
  onSelectConv: (convId: string) => void;
  onReady: (firstConvId: string) => void;
  onOpenSettings: () => void;
  onOpenAdmin?: () => void;
  isAdmin?: boolean;
  modelLabel: string;
  familyRouting?: { family: string; label: string; model: string } | null;
  currentProfile: Profile | null;
  onProfileChange: (profile: Profile | null) => void;
  currentUsername?: string;
  onLogout?: () => void;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function flattenTree(tree: ConvTree | null | undefined): Conversation[] {
  if (!tree) return [];
  return [
    ...(tree.unfiled ?? []),
    ...Object.values(tree.conversations_by_folder ?? {}).flat(),
  ];
}

function findConvTitle(tree: ConvTree | null | undefined, convId: string): string {
  if (!tree) return "";
  for (const convs of Object.values(tree.conversations_by_folder as Record<string, Conversation[]>)) {
    const c = convs.find((c) => c.id === convId);
    if (c) return c.title;
  }
  const u = tree.unfiled?.find((c: Conversation) => c.id === convId);
  return u?.title ?? "";
}

// ── Composant principal ───────────────────────────────────────────────────────

export function ConvSidePanel({
  activeConvId,
  onSelectConv,
  onReady,
  onOpenSettings,
  onOpenAdmin,
  isAdmin,
  modelLabel,
  familyRouting,
  currentProfile,
  onProfileChange,
  currentUsername,
  onLogout,
}: ConvSidePanelProps) {
  const { isDark, toggle: toggleTheme } = useTheme();

  const [historyOpen, setHistoryOpen] = useState(false);
  const [activePanel, setActivePanel] = useState<"tools" | "profiles" | "discussions" | "vfs" | "projects" | "ingest" | null>(null);
  const [activeFolder, setActiveFolder] = useState<Folder | null>(null);
  const [confirmModal, setConfirmModal] = useState<{ message: string; onConfirm: () => void } | null>(null);

  const railRef = useRef<HTMLDivElement>(null);
  const readyFiredRef = useRef(false);
  const [draggingConvId, setDraggingConvId] = useState<string | null>(null);

  const {
    tree, loading,
    refresh,
    createConversation, deleteConversation, moveConversation,
    renameConversation, starConversation,
    createFolder, renameFolder, deleteFolder,
    searchQuery, setSearchQuery,
  } = useConversationTree();

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } })
  );

  // Fermer au clic extérieur
  useEffect(() => {
    function handleOutside(e: MouseEvent) {
      const target = e.target as Node;
      if (!railRef.current?.contains(target)) {
        if (historyOpen) setHistoryOpen(false);
      }
    }
    window.addEventListener("mousedown", handleOutside);
    return () => window.removeEventListener("mousedown", handleOutside);
  }, [historyOpen]);

  // Écouter la suppression globale des conversations (émis par TabsExtra)
  useEffect(() => {
    async function handleConversationsCleared() {
      // Vider l'arbre localement immédiatement
      await refresh();
      // Créer une nouvelle conversation vide pour ne pas rester sur du vide
      try {
        const conv = await createConversation("Nouvelle conversation", null);
        onSelectConv(conv.id);
      } catch (e) {
        console.error("Erreur création conv après suppression globale :", e);
      }
    }
    window.addEventListener("promethee:conversations-cleared", handleConversationsCleared);
    return () => window.removeEventListener("promethee:conversations-cleared", handleConversationsCleared);
  }, [refresh, createConversation, onSelectConv]);

  // Init : s'assurer qu'une conversation existe
  useEffect(() => {
    if (loading) return;
    if (readyFiredRef.current) return;
    readyFiredRef.current = true;

    async function ensureConv() {
      const allConvs = flattenTree(tree);
      if (allConvs.length > 0) {
        onReady(allConvs[0].id);
      } else {
        try {
          const conv = await createConversation("Nouvelle conversation", null);
          onReady(conv.id);
        } catch (e) {
          console.error("Impossible de créer la conversation initiale :", e);
        }
      }
    }
    ensureConv();
  }, [loading, tree]);

  const createAndSelect = useCallback(async () => {
    const conv = await createConversation("Nouvelle conversation", null);
    onSelectConv(conv.id);
    return conv;
  }, [createConversation, onSelectConv]);

  const handleNewConv = useCallback(async () => {
    try {
      await createAndSelect();
      setHistoryOpen(false);
    } catch (e) {
      console.error("Erreur création conversation :", e);
    }
  }, [createAndSelect]);

  const handleDeleteConv = useCallback((convId: string) => {
    setConfirmModal({
      message: "Supprimer cette conversation ?",
      onConfirm: async () => {
        await deleteConversation(convId);
        if (activeConvId === convId) {
          const allConvs = flattenTree(tree).filter((c) => c.id !== convId);
          if (allConvs.length > 0) {
            onSelectConv(allConvs[0].id);
          } else {
            try { await createAndSelect(); }
            catch (e) { console.error("Erreur création conv après suppression :", e); }
          }
        }
      },
    });
  }, [activeConvId, tree, deleteConversation, createAndSelect, onSelectConv]);

  function promptDeleteFolder(folderId: string, folderName: string) {
    setConfirmModal({
      message: `Supprimer le dossier "${folderName}" ? Les conversations seront déplacées dans "Sans dossier".`,
      onConfirm: async () => {
        await deleteFolder(folderId);
        if (activeFolder?.id === folderId) setActiveFolder(null);
      },
    });
  }

  function handleDragStart(e: DragStartEvent) { setDraggingConvId(e.active.id as string); }

  async function handleDragEnd(e: DragEndEvent) {
    setDraggingConvId(null);
    const convId = e.active.id as string;
    const overId = e.over?.id as string | undefined;
    if (!overId || overId === convId) return;
    const targetFolderId = overId === "__unfiled__" ? null : overId;
    await moveConversation(convId, targetFolderId);
  }

  const displayTree = tree
    ? searchQuery ? filterTree(tree, searchQuery) : tree
    : null;

  const filteredConvs = useMemo(() => {
    if (!displayTree) return [];
    if (!activeFolder) {
      return flattenTree(displayTree).sort((a, b) => b.updated_at.localeCompare(a.updated_at));
    }
    return displayTree.conversations_by_folder[activeFolder.id] ?? [];
  }, [displayTree, activeFolder]);

  // ── Rendu ─────────────────────────────────────────────────────────────────

  return (
    <DndContext
      sensors={sensors}
      collisionDetection={closestCenter}
      onDragStart={handleDragStart}
      onDragEnd={handleDragEnd}
    >
      <style>{`
        .conv-item-row:hover { background: var(--sidebar-item-hover-bg); }
        .disc-row:hover { background: var(--sidebar-item-hover-bg, rgba(0,0,0,0.04)); }
        .conv-menu-btn:hover, .disc-menu-btn:hover {
          background: var(--sidebar-item-hover-bg) !important;
        }
        .conv-item-row.active, .disc-row.active {
          background: var(--sidebar-item-active-bg) !important;
          color: var(--text-primary) !important;
        }
      `}</style>

      <div ref={railRef} style={historyOpen ? s.sidebarOpen : s.sidebarClosed}>

        {/* En-tête */}
        <div style={historyOpen ? s.sidebarHeaderOpen : s.sidebarHeaderClosed}>
          <div style={s.appLogoWrap}>
            <div style={s.appLogoIcon}>
              <span style={s.appLogoLetter}>P</span>
            </div>
            {historyOpen && <span style={s.appName}>Prométhée</span>}
          </div>
          <button
            style={{ ...s.railBtn, background: historyOpen ? "var(--sidebar-item-hover-bg)" : "none" }}
            onClick={() => { setHistoryOpen((v) => !v); setActivePanel(null); }}
            title={historyOpen ? "Réduire" : "Historique des conversations"}
          >
            <IconHamburger color="var(--text-muted)" size={17} />
          </button>
        </div>

        {/* ── Rail fermé ── */}
        {!historyOpen && (
          <>
            <div style={s.railSep} />
            <RailBtn icon={<IconChat    color="var(--text-muted)" size={17} />} tip="Discussions"         onClick={() => setActivePanel((v) => v === "discussions" ? null : "discussions")} active={activePanel === "discussions"} />
            <RailBtn icon={<IconFolder  color="var(--text-muted)" size={17} />} tip="Dossiers"             onClick={() => setActivePanel((v) => v === "projects"    ? null : "projects")}    active={activePanel === "projects"} />
            <RailBtn icon={<IconTools   color="var(--text-muted)" size={17} />} tip="Panneau Outils"      onClick={() => setActivePanel((v) => v === "tools"       ? null : "tools")}       active={activePanel === "tools"} />
            <RailBtn icon={<IconVfs     color="var(--text-muted)" size={17} />} tip="Fichiers virtuels"   onClick={() => setActivePanel((v) => v === "vfs"         ? null : "vfs")}         active={activePanel === "vfs"} />
            <RailBtn
              icon={<IconIngest color={activePanel === "ingest" ? "var(--accent)" : "var(--text-muted)"} size={17} />}
              tip="Ingestion Qdrant"
              onClick={() => setActivePanel((v) => v === "ingest" ? null : "ingest")}
              active={activePanel === "ingest"}
            />
            <RailBtn
              icon={<IconProfiles color={currentProfile && currentProfile.name !== "Aucun rôle" ? "var(--accent)" : "var(--text-muted)"} size={17} />}
              tip={`Profils & Skills${currentProfile ? ` — ${currentProfile.name}` : ""}`}
              onClick={() => setActivePanel((v) => v === "profiles" ? null : "profiles")}
              active={activePanel === "profiles"}
            />
            <div style={{ flex: 1 }} />
            <SidebarFooter
              isDark={isDark} toggleTheme={toggleTheme}
              isAdmin={isAdmin} onOpenAdmin={onOpenAdmin}
              onOpenSettings={onOpenSettings} onLogout={onLogout}
              currentUsername={currentUsername} iconSize={16}
            />
          </>
        )}

        {/* ── Sidebar ouverte ── */}
        {historyOpen && (
          <>
            <div style={s.modelChipWrap}>
              <span style={s.modelChip}>
                {familyRouting?.family ? familyRouting.model : modelLabel}
              </span>
            </div>

            <button style={s.newChatBtn} onClick={handleNewConv}>
              <IconPlus color="var(--accent)" size={13} />
              <span>Nouveau chat</span>
            </button>

            <div style={s.searchWrap}>
              <input
                type="search"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Rechercher…"
                style={s.searchInput}
              />
            </div>

            <div style={s.navItems}>
              <NavItem icon={<IconChat    color={activePanel === "discussions" ? "var(--accent)" : "var(--text-muted)"} size={16} />} label="Discussions"       onClick={() => setActivePanel((v) => v === "discussions" ? null : "discussions")} active={activePanel === "discussions"} />
              <NavItem icon={<IconFolder  color={activePanel === "projects"    ? "var(--accent)" : "var(--text-muted)"} size={16} />} label="Dossiers"           onClick={() => setActivePanel((v) => v === "projects"    ? null : "projects")}    active={activePanel === "projects"} />
              <NavItem icon={<IconTools   color={activePanel === "tools"      ? "var(--accent)" : "var(--text-muted)"} size={16} />} label="Outils"            onClick={() => setActivePanel((v) => v === "tools"      ? null : "tools")}      active={activePanel === "tools"} />
              <NavItem icon={<IconVfs     color={activePanel === "vfs"        ? "var(--accent)" : "var(--text-muted)"} size={16} />} label="Fichiers"          onClick={() => setActivePanel((v) => v === "vfs"        ? null : "vfs")}        active={activePanel === "vfs"} />
              <NavItem
                icon={<IconIngest color={activePanel === "ingest" ? "var(--accent)" : "var(--text-muted)"} size={16} />}
                label="Ingestion Qdrant"
                onClick={() => setActivePanel((v) => v === "ingest" ? null : "ingest")}
                active={activePanel === "ingest"}
              />
              <NavItem
                icon={<IconProfiles color={currentProfile && currentProfile.name !== "Aucun rôle" ? "var(--accent)" : "var(--text-muted)"} size={16} />}
                label={currentProfile && currentProfile.name !== "Aucun rôle" ? currentProfile.name : "Profils & Skills"}
                onClick={() => setActivePanel((v) => v === "profiles" ? null : "profiles")}
                active={activePanel === "profiles"}
              />
            </div>

            <div style={s.navSep} />

            {activeFolder ? (
              <div style={s.activeFolderHeader}>
                <button style={s.activeFolderBack} onClick={() => setActiveFolder(null)} title="Tous les chats">←</button>
                <IconFolder color="var(--accent)" size={13} open />
                <span style={s.activeFolderName}>{activeFolder.name}</span>
              </div>
            ) : (
              <div style={s.recentsLabel}>Récents</div>
            )}

            <div style={s.tree}>
              {loading && <div style={s.hint}>Chargement…</div>}
              {!loading && filteredConvs.length === 0 && (
                <div style={s.hint}>{activeFolder ? "Aucune conversation dans ce dossier." : "Aucune conversation."}</div>
              )}
              {filteredConvs.map((conv) => (
                <ConvItem
                  key={conv.id}
                  conv={conv}
                  isActive={conv.id === activeConvId}
                  onSelect={() => { onSelectConv(conv.id); }}
                  indent={0}
                  onRename={renameConversation}
                  onDelete={handleDeleteConv}
                  onStar={starConversation}
                  onMove={moveConversation}
                  folders={tree?.folders ?? []}
                />
              ))}
            </div>

            <div style={s.sidebarBottom}>
              <div style={s.sidebarBottomRow}>
                <div style={{ flex: 1 }} />
                <SidebarFooter
                  isDark={isDark} toggleTheme={toggleTheme}
                  isAdmin={isAdmin} onOpenAdmin={onOpenAdmin}
                  onOpenSettings={onOpenSettings} onLogout={onLogout}
                  currentUsername={currentUsername} iconSize={15}
                />
              </div>
            </div>
          </>
        )}
      </div>

      {/* ── Panneaux modaux ── */}
      {activePanel && (
        <div
          style={s.modalOverlay}
          onMouseDown={(e) => { if (e.target === e.currentTarget) setActivePanel(null); }}
        >
          <div style={
            activePanel === "profiles"    ? { ...s.modalBox, ...s.modalBoxWide }
            : activePanel === "discussions" ? { ...s.modalBox, ...s.modalBoxDiscussions }
            : activePanel === "tools"       ? { ...s.modalBox, ...s.modalBoxTools }
            : activePanel === "vfs"         ? { ...s.modalBox, ...s.modalBoxVfs }
            : activePanel === "ingest"      ? { ...s.modalBox, ...s.modalBoxIngest }
            : s.modalBox
          }>
            {activePanel === "projects" && (
              <ProjectsPanel
                folders={tree?.folders.filter((f) => !f.parent_id) ?? []}
                activeFolder={activeFolder}
                conversationsByFolder={tree?.conversations_by_folder ?? {}}
                onSelectFolder={(folder) => { setActiveFolder(folder); setActivePanel(null); setHistoryOpen(true); }}
                onCreateFolder={async (name: string, description: string) => {
                  const folder = await createFolder(name, null);
                  if (description && folder?.id) setProjDesc(folder.id, description);
                }}
                onRenameFolder={async (folderId, currentName) => {
                  const name = window.prompt("Nouveau nom :", currentName);
                  if (!name?.trim() || name === currentName) return;
                  await renameFolder(folderId, name.trim());
                }}
                onDeleteFolder={(folderId, name) => promptDeleteFolder(folderId, name)}
                onClose={() => setActivePanel(null)}
              />
            )}
            {activePanel === "discussions" && (
              <DiscussionsPanel
                tree={tree}
                activeConvId={activeConvId}
                onSelectConv={(id) => { onSelectConv(id); setActivePanel(null); }}
                onNewConv={() => { handleNewConv(); setActivePanel(null); }}
                onClose={() => setActivePanel(null)}
                onRename={renameConversation}
                onDelete={handleDeleteConv}
                onStar={starConversation}
                onMove={moveConversation}
              />
            )}
            {activePanel === "tools" && (
              <ToolsPanel
                onClose={() => setActivePanel(null)}
                embedded
                currentProfile={currentProfile}
              />
            )}
            {activePanel === "profiles" && (
              <ProfilesPanel
                currentProfile={currentProfile}
                onProfileChange={(profile) => { onProfileChange(profile); }}
                onClose={() => setActivePanel(null)}
                embedded
                isAdmin={isAdmin ?? false}
              />
            )}
            {activePanel === "vfs" && (
              <VfsPanel
                onClose={() => setActivePanel(null)}
                embedded
              />
            )}
            {activePanel === "ingest" && (
              <IngestPanel
                onClose={() => setActivePanel(null)}
                embedded
                isAdmin={isAdmin ?? false}
              />
            )}
          </div>
        </div>
      )}

      {/* Drag overlay */}
      <DragOverlay>
        {draggingConvId && (
          <div style={s.dragOverlay}>
            <IconChat color="var(--accent)" size={13} />
            <span style={{ marginLeft: 6, fontSize: 12 }}>
              {findConvTitle(displayTree, draggingConvId)}
            </span>
          </div>
        )}
      </DragOverlay>

      {/* Modale de confirmation */}
      {confirmModal && (
        <ConfirmModal
          message={confirmModal.message}
          onConfirm={confirmModal.onConfirm}
          onCancel={() => setConfirmModal(null)}
        />
      )}
    </DndContext>
  );
}
