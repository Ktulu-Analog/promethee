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
 * ArtifactPanel.tsx
 *
 * Panneau droit du split-view.
 *
 * Affiche les artefacts extraits des messages IA :
 *   - Code     : SyntaxHighlighter + "📋 Copier (brut)"
 *   - Mermaid  : rendu diagramme  + "📋 Copier (source)"
 *   - Echarts  : rendu diagramme + "📋 Copier (source)" + "💾 Copier l'image" + "📄 Copier (Word)"
 *   - Table    : rendu HTML natif  + "📋 Copier (brut)" + "📄 Copier (Word)"
 *   - Document : rendu Markdown    + "📋 Copier (brut)" + "📄 Copier (Word)"
 *   - Image    : img zoomable      + "💾 Copier l'image"
 *
 * La toolbar de copie est unifiée et placée dans l'en-tête du panneau,
 * à droite du titre — visible en permanence (pas de hover requis).
 */

import React, { memo, useCallback, useRef, useState, useEffect } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneDark, oneLight } from "react-syntax-highlighter/dist/esm/styles/prism";
import { MermaidBlock } from "./MermaidBlock";
import { EChartsBlock } from "./EChartsBlock";
import { useTheme } from "../../lib/useTheme";
import { markdownToHtml } from "../../lib/markdownToHtml";
import type { Artifact } from "../../hooks/useArtifactPanel";

// ── Icônes par type ─────────────────────────────────────────────────────────

const KIND_ICON: Record<string, string> = {
  code:     "⌨",
  table:    "⊞",
  document: "≡",
  image:    "◫",
  full:     "❖",
  echarts:  "📊",
};

// ── Hook copie générique ─────────────────────────────────────────────────────

type CopyState = "idle" | "ok" | "err";

function useCopyState(delay = 1800) {
  const [state, setState] = React.useState<CopyState>("idle");
  const timerRef = React.useRef<ReturnType<typeof setTimeout> | null>(null);

  const trigger = useCallback(async (action: () => Promise<void>) => {
    try {
      await action();
      setState("ok");
    } catch {
      setState("err");
    } finally {
      if (timerRef.current) clearTimeout(timerRef.current);
      timerRef.current = setTimeout(() => setState("idle"), delay);
    }
  }, [delay]);

  return { state, trigger };
}

// ── Bouton copie atomique ────────────────────────────────────────────────────

interface CopyBtnProps {
  label: string;       // label idle, ex: "📋 Copier (brut)"
  title?: string;
  onCopy: () => Promise<void>;
}

function CopyBtn({ label, title, onCopy }: CopyBtnProps) {
  const { state, trigger } = useCopyState();

  const displayLabel =
    state === "ok"  ? "✓ Copié"  :
    state === "err" ? "✗ Erreur" :
    label;

  return (
    <button
      onClick={() => trigger(onCopy)}
      title={title ?? label}
      style={{
        ...btnStyle,
        color: state === "ok"  ? "#5aaa7a"
             : state === "err" ? "#e07878"
             : "var(--text-muted)",
        borderColor: state === "ok"  ? "#3a7a5a"
                   : state === "err" ? "#6e3030"
                   : "var(--border)",
      }}
    >
      {displayLabel}
    </button>
  );
}

const btnStyle: React.CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  padding: "3px 10px",
  fontSize: 11,
  borderRadius: 5,
  border: "1px solid var(--border)",
  background: "var(--elevated-bg)",
  cursor: "pointer",
  fontFamily: "inherit",
  transition: "color 0.15s, border-color 0.15s",
  whiteSpace: "nowrap",
  userSelect: "none" as const,
  lineHeight: 1.5,
};

// ── Bouton téléchargement PNG avec sélecteur de résolution ──────────────────

interface PngDownloadBtnProps {
  /** Fonction appelée avec le pixelRatio choisi (1, 2, 3 ou 4) */
  onDownload: (pixelRatio: number) => Promise<void>;
}

function PngDownloadBtn({ onDownload }: PngDownloadBtnProps) {
  const [open, setOpen]     = useState(false);
  const [ratio, setRatio]   = useState(2);
  const [state, setState]   = useState<CopyState>("idle");
  const wrapRef             = useRef<HTMLDivElement>(null);

  // Fermer le popover au clic extérieur
  useEffect(() => {
    if (!open) return;
    function onDown(e: MouseEvent) {
      if (!wrapRef.current?.contains(e.target as Node)) setOpen(false);
    }
    window.addEventListener("mousedown", onDown);
    return () => window.removeEventListener("mousedown", onDown);
  }, [open]);

  const label =
    state === "ok"  ? "✓ Téléchargé" :
    state === "err" ? "✗ Erreur"      :
    "🖼 Télécharger PNG";

  async function handleDownload() {
    try {
      await onDownload(ratio);
      setState("ok");
    } catch {
      setState("err");
    } finally {
      setTimeout(() => setState("idle"), 2000);
      setOpen(false);
    }
  }

  return (
    <div ref={wrapRef} style={{ position: "relative", display: "inline-flex" }}>
      {/* Bouton principal */}
      <button
        onClick={() => setOpen((v) => !v)}
        title="Télécharger le diagramme en PNG — cliquer pour choisir la résolution"
        style={{
          ...btnStyle,
          color: state === "ok"  ? "#5aaa7a"
               : state === "err" ? "#e07878"
               : "var(--text-muted)",
          borderColor: state === "ok"  ? "#3a7a5a"
                     : state === "err" ? "#6e3030"
                     : "var(--border)",
        }}
      >
        {label}
      </button>

      {/* Popover résolution */}
      {open && (
        <div style={{
          position: "absolute",
          top: "calc(100% + 6px)",
          right: 0,
          background: "var(--elevated-bg)",
          border: "1px solid var(--border)",
          borderRadius: 7,
          padding: "10px 14px",
          boxShadow: "0 4px 16px rgba(0,0,0,0.25)",
          zIndex: 999,
          minWidth: 200,
          display: "flex",
          flexDirection: "column",
          gap: 8,
        }}>
          <div style={{ fontSize: 11, color: "var(--text-muted)", fontWeight: 600 }}>
            Résolution : ×{ratio}
            <span style={{ fontWeight: 400, marginLeft: 6 }}>
              ({ratio === 1 ? "72 dpi — écran" :
                ratio === 2 ? "144 dpi — standard" :
                ratio === 3 ? "216 dpi — impression" :
                              "288 dpi — haute def"})
            </span>
          </div>
          <input
            type="range" min={1} max={4} step={1} value={ratio}
            onChange={(e) => setRatio(Number(e.target.value))}
            style={{ width: "100%", cursor: "pointer", accentColor: "var(--accent)" }}
          />
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: "var(--text-disabled)" }}>
            <span>×1</span><span>×2</span><span>×3</span><span>×4</span>
          </div>
          <button
            onClick={handleDownload}
            style={{
              ...btnStyle,
              background: "var(--accent)",
              color: "#fff",
              borderColor: "var(--accent)",
              justifyContent: "center",
            }}
          >
            Télécharger
          </button>
        </div>
      )}
    </div>
  );
}

// ── Barre de copie par type d'artefact ──────────────────────────────────────

function CopyToolbar({ artifact, onDownloadPng, onCopyPng }: {
  artifact: Artifact;
  onDownloadPng?: (pixelRatio: number) => Promise<void>;
  onCopyPng?: () => Promise<void>;
}) {
  const { kind, content } = artifact;

  // ── ECharts ───────────────────────────────────────────────────────────
  if (kind === "echarts") {
    return (
      <div style={toolbarStyle}>
        <CopyBtn
          label="📋 Copier (JSON)"
          title="Copier la config ECharts"
          onCopy={() => navigator.clipboard.writeText(content)}
        />
        <CopyBtn
          label="📋 Copier image"
          title="Copier le graphique en PNG dans le presse-papiers (pour Word, Outlook…)"
          onCopy={async () => { if (onCopyPng) await onCopyPng(); }}
        />
        {onDownloadPng && <PngDownloadBtn onDownload={onDownloadPng} />}
      </div>
    );
  }

  // ── Code / Mermaid ────────────────────────────────────────────────────
  if (kind === "code") {
    const isMermaid = artifact.language === "mermaid";
    return (
      <div style={toolbarStyle}>
        <CopyBtn
          label="📋 Copier (brut)"
          title="Copier le code source"
          onCopy={() => navigator.clipboard.writeText(content)}
        />
        {isMermaid && onCopyPng && (
          <CopyBtn
            label="📋 Copier image"
            title="Copier le diagramme en PNG dans le presse-papiers (pour Word, Outlook…)"
            onCopy={async () => { if (onCopyPng) await onCopyPng(); }}
          />
        )}
        {isMermaid && onDownloadPng && <PngDownloadBtn onDownload={onDownloadPng} />}
      </div>
    );
  }

  // ── Image ─────────────────────────────────────────────────────────────
  if (kind === "image") {
    return (
      <div style={toolbarStyle}>
        <CopyBtn
          label="💾 Copier l'image"
          title="Copier l'image dans le presse-papiers"
          onCopy={async () => {
            // Convertit le data URI en blob et le copie
            const res  = await fetch(content);
            const blob = await res.blob();
            await navigator.clipboard.write([
              new ClipboardItem({ [blob.type]: blob }),
            ]);
          }}
        />
      </div>
    );
  }

  // ── Table, Document & Réponse complète : brut + Word ─────────────────────────────────
  return (
    <div style={toolbarStyle}>
      <CopyBtn
        label="📋 Copier (brut)"
        title="Copier le texte Markdown brut"
        onCopy={() => navigator.clipboard.writeText(content)}
      />
      <CopyBtn
        label="📄 Copier (Word)"
        title="Copier en HTML mis en forme (Word, LibreOffice, Pages…)"
        onCopy={async () => {
          const html = markdownToHtml(content);
          const blob = new Blob([html], { type: "text/html" });
          await navigator.clipboard.write([
            new ClipboardItem({ "text/html": blob }),
          ]);
        }}
      />
    </div>
  );
}

const toolbarStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: 6,
  flexShrink: 0,
};

// ── Rendu ECharts dans le panneau artefact ──────────────────────────────────
//
// Expose une ref vers l'instance ECharts pour que la CopyToolbar puisse
// déclencher le téléchargement PNG directement depuis le chart canvas.

interface EChartsArtifactProps {
  content: string;
  isDark: boolean;
  chartRef: React.MutableRefObject<any>;
}

function EChartsArtifact({ content, isDark, chartRef }: EChartsArtifactProps) {
  return (
    // overflow:hidden garantit que le graphique ne déborde pas du panneau
    <div style={{ height: "100%", width: "100%", display: "flex", flexDirection: "column", overflow: "hidden", padding: "12px", boxSizing: "border-box" }}>
      <EChartsBlock
        code={content}
        isDark={isDark}
        variant="panel"
        onChartReady={(instance) => { chartRef.current = instance; }}
      />
    </div>
  );
}

// ── Rendu Mermaid dans le panneau artefact ──────────────────────────────────
//
// Expose une ref vers le SVG rendu pour que la CopyToolbar puisse
// déclencher le téléchargement/copie PNG via conversion SVG→canvas.

interface MermaidArtifactProps {
  content: string;
  isDark: boolean;
  svgRef: React.MutableRefObject<string | null>;
}

function MermaidArtifact({ content, isDark, svgRef }: MermaidArtifactProps) {
  return (
    <div style={{ height: "100%", width: "100%", display: "flex", flexDirection: "column", overflow: "hidden", padding: "12px", boxSizing: "border-box" }}>
      <MermaidBlock
        code={content}
        isDark={isDark}
        variant="panel"
        onSvgReady={(svg) => { svgRef.current = svg; }}
      />
    </div>
  );
}

const ArtifactContent = memo(function ArtifactContent({
  artifact,
  echartsRef,
  mermaidSvgRef,
}: {
  artifact: Artifact;
  echartsRef: React.MutableRefObject<any>;
  mermaidSvgRef: React.MutableRefObject<string | null>;
}) {
  const { isDark } = useTheme();
  const codeStyle = isDark ? oneDark : oneLight;

  // ── ECharts ────────────────────────────────────────────────────────────
  if (artifact.kind === "echarts") {
    return <EChartsArtifact content={artifact.content} isDark={isDark} chartRef={echartsRef} />;
  }

  // ── Image ──────────────────────────────────────────────────────────────
  if (artifact.kind === "image") {
    return (
      <div style={s.imageContainer}>
        <img
          src={artifact.content}
          alt="Graphique généré"
          style={s.image}
          onClick={() => window.open(artifact.content, "_blank")}
          title="Cliquer pour agrandir"
        />
      </div>
    );
  }

  // ── Code ───────────────────────────────────────────────────────────────
  if (artifact.kind === "code") {
    const lang = artifact.language || "text";

    if (lang === "mermaid") {
      return (
        <div style={s.codeContainer}>
          <div style={s.mermaidWrapper}>
            <MermaidArtifact content={artifact.content} isDark={isDark} svgRef={mermaidSvgRef} />
          </div>
        </div>
      );
    }

    return (
      <div style={s.codeContainer}>
        <div style={s.syntaxWrapper}>
          <SyntaxHighlighter
            style={codeStyle}
            language={lang}
            PreTag="div"
            showLineNumbers
            lineNumberStyle={{
              minWidth: "2.8em",
              paddingRight: "1em",
              color: isDark ? "#4a4a58" : "#bbbbc8",
              userSelect: "none",
              fontSize: "11px",
              textAlign: "right",
            }}
            customStyle={{
              margin: 0,
              borderRadius: 0,
              fontSize: "13px",
              background: "var(--code-block-bg)",
              minHeight: "100%",
              overflowX: "auto",
            }}
          >
            {artifact.content}
          </SyntaxHighlighter>
        </div>
      </div>
    );
  }

  // ── Table & Document — rendu Markdown ─────────────────────────────────
  return (
    <div style={s.mdContainer}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkMath]}
        rehypePlugins={[rehypeKatex]}
        components={{
          table({ children }) {
            return (
              <div style={{ overflowX: "auto", margin: "8px 0" }}>
                <table style={{ borderCollapse: "collapse", width: "100%", fontSize: "13px" }}>
                  {children}
                </table>
              </div>
            );
          },
          th({ children }) {
            return (
              <th style={{ border: "1px solid var(--border)", padding: "7px 12px",
                background: "var(--elevated-bg)", textAlign: "left", fontWeight: 600 }}>
                {children}
              </th>
            );
          },
          td({ children }) {
            return (
              <td style={{ border: "1px solid var(--border)", padding: "6px 12px" }}>
                {children}
              </td>
            );
          },
          code({ node, inline, className, children, ...props }: any) {
            const lang = /language-(\w+)/.exec(className || "")?.[1];
            const codeText = String(children).replace(/\n$/, "");
            if (!inline && lang === "mermaid") return <MermaidBlock code={codeText} isDark={isDark} variant="panel" />;
            if (!inline && lang) {
              return (
                <SyntaxHighlighter style={codeStyle} language={lang} PreTag="div"
                  customStyle={{ margin: "8px 0", borderRadius: 6, fontSize: "13px",
                    background: "var(--code-block-bg)" }}>
                  {codeText}
                </SyntaxHighlighter>
              );
            }
            return (
              <code style={{ fontFamily: "monospace", fontSize: "0.875em",
                color: "var(--code-inline-color)", background: "var(--code-bg)",
                borderRadius: 3, padding: "1px 5px" }} {...props}>
                {children}
              </code>
            );
          },
          a({ href, children }) {
            return (
              <a href={href} target="_blank" rel="noopener noreferrer"
                style={{ color: "var(--link-color)" }}>{children}</a>
            );
          },
          blockquote({ children }) {
            return (
              <blockquote style={{ borderLeft: "3px solid var(--accent)", margin: "8px 0",
                padding: "6px 12px", background: "var(--blockquote-bg)", borderRadius: "0 4px 4px 0" }}>
                {children}
              </blockquote>
            );
          },
        }}
      >
        {artifact.content}
      </ReactMarkdown>
    </div>
  );
});

// ── Navigation latérale ─────────────────────────────────────────────────────
//
// Remplace la tabBar horizontale par un panneau de liste scrollable à gauche,
// avec flèches ↑↓ pour naviguer sans souris.
// Seuil : affiché dès qu'il y a au moins 2 artefacts.

interface NavPanelProps {
  artifacts: Artifact[];
  activeIdx: number;
  onSelect: (idx: number) => void;
}

function NavPanel({ artifacts, activeIdx, onSelect }: NavPanelProps) {
  const listRef = React.useRef<HTMLDivElement>(null);

  // Scroll automatique vers l'item actif
  React.useEffect(() => {
    const list = listRef.current;
    if (!list) return;
    const item = list.children[activeIdx] as HTMLElement | undefined;
    item?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [activeIdx]);

  const prev = () => onSelect(Math.max(0, activeIdx - 1));
  const next = () => onSelect(Math.min(artifacts.length - 1, activeIdx + 1));

  const arrowBtn = (disabled: boolean, onClick: () => void, label: string): React.CSSProperties => ({
    ...navArrowStyle,
    opacity: disabled ? 0.3 : 1,
    cursor: disabled ? "default" : "pointer",
    pointerEvents: disabled ? "none" : "auto",
  });

  return (
    <div style={n.root}>
      {/* Flèche haut */}
      <button
        onClick={prev}
        disabled={activeIdx === 0}
        title="Précédent"
        style={{ ...navArrowStyle, opacity: activeIdx === 0 ? 0.3 : 1 }}
        aria-label="Artefact précédent"
      >▲</button>

      {/* Liste scrollable */}
      <div ref={listRef} style={n.list}>
        {artifacts.map((art, idx) => (
          <React.Fragment key={art.id}>
            <button
              onClick={() => onSelect(idx)}
              title={art.title}
              aria-selected={idx === activeIdx}
              style={{
                ...n.item,
                ...(art.kind === "full" ? n.itemFull : {}),
                ...(idx === activeIdx ? n.itemActive : {}),
              }}
            >
              <span style={n.itemIcon}>{KIND_ICON[art.kind]}</span>
              <span style={n.itemLabel}>{art.title}</span>
              {/* Pas de numéro pour l'item "full" */}
              {art.kind !== "full" && (
                <span style={{ ...n.itemBadge, ...(idx === activeIdx ? n.itemBadgeActive : {}) }}>
                  {idx}
                </span>
              )}
            </button>
            {/* Diviseur après l'item synthétique */}
            {art.kind === "full" && (
              <div style={n.divider} />
            )}
          </React.Fragment>
        ))}
      </div>

      {/* Compteur (ne compte que les artefacts spécifiques) + flèche bas */}
      <div style={n.footer}>
        <span style={n.counter}>
          {activeIdx === 0
            ? "Tout"
            : `${activeIdx} / ${artifacts.length - 1}`}
        </span>
        <button
          onClick={next}
          disabled={activeIdx === artifacts.length - 1}
          title="Suivant"
          style={{ ...navArrowStyle, opacity: activeIdx === artifacts.length - 1 ? 0.3 : 1 }}
          aria-label="Artefact suivant"
        >▼</button>
      </div>
    </div>
  );
}

const navArrowStyle: React.CSSProperties = {
  background: "none",
  border: "none",
  color: "var(--text-muted)",
  cursor: "pointer",
  fontSize: 10,
  padding: "4px 0",
  lineHeight: 1,
  width: "100%",
  textAlign: "center",
  flexShrink: 0,
  transition: "color 0.12s",
};

const n: Record<string, React.CSSProperties> = {
  root: {
    display: "flex",
    flexDirection: "column",
    width: 160,
    minWidth: 120,
    maxWidth: 180,
    height: "100%",
    background: "var(--elevated-bg)",
    borderRight: "1px solid var(--border)",
    flexShrink: 0,
    overflow: "hidden",
  },
  list: {
    flex: 1,
    overflowY: "auto" as const,
    overflowX: "hidden" as const,
    padding: "2px 0",
  },
  item: {
    display: "flex",
    alignItems: "center",
    gap: 6,
    width: "100%",
    padding: "7px 10px",
    background: "none",
    border: "none",
    borderLeft: "2px solid transparent",
    cursor: "pointer",
    textAlign: "left" as const,
    transition: "background 0.12s, border-color 0.12s",
    color: "var(--text-muted)",
    fontSize: 12,
  },
  itemActive: {
    background: "var(--surface-bg)",
    borderLeft: "2px solid var(--accent)",
    color: "var(--text-primary)",
  },
  itemIcon: {
    fontSize: 13,
    flexShrink: 0,
  },
  itemLabel: {
    flex: 1,
    overflow: "hidden",
    whiteSpace: "nowrap" as const,
    textOverflow: "ellipsis",
    fontSize: 12,
  },
  itemFull: {
    color: "var(--text-secondary)",
    fontStyle: "italic" as const,
    background: "var(--surface-bg)",
  },
  divider: {
    height: 1,
    background: "var(--border)",
    margin: "4px 8px",
    flexShrink: 0,
  },
  itemBadge: {
    fontSize: 10,
    color: "var(--text-disabled)",
    flexShrink: 0,
  },
  itemBadgeActive: {
    color: "var(--accent)",
  },
  footer: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    padding: "4px 8px",
    borderTop: "1px solid var(--border)",
    flexShrink: 0,
  },
  counter: {
    fontSize: 10,
    color: "var(--text-disabled)",
    userSelect: "none" as const,
  },
};

// ── Composant principal ──────────────────────────────────────────────────────

interface ArtifactPanelProps {
  artifacts: Artifact[];
  activeIdx: number;
  onSelectArtifact: (idx: number) => void;
  onClose: () => void;
}

export const ArtifactPanel = memo(function ArtifactPanel({
  artifacts,
  activeIdx,
  onSelectArtifact,
  onClose,
}: ArtifactPanelProps) {
  const active = artifacts[activeIdx] ?? null;
  const hasMany = artifacts.length > 1;

  // Ref vers l'instance ECharts active — mis à jour par EChartsArtifact via onChartReady
  const echartsRef = useRef<any>(null);

  // Ref vers le SVG Mermaid actif — mis à jour par MermaidArtifact via onSvgReady
  const mermaidSvgRef = useRef<string | null>(null);

  // Reset les refs quand on change d'artefact
  useEffect(() => { echartsRef.current = null; mermaidSvgRef.current = null; }, [activeIdx]);

  // Masque le toolbox le temps du snapshot puis le restaure — évite qu'il
  // apparaisse dans l'image exportée.
  function getEchartsDataURLClean(chart: any, pixelRatio = 2): string {
    chart.setOption({ toolbox: { show: false } });
    const url = chart.getDataURL({ type: "png", pixelRatio, backgroundColor: "#ffffff" });
    chart.setOption({ toolbox: { show: true } });
    return url;
  }

  // Fonction PNG téléchargeable depuis la toolbar
  const downloadEchartsPng = async (pixelRatio: number = 2) => {
    const chart = echartsRef.current;
    if (!chart) throw new Error("Graphique non encore initialisé");
    const url = getEchartsDataURLClean(chart, pixelRatio);
    const a = document.createElement("a");
    a.href = url;
    a.download = "graphique_echarts.png";
    a.click();
  };

  // Fonction PNG → presse-papiers (pour coller dans Word, Outlook, etc.)
  const copyEchartsPng = async () => {
    const chart = echartsRef.current;
    if (!chart) throw new Error("Graphique non encore initialisé");
    const dataUrl = getEchartsDataURLClean(chart, 2);
    // Convertir le data URI en Blob PNG
    const res  = await fetch(dataUrl);
    const blob = await res.blob();
    await navigator.clipboard.write([
      new ClipboardItem({ "image/png": blob }),
    ]);
  };

  /**
   * Extrait les dimensions d'un SVG.
   * Priorité : attributs width/height > viewBox > fallback 800×600.
   * Nécessaire car Mermaid n'émet pas toujours width/height explicites,
   * ce qui rend img.naturalWidth = 0 une fois chargé dans une <img>.
   */
  function parseSvgDimensions(svg: string): { w: number; h: number } {
    const parser = new DOMParser();
    const doc = parser.parseFromString(svg, "image/svg+xml");
    const el  = doc.querySelector("svg");
    if (!el) return { w: 800, h: 600 };

    const wAttr = parseFloat(el.getAttribute("width")  ?? "");
    const hAttr = parseFloat(el.getAttribute("height") ?? "");
    if (wAttr > 0 && hAttr > 0) return { w: wAttr, h: hAttr };

    const vb = el.getAttribute("viewBox");
    if (vb) {
      const parts = vb.trim().split(/[\s,]+/).map(Number);
      if (parts.length === 4 && parts[2] > 0 && parts[3] > 0)
        return { w: parts[2], h: parts[3] };
    }
    return { w: 800, h: 600 };
  }

  /** Convertit le SVG Mermaid en PNG via un canvas offscreen */
  async function mermaidSvgToPngBlob(pixelRatio: number = 2): Promise<Blob> {
    const svg = mermaidSvgRef.current;
    if (!svg) throw new Error("Diagramme non encore rendu");
    const { w: svgW, h: svgH } = parseSvgDimensions(svg);
    return new Promise((resolve, reject) => {
      const img = new Image();
      const blob = new Blob([svg], { type: "image/svg+xml" });
      const url = URL.createObjectURL(blob);
      img.onload = () => {
        const canvas = document.createElement("canvas");
        const w = (img.naturalWidth  || svgW) * pixelRatio;
        const h = (img.naturalHeight || svgH) * pixelRatio;
        canvas.width  = w;
        canvas.height = h;
        const ctx = canvas.getContext("2d")!;
        ctx.drawImage(img, 0, 0, w, h);
        URL.revokeObjectURL(url);
        canvas.toBlob((b) => b ? resolve(b) : reject(new Error("Conversion PNG échouée")), "image/png");
      };
      img.onerror = () => { URL.revokeObjectURL(url); reject(new Error("Chargement SVG échoué")); };
      img.src = url;
    });
  }

  const downloadMermaidPng = async (pixelRatio: number = 2) => {
    const blob = await mermaidSvgToPngBlob(pixelRatio);
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "diagramme_mermaid.png";
    a.click();
  };

  const copyMermaidPng = async () => {
    const blob = await mermaidSvgToPngBlob(2);
    await navigator.clipboard.write([new ClipboardItem({ "image/png": blob })]);
  };

  return (
    <div style={s.root}>
      {/* ── En-tête : titre + boutons copier + fermer ────────────────── */}
      <div style={s.header}>
        <div style={s.headerLeft}>
          {active && (
            <span style={s.activeTitle}>
              <span style={s.activeIcon}>{KIND_ICON[active.kind]}</span>
              <span style={s.activeTitleText}>{active.title}</span>
            </span>
          )}
        </div>
        {active && (
          <CopyToolbar
            artifact={active}
            onDownloadPng={active.kind === "echarts" ? downloadEchartsPng
              : (active.kind === "code" && active.language === "mermaid") ? downloadMermaidPng
              : undefined}
            onCopyPng={active.kind === "echarts" ? copyEchartsPng
              : (active.kind === "code" && active.language === "mermaid") ? copyMermaidPng
              : undefined}
          />
        )}
        <button
          onClick={onClose}
          title="Fermer le panneau"
          style={s.closeBtn}
          aria-label="Fermer"
        >✕</button>
      </div>

      {/* ── Barre langue pour le code ────────────────────────────────── */}
      {active?.kind === "code" && (
        <div style={s.codeSubbar}>
          <span style={s.langBadge}>{active.language || "text"}</span>
        </div>
      )}

      {/* ── Corps : nav latérale (si > 1) + contenu ─────────────────── */}
      <div style={s.body}>
        {hasMany && (
          <NavPanel
            artifacts={artifacts}
            activeIdx={activeIdx}
            onSelect={onSelectArtifact}
          />
        )}

        <div style={s.content}>
          {active ? (
            <ArtifactContent key={active.id} artifact={active} echartsRef={echartsRef} mermaidSvgRef={mermaidSvgRef} />
          ) : (
            <div style={s.empty}>
              <span style={s.emptyIcon}>◫</span>
              <p style={s.emptyText}>Aucun artefact à afficher</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
});

// ── Styles ───────────────────────────────────────────────────────────────────

const s: Record<string, React.CSSProperties> = {
  root: {
    display: "flex",
    flexDirection: "column",
    height: "100%",
    background: "var(--artifact-bg)",
  },

  // ── En-tête ──────────────────────────────────────────────────────────────
  header: {
    display: "flex",
    alignItems: "center",
    gap: 8,
    padding: "8px 12px",
    borderBottom: "1px solid var(--border)",
    background: "var(--artifact-bg)",
    minHeight: 44,
    flexShrink: 0,
    flexWrap: "nowrap" as const,
  },
  headerLeft: {
    flex: 1,
    display: "flex",
    alignItems: "center",
    overflow: "hidden",
    minWidth: 0,
  },
  activeTitle: {
    display: "flex",
    alignItems: "center",
    gap: 6,
    overflow: "hidden",
    minWidth: 0,
  },
  activeIcon: {
    fontSize: 15,
    flexShrink: 0,
  },
  activeTitleText: {
    fontSize: 13,
    fontWeight: 600,
    color: "var(--text-primary)",
    overflow: "hidden",
    whiteSpace: "nowrap" as const,
    textOverflow: "ellipsis",
  },
  closeBtn: {
    background: "none",
    border: "none",
    color: "var(--text-muted)",
    cursor: "pointer",
    fontSize: 14,
    padding: "2px 6px",
    borderRadius: 4,
    lineHeight: 1,
    flexShrink: 0,
    transition: "color 0.15s, background 0.15s",
  },

  // ── Sous-barre langue code ────────────────────────────────────────────────
  codeSubbar: {
    display: "flex",
    alignItems: "center",
    padding: "4px 12px",
    background: "var(--elevated-bg)",
    borderBottom: "1px solid var(--border)",
    flexShrink: 0,
  },
  langBadge: {
    fontSize: 11,
    color: "var(--text-muted)",
    fontFamily: "monospace",
    background: "var(--surface-bg)",
    border: "1px solid var(--border)",
    borderRadius: 4,
    padding: "1px 7px",
  },

  // ── Corps (nav + contenu) ────────────────────────────────────────────────
  body: {
    flex: 1,
    display: "flex",
    flexDirection: "row",
    overflow: "hidden",
    minHeight: 0,
  },

  // ── Zone de contenu ──────────────────────────────────────────────────────
  content: {
    flex: 1,
    overflowY: "auto" as const,
    overflowX: "hidden" as const,
    minWidth: 0,
  },
  empty: {
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    height: "100%",
    gap: 12,
    opacity: 0.4,
  },
  emptyIcon: {
    fontSize: 40,
    color: "var(--text-muted)",
  },
  emptyText: {
    margin: 0,
    fontSize: 13,
    color: "var(--text-muted)",
  },

  // ── Code ────────────────────────────────────────────────────────────────
  codeContainer: {
    display: "flex",
    flexDirection: "column",
    height: "100%",
  },
  syntaxWrapper: {
    flex: 1,
    overflowY: "auto" as const,
  },
  mermaidWrapper: {
    flex: 1,
    overflowY: "auto" as const,
    overflowX: "auto" as const,
    padding: "16px",
    boxSizing: "border-box" as const,
    width: "100%",
  },

  // ── Markdown ─────────────────────────────────────────────────────────────
  mdContainer: {
    padding: "20px 24px",
    fontSize: 14,
    lineHeight: 1.7,
    color: "var(--text-primary)",
  },

  // ── Image ─────────────────────────────────────────────────────────────────
  imageContainer: {
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    padding: 16,
    height: "100%",
  },
  image: {
    maxWidth: "100%",
    maxHeight: "100%",
    objectFit: "contain" as const,
    borderRadius: 6,
    border: "1px solid var(--border)",
    cursor: "pointer",
  },
};
