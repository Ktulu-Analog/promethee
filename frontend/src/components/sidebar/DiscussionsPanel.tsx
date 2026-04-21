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
 * DiscussionsPanel.tsx — Panneau modal listant toutes les conversations groupées par dossier.
 */

import React, { useState, useMemo } from "react";
import { ConvTree, Conversation, Folder } from "../../hooks/useConversationTree";
import { DiscussionRow } from "./ConvItem";

interface DiscussionsPanelProps {
  tree: ConvTree | null;
  activeConvId: string | null;
  onSelectConv: (id: string) => void;
  onNewConv: () => void;
  onClose: () => void;
  onRename?: (convId: string, title: string) => void;
  onDelete?: (convId: string) => void;
  onStar?: (convId: string, starred: boolean) => void;
  onMove?: (convId: string, folderId: string | null) => void;
}

export function DiscussionsPanel({
  tree, activeConvId, onSelectConv, onNewConv, onClose,
  onRename, onDelete, onStar, onMove,
}: DiscussionsPanelProps) {
  const [query, setQuery] = useState("");
  const allFolders: Folder[] = tree?.folders ?? [];

  type Section = { label: string; convs: Conversation[] };

  const sections: Section[] = useMemo(() => {
    if (!tree) return [];
    const q = query.trim().toLowerCase();
    const matchConv = (c: Conversation) => !q || c.title.toLowerCase().includes(q);
    const result: Section[] = [];

    const rootFolders = tree.folders
      .filter((f) => !f.parent_id)
      .sort((a, b) => a.name.localeCompare(b.name));

    for (const folder of rootFolders) {
      const subFolderIds = tree.folders
        .filter((f) => f.parent_id === folder.id)
        .map((f) => f.id);
      const allIds = [folder.id, ...subFolderIds];
      const convs = allIds
        .flatMap((fid) => tree.conversations_by_folder[fid] ?? [])
        .filter(matchConv)
        .sort((a, b) => b.updated_at.localeCompare(a.updated_at));
      if (convs.length > 0) {
        result.push({ label: `📁 ${folder.name}`, convs });
      }
    }

    const unfiled = (tree.unfiled ?? [])
      .filter(matchConv)
      .sort((a, b) => b.updated_at.localeCompare(a.updated_at));
    if (unfiled.length > 0) {
      result.push({ label: "Sans dossier", convs: unfiled });
    }

    return result;
  }, [tree, query]);

  const totalCount = sections.reduce((n, s) => n + s.convs.length, 0);

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", overflow: "hidden" }}>
      {/* En-tête */}
      <div style={{
        display: "flex", alignItems: "center", justifyContent: "space-between",
        padding: "16px 20px 12px", flexShrink: 0,
      }}>
        <span style={{ fontSize: 20, fontWeight: 700, color: "var(--text-primary)" }}>Discussions</span>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <button
            onClick={onNewConv}
            style={{
              display: "flex", alignItems: "center", gap: 6,
              background: "var(--accent)", border: "none", borderRadius: 8,
              color: "#fff", fontSize: 13, fontWeight: 600, padding: "7px 14px",
              cursor: "pointer", fontFamily: "inherit",
            }}
          >
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
            </svg>
            Nouvelle conversation
          </button>
          <button onClick={onClose} style={{
            background: "none", border: "none", cursor: "pointer",
            color: "var(--text-muted)", fontSize: 20, lineHeight: 1,
            padding: "2px 4px", fontFamily: "inherit",
          }}>×</button>
        </div>
      </div>

      {/* Barre de recherche */}
      <div style={{ padding: "0 20px 12px", flexShrink: 0 }}>
        <div style={{
          display: "flex", alignItems: "center", gap: 8,
          background: "var(--input-bg)", border: "1px solid var(--input-border)",
          borderRadius: 8, padding: "8px 12px",
        }}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--text-muted)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0 }}>
            <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
          </svg>
          <input
            autoFocus
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Rechercher dans vos conversations..."
            style={{
              flex: 1, background: "none", border: "none", outline: "none",
              color: "var(--text-primary)", fontSize: 13, fontFamily: "inherit",
            }}
          />
        </div>
      </div>

      <div style={{ padding: "0 20px 8px", fontSize: 12, color: "var(--text-muted)", flexShrink: 0 }}>
        {query ? `${totalCount} résultat${totalCount !== 1 ? "s" : ""}` : "Vos conversations"}
      </div>

      <div style={{ height: 1, background: "var(--border)", flexShrink: 0 }} />

      {/* Liste groupée */}
      <div style={{ flex: 1, overflowY: "auto", overflowX: "hidden" }}>
        {totalCount === 0 && (
          <div style={{ padding: "32px 20px", textAlign: "center", color: "var(--text-muted)", fontSize: 13, fontStyle: "italic" }}>
            Aucune conversation trouvée
          </div>
        )}
        {sections.map((section) => (
          <div key={section.label}>
            <div style={{
              padding: "8px 20px 4px",
              fontSize: 11,
              fontWeight: 600,
              letterSpacing: "0.04em",
              color: "var(--text-muted)",
              textTransform: "uppercase" as const,
              borderBottom: "1px solid var(--border)",
              background: "var(--elevated-bg, rgba(0,0,0,0.02))",
            }}>
              {section.label}
            </div>
            {section.convs.map((conv) => (
              <DiscussionRow
                key={conv.id}
                conv={conv}
                isActive={conv.id === activeConvId}
                onSelect={() => onSelectConv(conv.id)}
                onRename={onRename}
                onDelete={onDelete}
                onStar={onStar}
                onMove={onMove}
                folders={allFolders}
              />
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}
