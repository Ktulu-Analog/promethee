# Protocole WebSocket — Prométhée

## Vue d'ensemble

Un WebSocket est ouvert par conversation active.

```
ws://localhost:8000/ws/chat/{conv_id}
```

---

## Flux de la session

```
Client                          Serveur
  |                                |
  |──── WebSocket connect ────────>|
  |──── ChatPayload JSON ─────────>|  (1 seul message pour démarrer)
  |                                |── asyncio.to_thread(agent_loop) ──>
  |<─── { t:"token", d:"Bon" } ───|
  |<─── { t:"token", d:"jour" } ──|
  |<─── { t:"tool_called", ... } ─|
  |<─── { t:"tool_result", ... } ─|
  |<─── { t:"token", d:"..." } ───|
  |<─── { t:"usage", ... } ───────|
  |<─── { t:"finished", text } ───|
  |                                |──── WebSocket close ──────────────>
```

Pour annuler pendant la génération :
```
Client
  |──── { "action": "cancel" } ──>|
  |<─── { t:"cancelled", text } ──|
```

---

## Message entrant : ChatPayload

```typescript
interface ChatPayload {
  messages: { role: string; content: any }[];   // historique OpenAI
  system_prompt?: string;                        // défaut: ""
  model?: string | null;                         // défaut: Config.active_model
  use_tools?: boolean;                           // défaut: true
  max_iterations?: number;                       // défaut: 8
  disable_context_management?: boolean;          // défaut: false
  save_user_message?: string | null;             // persiste en DB si fourni
}
```

---

## Messages sortants

Tous les messages sont du JSON avec un champ `t` (type).

### Streaming de tokens

```typescript
{ t: "token"; d: string }
```
Émis pour chaque token de la réponse finale. Accumuler dans un state pour
afficher le texte en cours de génération.

### Outils

```typescript
{ t: "tool_called"; name: string; args: string }
// → afficher la bulle "outils en cours"

{ t: "tool_result"; name: string }
// → mettre à jour la bulle (résultat reçu, génération en cours)

{ t: "tool_image"; mime: string; data: string }
// → afficher l'image inline (data est base64)

{ t: "tool_progress"; msg: string }
// → mise à jour de progression dans la bulle outil
```

### Événements internes

```typescript
{ t: "context_event"; msg: string }
// → notification discrète (trim/compression du contexte)

{ t: "memory_event"; msg: string }
// → notification mémoire de session (consolidation, pinning)

{ t: "family_routing"; family: string; label: string; model: string; backend: string }
// → le modèle actif a changé (famille d'outils)
// family == "" → retour au modèle principal

{ t: "compression_stats"; op_type: string; before: int; after: int; saved: int; pct: float }
// → pour MonitoringPanel
```

### Tokens et usage

```typescript
{ t: "usage"; prompt: number; completion: number; total: number }
// → mise à jour du compteur de tokens

{ t: "model_usage"; model: string; prompt: number; completion: number; role: string }
// role: "decision" | "final" | "stream"
// → pour ModelUsagePanel (breakdown par modèle)
```

### Fin de génération

```typescript
{ t: "finished"; text: string }
// → texte complet persisté en DB

{ t: "cancelled"; text: string }
// → annulé par l'utilisateur, texte partiel

{ t: "error"; msg: string }
// → erreur, afficher dans le chat
```

---

## Hook React — useAgentStream

```typescript
// hooks/useAgentStream.ts
import { useRef, useState, useCallback } from "react";

type WsMsg =
  | { t: "token"; d: string }
  | { t: "tool_called"; name: string; args: string }
  | { t: "tool_result"; name: string }
  | { t: "tool_image"; mime: string; data: string }
  | { t: "tool_progress"; msg: string }
  | { t: "context_event"; msg: string }
  | { t: "memory_event"; msg: string }
  | { t: "family_routing"; family: string; label: string; model: string; backend: string }
  | { t: "usage"; prompt: number; completion: number; total: number }
  | { t: "model_usage"; model: string; prompt: number; completion: number; role: string }
  | { t: "finished"; text: string }
  | { t: "cancelled"; text: string }
  | { t: "error"; msg: string };

export interface StreamState {
  streamingText: string;         // tokens accumulés (en cours)
  toolsBubble: string | null;    // markdown de la bulle outils
  isGenerating: boolean;
  usage: { prompt: number; completion: number; total: number } | null;
  error: string | null;
}

export function useAgentStream(convId: string) {
  const wsRef = useRef<WebSocket | null>(null);
  const [state, setState] = useState<StreamState>({
    streamingText: "",
    toolsBubble: null,
    isGenerating: false,
    usage: null,
    error: null,
  });

  // Noms des outils appelés ce tour (pour reconstruire la bulle)
  const toolsCalledRef = useRef<string[]>([]);

  function _buildToolsBubble(suffix = ""): string {
    const parts = toolsCalledRef.current.map((n) => `🔧 *${n}*`);
    return parts.join("  ·  ") + (suffix ? `\n\n${suffix}` : "");
  }

  const send = useCallback(
    (payload: object, onFinished: (text: string) => void) => {
      toolsCalledRef.current = [];
      setState({ streamingText: "", toolsBubble: null, isGenerating: true, usage: null, error: null });

      const ws = new WebSocket(`ws://localhost:8000/ws/chat/${convId}`);
      wsRef.current = ws;

      ws.onmessage = (e) => {
        const msg: WsMsg = JSON.parse(e.data);

        switch (msg.t) {
          case "token":
            setState((s) => ({ ...s, streamingText: s.streamingText + msg.d }));
            break;

          case "tool_called":
            toolsCalledRef.current.push(msg.name);
            setState((s) => ({ ...s, toolsBubble: _buildToolsBubble() }));
            break;

          case "tool_progress":
            setState((s) => ({ ...s, toolsBubble: _buildToolsBubble(`_${msg.msg}_`) }));
            break;

          case "tool_result":
            setState((s) => ({ ...s, toolsBubble: _buildToolsBubble() }));
            break;

          case "usage":
            setState((s) => ({
              ...s,
              usage: { prompt: msg.prompt, completion: msg.completion, total: msg.total },
            }));
            break;

          case "finished":
          case "cancelled":
            setState((s) => ({
              ...s,
              streamingText: "",
              toolsBubble: null,
              isGenerating: false,
            }));
            onFinished(msg.text);
            ws.close();
            break;

          case "error":
            setState((s) => ({ ...s, isGenerating: false, error: msg.msg }));
            ws.close();
            break;
        }
      };

      ws.onerror = () =>
        setState((s) => ({ ...s, isGenerating: false, error: "Connexion WebSocket perdue." }));

      ws.onopen = () => ws.send(JSON.stringify(payload));
    },
    [convId]
  );

  const cancel = useCallback(() => {
    wsRef.current?.send(JSON.stringify({ action: "cancel" }));
  }, []);

  return { state, send, cancel };
}
```

---

## Points d'attention multi-utilisateurs

Le serveur utilise actuellement `_generation_lock` (asyncio.Lock) pour
sérialiser les générations : une seule à la fois, toutes conversations
confondues. C'est le comportement sûr compte tenu des globals module-level
de `llm_events.py`.

**Pour passer en multi-utilisateurs simultanés**, implémenter l'Option B :

```python
# core/llm_events.py — remplacer les globals par des ContextVar
import contextvars

_cancel_cv: contextvars.ContextVar[Callable[[], bool] | None] = \
    contextvars.ContextVar("_cancel_cv", default=None)

def set_cancel_callback(fn): _cancel_cv.set(fn)
def is_cancelled(): fn = _cancel_cv.get(); return fn is not None and fn()
```

Même chose pour tous les autres callbacks (`_context_event_callback`, etc.).
`asyncio.to_thread()` propage automatiquement le contexte d'exécution.
