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
 * echarts-defaults.ts
 *
 * Defaults de thème ECharts cohérents avec la charte graphique de Prométhée.
 *
 * Stratégie : les couleurs de l'app sont définies via des variables CSS sur
 * :root (theme.css). On les lit au moment de la création de l'instance pour
 * construire un objet de configuration ECharts qui s'adapte automatiquement
 * au thème actif (dark / light).
 *
 * Utilisation :
 *   import { buildEChartsDefaults, mergeEChartsOption } from "../../lib/echarts-defaults";
 *
 *   const defaults = buildEChartsDefaults();          // lire les CSS vars
 *   const finalOpt = mergeEChartsOption(defaults, userOption);
 *   chart.setOption(finalOpt);
 *
 * Porté et adapté depuis Démeter (même auteur) — palette et variables CSS
 * ajustées pour Prométhée.
 */

// ── Palette de couleurs de graphiques ────────────────────────────────────────
//
// Identique entre les deux thèmes : couleurs douces mais bien contrastées,
// lisibles sur fond sombre comme clair.
// L'accent Prométhée (orange #d4813d / #8e4e18) est placé en premier pour
// que la première série soit toujours dans la charte de l'app.
const CHART_PALETTE_DARK = [
  "#d4813d", // accent Prométhée dark
  "#7aafd4", // accent-assistant dark
  "#6abf8a", // vert doux
  "#c97fc4", // violet doux
  "#e8c96a", // jaune/or doux
  "#6ac0c0", // cyan doux
  "#e07878", // rouge doux
  "#7eaadd", // bleu clair
  "#c9a87a", // sable
  "#a0c87e", // vert pomme
];

const CHART_PALETTE_LIGHT = [
  "#8e4e18", // accent Prométhée light
  "#3a6e9e", // accent-assistant light
  "#3d8f5f", // vert
  "#7a4a9e", // violet
  "#9e7e20", // or
  "#2e8e8e", // cyan
  "#9e4040", // rouge
  "#3a5e9e", // bleu
  "#8e6e3a", // sable
  "#5e8e3a", // vert pomme
];

// ── Nettoyage du code ECharts généré par le LLM ─────────────────────────────
//
// Parseur caractère-par-caractère (O(n), un seul pass) qui gère :
//   • strings "..." et '...' avec échappement correct
//     (les apostrophes sont converties en guillemets doubles)
//   • template literals `...` avec ${} imbriqués
//   • commentaires // et /* */
//   • ? dans les tableaux → null (ex: [1, ?, 3])
//   • virgules trailing avant } ou ]
//
// Résultat : code JS valide passable à new Function(`return (${cleaned})`).
//
// Porté depuis Démeter (text.ts → cleanEChartsCode).

export function cleanEChartsCode(src: string): string {
  src = (src || "").trim();
  let out = "";
  let i = 0;

  while (i < src.length) {
    // ── String double-quote ──────────────────────────────────────────────
    if (src[i] === '"') {
      out += '"'; i++;
      while (i < src.length) {
        if (src[i] === "\\") { out += src[i] + (src[i + 1] || ""); i += 2; continue; }
        if (src[i] === '"')  { out += '"'; i++; break; }
        if (src[i] === "\n") { out += "\\n"; i++; continue; }
        if (src[i] === "\r") { i++; continue; }
        out += src[i++];
      }
      continue;
    }

    // ── String single-quote → converti en double-quote ───────────────────
    if (src[i] === "'") {
      out += '"'; i++;
      while (i < src.length) {
        if (src[i] === "\\") { out += src[i] + (src[i + 1] || ""); i += 2; continue; }
        if (src[i] === '"')  { out += '\\"'; i++; continue; }
        if (src[i] === "\n") { out += "\\n"; i++; continue; }
        if (src[i] === "\r") { i++; continue; }
        if (src[i] === "'")  { out += '"'; i++; break; }
        out += src[i++];
      }
      continue;
    }

    // ── Template literal `...` avec ${} imbriqués ────────────────────────
    if (src[i] === "`") {
      out += "`"; i++;
      let depth = 0;
      while (i < src.length) {
        if (src[i] === "\\") { out += src[i] + (src[i + 1] || ""); i += 2; continue; }
        if (src[i] === "$" && src[i + 1] === "{") { out += "${"; i += 2; depth++; continue; }
        if (depth > 0 && src[i] === "}") { out += "}"; i++; depth--; continue; }
        if (depth === 0 && src[i] === "`") { out += "`"; i++; break; }
        out += src[i++];
      }
      continue;
    }

    // ── Commentaire ligne //... ──────────────────────────────────────────
    if (src[i] === "/" && src[i + 1] === "/") {
      while (i < src.length && src[i] !== "\n") i++;
      continue;
    }

    // ── Commentaire bloc /* ... */ ───────────────────────────────────────
    if (src[i] === "/" && src[i + 1] === "*") {
      i += 2;
      while (i < src.length && !(src[i] === "*" && src[i + 1] === "/")) i++;
      i += 2;
      continue;
    }

    out += src[i++];
  }

  // ? dans les tableaux → null  (ex: [1, ?, 3])
  out = out.replace(/(?<=[[\],]\s*)\?(?=\s*[,\]])/g, "null");
  // Virgules trailing avant } ou ]
  out = out.replace(/,(\s*[}\]])/g, "$1");

  return out;
}

// ── Lecture des variables CSS du thème actif ─────────────────────────────────

function getCssVar(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

// ── Construction des defaults adaptés au thème courant ───────────────────────

export function buildEChartsDefaults(isDark: boolean): Record<string, unknown> {
  // Lecture des tokens CSS de Prométhée
  const textPrimary = getCssVar("--text-primary");
  const textMuted   = getCssVar("--text-muted");
  const borderColor = getCssVar("--border");
  const surfaceBg   = getCssVar("--surface-bg");

  // Si les variables CSS ne sont pas encore disponibles (SSR, test),
  // on utilise des fallbacks cohérents avec le thème dark par défaut.
  const fg      = textPrimary || (isDark ? "#e4e2ec" : "#1e1c18");
  const subtle  = textMuted   || (isDark ? "#8a8a98" : "#646058");
  const border  = borderColor || (isDark ? "#2e2e34" : "#d8d4cc");
  const surface = surfaceBg   || (isDark ? "#1c1c1f" : "#e6e3dc");

  const palette = isDark ? CHART_PALETTE_DARK : CHART_PALETTE_LIGHT;

  // Tooltip : fond surface + texte primaire pour rester cohérent
  const tooltipBg     = isDark ? "#242428" : "#f2f0eb";
  const tooltipBorder = isDark ? "#3a3a40" : "#b8b4ac";
  const tooltipFg     = isDark ? "#e4e2ec" : "#1e1c18";

  return {
    backgroundColor: "transparent",

    color: palette,

    textStyle: {
      fontFamily: "inherit",
      color: fg,
      fontSize: 12,
    },

    title: {
      textStyle: {
        color: fg,
        fontWeight: 600,
        fontSize: 14,
        fontFamily: "inherit",
      },
      subtextStyle: {
        color: subtle,
        fontFamily: "inherit",
      },
    },

    legend: {
      orient: "horizontal",
      bottom: 0,
      left: "center",
      textStyle: { color: fg, fontFamily: "inherit" },
      pageTextStyle: { color: subtle },
      inactiveColor: subtle,
    },

    tooltip: {
      backgroundColor: tooltipBg,
      borderColor: tooltipBorder,
      borderWidth: 1,
      textStyle: { color: tooltipFg, fontFamily: "inherit", fontSize: 12 },
      axisPointer: {
        lineStyle:   { color: border, type: "dashed" },
        crossStyle:  { color: subtle },
        shadowStyle: { color: isDark ? "rgba(0,0,0,0.12)" : "rgba(0,0,0,0.04)" },
      },
    },

    grid: {
      containLabel: true,
      left: 16,
      right: 16,
      top: 40,
      bottom: 48,
      borderColor: border,
    },

    xAxis: {
      axisLine:   { lineStyle: { color: border } },
      axisTick:   { lineStyle: { color: border } },
      axisLabel:  { color: subtle, fontFamily: "inherit" },
      splitLine:  { lineStyle: { color: border, type: "dashed" } },
    },

    yAxis: {
      axisLine:   { lineStyle: { color: border } },
      axisTick:   { lineStyle: { color: border } },
      axisLabel:  { color: subtle, fontFamily: "inherit" },
      splitLine:  { lineStyle: { color: border, type: "dashed" } },
    },

    // Radar
    radar: {
      axisLine:  { lineStyle: { color: border } },
      splitLine: { lineStyle: { color: border } },
      splitArea: { areaStyle: { color: ["transparent", isDark ? "rgba(255,255,255,0.02)" : "rgba(0,0,0,0.02)"] } },
      axisName:  { color: fg },
    },
  };
}

// ── Fusion defaults + option LLM ─────────────────────────────────────────────
//
// Règles de fusion :
//   - Les clés de premier niveau de l'option LLM écrasent les defaults
//     (comportement standard du spread).
//   - Exception : `legend` est fusionné en profondeur pour préserver
//     `legend.bottom = 0` (la légende en bas est le comportement voulu ;
//     si le LLM envoie { legend: { data: [...] } } il ne faut pas perdre
//     le positionnement).
//   - `backgroundColor` reste toujours "transparent" (injecté dans les defaults
//     et l'option LLM peut le surcharger, mais on le force en dernier).

export function mergeEChartsOption(
  defaults: Record<string, unknown>,
  userOption: Record<string, unknown>,
): Record<string, unknown> {
  const merged: Record<string, unknown> = { ...defaults, ...userOption };

  // Fusion profonde de legend
  const baseLegend  = defaults.legend  as Record<string, unknown> | undefined;
  const userLegend  = userOption.legend as Record<string, unknown> | Array<Record<string, unknown>> | undefined;
  const firstLegend = Array.isArray(userLegend) ? userLegend[0] : userLegend;
  if (baseLegend || firstLegend) {
    merged.legend = { ...(baseLegend ?? {}), ...(firstLegend ?? {}) };
  }

  // Forcer backgroundColor transparent quoi qu'il arrive
  merged.backgroundColor = "transparent";

  return merged;
}
