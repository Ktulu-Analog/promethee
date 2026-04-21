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
 * ChatPanel.tsx
 *
 * Composant racine du chat.
 *
 * Responsabilités :
 *   - Charge l'historique depuis GET /conversations/{id}/messages
 *   - Orchestre useAgentStream (hook WS)
 *   - Construit le ChatPayload (historique + system_prompt profil + RAG + LTM)
 *   - Gère le scroll automatique vers le bas
 *   - Persiste le titre automatiquement (PATCH /conversations/{id})
 *   - Affiche MessageBubble pour chaque message (streaming inclus)
 *   - Monte ChatInput avec tous ses callbacks (y compris profil + skills)
 *   - Split-view : panneau droit ArtifactPanel (code, tables, docs, images)
 *     avec détection auto + toggle manuel + redimensionnement par drag
 */

import React, {
  useEffect,
  useRef,
  useState,
  useCallback,
  useMemo,
} from "react";

// ── Bouton retour en bas ───────────────────────────────────────────────────

function ScrollToBottomBtn({ visible, onClick }: { visible: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      title="Aller en bas"
      style={{
        position: "absolute",
        bottom: 16,
        left: "50%",
        transform: `translateX(-50%) translateY(${visible ? "0" : "12px"})`,
        opacity: visible ? 1 : 0,
        pointerEvents: visible ? "auto" : "none",
        transition: "opacity 0.2s ease, transform 0.2s ease",
        background: "var(--surface-bg)",
        border: "1px solid var(--border-active)",
        borderRadius: 20,
        padding: "6px 14px 6px 10px",
        display: "flex",
        alignItems: "center",
        gap: 6,
        cursor: "pointer",
        fontSize: 12,
        color: "var(--text-secondary)",
        boxShadow: "0 2px 12px rgba(0,0,0,0.25)",
        zIndex: 10,
        whiteSpace: "nowrap",
        userSelect: "none" as const,
      }}
    >
      <span style={{ fontSize: 14, lineHeight: 1 }}>↓</span>
      Aller en bas
    </button>
  );
}

import { useAgentStream, ChatMessage, SendPayload } from "../../hooks/useAgentStream";
import { MessageBubble } from "./MessageBubble";
import { ChatInput, AttachmentItem } from "./ChatInput";
import { ArtifactPanel } from "./ArtifactPanel";
import { MetricsBar, ConvTitleMenu as ConvTitleWidget } from "./MetricsBar";
import { useArtifactPanel } from "../../hooks/useArtifactPanel";
import { useSplitPane } from "../../hooks/useSplitPane";
import { api } from "../../lib/api";

// ── Types ──────────────────────────────────────────────────────────────────

export interface ChatPanelProps {
  convId: string;
  ragEnabled?: boolean;
  ragCollection?: string | null;
  onCollectionChange?: (collection: string) => void;
  onTitleChange?: (convId: string, title: string) => void;
  onTokenUsage?: (usage: { prompt: number; completion: number; total: number }) => void;
  onModelUsage?: (info: { model: string; prompt: number; completion: number; role: string }) => void;
  onFamilyRouting?: (info: { family: string; label: string; model: string; backend: string } | null) => void;
  currentProfile?: { name: string; prompt: string; tool_families?: { enabled: string[]; disabled: string[] }; is_personal?: boolean } | null;
  onProfileChange?: (profile: { name: string; prompt: string; is_personal?: boolean } | null) => void;
  username?: string;
  onClearRequest?: (clearFn: () => void) => void;
  /** Dossiers disponibles (pour le menu titre) */
  folders?: { id: string; name: string }[];
  /** Callbacks conversation (pour le menu titre) */
  onRenameConv?: (convId: string, title: string) => Promise<void>;
  onStarConv?: (convId: string, starred: boolean) => Promise<void>;
  onMoveConv?: (convId: string, folderId: string | null) => Promise<void>;
  onClearConv?: () => void;
}

// ── Bouton toggle panneau artefacts ───────────────────────────────────────

function ArtifactToggleBtn({
  isOpen,
  count,
  onToggle,
}: {
  isOpen: boolean;
  count: number;
  onToggle: () => void;
}) {
  return (
    <button
      onClick={onToggle}
      title={isOpen ? "Fermer le panneau artefacts" : "Ouvrir le panneau artefacts"}
      style={{
        display: "flex",
        alignItems: "center",
        gap: 5,
        padding: "4px 10px",
        fontSize: 12,
        borderRadius: 6,
        border: `1px solid ${isOpen ? "var(--accent)" : "var(--border)"}`,
        background: isOpen ? "var(--accent)" : "var(--elevated-bg)",
        color: isOpen ? "#fff" : "var(--text-muted)",
        cursor: "pointer",
        transition: "all 0.15s ease",
        fontFamily: "inherit",
        userSelect: "none" as const,
        flexShrink: 0,
      }}
    >
      <span style={{ fontSize: 13 }}>◫</span>
      {count > 0 && (
        <span style={{
          background: isOpen ? "rgba(255,255,255,0.25)" : "var(--accent)",
          color: isOpen ? "#fff" : "#fff",
          borderRadius: 8,
          padding: "0 5px",
          fontSize: 10,
          fontWeight: 700,
          lineHeight: "16px",
          minWidth: 16,
          textAlign: "center",
        }}>{count}</span>
      )}
    </button>
  );
}

// ── Composant ──────────────────────────────────────────────────────────────

export function ChatPanel({
  convId,
  ragEnabled: initialRagEnabled = false,
  ragCollection = null,
  onCollectionChange,
  onTitleChange,
  onTokenUsage,
  onModelUsage,
  onFamilyRouting,
  currentProfile = null,
  onProfileChange,
  username,
  onClearRequest,
  folders = [],
  onRenameConv,
  onStarConv,
  onMoveConv,
  onClearConv,
}: ChatPanelProps) {

  const { state, messages, send, cancel, clearMessages, addMessage } =
    useAgentStream(convId);
  React.useEffect(() => { onClearRequest?.(clearMessages); }, [onClearRequest, clearMessages]);

  // ── État local ────────────────────────────────────────────────────────────
  const [agentMode, setAgentMode] = useState(false);
  const [maxIterations, setMaxIterations] = useState(6);
  const [disableContextManagement, setDisableContextManagement] = useState(false);
  const [ragEnabled, setRagEnabled] = useState(initialRagEnabled);
  const [ragAvailable, setRagAvailable] = useState(false);
  const [ragStatus, setRagStatus] = useState<
    | { kind: "idle" }
    | { kind: "ok"; chunks: number }
    | { kind: "warn"; error: string }
  >({ kind: "idle" });
  const [allTools, setAllTools] = useState<{ enabled: boolean; family: string }[]>([]);

  // Comptage outils actifs selon le profil courant.
  // Le profil peut activer/désactiver des familles par rapport aux réglages globaux.
  const activeToolCount = useMemo(() => {
    const tf = currentProfile?.tool_families;
    return allTools.filter((tool) => {
      if (!tf) return tool.enabled;
      if (tf.enabled?.includes(tool.family)) return true;
      if (tf.disabled?.includes(tool.family)) return false;
      return tool.enabled;
    }).length;
  }, [allTools, currentProfile]);
  const [historyLoaded, setHistoryLoaded] = useState(false);
  const [titleUpdated, setTitleUpdated] = useState(false);
  const [convTitle, setConvTitle]   = useState("");
  const [isStarred, setIsStarred]   = useState(false);

  const scrollBottomRef = useRef<HTMLDivElement>(null);
  const scrollAreaRef   = useRef<HTMLDivElement>(null);
  const splitContainerRef = useRef<HTMLDivElement>(null);
  const isFirstMessageRef = useRef(true);
  const [showScrollBtn, setShowScrollBtn] = useState(false);

  // ── Split-view ────────────────────────────────────────────────────────────
  const {
    artifacts,
    activeIdx,
    panelOpen,
    toggle: toggleArtifactPanel,
    selectArtifact,
  } = useArtifactPanel(messages, state.isGenerating);

  const { leftWidth, onDragStart, isDragging } = useSplitPane(splitContainerRef);

  // ── Chargement initial ────────────────────────────────────────────────────

  useEffect(() => {
    if (!convId) return;

    clearMessages();
    setHistoryLoaded(false);
    setTitleUpdated(false);
    setConvTitle("");
    setIsStarred(false);
    isFirstMessageRef.current = true;

    // Charger les métadonnées de la conversation (titre, favori)
    api
      .get<{ id: string; title: string; starred: boolean }>(`/conversations/${convId}`)
      .then((conv) => {
        setConvTitle(conv.title ?? "");
        setIsStarred(conv.starred ?? false);
      })
      .catch(() => {});

    api
      .get<{ id: string; role: string; content: string; created_at: string }[]>(
        `/conversations/${convId}/messages`
      )
      .then((msgs) => {
        msgs.forEach((m) =>
          addMessage({
            id: m.id,
            role: m.role as ChatMessage["role"],
            content: m.content,
          })
        );
        setHistoryLoaded(true);
        if (msgs.length > 0) isFirstMessageRef.current = false;
      })
      .catch(console.error);

    api
      .get<{ available: boolean }>("/rag/status")
      .then((r) => setRagAvailable(r.available))
      .catch(() => setRagAvailable(false));

    api
      .get<{ enabled: boolean; family: string }[]>("/tools")
      .then((tools) => setAllTools(tools))
      .catch(() => setAllTools([]));
  }, [convId]);

  // ── Scroll automatique ────────────────────────────────────────────────────

  const scrollToBottom = useCallback((smooth = true) => {
    scrollBottomRef.current?.scrollIntoView({ behavior: smooth ? "smooth" : "instant" });
  }, []);

  useEffect(() => {
    const el = scrollAreaRef.current;
    if (!el) return;
    const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
    if (distanceFromBottom < 120) {
      scrollToBottom();
    }
  }, [messages.length, state.streamingText, scrollToBottom]);

  useEffect(() => {
    const el = scrollAreaRef.current;
    if (!el) return;
    const handleScroll = () => {
      const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
      setShowScrollBtn(distanceFromBottom > 200);
    };
    el.addEventListener("scroll", handleScroll, { passive: true });
    return () => el.removeEventListener("scroll", handleScroll);
  }, []);

  // ── Propagation des événements vers le parent ─────────────────────────────

  useEffect(() => {
    if (state.usage && onTokenUsage) onTokenUsage(state.usage);
  }, [state.usage]);

  useEffect(() => {
    if (onFamilyRouting) onFamilyRouting(state.familyRouting ?? null);
  }, [state.familyRouting]);

  // ── Envoi ─────────────────────────────────────────────────────────────────

  const handleSend = useCallback(
    async (text: string, attachments: AttachmentItem[], profileName: string | null, profileIsPersonal: boolean = false) => {
      if (!text && attachments.length === 0) return;
      if (state.isGenerating) return;

      if (isFirstMessageRef.current && text && !titleUpdated) {
        isFirstMessageRef.current = false;
        const title = text.slice(0, 50) + (text.length > 50 ? "…" : "");
        api
          .patch(`/conversations/${convId}`, { title })
          .then(() => {
            setTitleUpdated(true);
            setConvTitle(title);
            onTitleChange?.(convId, title);
          })
          .catch(console.error);
      }

      const displayText = buildDisplayText(text, attachments);
      const userMessage: ChatMessage = {
        id: Math.random().toString(36).slice(2),
        role: "user",
        content: displayText,
      };

      const apiMessages = buildApiHistory(messages, text, attachments);

      // Le system_prompt RAG reste assemblé côté client (données de session).
      // Le prompt de profil + skills épinglés sont assemblés côté serveur
      // à partir du profile_name — on ne passe plus system_prompt ici.
      let ragSystemPrompt = "";
      if (ragEnabled && ragAvailable) {
        try {
          const ragCtx = await buildRagContext(text, convId, ragCollection);
          if (ragCtx) {
            ragSystemPrompt = ragCtx;
            // Estimation du nombre de chunks : on compte les blocs "[N]" dans le contexte
            const chunkCount = (ragCtx.match(/^\[\d+\]/gm) ?? []).length;
            setRagStatus({ kind: "ok", chunks: chunkCount });
          } else {
            setRagStatus({ kind: "ok", chunks: 0 });
          }
        } catch (e) {
          const msg = e instanceof Error ? e.message : String(e);
          console.warn("[rag] context error", e);
          setRagStatus({ kind: "warn", error: msg });
        }
      } else {
        setRagStatus({ kind: "idle" });
      }

      const payload: SendPayload = {
        messages: apiMessages,
        profile_name: profileName,
        profile_is_personal: profileIsPersonal,
        // system_prompt contient uniquement le contexte RAG si présent.
        // Le serveur le concatène après le prompt de profil + skills.
        system_prompt: ragSystemPrompt,
        use_tools: agentMode,
        max_iterations: maxIterations,
        disable_context_management: disableContextManagement,
        save_user_message: buildSaveText(text, attachments),
      };

      send(payload, userMessage);
    },
    [
      convId,
      messages,
      ragEnabled,
      ragAvailable,
      ragCollection,
      agentMode,
      maxIterations,
      disableContextManagement,
      state.isGenerating,
      send,
      titleUpdated,
      onTitleChange,
    ]
  );

  // ── Rendu ──────────────────────────────────────────────────────────────────

  const lastMsgId =
    state.isGenerating && messages.length > 0
      ? messages[messages.length - 1].id
      : null;

  return (
    <div
      ref={splitContainerRef}
      style={{
        ...s.root,
        cursor: isDragging ? "col-resize" : undefined,
        userSelect: isDragging ? "none" : undefined,
      }}
    >
      {/* ── Panneau gauche : chat ────────────────────────────────────── */}
      <div
        style={{
          ...s.chatPane,
          width: panelOpen ? leftWidth : "100%",
          flexShrink: 0,
        }}
      >
        {/* Barre du haut avec métriques + toggle artefacts */}
        <div style={s.chatTopBar}>
          {/* Zone gauche — métriques */}
          <MetricsBar
            convId={convId}
            convTitle={convTitle}
            isStarred={isStarred}
            folders={folders}
            onRenameConv={async (id, title) => {
              await onRenameConv?.(id, title);
              setConvTitle(title);
            }}
            onStarConv={async (id, starred) => {
              await onStarConv?.(id, starred);
              setIsStarred(starred);
            }}
            onMoveConv={onMoveConv}
            onClearConv={onClearConv}
            livePrompt={state.usage?.prompt}
            liveCompletion={state.usage?.completion}
            isGenerating={state.isGenerating}
            ragStatus={ragEnabled && ragAvailable ? ragStatus : { kind: "idle" }}
          />
          {/* Titre centré — position absolue pour ne pas déplacer les autres éléments */}
          {convId && (
            <div style={{
              position: "absolute",
              left: "50%",
              transform: "translateX(-50%)",
              display: "flex",
              alignItems: "center",
              pointerEvents: "none",
              zIndex: 10,
            }}>
              <div style={{ pointerEvents: "auto" }}>
                <ConvTitleWidget
                  convId={convId}
                  title={convTitle}
                  isStarred={isStarred}
                  folders={folders}
                  onRename={async (id: string, title: string) => { await onRenameConv?.(id, title); setConvTitle(title); }}
                  onStar={async (id: string, starred: boolean) => { await onStarConv?.(id, starred); setIsStarred(starred); }}
                  onMove={onMoveConv}
                  onClear={onClearConv}
                />
              </div>
            </div>
          )}
          {/* Zone droite — bouton artefacts (flexShrink:0 pour rester visible) */}
          <div style={{ flex: 1 }} />
          <ArtifactToggleBtn
            isOpen={panelOpen}
            count={artifacts.length}
            onToggle={toggleArtifactPanel}
          />
        </div>

        {/* Zone messages */}
        <div style={s.messagesAreaWrapper}>
          <div ref={scrollAreaRef} style={s.messagesArea}>
            <div style={s.messagesInner}>
              {!historyLoaded && (
                <div style={s.loading}>Chargement de l'historique…</div>
              )}

              {messages.map((msg) => (
                <MessageBubble
                  key={msg.id}
                  message={msg}
                  isStreaming={msg.id === lastMsgId && state.isGenerating}
                  username={username}
                />
              ))}

              {state.isGenerating && !state.streamingText && !state.toolsBubble && (
                <TypingIndicator />
              )}

              <div ref={scrollBottomRef} />
            </div>
          </div>

          <ScrollToBottomBtn
            visible={showScrollBtn}
            onClick={() => { scrollToBottom(true); setShowScrollBtn(false); }}
          />
        </div>

        {/* Zone de saisie */}
        <ChatInput
          onSend={handleSend}
          onCancel={cancel}
          isGenerating={state.isGenerating}
          ragEnabled={ragEnabled}
          onToggleRag={() => {
            if (!ragAvailable && !ragEnabled) return;
            setRagEnabled((v) => !v);
          }}
          ragAvailable={ragAvailable}
          ragCollection={ragCollection}
          onCollectionChange={onCollectionChange}
          agentMode={agentMode}
          onToggleAgent={setAgentMode}
          maxIterations={maxIterations}
          onIterationsChange={setMaxIterations}
          disableContextManagement={disableContextManagement}
          onToggleContextManagement={setDisableContextManagement}
          activeToolCount={activeToolCount}
          statusMessage={state.statusMessage ?? ""}
          externalProfile={currentProfile}
          onProfileChange={onProfileChange}
        />
      </div>

      {/* ── Séparateur drag ──────────────────────────────────────────── */}
      {panelOpen && (
        <div
          style={s.divider}
          onMouseDown={onDragStart}
          title="Redimensionner"
        >
          <div style={s.dividerHandle} />
        </div>
      )}

      {/* ── Panneau droit : artefacts ────────────────────────────────── */}
      {panelOpen && (
        <div style={s.artifactPane}>
          <ArtifactPanel
            artifacts={artifacts}
            activeIdx={activeIdx}
            onSelectArtifact={selectArtifact}
            onClose={toggleArtifactPanel}
          />
        </div>
      )}
    </div>
  );
}

// ── Typing indicator ──────────────────────────────────────────────────────

function TypingIndicator() {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 4, padding: "8px 0", opacity: 0.7 }}>
      <span style={{ fontSize: 11, color: "var(--text-muted)" }}>IA</span>
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          style={{
            width: 6,
            height: 6,
            borderRadius: "50%",
            background: "var(--accent)",
            display: "inline-block",
            animation: `bounce 1.2s ease-in-out ${i * 0.2}s infinite`,
          }}
        />
      ))}
      <style>{`
        @keyframes bounce {
          0%, 60%, 100% { transform: translateY(0); opacity: 0.4; }
          30%            { transform: translateY(-6px); opacity: 1; }
        }
      `}</style>
    </div>
  );
}

// ── Helpers ───────────────────────────────────────────────────────────────

function buildDisplayText(text: string, attachments: AttachmentItem[]): string {
  if (!attachments.length) return text;
  const summary = attachments
    .map((a) =>
      a.type === "image" ? `[IMG] ${a.name}` :
      a.type === "url"   ? `🔗 ${a.url?.slice(0, 30)}…` :
                           `[F] ${a.name}`
    )
    .join(", ");
  return `${text}\n\n_Attachements : ${summary}_`;
}

function buildSaveText(text: string, attachments: AttachmentItem[]): string {
  if (!attachments.length) return text;
  const parts: string[] = [];
  if (text.trim()) parts.push(text);
  attachments.forEach((att) => {
    if (att.type === "file" && att.content) {
      parts.push(`--- Fichier '${att.name}' ---\n${att.content}\n---`);
    } else if (att.type === "image") {
      parts.push(`[Image : ${att.name}]`);
    } else if (att.type === "url" && att.url) {
      parts.push(`[URL : ${att.url}]`);
    }
  });
  return parts.join("\n\n");
}

function buildApiHistory(
  messages: ChatMessage[],
  newText: string,
  attachments: AttachmentItem[]
): { role: string; content: string | any[] }[] {
  const history: { role: string; content: string | any[] }[] = messages
    .filter((m) => m.role !== "system" && m.content.trim())
    .map((m) => ({ role: m.role, content: m.content }));

  if (attachments.length > 0) {
    const parts: any[] = [];
    if (newText.trim()) parts.push({ type: "text", text: newText });
    attachments.forEach((att) => {
      if (att.type === "image" && att.base64) {
        parts.push({
          type: "image_url",
          image_url: {
            url: `data:${att.mimeType || "image/jpeg"};base64,${att.base64}`,
          },
        });
      } else if (att.type === "file" && att.content) {
        parts.push({
          type: "text",
          text: `\n\n--- Fichier '${att.name}' ---\n${att.content}\n---`,
        });
      }
    });
    history.push({ role: "user", content: parts });
  } else {
    history.push({ role: "user", content: newText });
  }

  return history;
}

async function buildRagContext(
  query: string,
  convId: string,
  collection: string | null
): Promise<string> {
  const params = new URLSearchParams({ query, conv_id: convId });
  if (collection) params.set("collection_name", collection);
  const res = await api.get<{ context: string }>(`/rag/context?${params}`);
  return res.context ?? "";
}

// ── Styles ────────────────────────────────────────────────────────────────

const s: Record<string, React.CSSProperties> = {
  root: {
    display: "flex",
    flexDirection: "row",
    height: "100%",
    background: "var(--base-bg)",
    overflow: "hidden",
  },

  // ── Panneau chat ────────────────────────────────────────────────────────
  chatPane: {
    display: "flex",
    flexDirection: "column",
    height: "100%",
    overflow: "hidden",
    minWidth: 0,
    flexGrow: 1,
  },
  chatTopBar: {
    display: "flex",
    alignItems: "center",
    padding: "6px 16px",
    borderBottom: "1px solid var(--border)",
    background: "var(--base-bg)",
    minHeight: 40,
    flexShrink: 0,
    gap: 8,
    overflow: "visible",
    position: "relative",
    zIndex: 20,
  },
  messagesAreaWrapper: {
    flex: 1,
    position: "relative",
    overflow: "hidden",
    display: "flex",
    flexDirection: "column",
  },
  messagesArea: {
    flex: 1,
    overflowY: "auto",
    overflowX: "hidden",
  },
  messagesInner: {
    width: 940,
    maxWidth: "100%",
    margin: "0 auto",
    padding: "24px 0",
    boxSizing: "border-box" as const,
  },
  loading: {
    color: "var(--text-muted)",
    fontSize: 13,
    textAlign: "center",
    padding: "16px 0",
  },

  // ── Séparateur ─────────────────────────────────────────────────────────
  divider: {
    width: 8,
    flexShrink: 0,
    cursor: "col-resize",
    background: "transparent",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    position: "relative",
    zIndex: 10,
    transition: "background 0.15s",
  },
  dividerHandle: {
    width: 2,
    height: 40,
    borderRadius: 2,
    background: "var(--border-active)",
    transition: "background 0.15s, height 0.15s",
  },

  // ── Panneau artefacts ──────────────────────────────────────────────────
  artifactPane: {
    flex: 1,
    minWidth: 280,
    height: "100%",
    overflow: "hidden",
    borderLeft: "1px solid var(--border)",
  },
};
