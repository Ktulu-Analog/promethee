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
 * useConversationTree.ts
 *
 * Charge et mutate l'arborescence dossiers/conversations.
 *
 * Expose un état local mis à jour et synchronisé avec l'API REST.
 */

import { useState, useEffect, useCallback } from "react";
import { api } from "../lib/api";

// ── Types ──────────────────────────────────────────────────────────────────

export interface Conversation {
  id: string;
  title: string;
  system_prompt: string;
  folder_id: string | null;
  starred: boolean;
  updated_at: string;
}

export interface Folder {
  id: string;
  name: string;
  parent_id: string | null;
  position: number;
}

export interface ConvTree {
  folders: Folder[];
  conversations_by_folder: Record<string, Conversation[]>;
  unfiled: Conversation[];
}

export interface UseConversationTreeReturn {
  tree: ConvTree | null;
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;

  // Conversations
  createConversation: (title?: string, folderId?: string | null) => Promise<Conversation>;
  deleteConversation: (convId: string) => Promise<void>;
  renameConversation: (convId: string, title: string) => Promise<void>;
  moveConversation: (convId: string, folderId: string | null) => Promise<void>;
  starConversation: (convId: string, starred: boolean) => Promise<void>;

  // Dossiers
  createFolder: (name: string, parentId?: string | null) => Promise<Folder>;
  renameFolder: (folderId: string, name: string) => Promise<void>;
  deleteFolder: (folderId: string) => Promise<void>;

  // Recherche
  searchQuery: string;
  setSearchQuery: (q: string) => void;
}

// ── Hook ──────────────────────────────────────────────────────────────────

export function useConversationTree(): UseConversationTreeReturn {
  const [tree, setTree] = useState<ConvTree | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");

  const refresh = useCallback(async () => {
    try {
      setLoading(true);
      const data = await api.get<ConvTree>("/conversations/tree");
      setTree(data);
      setError(null);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, []);

  // ── Conversations ──────────────────────────────────────────────────────

  const createConversation = useCallback(
    async (title = "Nouvelle conversation", folderId: string | null = null): Promise<Conversation> => {
      const conv = await api.post<Conversation>("/conversations", {
        title,
        folder_id: folderId,
      });
      // Mise à jour optimiste
      setTree((t) => {
        if (!t) return t;
        if (folderId) {
          return {
            ...t,
            conversations_by_folder: {
              ...t.conversations_by_folder,
              [folderId]: [conv, ...(t.conversations_by_folder[folderId] ?? [])],
            },
          };
        }
        return { ...t, unfiled: [conv, ...t.unfiled] };
      });
      return conv;
    },
    []
  );

  const deleteConversation = useCallback(async (convId: string) => {
    await api.delete(`/conversations/${convId}`);
    setTree((t) => {
      if (!t) return t;
      return {
        ...t,
        unfiled: t.unfiled.filter((c) => c.id !== convId),
        conversations_by_folder: Object.fromEntries(
          Object.entries(t.conversations_by_folder).map(([fid, convs]) => [
            fid,
            convs.filter((c) => c.id !== convId),
          ])
        ),
      };
    });
  }, []);

  const renameConversation = useCallback(async (convId: string, title: string) => {
    await api.patch(`/conversations/${convId}`, { title });
    setTree((t) => {
      if (!t) return t;
      const patch = (convs: Conversation[]) =>
        convs.map((c) => (c.id === convId ? { ...c, title } : c));
      return {
        ...t,
        unfiled: patch(t.unfiled),
        conversations_by_folder: Object.fromEntries(
          Object.entries(t.conversations_by_folder).map(([fid, convs]) => [
            fid,
            patch(convs),
          ])
        ),
      };
    });
  }, []);

  const moveConversation = useCallback(async (convId: string, folderId: string | null) => {
    await api.patch(`/conversations/${convId}/folder`, { folder_id: folderId });
    // Rechargement complet (plus simple que la mutation optimiste cross-folder)
    await refresh();
  }, [refresh]);

  const starConversation = useCallback(async (convId: string, starred: boolean) => {
    await api.patch(`/conversations/${convId}`, { starred });
    setTree((t) => {
      if (!t) return t;
      const patch = (convs: Conversation[]) =>
        convs.map((c) => (c.id === convId ? { ...c, starred } : c));
      return {
        ...t,
        unfiled: patch(t.unfiled),
        conversations_by_folder: Object.fromEntries(
          Object.entries(t.conversations_by_folder).map(([fid, convs]) => [fid, patch(convs)])
        ),
      };
    });
  }, []);

  // ── Dossiers ──────────────────────────────────────────────────────────

  const createFolder = useCallback(async (name: string, parentId: string | null = null): Promise<Folder> => {
    const folder = await api.post<Folder>("/conversations/folders", {
      name,
      parent_id: parentId,
    });
    setTree((t) => {
      if (!t) return t;
      return { ...t, folders: [...t.folders, folder] };
    });
    return folder;
  }, []);

  const renameFolder = useCallback(async (folderId: string, name: string) => {
    await api.patch(`/conversations/folders/${folderId}`, { name });
    setTree((t) => {
      if (!t) return t;
      return {
        ...t,
        folders: t.folders.map((f) => (f.id === folderId ? { ...f, name } : f)),
      };
    });
  }, []);

  const deleteFolder = useCallback(async (folderId: string) => {
    await api.delete(`/conversations/folders/${folderId}`);
    // Les convs déplacées en "sans dossier" → rechargement complet
    await refresh();
  }, [refresh]);

  return {
    tree,
    loading,
    error,
    refresh,
    createConversation,
    deleteConversation,
    renameConversation,
    moveConversation,
    starConversation,
    createFolder,
    renameFolder,
    deleteFolder,
    searchQuery,
    setSearchQuery,
  };
}

// ── Helpers ───────────────────────────────────────────────────────────────

/** Filtre l'arbre selon une requête de recherche (insensible à la casse). */
export function filterTree(tree: ConvTree, query: string): ConvTree {
  if (!query.trim()) return tree;
  const q = query.toLowerCase();
  const matchConv = (c: Conversation) => c.title.toLowerCase().includes(q);
  return {
    folders: tree.folders, // On garde les dossiers, on filtre leur contenu
    conversations_by_folder: Object.fromEntries(
      Object.entries(tree.conversations_by_folder).map(([fid, convs]) => [
        fid,
        convs.filter(matchConv),
      ])
    ),
    unfiled: tree.unfiled.filter(matchConv),
  };
}
