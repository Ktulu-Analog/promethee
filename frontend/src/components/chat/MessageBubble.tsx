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
 * MessageBubble.tsx
 *
 *
 * Rendu :
 *   - Markdown via react-markdown
 *   - Code avec coloration via react-syntax-highlighter (oneDark / oneLight)
 *   - Formules KaTeX via rehype-katex + remark-math
 *   - Diagrammes Mermaid via mermaid.js (rendu côté client)
 *   - Images générées par outils (data:image/... affichées inline)
 *   - Streaming : le texte s'accumule, le rendu final remplace le brut
 *
 * FIX LaTeX :
 *   remark-math v6 ne reconnaît QUE $...$ et $$...$$.
 *   Les délimiteurs \(...\) et \[...\] produits par les LLM sont normalisés
 *   par normalizeLatex() avant d'être passés à ReactMarkdown.
 *
 * Boutons de copie (visibles au survol de la bulle assistant) :
 *   📋  Copie le texte brut (markdown source)
 *   📄  Copie en HTML mis en forme (compatible Word / LibreOffice)
 */

import React, { useRef, useState, useCallback, memo } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import rehypeRaw from "rehype-raw";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneDark, oneLight } from "react-syntax-highlighter/dist/esm/styles/prism";
import type { ChatMessage } from "../../hooks/useAgentStream";
import { useTheme } from "../../lib/useTheme";
import { MermaidBlock } from "./MermaidBlock";
import { EChartsBlock } from "./EChartsBlock";
import { markdownToHtml } from "../../lib/markdownToHtml";

import "katex/dist/katex.min.css";

// ── Normalisation LaTeX ────────────────────────────────────────────────────

function normalizeLatex(text: string): string {
  // display \[ ... \]  →  $$ ... $$
  let result = text.replace(/\\\[([\s\S]*?)\\\]/g, (_m, inner) => `$$${inner}$$`);
  // inline \( ... \)   →  $ ... $
  result = result.replace(/\\\(([\s\S]*?)\\\)/g, (_m, inner) => `$${inner}$`);
  // [ ... ] en début de ligne (heuristique LLM) → $$ ... $$
  result = result.replace(
    /^\[\s*(\\[a-zA-Z\\{(][\s\S]*?)\s*\]$/gm,
    (_m, inner) => `$$${inner}$$`
  );
  return result;
}




// ── Hook copie ────────────────────────────────────────────────────────────

type CopyState = "idle" | "ok" | "err";

function useCopy(delay = 1800) {
  const [state, setState] = useState<CopyState>("idle");
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const copy = useCallback(
    async (getFn: () => Promise<void>) => {
      try {
        await getFn();
        setState("ok");
      } catch {
        setState("err");
      } finally {
        if (timerRef.current) clearTimeout(timerRef.current);
        timerRef.current = setTimeout(() => setState("idle"), delay);
      }
    },
    [delay]
  );

  return { state, copy };
}

// ── Boutons de copie ──────────────────────────────────────────────────────

interface CopyButtonsProps {
  rawContent: string;
  visible: boolean;
}

const CopyButtons = memo(function CopyButtons({ rawContent, visible }: CopyButtonsProps) {
  const { state: stateRaw, copy: copyRaw } = useCopy();
  const { state: stateRtf, copy: copyRtf } = useCopy();

  const handleCopyRaw = () =>
    copyRaw(() => navigator.clipboard.writeText(rawContent));

  const handleCopyRtf = () =>
    copyRtf(async () => {
      const html = markdownToHtml(rawContent);
      const blob = new Blob([html], { type: "text/html" });
      await navigator.clipboard.write([new ClipboardItem({ "text/html": blob })]);
    });

  const labelRaw = stateRaw === "ok" ? "✓ Copié" : stateRaw === "err" ? "✗ Erreur" : "Copier (brut)";
  const labelRtf = stateRtf === "ok" ? "✓ Copié" : stateRtf === "err" ? "✗ Erreur" : "Copier (Word)";

  return (
    <div style={{ ...styles.copyBar, opacity: visible ? 1 : 0, pointerEvents: visible ? "auto" : "none" }}>
      <button
        onClick={handleCopyRaw}
        title="Copier le texte brut (markdown source)"
        style={{
          ...styles.copyBtn,
          ...(stateRaw === "ok" ? styles.copyBtnOk : {}),
          ...(stateRaw === "err" ? styles.copyBtnErr : {}),
        }}
      >
        {stateRaw === "ok" ? "✓" : stateRaw === "err" ? "✗" : "📋"}&nbsp;{labelRaw}
      </button>
      <button
        onClick={handleCopyRtf}
        title="Copier en HTML mis en forme (Word, LibreOffice, Pages)"
        style={{
          ...styles.copyBtn,
          ...(stateRtf === "ok" ? styles.copyBtnOk : {}),
          ...(stateRtf === "err" ? styles.copyBtnErr : {}),
        }}
      >
        {stateRtf === "ok" ? "✓" : stateRtf === "err" ? "✗" : "📄"}&nbsp;{labelRtf}
      </button>
    </div>
  );
});

// ── Helpers ────────────────────────────────────────────────────────────────

function isMermaid(lang: string | undefined) {
  return lang === "mermaid";
}

function isECharts(lang: string | undefined) {
  return lang === "echarts";
}


function isToolBubble(content: string) {
  return /^🔧/.test(content.trim());
}

// ── Composant principal ───────────────────────────────────────────────────

interface Props {
  message: ChatMessage;
  isStreaming?: boolean;
  username?: string;
}

export const MessageBubble = memo(function MessageBubble({ message, isStreaming, username }: Props) {
  const { isDark } = useTheme();
  const { role, content, imageUri, cancelled, isError } = message;
  const [hovered, setHovered] = useState(false);

  const isUser      = role === "user";
  const isToolBub   = !isUser && isToolBubble(content);
  const isImageOnly = !!imageUri && !content.trim();

  if (isImageOnly) {
    return (
      <div style={styles.imageWrapper}>
        <img src={imageUri} alt="Graphique généré" style={styles.generatedImage}
          onClick={() => window.open(imageUri, "_blank")} title="Cliquer pour agrandir" />
      </div>
    );
  }

  if (isUser) {
    return (
      <div style={styles.userRow}>
        <div style={styles.userLabel}>{username || "Vous"}</div>
        <div style={{ ...styles.userBubble, whiteSpace: "pre-wrap" }}>{content}</div>
      </div>
    );
  }

  const bubbleStyle = {
    ...styles.assistantBubble,
    ...(isToolBub ? styles.toolBubble     : {}),
    ...(isError   ? styles.errorBubble    : {}),
    ...(cancelled ? styles.cancelledBubble : {}),
  };

  // Boutons visibles uniquement sur les vraies réponses IA, hors streaming
  const showCopyButtons = !isToolBub && !isError && !isStreaming;

  return (
    <div
      style={styles.assistantRow}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      <div style={styles.assistantLabel}>
        {isToolBub ? "Outils" : isError ? "⚠" : "IA"}
      </div>
      <div style={bubbleStyle}>
        <MarkdownContent content={content} isStreaming={isStreaming} isDark={isDark} imageUri={imageUri} />
      </div>
      {showCopyButtons && (
        <CopyButtons rawContent={content} visible={hovered} />
      )}
    </div>
  );
});

// ── Rendu Markdown ─────────────────────────────────────────────────────────

interface MarkdownProps {
  content: string;
  isStreaming?: boolean;
  isDark: boolean;
  imageUri?: string;
}

const MarkdownContent = memo(function MarkdownContent({
  content, isStreaming, isDark, imageUri,
}: MarkdownProps) {
  const codeStyle = isDark ? oneDark : oneLight;
  const normalizedContent = isStreaming ? content : normalizeLatex(content);

  return (
    <>
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkMath]}
        rehypePlugins={[rehypeRaw, rehypeKatex]}
        components={{
          code({ node, inline, className, children, ...props }: any) {
            const lang = /language-(\w+)/.exec(className || "")?.[1];
            const codeText = String(children).replace(/\n$/, "");
            if (!inline && isMermaid(lang)) return <MermaidBlock code={codeText} isDark={isDark} />;
            if (!inline && isECharts(lang)) return <EChartsBlock code={codeText} isDark={isDark} />;
            if (!inline && lang) {
              return (
                <div style={styles.codeWrapper}>
                  <div style={styles.codeLang}>{lang}</div>
                  <SyntaxHighlighter style={codeStyle} language={lang} PreTag="div"
                    customStyle={{ margin: 0, borderRadius: "0 0 6px 6px", fontSize: "13px", background: "var(--code-block-bg)" }}>
                    {codeText}
                  </SyntaxHighlighter>
                </div>
              );
            }
            return (
              <code style={{ fontFamily: "monospace", fontSize: "0.875em", color: "var(--code-inline-color)",
                background: "var(--code-bg)", borderRadius: "3px", padding: "1px 5px" }} {...props}>
                {children}
              </code>
            );
          },
          a({ href, children }) {
            return <a href={href} target="_blank" rel="noopener noreferrer" style={{ color: "var(--link-color)" }}>{children}</a>;
          },
          blockquote({ children }) {
            return (
              <blockquote style={{ borderLeft: "3px solid var(--accent)", margin: "8px 0",
                padding: "6px 12px", background: "var(--blockquote-bg)", borderRadius: "0 4px 4px 0" }}>
                {children}
              </blockquote>
            );
          },
          table({ children }) {
            return (
              <div style={{ overflowX: "auto", margin: "8px 0" }}>
                <table style={{ borderCollapse: "collapse", width: "100%", fontSize: "13px" }}>{children}</table>
              </div>
            );
          },
          th({ children }) {
            return <th style={{ border: "1px solid var(--border)", padding: "6px 10px",
              background: "var(--elevated-bg)", textAlign: "left", fontWeight: 600 }}>{children}</th>;
          },
          td({ children }) {
            return <td style={{ border: "1px solid var(--border)", padding: "5px 10px" }}>{children}</td>;
          },
          img({ src, alt }) {
            if (src?.startsWith("data:")) {
              return <img src={src} alt={alt} style={{ maxWidth: "100%", borderRadius: "4px", cursor: "pointer" }}
                onClick={() => window.open(src, "_blank")} />;
            }
            return <img src={src} alt={alt} style={{ maxWidth: "100%" }} />;
          },
        }}
      >
        {normalizedContent}
      </ReactMarkdown>

      {imageUri && content.trim() && (
        <img src={imageUri} alt="Graphique"
          style={{ ...styles.generatedImage, marginTop: 8 }}
          onClick={() => window.open(imageUri, "_blank")} />
      )}

      {isStreaming && (
        <span style={{ display: "inline-block", width: "2px", height: "1em", background: "var(--accent)",
          marginLeft: "2px", verticalAlign: "text-bottom", animation: "blink 1s step-end infinite" }} />
      )}

      <style>{`
        @keyframes blink { 0%, 100% { opacity: 1; } 50% { opacity: 0; } }
      `}</style>
    </>
  );
});

// ── Styles ─────────────────────────────────────────────────────────────────

const styles: Record<string, React.CSSProperties> = {
  userRow: { display: "flex", flexDirection: "column", alignItems: "flex-end", margin: "8px 0", paddingLeft: "20%" },
  userLabel: { fontSize: "11px", color: "var(--accent-user-role)", fontWeight: 600, marginBottom: "3px", textTransform: "uppercase", letterSpacing: "0.05em" },
  userBubble: { background: "var(--msg-user-bg)", border: "1px solid var(--msg-user-border)", borderRadius: "12px 12px 3px 12px",
    padding: "10px 14px", fontSize: "15px", lineHeight: 1.6, color: "var(--text-primary)", maxWidth: "100%", wordBreak: "break-word" },
  assistantRow: { display: "flex", flexDirection: "column", alignItems: "flex-start", margin: "8px 0", paddingRight: "10%" },
  assistantLabel: { fontSize: "11px", color: "var(--accent-assistant-role)", fontWeight: 600, marginBottom: "3px", textTransform: "uppercase", letterSpacing: "0.05em" },
  assistantBubble: { background: "transparent", borderRadius: "3px 12px 12px 12px", padding: "2px 0",
    fontSize: "15px", lineHeight: 1.7, color: "var(--text-primary)", maxWidth: "100%", wordBreak: "break-word" },
  toolBubble: { background: "var(--tool-call-bg)", border: "1px solid var(--tool-call-border)", borderRadius: "8px",
    padding: "8px 12px", color: "var(--tool-call-color)", fontSize: "13px" },
  errorBubble: { background: "#2e1a1a", border: "1px solid #6e3030", borderRadius: "8px", padding: "8px 12px", color: "#e07878" },
  cancelledBubble: { opacity: 0.7 },
  imageWrapper: { margin: "8px 0", display: "flex", justifyContent: "flex-start" },
  generatedImage: { maxWidth: "100%", maxHeight: "480px", borderRadius: "6px", cursor: "pointer", border: "1px solid var(--border)" },
  codeWrapper: { borderRadius: "6px", overflow: "hidden", border: "1px solid var(--code-border)", margin: "8px 0" },
  codeLang: { background: "var(--elevated-bg)", color: "var(--text-muted)", fontSize: "11px",
    padding: "4px 10px", borderBottom: "1px solid var(--code-border)", fontFamily: "monospace" },

  // ── Barre de copie ────────────────────────────────────────────────────
  copyBar: {
    display: "flex",
    gap: "6px",
    marginTop: "6px",
    transition: "opacity 0.15s ease",
  },
  copyBtn: {
    display: "inline-flex",
    alignItems: "center",
    gap: "3px",
    padding: "3px 9px",
    fontSize: "11px",
    fontFamily: "inherit",
    borderRadius: "5px",
    border: "1px solid var(--border)",
    background: "var(--elevated-bg)",
    color: "var(--text-muted)",
    cursor: "pointer",
    transition: "background 0.12s, color 0.12s, border-color 0.12s",
    outline: "none",
    userSelect: "none" as React.CSSProperties["userSelect"],
    lineHeight: 1.4,
  },
  copyBtnOk:  { color: "#5aaa7a", borderColor: "#3a7a5a" },
  copyBtnErr: { color: "#e07878", borderColor: "#6e3030" },
};
