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
 * useArtifactPanel.ts
 *
 * Détecte automatiquement les "artefacts" dans les messages IA :
 *   - Blocs de code (```lang ... ```)
 *   - Tableaux Markdown (lignes | ... |)
 *   - Documents Markdown longs (> seuil de lignes, avec titres)
 *   - Images générées (imageUri)
 *
 * Retourne l'artefact le plus récent et un flag pour l'ouverture auto.
 *
 * Logique d'ouverture automatique :
 *   - S'ouvre dès qu'un artefact riche est détecté dans le dernier message IA
 *   - Ne se ferme PAS automatiquement (l'utilisateur garde le contrôle)
 *   - Toggle manuel toujours disponible
 */

import { useMemo, useRef, useEffect, useState } from "react";
import type { ChatMessage } from "./useAgentStream";

// ── Types ──────────────────────────────────────────────────────────────────

export type ArtifactKind = "code" | "table" | "document" | "image" | "full" | "echarts";

export interface Artifact {
  id: string;
  kind: ArtifactKind;
  language?: string;     // pour "code"
  content: string;       // markdown, code ou data URI
  title: string;
  messageId: string;
}

export interface ArtifactPanelState {
  artifacts: Artifact[];
  activeIdx: number;
  isOpen: boolean;
  autoOpened: boolean;
}

// ── Seuils ─────────────────────────────────────────────────────────────────

const MIN_CODE_LINES   = 4;   // blocs de code trop courts ignorés
const MIN_DOC_LINES    = 12;  // document Markdown : nb de lignes minimum
const MIN_TABLE_ROWS   = 3;   // tableau : nb de lignes minimum (header + sep + données)

// ── Extraction des artefacts d'un message ─────────────────────────────────

function extractArtifacts(msg: ChatMessage): Artifact[] {
  const results: Artifact[] = [];
  const content = msg.content ?? "";

  // ── Image générée par outil ────────────────────────────────────────────
  // Ces messages ont content: "" et imageUri défini — on les traite en premier
  // et on retourne immédiatement (pas d'autre artefact possible).
  if (msg.imageUri) {
    results.push({
      id: `${msg.id}-img`,
      kind: "image",
      content: msg.imageUri,
      title: "Image générée",
      messageId: msg.id,
    });
    return results;
  }

  // ── Ignorer les bulles "outils" (🔧 ...) — pas de contenu exploitable ──
  if (/^🔧/.test(content.trim())) return results;

  if (!content.trim()) return results;

  // ── Blocs de code ──────────────────────────────────────────────────────
  const codeRe = /```(\w*)\n([\s\S]*?)```/g;
  let m: RegExpExecArray | null;
  let codeIdx = 0;
  while ((m = codeRe.exec(content)) !== null) {
    const lang = m[1] || "text";
    const code = m[2];
    const lines = code.split("\n").length;
    if (lines >= MIN_CODE_LINES) {
      // Blocs ECharts → kind dédié pour rendu interactif dans le panneau
      if (lang === "echarts") {
        results.push({
          id: `${msg.id}-code-${codeIdx++}`,
          kind: "echarts",
          language: "echarts",
          content: code,
          title: "Graphique ECharts",
          messageId: msg.id,
        });
        continue;
      }
      const title = lang === "mermaid"
        ? "Diagramme Mermaid"
        : lang
          ? `Code ${lang}`
          : "Bloc de code";
      results.push({
        id: `${msg.id}-code-${codeIdx++}`,
        kind: "code",
        language: lang,
        content: code,
        title,
        messageId: msg.id,
      });
    }
  }

  // ── Tableaux Markdown ──────────────────────────────────────────────────
  // On cherche des groupes de lignes commençant par |
  const lines = content.split("\n");
  let tableStart = -1;
  let tableLines: string[] = [];
  let tableIdx = 0;

  const flushTable = (end: number) => {
    if (tableLines.length >= MIN_TABLE_ROWS) {
      results.push({
        id: `${msg.id}-table-${tableIdx++}`,
        kind: "table",
        content: tableLines.join("\n"),
        title: "Tableau",
        messageId: msg.id,
      });
    }
    tableLines = [];
    tableStart = -1;
  };

  for (let i = 0; i < lines.length; i++) {
    const l = lines[i].trim();
    if (/^\|.+\|/.test(l)) {
      if (tableStart === -1) tableStart = i;
      tableLines.push(lines[i]);
    } else if (tableStart !== -1) {
      flushTable(i);
    }
  }
  if (tableStart !== -1) flushTable(lines.length);

  // ── Document Markdown ──────────────────────────────────────────────────
  // Un document est un message sans code et sans tableau, suffisamment long,
  // avec au moins un titre Markdown.
  const hasNoCode  = !content.includes("```");
  const hasNoTable = !content.includes("|");
  const hasTitle   = /^#{1,3}\s/m.test(content);
  const lineCount  = lines.length;

  if (hasNoCode && hasNoTable && hasTitle && lineCount >= MIN_DOC_LINES) {
    // Titre = premier H1/H2/H3 trouvé
    const titleMatch = content.match(/^#{1,3}\s+(.+)/m);
    results.push({
      id: `${msg.id}-doc`,
      kind: "document",
      content,
      title: titleMatch ? titleMatch[1].trim() : "Document",
      messageId: msg.id,
    });
  }

  return results;
}

// ── Hook ───────────────────────────────────────────────────────────────────

export function useArtifactPanel(messages: ChatMessage[], isGenerating: boolean) {
  const [panelOpen, setPanelOpen]     = useState(false);
  const [activeIdx, setActiveIdx]     = useState(0);
  const [autoOpened, setAutoOpened]   = useState(false);

  // Mémoïse la liste de tous les artefacts (stable tant que messages ne change pas)
  const artifacts = useMemo<Artifact[]>(() => {
    // ── Artefacts extraits message par message ─────────────────────────────
    const extracted: Artifact[] = [];
    for (const msg of messages) {
      if (msg.role !== "assistant" || msg.isError) continue;
      extracted.push(...extractArtifacts(msg));
    }

    if (extracted.length === 0) return [];

    // ── Item synthétique "Réponse complète" (toujours en index 0) ──────────
    // Concatène tous les messages IA non-erreur, séparés par un séparateur HR.
    const fullContent = messages
      .filter((m) => m.role === "assistant" && !m.isError && m.content?.trim())
      .map((m) => m.content.trim())
      .join("\n\n---\n\n");

    const fullArtifact: Artifact = {
      id: "full-response",
      kind: "full",
      content: fullContent,
      title: "Réponse complète",
      messageId: "full",
    };

    return [fullArtifact, ...extracted];
  }, [messages]);

  // Suivi du dernier messageId pour lequel on a fait l'auto-open
  const lastAutoMsgIdRef = useRef<string | null>(null);

  // Auto-ouverture : surveille les nouveaux artefacts après la génération.
  // Pointe sur le premier artefact spécifique (index 1), pas sur le synthétique.
  useEffect(() => {
    if (isGenerating) return;
    if (artifacts.length <= 1) return; // seulement le "full" → pas d'auto-open

    const last = artifacts[artifacts.length - 1];
    if (last.messageId === lastAutoMsgIdRef.current) return;

    lastAutoMsgIdRef.current = last.messageId;
    setActiveIdx(artifacts.length - 1); // dernier artefact spécifique
    setPanelOpen(true);
    setAutoOpened(true);
  }, [artifacts, isGenerating]);

  // Reset autoOpened après toggle manuel
  const toggle = () => {
    setPanelOpen((v) => {
      if (v) setAutoOpened(false);
      return !v;
    });
  };

  const selectArtifact = (idx: number) => {
    setActiveIdx(idx);
  };

  return {
    artifacts,
    activeIdx,
    panelOpen,
    autoOpened,
    toggle,
    selectArtifact,
  };
}
