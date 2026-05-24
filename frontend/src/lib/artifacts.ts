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
 * artifacts.ts
 *
 * Extraction des artefacts depuis le contenu Markdown des messages IA.
 *
 * Ce module est volontairement découplé de React : pas d'import de hooks,
 * pas de dépendance à l'état du composant. Il peut être testé en isolation.
 *
 * Types d'artefacts détectés :
 *   - "echarts"  : bloc ```echarts ... ```
 *   - "code"     : tout autre bloc de code (y compris mermaid comme language)
 *   - "table"    : tableau Markdown (lignes | ... |)
 *   - "word"     : bloc ```word ... ``` (document bureautique)
 *   - "document" : message long sans code ni tableau, avec au moins un titre
 *   - "image"    : message avec imageUri (outil de génération d'image)
 *   - "full"     : artefact synthétique — toute la conversation IA concaténée
 *
 * Porté et enrichi depuis Démeter (même auteur) — ajout du support "word"
 * avec parser d'imbrication et reconstructWordContent.
 */

import type { ChatMessage } from "../hooks/useAgentStream";

// ── Types ────────────────────────────────────────────────────────────────────

export type ArtifactKind =
  | "code"
  | "table"
  | "document"
  | "image"
  | "full"
  | "echarts"
  | "word";

export interface Artifact {
  id: string;
  kind: ArtifactKind;
  language?: string;  // pour "code"
  content: string;    // markdown, code source, ou data URI
  title: string;
  messageId: string;
}

// ── Seuils ───────────────────────────────────────────────────────────────────

const MIN_CODE_LINES = 4;   // blocs de code trop courts ignorés
const MIN_DOC_LINES  = 12;  // document Markdown : nb de lignes minimum
const MIN_TABLE_ROWS = 3;   // tableau : header + séparateur + au moins 1 ligne

// ── Helpers ──────────────────────────────────────────────────────────────────

/**
 * Reconstruit le contenu d'un bloc word en fusionnant les blocs echarts/mermaid
 * orphelins qui le suivent immédiatement dans le message.
 *
 * Contexte : le LLM génère parfois un bloc word suivi de blocs echarts/mermaid
 * séparés (hors de la clôture word). Ces blocs font sémantiquement partie du
 * document — on les réintègre dans le contenu word pour que la génération docx
 * les inclue correctement.
 *
 * Porté depuis Démeter (artifacts.ts → reconstructWordContent).
 */
export function reconstructWordContent(
  fullContent: string,
  _wordStart: number,
  wordEnd: number,
  wordBodyContent: string,
): string {
  const after = fullContent.slice(wordEnd);
  if (!after.trim()) return wordBodyContent;

  const extra: string[] = [];
  let pos = 0;
  let lastTextEnd = 0;

  while (pos < after.length) {
    const tickPos = after.indexOf("```", pos);
    if (tickPos === -1) {
      const tail = after.slice(lastTextEnd).trimEnd();
      if (tail) extra.push(tail);
      break;
    }

    const textChunk = after.slice(lastTextEnd, tickPos).trimEnd();
    if (textChunk) extra.push(textChunk);

    const lineEnd = after.indexOf("\n", tickPos + 3);
    if (lineEnd === -1) break;
    const lang = after.slice(tickPos + 3, lineEnd).trim().toLowerCase();

    const closePos = after.indexOf("\n```", lineEnd);
    if (closePos === -1) break;
    const blockEnd = closePos + 4;

    if (lang === "echarts" || lang === "mermaid") {
      const blockContent = after.slice(lineEnd + 1, closePos);
      extra.push("```" + lang + "\n" + blockContent + "\n```");
    }

    pos = blockEnd;
    lastTextEnd = blockEnd;
  }

  const extraContent = extra.join("\n").trim();
  if (!extraContent) return wordBodyContent;
  return wordBodyContent + "\n\n" + extraContent;
}

// ── Extraction principale ────────────────────────────────────────────────────

/**
 * Extrait tous les artefacts d'un message IA.
 *
 * Ordre de traitement :
 *   1. Image (imageUri) — retour immédiat
 *   2. Blocs word — parser d'imbrication pour gérer les blocs code imbriqués
 *   3. Blocs echarts/code
 *   4. Tableaux Markdown
 *   5. Document long (heuristique)
 */
export function extractArtifacts(msg: ChatMessage): Artifact[] {
  const results: Artifact[] = [];
  const content = msg.content ?? "";

  // ── 1. Image générée par outil ───────────────────────────────────────────
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

  // ── Ignorer les bulles "outils" (🔧 …) ─────────────────────────────────
  if (/^🔧/.test(content.trim())) return results;
  if (!content.trim()) return results;

  // ── 2. Blocs word — parser d'imbrication ────────────────────────────────
  //
  // Un bloc word peut contenir d'autres blocs de code (python, json…) :
  //   ```word Mon rapport
  //   # Titre
  //   ```python
  //   print("hello")
  //   ```
  //   ```
  //
  // On ne peut pas utiliser une regex simple ici — on track la profondeur
  // d'imbrication pour trouver la vraie clôture du bloc word.
  {
    let pos = 0;
    let wIdx = 0;

    while (pos < content.length) {
      const startMarker = content.indexOf("```word", pos);
      if (startMarker === -1) break;

      // Titre optionnel sur la même ligne que ```word
      const titleStart = startMarker + 7;
      const titleEnd   = content.indexOf("\n", titleStart);
      if (titleEnd === -1) break;
      const inlineTitle = content.slice(titleStart, titleEnd).trim();

      // Parser d'imbrication : cherche la clôture correspondante.
      //
      // IMPORTANT : les blocs echarts/mermaid à l'intérieur du bloc word
      // sont des blocs "leaf" — ils n'incrémentent PAS depth car leur
      // clôture ``` est sur une ligne seule (pas suivie d'un identifiant).
      // Seuls les blocs avec un langage textuel (```python, ```json…)
      // incrémentent depth.
      // Les blocs echarts/mermaid sont traités comme du contenu opaque :
      // on saute directement à leur clôture sans modifier depth.
      let depth = 1;
      let cur   = titleEnd + 1;

      while (cur < content.length && depth > 0) {
        const nextTicks = content.indexOf("```", cur);
        if (nextTicks === -1) { cur = content.length; break; }

        const afterTicks = content.slice(nextTicks + 3, nextTicks + 30);
        const langMatch  = afterTicks.match(/^([a-zA-Z]\w*)/);
        const innerLang  = langMatch ? langMatch[1].toLowerCase() : "";

        // Blocs echarts/mermaid : sauter le contenu jusqu'à la prochaine
        // clôture ``` sans modifier depth
        if (innerLang === "echarts" || innerLang === "mermaid") {
          const closePos = content.indexOf("\n```", nextTicks + 3);
          cur = closePos !== -1 ? closePos + 4 : content.length;
          continue;
        }

        if (innerLang) {
          // Bloc de code imbriqué (python, json, etc.) → ouvre
          depth++;
          cur = nextTicks + 3;
        } else {
          // Clôture ```  (ligne seule)
          depth--;
          if (depth === 0) {
            const wordEnd    = nextTicks + 3;
            const rawBody    = content.slice(titleEnd + 1, nextTicks).trim();
            const bodyContent = reconstructWordContent(content, startMarker, wordEnd, rawBody);

            wIdx++;
            const firstLine = bodyContent.split("\n")[0];
            const h1Match   = firstLine.match(/^#\s+(.+)/);
            const label = (inlineTitle || (h1Match && h1Match[1]) || `Document ${wIdx}`)
              .slice(0, 40);

            results.push({
              id: `${msg.id}-word-${wIdx}`,
              kind: "word",
              content: bodyContent,
              title: label,
              messageId: msg.id,
            });
            pos = wordEnd;
          } else {
            cur = nextTicks + 3;
          }
        }
      }
      if (depth > 0) break;  // bloc non fermé — on arrête
    }
  }

  // ── 3. Blocs echarts / code ──────────────────────────────────────────────
  //
  // On skippe les blocs word déjà traités en les excluant du scan.
  // Stratégie simple : on reconstruit le contenu en remplaçant les blocs word
  // par des espaces de même longueur pour préserver les offsets (pas nécessaire
  // ici car on utilise regex globale sans offset absolu).
  const contentWithoutWord = content.replace(
    /```word[\s\S]*?(?:\n```|$)/g,
    (m) => " ".repeat(m.length),
  );

  const codeRe = /```(\w*)\n([\s\S]*?)```/g;
  let m: RegExpExecArray | null;
  let codeIdx = 0;

  while ((m = codeRe.exec(contentWithoutWord)) !== null) {
    const lang  = m[1] || "text";
    const code  = m[2];
    const lines = code.split("\n").length;

    if (lines < MIN_CODE_LINES) continue;

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

    const title =
      lang === "mermaid" ? "Diagramme Mermaid" :
      lang               ? `Code ${lang}`       :
                           "Bloc de code";

    results.push({
      id: `${msg.id}-code-${codeIdx++}`,
      kind: "code",
      language: lang,
      content: code,
      title,
      messageId: msg.id,
    });
  }

  // ── 4. Tableaux Markdown ─────────────────────────────────────────────────
  const lines = content.split("\n");
  let tableStart = -1;
  let tableLines: string[] = [];
  let tableIdx = 0;

  const flushTable = () => {
    if (tableLines.length >= MIN_TABLE_ROWS) {
      results.push({
        id: `${msg.id}-table-${tableIdx++}`,
        kind: "table",
        content: tableLines.join("\n"),
        title: "Tableau",
        messageId: msg.id,
      });
    }
    tableLines  = [];
    tableStart  = -1;
  };

  for (let i = 0; i < lines.length; i++) {
    const l = lines[i].trim();
    if (/^\|.+\|/.test(l)) {
      if (tableStart === -1) tableStart = i;
      tableLines.push(lines[i]);
    } else if (tableStart !== -1) {
      flushTable();
    }
  }
  if (tableStart !== -1) flushTable();

  // ── 5. Document Markdown (heuristique) ──────────────────────────────────
  //
  // Un message est un "document" si :
  //   - pas de blocs de code
  //   - pas de tableaux
  //   - au moins un titre Markdown
  //   - assez long
  //   - pas déjà capturé comme word
  const hasWordBlocks = content.includes("```word");
  const hasNoCode     = !content.includes("```");
  const hasNoTable    = !content.includes("|");
  const hasTitle      = /^#{1,3}\s/m.test(content);

  if (!hasWordBlocks && hasNoCode && hasNoTable && hasTitle && lines.length >= MIN_DOC_LINES) {
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

// ── Construction de la liste complète pour le panneau ────────────────────────

/**
 * Construit la liste d'artefacts pour toute une conversation :
 *   - artefact synthétique "Réponse complète" en index 0
 *   - artefacts extraits message par message
 */
export function buildArtifactList(messages: ChatMessage[]): Artifact[] {
  const extracted: Artifact[] = [];
  for (const msg of messages) {
    if (msg.role !== "assistant" || msg.isError) continue;
    extracted.push(...extractArtifacts(msg));
  }

  if (extracted.length === 0) return [];

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
}
