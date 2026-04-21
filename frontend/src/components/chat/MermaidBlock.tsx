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
 *
 * MermaidBlock.tsx
 *
 * Rendu asynchrone des diagrammes Mermaid, équivalent de mermaid_renderer.py.
 *
 * Utilise mermaid.js côté client pour rendre le SVG.
 * Boutons de téléchargement SVG/PNG fidèles aux boutons Qt.
 *
 * FIX : Mermaid injecte parfois des éléments d'erreur directement dans le DOM
 * (en dehors du composant React), cassant la mise en page. On les supprime
 * systématiquement après chaque tentative de rendu, qu'elle réussisse ou non.
 * L'erreur est affichée proprement dans la bulle de chat via onError.
 */

import React, { useEffect, useRef, useState } from "react";

interface Props {
  code: string;
  isDark: boolean;
  /** Callback optionnel : remonte l'erreur vers le chat parent */
  onError?: (msg: string) => void;
  /** Contexte de rendu : "chat" (défaut) compense le padding bulle, "panel" remplit le panneau artefact */
  variant?: "chat" | "panel";
  /** Callback optionnel : expose le SVG rendu pour export PNG depuis le panneau artefact */
  onSvgReady?: (svg: string) => void;
}

/** Compteur global — garantit des ids uniques même avec plusieurs instances simultanées */
let mermaidIdCounter = 0;

/** Dernier thème passé à mermaid.initialize() — null = jamais initialisé */
let lastMermaidTheme: string | null = null;

/**
 * File d'attente globale pour sérialiser les appels à mermaid.render().
 * Mermaid v11 n'est pas thread-safe : plusieurs renders simultanés se
 * disputent le DOM et produisent "can't access property firstChild, C is null".
 * Chaque appel enchaîne une Promise sur la précédente — les renders s'exécutent
 * l'un après l'autre sans jamais se chevaucher.
 */
let mermaidRenderQueue: Promise<void> = Promise.resolve();

function enqueueMermaidRender(fn: () => Promise<void>): Promise<void> {
  mermaidRenderQueue = mermaidRenderQueue.then(() => fn()).catch(() => fn());
  return mermaidRenderQueue;
}

async function getMermaid() {
  const m = await import("mermaid");
  return m.default;
}

/** Supprime tous les éléments d'erreur que Mermaid injecte hors-React dans le DOM */
function purgeMermaidErrorNodes() {
  // Mermaid v11 peut insérer des <div id="dmermaid-…"> et des éléments avec
  // la classe .error-icon / .error-text directement dans <body>.
  document
    .querySelectorAll(
      '[id^="dmermaid"], [id^="mermaid-"], .mermaid-error, ' +
      '.error-icon, .error-text, svg[id^="mermaid-"]'
    )
    .forEach((el) => {
      // Ne supprimer que les éléments orphelins dans <body>
      // (pas ceux intégrés dans un composant React monté)
      if (el.closest("[data-mermaid-host]") === null) {
        el.remove();
      }
    });
}

export function MermaidBlock({ code, isDark, onError, variant = "chat", onSvgReady }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [svgContent, setSvgContent] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  // ID unique basé sur un compteur global — évite les collisions entre instances simultanées
  const idRef = useRef(`mermaid-${++mermaidIdCounter}`);

  useEffect(() => {
    let cancelled = false;

    async function doRender() {
      try {
        const mermaid = await getMermaid();

        const theme = isDark ? "dark" : "default";

        if (lastMermaidTheme !== theme) {
          mermaid.initialize({
            startOnLoad: false,
            theme,
            themeVariables: isDark
              ? { background: "#1c1c1f", primaryColor: "#d4813d" }
              : { background: "#f2f0eb", primaryColor: "#8e4e18" },
          });
          lastMermaidTheme = theme;
        }

        // Rendre dans un conteneur détaché attaché à <body> avec data-mermaid-host
        // pour que purgeMermaidErrorNodes() d'une autre instance ne le supprime pas
        const host = document.createElement("div");
        host.setAttribute("data-mermaid-host", "true");
        host.style.position = "absolute";
        host.style.visibility = "hidden";
        host.style.pointerEvents = "none";
        document.body.appendChild(host);

        let svg: string;
        try {
          ({ svg } = await mermaid.render(idRef.current, code, host));
        } finally {
          // Toujours retirer le conteneur temporaire, succès ou échec
          if (host.parentNode) host.parentNode.removeChild(host);
        }

        if (!cancelled) {
          setSvgContent(svg);
          setError(null);
          onSvgReady?.(svg);
        }
      } catch (e: any) {
        purgeMermaidErrorNodes();

        if (!cancelled) {
          const msg = e?.message ?? "Erreur Mermaid inconnue";
          setError(msg);
          onError?.(msg);
        }
      }
    }

    // Sérialiser via la file globale — évite les renders simultanés qui se
    // corrompent mutuellement dans le DOM
    enqueueMermaidRender(() => cancelled ? Promise.resolve() : doRender());
    return () => {
      cancelled = true;
    };
  }, [code, isDark, onError]);

  // ── Téléchargements ──────────────────────────────────────────────────────

  function downloadSvg() {
    if (!svgContent) return;
    const blob = new Blob([svgContent], { type: "image/svg+xml" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "diagram.svg";
    a.click();
    URL.revokeObjectURL(url);
  }

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

  function downloadPng() {
    if (!svgContent) return;
    const SCALE = 2;
    const { w: svgW, h: svgH } = parseSvgDimensions(svgContent);
    const img = new Image();
    const blob = new Blob([svgContent], { type: "image/svg+xml" });
    const url = URL.createObjectURL(blob);
    img.onload = () => {
      // Préférer naturalWidth si disponible, sinon utiliser les dimensions parsées
      const w = (img.naturalWidth  || svgW) * SCALE;
      const h = (img.naturalHeight || svgH) * SCALE;
      const canvas = document.createElement("canvas");
      canvas.width  = w;
      canvas.height = h;
      const ctx = canvas.getContext("2d")!;
      ctx.drawImage(img, 0, 0, w, h);
      URL.revokeObjectURL(url);
      canvas.toBlob((b) => {
        if (!b) return;
        const a = document.createElement("a");
        a.href = URL.createObjectURL(b);
        a.download = "diagram.png";
        a.click();
      }, "image/png");
    };
    img.src = url;
  }

  // ── Rendu erreur (inline, dans la bulle) ─────────────────────────────────

  if (error) {
    return (
      <div
        style={{
          background: "var(--elevated-bg)",
          border: "1px solid var(--border)",
          borderRadius: "8px",
          padding: "10px 14px",
          margin: "8px 0",
          display: "flex",
          alignItems: "flex-start",
          gap: "8px",
        }}
      >
        <span style={{ fontSize: "16px", lineHeight: 1.4, flexShrink: 0 }}>⚠️</span>
        <div>
          <div
            style={{
              fontSize: "12px",
              fontWeight: 600,
              color: "var(--text-muted)",
              marginBottom: "4px",
              textTransform: "uppercase",
              letterSpacing: "0.05em",
            }}
          >
            Diagramme Mermaid — erreur de syntaxe
          </div>
          <pre
            style={{
              margin: 0,
              fontSize: "12px",
              color: "#e07878",
              whiteSpace: "pre-wrap",
              wordBreak: "break-word",
              fontFamily: "monospace",
            }}
          >
            {error}
          </pre>
        </div>
      </div>
    );
  }

  // ── Rendu en attente ─────────────────────────────────────────────────────

  if (!svgContent) {
    return (
      <div style={{ padding: "12px", color: "var(--text-muted)", fontSize: "13px" }}>
        Rendu du diagramme…
      </div>
    );
  }

  // ── Rendu SVG ────────────────────────────────────────────────────────────

  const isPanelMode = variant === "panel";

  return (
    <div
      data-mermaid-host="true"
      style={{
        background: "var(--elevated-bg)",
        border: "1px solid var(--border)",
        borderRadius: "8px",
        padding: "12px",
        boxSizing: "border-box" as const,
        ...(isPanelMode ? {
          // Mode panneau : remplit la zone disponible sans déborder
          margin: 0,
          width: "100%",
          minWidth: 0,
        } : {
          // Mode chat : même pattern qu'EChartsBlock pour occuper toute la bulle
          margin: "8px 0",
          marginRight: "calc(-10% / 0.9)",
          minWidth: "480px",
        }),
      }}
    >
      {/* SVG rendu */}
      <div
        ref={containerRef}
        dangerouslySetInnerHTML={{ __html: svgContent }}
        style={{ width: "100%", overflowX: "auto" }}
      />

      {/* Toolbar téléchargement */}
      <div
        style={{
          display: "flex",
          gap: "6px",
          marginTop: "8px",
          justifyContent: "flex-end",
        }}
      >
        {[
          { label: "SVG", onClick: downloadSvg },
          { label: "PNG", onClick: downloadPng },
        ].map(({ label, onClick }) => (
          <button
            key={label}
            onClick={onClick}
            style={{
              background: "var(--mermaid-btn-bg)",
              color: "var(--mermaid-btn-color)",
              border: "1px solid var(--mermaid-btn-border)",
              borderRadius: "4px",
              padding: "2px 8px",
              fontSize: "11px",
              cursor: "pointer",
            }}
          >
            ↓ {label}
          </button>
        ))}
      </div>
    </div>
  );
}
