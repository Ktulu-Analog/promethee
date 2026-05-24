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
 * docx.ts
 *
 * Génération de fichiers Word (.docx) entièrement côté client, sans round-trip
 * serveur. Parse le Markdown et produit un Document docx téléchargeable.
 *
 * Éléments Markdown supportés :
 *   H1 / H2 / H3 / H4, paragraphes, listes à puces et numérotées, blockquotes,
 *   séparateurs HR, blocs de code (avec coloration), tableaux GFM,
 *   inline : gras, italique, code inline
 *
 * Blocs spéciaux :
 *   - ```echarts … ``` : rendu off-screen via ECharts puis inséré en image PNG
 *   - ```mermaid … ``` : ignoré (pas de rendu headless disponible côté client)
 *   - ```word … ```   : ignoré (wrapper — le contenu est déjà parsé directement)
 *
 * Porté depuis Démeter (utils/docx.ts — même auteur) — API Tauri supprimée
 * (Prométhée est une app web), import de cleanEChartsCode / buildEChartsDefaults
 * depuis echarts-defaults.ts.
 */

import * as echarts from "echarts";
import {
  Document, Packer, Paragraph, TextRun, HeadingLevel,
  Table, TableRow, TableCell, WidthType, BorderStyle,
  AlignmentType, ShadingType, ImageRun,
} from "docx";
import { cleanEChartsCode, buildEChartsDefaults, mergeEChartsOption } from "./echarts-defaults";

// ── Palette de couleurs du document ─────────────────────────────────────────

const COLOR_H1      = "1a1a2e";
const COLOR_H2      = "16213e";
const COLOR_H3      = "0f3460";
const COLOR_TEXT    = "2d2d2d";
const COLOR_SUBTLE  = "666666";
const COLOR_CODE    = "3b3b3b";
const COLOR_CODE_BG = "f0f0f0";

// ── Inline formatting ────────────────────────────────────────────────────────
//
// Parse **gras**, *italique*, `code inline` et retourne un tableau de TextRun.

function inlineRuns(
  text: string,
  baseColor?: string,
  size?: number,
  forceBold?: boolean,
): TextRun[] {
  const runs: TextRun[] = [];
  const sz    = size || 22;
  const color = baseColor || COLOR_TEXT;
  const parts = text.split(/(`[^`]+`|\*\*[^*]+\*\*|\*[^*]+\*)/);

  for (const part of parts) {
    if (!part) continue;

    if (part.startsWith("**") && part.endsWith("**")) {
      runs.push(new TextRun({
        text: part.slice(2, -2), bold: true, color, size: sz,
      }));
    } else if (part.startsWith("*") && part.endsWith("*")) {
      runs.push(new TextRun({
        text: part.slice(1, -1), italics: true, color: COLOR_SUBTLE, size: sz,
      }));
    } else if (part.startsWith("`") && part.endsWith("`")) {
      runs.push(new TextRun({
        text: part.slice(1, -1),
        font: "Courier New",
        color: COLOR_CODE,
        size: Math.min(sz, 20),
        shading: { type: ShadingType.CLEAR, fill: COLOR_CODE_BG },
      }));
    } else {
      runs.push(new TextRun({
        text: part, bold: forceBold || false, color, size: sz,
      }));
    }
  }

  return runs.length
    ? runs
    : [new TextRun({ text, bold: forceBold || false, color, size: sz })];
}

// ── Rendu ECharts off-screen → PNG ───────────────────────────────────────────
//
// Crée un wrapper div positionné hors-écran, initialise une instance ECharts,
// attend la fin du rendu, exporte en PNG, puis dispose et supprime le wrapper.

async function renderEChartsToImage(codeContent: string): Promise<Uint8Array> {
  const wrapper = document.createElement("div");
  wrapper.style.cssText =
    "position:fixed;left:-9999px;top:-9999px;" +
    "width:900px;height:450px;opacity:0;pointer-events:none;";
  document.body.appendChild(wrapper);

  try {
    const cleaned = cleanEChartsCode(codeContent);
    // eslint-disable-next-line no-new-func
    const userOption = (new Function(`"use strict"; return (${cleaned})`))() as Record<string, unknown>;

    const chart = echarts.init(wrapper, null, { renderer: "canvas", width: 900, height: 450 });
    const defaults    = buildEChartsDefaults(false); // fond blanc pour le docx
    const finalOption = mergeEChartsOption(defaults, userOption);
    // Le fond doit être blanc pour l'export PNG dans Word
    (finalOption as any).backgroundColor = "#ffffff";
    chart.setOption(finalOption);

    // Attendre la fin du rendu (event "finished") avec timeout de sécurité
    await new Promise<void>((resolve) => {
      let settled = false;
      const onFinish = () => {
        if (settled) return;
        settled = true;
        setTimeout(resolve, 200);
      };
      chart.on("finished", onFinish);
      setTimeout(() => { if (!settled) onFinish(); }, 800);
    });

    const dataUrl  = chart.getDataURL({ type: "png", pixelRatio: 2, backgroundColor: "#ffffff" });
    chart.dispose();

    // Convertir le data URI en Uint8Array
    const base64 = dataUrl.split(",")[1];
    const binary = atob(base64);
    const imgData = new Uint8Array(binary.length);
    for (let k = 0; k < binary.length; k++) imgData[k] = binary.charCodeAt(k);
    return imgData;
  } finally {
    document.body.removeChild(wrapper);
  }
}

// ── Génération du document ────────────────────────────────────────────────────

/**
 * Génère un fichier .docx à partir de Markdown et déclenche son téléchargement
 * dans le navigateur.
 *
 * @param markdownContent  Contenu Markdown à convertir
 * @param filename         Nom du fichier téléchargé (défaut : "document.docx")
 */
export async function generateDocx(
  markdownContent: string,
  filename?: string,
): Promise<string> {
  const lines    = markdownContent.split("\n");
  const children: (Paragraph | Table)[] = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];

    // ── H1 ──────────────────────────────────────────────────────────────────
    if (/^# /.test(line)) {
      children.push(new Paragraph({
        heading: HeadingLevel.HEADING_1,
        children: inlineRuns(line.slice(2).trim(), COLOR_H1, 36, true),
        spacing: { before: 300, after: 160 },
        border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: "cccccc", space: 4 } },
      }));
      i++; continue;
    }

    // ── H2 ──────────────────────────────────────────────────────────────────
    if (/^## /.test(line)) {
      children.push(new Paragraph({
        heading: HeadingLevel.HEADING_2,
        children: inlineRuns(line.slice(3).trim(), COLOR_H2, 28, true),
        spacing: { before: 240, after: 120 },
      }));
      i++; continue;
    }

    // ── H3 ──────────────────────────────────────────────────────────────────
    if (/^### /.test(line)) {
      children.push(new Paragraph({
        heading: HeadingLevel.HEADING_3,
        children: inlineRuns(line.slice(4).trim(), COLOR_H3, 24, true),
        spacing: { before: 180, after: 80 },
      }));
      i++; continue;
    }

    // ── H4 ──────────────────────────────────────────────────────────────────
    if (/^#### /.test(line)) {
      children.push(new Paragraph({
        children: inlineRuns(line.slice(5).trim(), COLOR_SUBTLE, 22, true),
        spacing: { before: 140, after: 60 },
      }));
      i++; continue;
    }

    // ── HR ──────────────────────────────────────────────────────────────────
    if (/^---+$/.test(line.trim())) {
      children.push(new Paragraph({
        children: [new TextRun({ text: "" })],
        border: { bottom: { style: BorderStyle.SINGLE, size: 4, color: "dddddd", space: 1 } },
        spacing: { before: 120, after: 120 },
      }));
      i++; continue;
    }

    // ── Blockquote ──────────────────────────────────────────────────────────
    if (/^> /.test(line)) {
      children.push(new Paragraph({
        children: inlineRuns(line.slice(2).trim(), COLOR_SUBTLE),
        indent: { left: 560 },
        border: { left: { style: BorderStyle.SINGLE, size: 12, color: "aaaaaa", space: 8 } },
        spacing: { before: 80, after: 80 },
      }));
      i++; continue;
    }

    // ── Bloc de code (avec gestion de l'imbrication) ─────────────────────────
    if (line.startsWith("```")) {
      const blockLang = line.slice(3).trim().toLowerCase();
      i++;
      const codeLines: string[] = [];
      let depth = 1;

      while (i < lines.length && depth > 0) {
        const current = lines[i];
        if (current.startsWith("```")) {
          const innerLang = current.slice(3).trim();
          if (innerLang) { depth++; } else { depth--; if (depth === 0) { i++; break; } }
        }
        if (depth > 0) codeLines.push(current);
        i++;
      }

      const codeContent = codeLines.join("\n");

      // Blocs echarts → rendu PNG
      if (blockLang === "echarts") {
        try {
          const imgData = await renderEChartsToImage(codeContent);
          children.push(new Paragraph({
            children: [new ImageRun({
              data: imgData,
              transformation: { width: 600, height: 300 },
              type: "png",
            })],
            spacing: { before: 120, after: 120 },
          }));
        } catch (e) {
          console.warn("ECharts render failed in generateDocx:", e);
          children.push(new Paragraph({
            children: [new TextRun({
              text: "[Graphique — rendu indisponible]",
              color: COLOR_SUBTLE, italics: true, size: 20,
            })],
            spacing: { before: 60, after: 60 },
          }));
        }
        continue;
      }

      // Blocs word / mermaid → ignorés (wrapper ou pas de rendu headless)
      if (blockLang === "word" || blockLang === "mermaid") continue;

      // Autres blocs de code → police monospace avec fond gris
      for (const cl of codeLines) {
        children.push(new Paragraph({
          children: [new TextRun({
            text: cl, font: "Courier New", color: COLOR_CODE, size: 18,
          })],
          shading: { type: ShadingType.CLEAR, fill: COLOR_CODE_BG },
          spacing: { before: 0, after: 0 },
          indent: { left: 280 },
        }));
      }
      continue;
    }

    // ── Tableau Markdown ────────────────────────────────────────────────────
    if (/^\|/.test(line)) {
      const tableLines: string[] = [];
      while (i < lines.length && /^\|/.test(lines[i])) {
        tableLines.push(lines[i]); i++;
      }
      const dataRows = tableLines.filter(
        (r) => !/^\|[-:\s|]+\|$/.test(r.trim()),
      );
      if (dataRows.length >= 1) {
        const [head, ...body] = dataRows;
        const parseRow = (r: string) =>
          r.split("|").filter((_, j, a) => j > 0 && j < a.length - 1).map((c) => c.trim());

        const headers  = parseRow(head);
        const colCount = headers.length;
        const colW     = Math.floor(9360 / Math.max(colCount, 1));

        const tableRows = [
          new TableRow({
            tableHeader: true,
            children: headers.map((h) =>
              new TableCell({
                children: [new Paragraph({
                  children: [new TextRun({ text: h, bold: true, color: COLOR_H2, size: 20 })],
                  spacing: { before: 60, after: 60 },
                })],
                shading: { type: ShadingType.CLEAR, fill: "f5f5f5" },
                margins: { top: 80, bottom: 80, left: 140, right: 140 },
                width: { size: colW, type: WidthType.DXA },
              }),
            ),
          }),
          ...body.map((row, ri) =>
            new TableRow({
              children: parseRow(row).map((cell) =>
                new TableCell({
                  children: [new Paragraph({
                    children: inlineRuns(cell, COLOR_TEXT),
                    spacing: { before: 40, after: 40 },
                  })],
                  shading: ri % 2 === 1
                    ? { type: ShadingType.CLEAR, fill: "fafafa" }
                    : undefined,
                  margins: { top: 60, bottom: 60, left: 140, right: 140 },
                  width: { size: colW, type: WidthType.DXA },
                }),
              ),
            }),
          ),
        ];

        children.push(new Table({
          rows: tableRows,
          width: { size: 9360, type: WidthType.DXA },
          columnWidths: Array(colCount).fill(colW),
        }));
        // Espacement après le tableau
        children.push(new Paragraph({
          children: [new TextRun("")],
          spacing: { before: 80, after: 0 },
        }));
      }
      continue;
    }

    // ── Liste à puces ────────────────────────────────────────────────────────
    if (/^[*\-] /.test(line)) {
      children.push(new Paragraph({
        bullet: { level: 0 },
        children: inlineRuns(line.slice(2).trim(), COLOR_TEXT),
        spacing: { before: 40, after: 40 },
      }));
      i++; continue;
    }

    // ── Liste numérotée ──────────────────────────────────────────────────────
    const olMatch = line.match(/^(\d+)\. (.+)/);
    if (olMatch) {
      children.push(new Paragraph({
        numbering: { reference: "default-numbering", level: 0 },
        children: inlineRuns(olMatch[2].trim(), COLOR_TEXT),
        spacing: { before: 40, after: 40 },
      }));
      i++; continue;
    }

    // ── Ligne vide ───────────────────────────────────────────────────────────
    if (!line.trim()) {
      children.push(new Paragraph({
        children: [new TextRun("")],
        spacing: { before: 60, after: 0 },
      }));
      i++; continue;
    }

    // ── Ligne entièrement en gras → titre promu ──────────────────────────────
    const boldLineMatch = line.match(/^\*\*(.+)\*\*\s*$/);
    if (boldLineMatch) {
      const boldText = boldLineMatch[1].trim();
      const level = /^\d+\.\d+/.test(boldText) ? 3 : /^\d+[.)]/.test(boldText) ? 2 : 1;
      if (level === 1) {
        children.push(new Paragraph({
          heading: HeadingLevel.HEADING_1,
          children: [new TextRun({ text: boldText, bold: true, color: COLOR_H1, size: 36 })],
          spacing: { before: 300, after: 160 },
          border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: "cccccc", space: 4 } },
        }));
      } else if (level === 2) {
        children.push(new Paragraph({
          heading: HeadingLevel.HEADING_2,
          children: [new TextRun({ text: boldText, bold: true, color: COLOR_H2, size: 28 })],
          spacing: { before: 240, after: 120 },
        }));
      } else {
        children.push(new Paragraph({
          heading: HeadingLevel.HEADING_3,
          children: [new TextRun({ text: boldText, bold: true, color: COLOR_H3, size: 24 })],
          spacing: { before: 180, after: 80 },
        }));
      }
      i++; continue;
    }

    // ── Paragraphe normal ────────────────────────────────────────────────────
    children.push(new Paragraph({
      children: inlineRuns(line, COLOR_TEXT),
      spacing: { before: 60, after: 60 },
    }));
    i++;
  }

  // ── Construction du Document ─────────────────────────────────────────────

  const doc = new Document({
    numbering: {
      config: [{
        reference: "default-numbering",
        levels: [{
          level: 0,
          format: "decimal",
          text: "%1.",
          alignment: AlignmentType.START,
          style: { paragraph: { indent: { left: 560, hanging: 360 } } },
        }],
      }],
    },
    styles: {
      default: {
        document: { run: { font: "Calibri", color: COLOR_TEXT, size: 22 } },
      },
    },
    sections: [{
      properties: {
        page: { margin: { top: 1134, right: 1134, bottom: 1134, left: 1134 } },
      },
      children,
    }],
  });

  // ── Sauvegarde dans le VFS Prométhée ────────────────────────────────────
  const blob     = await Packer.toBlob(doc);
  const safeName = filename || "document.docx";

  const { getToken } = await import("../hooks/useAuth");
  const token = getToken();

  const formData = new FormData();
  formData.append("file", blob, safeName);

  const BASE = (import.meta as any).env?.VITE_API_URL ?? "http://localhost:8000";
  const res  = await fetch(`${BASE}/vfs/save-blob`, {
    method: "POST",
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: formData,
    credentials: "include",
  });

  if (!res.ok) {
    const detail = await res.text().catch(() => res.statusText);
    throw new Error(`VFS save-blob failed (${res.status}): ${detail}`);
  }

  const { path: vfsPath } = await res.json() as { path: string };
  return vfsPath;
}
