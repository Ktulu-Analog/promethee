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
 * useAgentStream.ts
 *
 *
 * Machine à états
 *
 * Gestion du thread-safety :
 *   Les messages WS arrivent dans la boucle event JS (single-thread),
 *   donc pas de race condition — setState() est toujours sûr.
 */

import { useRef, useState, useCallback, useEffect } from "react";
import { getToken } from "./useAuth";

// ── Types ──────────────────────────────────────────────────────────────────

export interface ChatMessage {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  /** Pour les images générées par outils */
  imageUri?: string;
  /** Marqueur d'interruption (cancelled) */
  cancelled?: boolean;
  /** Marqueur d'erreur */
  isError?: boolean;
}

export type WsInMsg =
  | { t: "token";            d: string }
  | { t: "tool_called";      name: string; args: string }
  | { t: "tool_result";      name: string }
  | { t: "tool_image";       mime: string; data: string }
  | { t: "tool_progress";    msg: string }
  | { t: "context_event";    msg: string }
  | { t: "memory_event";     msg: string }
  | { t: "family_routing";   family: string; label: string; model: string; backend: string }
  | { t: "usage";            prompt: number; completion: number; total: number }
  | { t: "model_usage";      model: string; prompt: number; completion: number; role: string }
  | { t: "compression_stats"; op_type: string; before: number; after: number; saved: number; pct: number }
  | { t: "finished";         text: string }
  | { t: "cancelled";        text: string }
  | { t: "error";            msg: string };

export interface UsageStats {
  prompt: number;
  completion: number;
  total: number;
}

export interface FamilyRouting {
  family: string;
  label: string;
  model: string;
  backend: string;
}

export interface StreamState {
  /** Tokens accumulés pendant le streaming (vidé à finished/cancelled) */
  streamingText: string;
  /**
   * Markdown de la bulle "outils en cours".
   * Null quand aucun outil n'est appelé.
   * Équivalent de _tool_bubble + _build_tools_mention() dans StreamingHandler.
   */
  toolsBubble: string | null;
  isGenerating: boolean;
  usage: UsageStats | null;
  familyRouting: FamilyRouting | null;
  error: string | null;
  statusMessage: string;
}

export interface UseAgentStreamReturn {
  state: StreamState;
  messages: ChatMessage[];
  send: (payload: SendPayload, userMessage: ChatMessage) => void;
  cancel: () => void;
  clearMessages: () => void;
  addMessage: (msg: ChatMessage) => void;
}

export interface SendPayload {
  messages: { role: string; content: any }[];
  profile_name?: string | null;
  profile_is_personal?: boolean;
  system_prompt?: string;
  model?: string | null;
  use_tools?: boolean;
  max_iterations?: number;
  disable_context_management?: boolean;
  save_user_message?: string | null;
}

// ── Hook ──────────────────────────────────────────────────────────────────

const WS_BASE = import.meta.env.VITE_WS_URL ?? "ws://localhost:8000";

function makeId() {
  return Math.random().toString(36).slice(2, 10);
}

export function useAgentStream(convId: string | null): UseAgentStreamReturn {
  const wsRef = useRef<WebSocket | null>(null);

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [state, setState] = useState<StreamState>({
    streamingText: "",
    toolsBubble: null,
    isGenerating: false,
    usage: null,
    familyRouting: null,
    error: null,
    statusMessage: "Prêt",
  });

  // Accumulateur de tokens (ref pour éviter les closures périmées)
  const streamingTextRef = useRef("");
  // Liste ordonnée des outils appelés ce tour (même logique que _tools_called)
  const toolsCalledRef = useRef<string[]>([]);
  // ID du message assistant en cours de streaming (pour le retrouver et le mettre à jour)
  const streamingMsgIdRef = useRef<string | null>(null);
  // ID de la bulle outils (pour la mettre à jour sans en créer une nouvelle)
  const toolsBubbleMsgIdRef = useRef<string | null>(null);

  // Fermeture propre au démontage du composant
  useEffect(() => {
    return () => {
      wsRef.current?.close();
    };
  }, []);

  // Reconstruire le markdown de la bulle outils — identique à _build_tools_mention()
  function _buildToolsBubble(suffix = ""): string {
    const parts = toolsCalledRef.current.map((n) => `🔧 *${n}*`);
    return parts.join("  ·  ") + (suffix ? `\n\n${suffix}` : "");
  }

  // ── Gestionnaire de messages WS ────────────────────────────────────────

  function handleWsMessage(msg: WsInMsg) {
    switch (msg.t) {

      // ── Token ────────────────────────────────────────────────────────────
      case "token": {
        streamingTextRef.current += msg.d;
        const accumulated = streamingTextRef.current;

        // Si aucun message assistant n'existe encore, en créer un
        if (!streamingMsgIdRef.current) {
          const id = makeId();
          streamingMsgIdRef.current = id;
          setMessages((prev) => [
            ...prev,
            { id, role: "assistant", content: accumulated },
          ]);
        } else {
          // Mettre à jour le contenu du message existant
          const id = streamingMsgIdRef.current;
          setMessages((prev) =>
            prev.map((m) => (m.id === id ? { ...m, content: accumulated } : m))
          );
        }
        setState((s) => ({ ...s, streamingText: accumulated }));
        break;
      }

      // ── Outil appelé ─────────────────────────────────────────────────────
      case "tool_called": {
        toolsCalledRef.current.push(msg.name);
        const bubble = _buildToolsBubble();

        if (!toolsBubbleMsgIdRef.current) {
          // Premier appel : créer la bulle outils
          const id = makeId();
          toolsBubbleMsgIdRef.current = id;
          setMessages((prev) => [
            ...prev,
            { id, role: "assistant", content: bubble },
          ]);
        } else {
          // Appels suivants : mettre à jour la bulle existante
          const id = toolsBubbleMsgIdRef.current;
          setMessages((prev) =>
            prev.map((m) => (m.id === id ? { ...m, content: bubble } : m))
          );
        }
        setState((s) => ({
          ...s,
          toolsBubble: bubble,
          statusMessage: `🔧 ${msg.name}…`,
        }));
        break;
      }

      // ── Progression d'outil ───────────────────────────────────────────────
      case "tool_progress": {
        const bubble = _buildToolsBubble(`_${msg.msg}_`);
        if (toolsBubbleMsgIdRef.current) {
          const id = toolsBubbleMsgIdRef.current;
          setMessages((prev) =>
            prev.map((m) => (m.id === id ? { ...m, content: bubble } : m))
          );
        }
        setState((s) => ({ ...s, toolsBubble: bubble, statusMessage: msg.msg }));
        break;
      }

      // ── Résultat d'outil ──────────────────────────────────────────────────
      case "tool_result": {
        const bubble = _buildToolsBubble();
        if (toolsBubbleMsgIdRef.current) {
          const id = toolsBubbleMsgIdRef.current;
          setMessages((prev) =>
            prev.map((m) => (m.id === id ? { ...m, content: bubble } : m))
          );
        }
        setState((s) => ({
          ...s,
          toolsBubble: bubble,
          statusMessage: `✓ ${msg.name} — génération de la réponse…`,
        }));
        break;
      }

      // ── Image générée par outil ───────────────────────────────────────────
      case "tool_image": {
        const dataUri = `data:${msg.mime};base64,${msg.data}`;
        setMessages((prev) => [
          ...prev,
          { id: makeId(), role: "assistant", content: "", imageUri: dataUri },
        ]);
        break;
      }

      // ── Usage de tokens ───────────────────────────────────────────────────
      case "usage": {
        setState((s) => ({
          ...s,
          usage: { prompt: msg.prompt, completion: msg.completion, total: msg.total },
        }));
        break;
      }

      // ── Routing de famille ────────────────────────────────────────────────
      case "family_routing": {
        setState((s) => ({
          ...s,
          familyRouting: msg.family
            ? { family: msg.family, label: msg.label, model: msg.model, backend: msg.backend }
            : null,
          statusMessage: msg.family ? `Modèle : ${msg.label} (${msg.model})` : "Prêt",
        }));
        break;
      }

      // ── Événements internes (contexte, mémoire) ───────────────────────────
      case "context_event":
      case "memory_event": {
        setState((s) => ({ ...s, statusMessage: msg.msg }));
        break;
      }

      // ── Fin de génération ─────────────────────────────────────────────────
      case "finished": {
        _finalizeGeneration(msg.text, false);
        break;
      }

      case "cancelled": {
        _finalizeGeneration(msg.text, true);
        break;
      }

      // ── Erreur ────────────────────────────────────────────────────────────
      case "error": {
        // Créer un message d'erreur visible dans le chat
        setMessages((prev) => [
          ...prev,
          {
            id: makeId(),
            role: "assistant",
            content: `**Erreur** : \`${msg.msg}\``,
            isError: true,
          },
        ]);
        _resetStreamState();
        setState((s) => ({
          ...s,
          isGenerating: false,
          error: msg.msg,
          statusMessage: `Erreur : ${msg.msg.slice(0, 60)}`,
        }));
        break;
      }
    }
  }

  function _finalizeGeneration(fullText: string, cancelled: boolean) {
    // Mettre à jour le dernier message assistant avec le texte final
    if (streamingMsgIdRef.current) {
      const id = streamingMsgIdRef.current;
      setMessages((prev) =>
        prev.map((m) =>
          m.id === id ? { ...m, content: fullText, cancelled } : m
        )
      );
    } else if (fullText.trim()) {
      // Aucun token reçu avant finished (cas rare) : créer le message maintenant
      setMessages((prev) => [
        ...prev,
        { id: makeId(), role: "assistant", content: fullText, cancelled },
      ]);
    }

    // Message d'annulation visuel (équivalent du widget "⏹ Réponse interrompue")
    if (cancelled && fullText.trim()) {
      setMessages((prev) => [
        ...prev,
        {
          id: makeId(),
          role: "assistant",
          content: "*⏹ Réponse interrompue par l'utilisateur.*",
          cancelled: true,
        },
      ]);
    }

    _resetStreamState();
    setState((s) => ({
      ...s,
      streamingText: "",
      toolsBubble: null,
      isGenerating: false,
      error: null,
      statusMessage: cancelled ? "Arrêté" : "Prêt",
    }));
  }

  function _resetStreamState() {
    streamingTextRef.current = "";
    toolsCalledRef.current = [];
    streamingMsgIdRef.current = null;
    toolsBubbleMsgIdRef.current = null;
  }

  // ── API publique ───────────────────────────────────────────────────────

  const send = useCallback(
    (payload: SendPayload, userMessage: ChatMessage) => {
      if (!convId) return;
      if (wsRef.current) {
        wsRef.current.close();
      }

      // Ajouter le message utilisateur immédiatement
      setMessages((prev) => [...prev, userMessage]);
      _resetStreamState();
      setState((s) => ({
        ...s,
        streamingText: "",
        toolsBubble: null,
        isGenerating: true,
        error: null,
        statusMessage: "Génération en cours…",
      }));

      const _tok = getToken();
      const _wsUrl = _tok
        ? `${WS_BASE}/ws/chat/${convId}?token=${encodeURIComponent(_tok)}`
        : `${WS_BASE}/ws/chat/${convId}`;
      const ws = new WebSocket(_wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        ws.send(JSON.stringify(payload));
      };

      ws.onmessage = (e) => {
        try {
          const msg: WsInMsg = JSON.parse(e.data);
          handleWsMessage(msg);
        } catch (err) {
          console.error("[ws] Parse error:", err);
        }
      };

      ws.onerror = () => {
        setMessages((prev) => [
          ...prev,
          {
            id: makeId(),
            role: "assistant",
            content: "**Erreur** : connexion WebSocket perdue.",
            isError: true,
          },
        ]);
        _resetStreamState();
        setState((s) => ({
          ...s,
          isGenerating: false,
          error: "Connexion WebSocket perdue",
          statusMessage: "Erreur de connexion",
        }));
      };

      ws.onclose = () => {
        wsRef.current = null;
      };
    },
    [convId]
  );

  const cancel = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ action: "cancel" }));
    }
  }, []);

  const clearMessages = useCallback(() => {
    setMessages([]);
    _resetStreamState();
  }, []);

  const addMessage = useCallback((msg: ChatMessage) => {
    setMessages((prev) => [...prev, msg]);
  }, []);

  return { state, messages, send, cancel, clearMessages, addMessage };
}
