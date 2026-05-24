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
import { buildEChartsDefaults, mergeEChartsOption, cleanEChartsCode } from "../../lib/echarts-defaults";

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

        // Nettoyage du code LLM (parseur caractère par caractère, robuste)
        // puis évaluation via new Function() — même stratégie que Démeter.
        let userOption: Record<string, unknown>;
        try {
          const cleaned = cleanEChartsCode(code);
          // eslint-disable-next-line no-new-func
          userOption = new Function(`"use strict"; return (${cleaned})`)() as Record<string, unknown>;
        } catch (parseErr: any) {
          throw new Error(`Config ECharts invalide — ${parseErr?.message ?? "erreur de parsing"}`);
        }

        // Créer l'instance sans thème ECharts natif :
        // les couleurs et styles sont entièrement gérés par nos defaults CSS.
        const chart = echarts.init(containerRef.current, null, {
          renderer: "canvas",
        });

        // Fusionner defaults (CSS Prométhée) + option LLM
        const defaults    = buildEChartsDefaults(isDark);
        const finalConfig = mergeEChartsOption(defaults, userOption);

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
  // Le toolbox est masqué le temps du snapshot puis restauré immédiatement,
  // afin qu'il n'apparaisse pas dans l'image exportée.

  function getDataURLClean(pixelRatio = 2, bgColor?: string): string {
    const chart = chartRef.current;
    if (!chart) return "";
    chart.setOption({ toolbox: { show: false } });
    const url = chart.getDataURL({
      type: "png",
      pixelRatio,
      backgroundColor: bgColor ?? (isDark ? "#1c1c1f" : "#ffffff"),
    });
    chart.setOption({ toolbox: { show: true } });
    return url;
  }

  function downloadPng() {
    if (!chartRef.current) return;
    const url = getDataURLClean(2);
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
