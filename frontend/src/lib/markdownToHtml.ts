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
 * markdownToHtml.ts
 *
 * Convertit du Markdown en HTML stylé inline, compatible Word / LibreOffice.
 * Extrait de MessageBubble.tsx pour être partagé avec ArtifactPanel.
 *
 * Couvre : gras, italique, code inline, blocs de code, titres H1-H3,
 * listes à puces, listes numérotées, blockquotes, tableaux GFM, séparateurs.
 */

export function markdownToHtml(md: string): string {
  const esc = (s: string) =>
  s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

  const normLatex = (s: string): string => {
    s = s.replace(/\\\((.+?)\\\)/gs, (_m, inner) => `$${inner}$`);
    s = s.replace(/\\\[(.+?)\\\]/gs, (_m, inner) => `$$${inner}$$`);
    return s;
  };

  const inlineFormat = (raw: string): string => {
    raw = raw.replace(/<br\s*\/?>/gi, "\x00BR\x00");
    raw = normLatex(raw);

    const tokens: Array<{ t: "code" | "math" | "text"; v: string }> = [];
    const re = /`([^`]+)`|\$([^$\n]+)\$/g;
    let last = 0;
    let m: RegExpExecArray | null;
    re.lastIndex = 0;
    while ((m = re.exec(raw)) !== null) {
      if (m.index > last) tokens.push({ t: "text", v: raw.slice(last, m.index) });
      if (m[1] !== undefined) tokens.push({ t: "code", v: m[1] });
      else tokens.push({ t: "math", v: m[2] });
      last = m.index + m[0].length;
    }
    if (last < raw.length) tokens.push({ t: "text", v: raw.slice(last) });

    return tokens.map((tok) => {
      if (tok.t === "code")
        return `<code style="font-family:Courier New,monospace;font-size:.9em;background:#f4f4f4;padding:1px 4px;border-radius:3px">${esc(tok.v)}</code>`;
      if (tok.t === "math")
        return `<span style="font-family:Courier New,monospace;font-style:italic">${esc(tok.v)}</span>`;
      let s = esc(tok.v);
      s = s.replace(/\*\*\*(.+?)\*\*\*/g, "<strong><em>$1</em></strong>");
      s = s.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
      s = s.replace(/\*(.+?)\*/g, "<em>$1</em>");
      s = s.replace(/(?<![a-zA-Z0-9])_(.+?)_(?![a-zA-Z0-9])/g, "<em>$1</em>");
      s = s.replace(/~~(.+?)~~/g, "<s>$1</s>");
      s = s.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2">$1</a>');
    s = s.replace(/\x00BR\x00/g, "<br>");
    return s;
    }).join("");
  };

  const renderTable = (tableLines: string[]): string => {
    const rows = tableLines.filter((l) => !/^\|[\s|:-]+\|$/.test(l.trim()));
    if (rows.length === 0) return "";
    const parseRow = (l: string): string[] =>
    l.trim().replace(/^\||\\|$/g, "").split("|").map((c) => c.trim());
    const [headerRow, ...bodyRows] = rows;
    const headers = parseRow(headerRow);
    const thStyle = `border:1px solid #bbb;padding:6px 10px;background:#f0f0f0;font-weight:bold;text-align:left;`;
    const tdStyle = `border:1px solid #bbb;padding:5px 10px;vertical-align:top;`;
    const ths = headers.map((h) => `<th style="${thStyle}">${inlineFormat(h)}</th>`).join("");
    const trs = bodyRows.map((row) => {
      const cells = parseRow(row);
      const tds = cells.map((c) => `<td style="${tdStyle}">${inlineFormat(c)}</td>`).join("");
      return `<tr>${tds}</tr>`;
    }).join("\n");
    return (
      `<table style="border-collapse:collapse;width:100%;margin:10px 0;font-size:10.5pt">` +
      `<thead><tr>${ths}</tr></thead>` +
      `<tbody>${trs}</tbody>` +
      `</table>`
    );
  };

  const lines = md.split("\n");
  const html: string[] = [];
  let inCodeBlock = false;
  let codeLines: string[] = [];
  let codeLang = "";
  let inList: "ul" | "ol" | null = null;
  let tableBuffer: string[] = [];

  const closeList = () => {
    if (inList) { html.push(`</${inList}>`); inList = null; }
  };
  const flushTable = () => {
    if (tableBuffer.length > 0) { html.push(renderTable(tableBuffer)); tableBuffer = []; }
  };
  const isTableLine = (l: string) => /^\|.+\|/.test(l.trim());

  for (const line of lines) {
    if (/^```/.test(line)) {
      flushTable();
      if (!inCodeBlock) {
        closeList(); inCodeBlock = true;
        codeLang = line.slice(3).trim(); codeLines = [];
      } else {
        inCodeBlock = false;
        const langLabel = codeLang
        ? `<div style="font-family:Courier New,monospace;font-size:.75em;color:#888;margin-bottom:2px">${esc(codeLang)}</div>` : "";
        html.push(
          `<div style="background:#f6f6f6;border:1px solid #ddd;border-radius:4px;padding:8px 12px;margin:8px 0">` +
          langLabel +
          `<pre style="margin:0;font-family:Courier New,monospace;font-size:.85em;white-space:pre-wrap;word-break:break-all">${codeLines.map(esc).join("\n")}</pre></div>`
        );
      }
      continue;
    }
    if (inCodeBlock) { codeLines.push(line); continue; }

    if (isTableLine(line)) { closeList(); tableBuffer.push(line); continue; }
    else { flushTable(); }

    if (/^\$\$/.test(line.trim())) {
      closeList();
      const formula = line.trim().replace(/^\$\$|\$\$$/g, "").trim();
      html.push(`<p style="font-family:Courier New,monospace;font-size:.9em;font-style:italic;margin:6px 0">${esc(formula || line.trim())}</p>`);
      continue;
    }

    const h3 = line.match(/^###\s+(.*)/);
    const h2 = line.match(/^##\s+(.*)/);
    const h1 = line.match(/^#\s+(.*)/);
    if (h3) { closeList(); html.push(`<h3 style="font-size:1.1em;margin:12px 0 4px">${inlineFormat(h3[1])}</h3>`); continue; }
    if (h2) { closeList(); html.push(`<h2 style="font-size:1.25em;margin:16px 0 6px">${inlineFormat(h2[1])}</h2>`); continue; }
    if (h1) { closeList(); html.push(`<h1 style="font-size:1.5em;margin:20px 0 8px">${inlineFormat(h1[1])}</h1>`); continue; }

    if (/^[-*_]{3,}$/.test(line.trim())) {
      closeList(); html.push(`<hr style="border:none;border-top:1px solid #ccc;margin:12px 0">`); continue;
    }

    const bullet = line.match(/^(\s*)[*\-+]\s+(.*)/);
    if (bullet) {
      if (inList !== "ul") { closeList(); html.push(`<ul style="margin:4px 0;padding-left:24px">`); inList = "ul"; }
      html.push(`<li style="margin:2px 0">${inlineFormat(bullet[2])}</li>`); continue;
    }

    const ordered = line.match(/^(\s*)\d+\.\s+(.*)/);
    if (ordered) {
      if (inList !== "ol") { closeList(); html.push(`<ol style="margin:4px 0;padding-left:24px">`); inList = "ol"; }
      html.push(`<li style="margin:2px 0">${inlineFormat(ordered[2])}</li>`); continue;
    }

    const bq = line.match(/^>\s?(.*)/);
    if (bq) {
      closeList();
      html.push(`<blockquote style="border-left:3px solid #ccc;margin:6px 0;padding:4px 12px;color:#555;font-style:italic">${inlineFormat(bq[1])}</blockquote>`);
      continue;
    }

    if (line.trim() === "") { closeList(); html.push(`<p style="margin:0;line-height:.6em">&nbsp;</p>`); continue; }

    closeList();
    html.push(`<p style="margin:4px 0">${inlineFormat(line)}</p>`);
  }

  closeList();
  flushTable();

  return (
    `<html><head><meta charset="utf-8"></head>` +
    `<body style="font-family:Calibri,Arial,sans-serif;font-size:11pt;color:#1e1e1e;line-height:1.5">` +
    html.join("\n") +
    `</body></html>`
  );
}
