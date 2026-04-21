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
 * EChartsBlock.tsx
 *
 * Rendu interactif des graphiques Apache ECharts à partir d'une config JSON.
 *
 * Le LLM génère un bloc ```echarts avec une config JSON standard ECharts.
 * Ce composant l'instancie, gère le thème dark/light, le resize, et propose
 * le téléchargement en PNG — même pattern que MermaidBlock.
 *
 * Avantages vs Matplotlib :
 *   - Rendu côté client (pas de round-trip serveur)
 *   - Graphiques interactifs (zoom, tooltip, légende cliquable)
 *   - Aucune dépendance Python supplémentaire
 *
 * Usage LLM — le modèle produit :
 *   ```echarts
 *   {
 *     "title": { "text": "Ventes par mois" },
 *     "xAxis": { "type": "category", "data": ["Jan","Fév","Mar"] },
 *     "yAxis": { "type": "value" },
 *     "series": [{ "type": "bar", "data": [120, 200, 150] }]
 *   }
 *   ```
 */

import React, { useEffect, useRef, useState } from "react";

interface Props {
  code: string;          // contenu brut du bloc ```echarts
  isDark: boolean;
  onChartReady?: (instance: any) => void;  // callback pour exposer l'instance ECharts
  variant?: "chat" | "panel";              // contexte de rendu (défaut: "chat")
}

// ── Chargement lazy d'ECharts ─────────────────────────────────────────────

let echartsPromise: Promise<typeof import("echarts")> | null = null;

function getECharts(): Promise<typeof import("echarts")> {
  if (!echartsPromise) {
    echartsPromise = import("echarts");
  }
  return echartsPromise;
}

// ── Nettoyage JSON robuste (tolérant aux sorties LLM imparfaites) ─────────
//
// Les LLM produisent régulièrement du "JSON-like" invalide pour les types
// de graphiques complexes (pie, scatter, radar, funnel, gauge…) :
//   • commentaires JS  // ... ou /* ... */
//   • virgules trailing avant } ou ]
//   • clés non-quotées  { xAxis: { ... } }
//   • fonctions inline  formatter: function(v) { return v; }
//   • valeurs NaN / Infinity / undefined
//   • apostrophes à la place des guillemets  'bar'
//   • retours à la ligne dans les strings
//
// Stratégie en deux passes :
//   1. Nettoyage textuel des patterns les plus courants
//   2. Évaluation via Function() en sandbox restreinte pour récupérer
//      les configurations contenant de vraies fonctions JS (formatter, etc.)
//      → les fonctions sont remplacées par null pour que JSON.parse passe,
//        puis réinjectées dans l'objet final via eval contrôlé.

function parseEChartsConfig(raw: string): any {
  // ── Passe 1 : nettoyage textuel ────────────────────────────────────────

  let cleaned = raw.trim();

  // Supprimer les commentaires JS sur une ligne  //...
  cleaned = cleaned.replace(/\/\/[^\n\r]*/g, "");

  // Supprimer les commentaires JS sur plusieurs lignes  /* ... */
  cleaned = cleaned.replace(/\/\*[\s\S]*?\*\//g, "");

  // Supprimer les virgules trailing avant } ou ]
  cleaned = cleaned.replace(/,\s*([}\]])/g, "$1");

  // Remplacer les valeurs spéciales JS non-JSON
  cleaned = cleaned.replace(/\bNaN\b/g, "null");
  cleaned = cleaned.replace(/\bInfinity\b/g, "null");
  cleaned = cleaned.replace(/\bundefined\b/g, "null");

  // ── Tentative 1 : JSON.parse direct ───────────────────────────────────
  try {
    return JSON.parse(cleaned);
  } catch (_) {
    // continue vers les passes suivantes
  }

  // ── Passe 2 : citer les clés non-quotées ──────────────────────────────
  // Transforme  { xAxis: {  →  { "xAxis": {
  // Attention : ne pas toucher aux clés déjà quotées ni aux valeurs string
  const quotedKeys = cleaned.replace(
    /([{,]\s*)([a-zA-Z_$][a-zA-Z0-9_$]*)(\s*:)/g,
    (_, prefix, key, colon) => `${prefix}"${key}"${colon}`
  );

  try {
    return JSON.parse(quotedKeys);
  } catch (_) {
    // continue
  }

  // ── Passe 3 : extraction des fonctions + JSON.parse ───────────────────
  // Les fonctions JS (formatter, etc.) sont remplacées par un placeholder
  // unique, puis réinjectées après parsing.
  const functions: string[] = [];
  const withPlaceholders = quotedKeys.replace(
    /:\s*(function\s*\([^)]*\)\s*\{[\s\S]*?\}|(?:\([^)]*\)|[a-zA-Z_$][a-zA-Z0-9_$]*)\s*=>\s*(?:\{[\s\S]*?\}|[^,\n\]}\)]+))/g,
    (_, fn) => {
      const idx = functions.length;
      functions.push(fn);
      return `: "__FN_${idx}__"`;
    }
  );

  // Re-tenter la suppression virgules trailing après les remplacements
  const cleanedAgain = withPlaceholders.replace(/,\s*([}\]])/g, "$1");

  let parsed: any;
  try {
    parsed = JSON.parse(cleanedAgain);
  } catch (_) {
    // Passe 4 (dernier recours) : eval dans une Function isolée
    try {
      // eslint-disable-next-line no-new-func
      parsed = new Function(`"use strict"; return (${raw.trim()})`)();
      return parsed;
    } catch (evalErr: any) {
      throw new Error(`JSON invalide — impossible de parser la config ECharts.\n${evalErr?.message ?? ""}`);
    }
  }

  // Réinjecter les fonctions JS parsées
  if (functions.length > 0) {
    const rehydrate = (obj: any): any => {
      if (obj === null || obj === undefined) return obj;
      if (typeof obj === "string") {
        const match = obj.match(/^__FN_(\d+)__$/);
        if (match) {
          try {
            // eslint-disable-next-line no-new-func
            return new Function(`"use strict"; return (${functions[parseInt(match[1], 10)]})`)();
          } catch {
            return null; // si la fonction est invalide, on la neutralise
          }
        }
        return obj;
      }
      if (Array.isArray(obj)) return obj.map(rehydrate);
      if (typeof obj === "object") {
        const result: any = {};
        for (const [k, v] of Object.entries(obj)) {
          result[k] = rehydrate(v);
        }
        return result;
      }
      return obj;
    };
    return rehydrate(parsed);
  }

  return parsed;
}

// ── Composant ─────────────────────────────────────────────────────────────

export function EChartsBlock({ code, isDark, onChartReady, variant = "chat" }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function render() {
      if (!containerRef.current) return;

      try {
        const echarts = await getECharts();
        if (cancelled) return;

        // Détruire l'instance précédente si re-render
        if (chartRef.current) {
          chartRef.current.dispose();
          chartRef.current = null;
        }

        const config = parseEChartsConfig(code);

        // Créer l'instance avec le bon thème
        const chart = echarts.init(containerRef.current, isDark ? "dark" : null, {
          renderer: "canvas",
        });

        // Fusionner un backgroundColor transparent pour coller au thème de l'app
        const finalConfig = {
          backgroundColor: "transparent",
          ...config,
        };

        chart.setOption(finalConfig);
        chartRef.current = chart;

        if (!cancelled) {
          setReady(true);
          onChartReady?.(chart);
        }
      } catch (e: any) {
        if (!cancelled) setError(e?.message ?? "Erreur ECharts inconnue");
      }
    }

    render();

    // Resize observer pour les redimensionnements de la fenêtre
    const ro = new ResizeObserver(() => {
      chartRef.current?.resize();
    });
    if (containerRef.current) ro.observe(containerRef.current);

    return () => {
      cancelled = true;
      ro.disconnect();
      chartRef.current?.dispose();
      chartRef.current = null;
    };
  }, [code, isDark]);

  // ── Téléchargement PNG ────────────────────────────────────────────────

  function downloadPng() {
    if (!chartRef.current) return;
    const url = chartRef.current.getDataURL({
      type: "png",
      pixelRatio: 2,
      backgroundColor: isDark ? "#1c1c1f" : "#ffffff",
    });
    const a = document.createElement("a");
    a.href = url;
    a.download = "graphique.png";
    a.click();
  }

  // ── Rendu erreur ─────────────────────────────────────────────────────

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
            Graphique ECharts — erreur de configuration
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

  // ── Rendu principal ───────────────────────────────────────────────────

  // En mode "panel" (panneau artefact) : pas de minWidth ni de margin négatif —
  // le graphique doit remplir exactement la zone disponible sans déborder.
  const isPanelMode = variant === "panel";

  return (
    <div
      style={{
        background: "var(--elevated-bg)",
        border: "1px solid var(--border)",
        borderRadius: "8px",
        padding: "12px",
        ...(isPanelMode ? {
          // Mode panneau : dimensionné par aspect-ratio du canvas enfant
          position: "relative" as const,
          margin: 0,
          display: "flex",
          flexDirection: "column" as const,
          minWidth: 0,
          overflow: "hidden",
          boxSizing: "border-box" as const,
        } : {
          // Mode chat : compense le padding de la bulle
          margin: "8px 0",
          marginRight: "calc(-10% / 0.9)",
          minWidth: "480px",
          boxSizing: "border-box" as const,
        }),
      }}
    >
      {/* Zone de rendu ECharts */}
      <div
        ref={containerRef}
        style={{
          width: "100%",
          ...(isPanelMode ? {
            // Ratio 1/2 : hauteur = largeur ÷ 2 — calculé automatiquement par CSS.
            // Le ResizeObserver existant appelle chart.resize() quand le panneau
            // est redimensionné, donc ECharts reste toujours bien calé.
            aspectRatio: "2 / 1",
            minHeight: 0,
            flexShrink: 0,
          } : {
            height: "420px",
            minHeight: "380px",
          }),
          opacity: ready ? 1 : 0,
          transition: "opacity 0.2s ease",
        }}
      />

      {/* Placeholder pendant le chargement */}
      {!ready && !error && (
        <div
          style={{
            ...(isPanelMode ? {
              // Superposé au canvas via position absolute pour ne pas affecter
              // le dimensionnement par aspect-ratio
              position: "absolute" as const,
              inset: 0,
            } : {
              height: "420px",
              marginTop: "-420px",
            }),
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            color: "var(--text-muted)",
            fontSize: "13px",
          }}
        >
          Rendu du graphique…
        </div>
      )}

      {/* Toolbar téléchargement */}
      {ready && (
        <div style={{ display: "flex", gap: "6px", marginTop: "8px", justifyContent: "flex-end" }}>
          <button
            onClick={downloadPng}
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
            ↓ PNG
          </button>
        </div>
      )}
    </div>
  );
}
