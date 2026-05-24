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
 * mermaid-sanitizer.ts
 *
 * Corrige automatiquement les erreurs de syntaxe Mermaid les plus fréquentes
 * générées par les LLMs avant de passer le code à mermaid.render().
 *
 * Corrections appliquées :
 *   - Conversion des diagrammes C4 (supprimé en Mermaid v11) → graph TD
 *   - Normalisation des fins de ligne et tabulations
 *   - Suppression des caractères typographiques problématiques (apostrophes
 *     courbes, tirets longs…)
 *   - Suppression des directives classDef / click / linkStyle / style
 *   - Suppression des commentaires %%
 *   - Flowchart/graph :
 *       · -->  >> → -->
 *       · translittération des accents dans les labels et ids de nœuds
 *       · parenthèses dans les labels de nœuds → label quoté
 *       · réservation des mots-clés Mermaid (end, start, class…) → N_<mot>
 *       · déduplication des définitions de nœuds
 *   - Gantt :
 *       · translittération des accents dans les titres de section et tâches
 *   - sequenceDiagram :
 *       · suppression des subgraph (invalides en séquence)
 *       · suppression des apostrophes dans les messages
 *       · équilibrage des blocs alt/opt/loop/par/critical/break / end
 *
 * Porté depuis Démeter (même auteur) — adapté pour Prométhée.
 */

/**
 * Corrige automatiquement les erreurs de syntaxe Mermaid les plus fréquentes
 * générées par les LLMs.
 */
export function sanitizeMermaid(raw: string): string {
  let code = raw.trim();

  // ── Détection et conversion C4 (retiré en Mermaid v11) ──────────────────
  if (/^C4\w*/i.test(code)) {
    const accentC4: Record<string, string> = {
      'é': 'e', 'è': 'e', 'ê': 'e', 'ë': 'e', 'à': 'a', 'â': 'a', 'ä': 'a',
      'ù': 'u', 'û': 'u', 'ü': 'u', 'ô': 'o', 'ö': 'o', 'î': 'i', 'ï': 'i',
      'ç': 'c', 'É': 'E', 'È': 'E', 'À': 'A', 'Î': 'I', 'Ç': 'C',
    };
    const trlC4 = (s: string) =>
      s.split('').map(c => accentC4[c] || c).join('').replace(/'/g, ' ').replace(/"/g, ' ');

    const lines = code.split('\n');
    const nodes = new Map<string, string>();
    const rels: Array<{ from: string; to: string; label: string }> = [];
    let title = '';

    for (const line of lines) {
      const t = line.trim();
      const titleM = t.match(/^title\s+(.+)$/i);
      if (titleM) { title = trlC4(titleM[1]); continue; }

      const nodeM = t.match(/^(?:Person|System|Container)\w*\s*\((\w+)\s*,\s*['"]([^'"]+)['"]/i);
      if (nodeM) { nodes.set(nodeM[1], trlC4(nodeM[2])); continue; }

      const relM = t.match(/^Rel\w*\s*\(\s*(\w+)\s*,\s*(\w+)\s*,\s*['"]([^'"]*)['"] /i);
      if (relM) rels.push({ from: relM[1], to: relM[2], label: trlC4(relM[3]) });
    }

    let out = title ? `graph TD\n    %%${title}\n` : 'graph TD\n';
    const usedIds = new Set(rels.flatMap(r => [r.from, r.to]));
    for (const [id, label] of nodes) {
      if (usedIds.has(id)) out += `    ${id}[${label}]\n`;
    }
    for (const { from, to, label } of rels) {
      out += label
        ? `    ${from} -->|${label}| ${to}\n`
        : `    ${from} --> ${to}\n`;
    }
    return out.trim();
  }

  // ── Normalisation des fins de ligne ─────────────────────────────────────
  code = code.replace(/\r\n/g, '\n').replace(/\r/g, '\n');

  // ── Tabulations → 4 espaces ──────────────────────────────────────────────
  code = code.replace(/\t/g, '    ');

  // ── Caractères typographiques problématiques ─────────────────────────────
  // Apostrophes courbes / guillemets / accent grave → espace
  code = code.replace(/[\u2018\u2019\u201A\u201B`]/g, ' ');
  // Tirets typographiques → tiret simple
  code = code.replace(/[\u2011\u2013\u2014\u2015\u2212]/g, '-');

  // ── Suppression des directives non supportées ────────────────────────────
  code = code.replace(/^\s*(classDef|click|linkStyle|style\s+\w)\s.*$/gm, '');

  // ── Suppression des commentaires %% ─────────────────────────────────────
  code = code.replace(/^\s*%%.*$/gm, '');

  // ── Corrections flowchart / graph ────────────────────────────────────────
  const isFlowchart = /^(graph|flowchart)\s/i.test(code);
  if (isFlowchart) {
    // -->> n'existe pas → -->
    code = code.replace(/-->>/g, '-->');

    // Labels de nœuds contenant des parenthèses → guillemets autour du label
    // ex: A[foo(bar)] → A["foo(bar)"]
    code = code.replace(
      /(\w+)\[([^\]"]*\([^\]]*)\)]/g,
      (_match: string, id: string, label: string) => `${id}["${label})"]`,
    );

    // Translittération des accents (labels, ids, edges labels)
    const accentMap: Record<string, string> = {
      'é': 'e', 'è': 'e', 'ê': 'e', 'ë': 'e', 'à': 'a', 'â': 'a', 'ä': 'a',
      'ù': 'u', 'ú': 'u', 'û': 'u', 'ü': 'u', 'ô': 'o', 'ó': 'o', 'ö': 'o',
      'î': 'i', 'í': 'i', 'ï': 'i', 'ç': 'c',
      'É': 'E', 'È': 'E', 'Ê': 'E', 'À': 'A', 'Â': 'A',
      'Î': 'I', 'Ï': 'I', 'Ç': 'C', 'Ô': 'O', 'Ù': 'U',
    };
    const transliterate = (s: string) => s.split('').map(c => accentMap[c] || c).join('');

    // Labels entre [ ] — translittérer et nettoyer les caractères problématiques
    code = code.replace(/\[([^\]]+)]/g, (_m: string, content: string) => {
      const fixed = transliterate(content)
        .replace(/'/g, ' ')
        .replace(/\(/g, ' ')
        .replace(/\)/g, ' ')
        .replace(/\s+/g, ' ')
        .trim();
      return `[${fixed}]`;
    });

    // Labels entre { } (losanges de décision)
    code = code.replace(/\{([^}]+)}/g, (_m: string, content: string) => {
      const fixed = transliterate(content).replace(/'/g, ' ').replace(/\s+/g, ' ').trim();
      return `{${fixed}}`;
    });

    // Labels d'arêtes entre | |
    code = code.replace(/\|([^|\n]+)\|/g, (_m: string, label: string) =>
      `|${transliterate(label).replace(/'/g, ' ')}|`,
    );

    // Translittération des ids de nœuds (partie avant le [ { ( >)
    code = code.replace(
      /^(\s*)([A-Za-z\u00C0-\u00FF0-9_]+)(\s*[\[{(>])/gm,
      (_m: string, indent: string, id: string, sep: string) => indent + transliterate(id) + sep,
    );

    // Renommage des mots-clés réservés utilisés comme ids de nœuds
    const reserved = /^(\s*)(end|start|class|style|default)(\s*[\[{(>-])/gm;
    code = code.replace(
      reserved,
      (_m: string, indent: string, id: string, sep: string) => `${indent}N_${id}${sep}`,
    );

    // Déduplication des définitions de nœuds (label redéfini → id seul)
    const seenNodeIds = new Map<string, string>();
    code = code.replace(
      /\b([A-Za-z][A-Za-z0-9_]*)(\[[^\]]*]|\{[^}]*}|\([^)]*\))/g,
      (_m: string, id: string, labelBlock: string) => {
        if (seenNodeIds.has(id)) return id;
        seenNodeIds.set(id, labelBlock);
        return _m;
      },
    );
  }

  // ── Corrections gantt ────────────────────────────────────────────────────
  const isGantt = /^gantt\b/i.test(code);
  if (isGantt) {
    const accentMapGantt: Record<string, string> = {
      'é': 'e', 'è': 'e', 'ê': 'e', 'ë': 'e', 'à': 'a', 'â': 'a', 'ä': 'a',
      'ù': 'u', 'ú': 'u', 'û': 'u', 'ü': 'u', 'ô': 'o', 'ó': 'o', 'ö': 'o',
      'î': 'i', 'í': 'i', 'ï': 'i', 'ç': 'c',
      'É': 'E', 'È': 'E', 'Ê': 'E', 'À': 'A', 'Â': 'A',
      'Î': 'I', 'Ï': 'I', 'Ç': 'C', 'Ô': 'O', 'Ù': 'U',
    };
    const trl = (s: string) => s.split('').map(c => accentMapGantt[c] || c).join('');

    // Translittération des titres de section
    code = code.replace(
      /^(\s*section\s+)(.+)$/gm,
      (_m: string, prefix: string, name: string) => prefix + trl(name),
    );

    // Translittération des noms de tâches (tout sauf les lignes de méta-données)
    code = code.replace(
      /^(\s*)([^:\n]+?)(\s*:[^\n]*)$/gm,
      (_m: string, indent: string, taskName: string, rest: string) => {
        if (/^\s*(title|dateFormat|axisFormat|%%|section)/i.test(indent + taskName)) return _m;
        return indent + trl(taskName).replace(/'/g, ' ') + rest;
      },
    );
  }

  // ── Corrections sequenceDiagram ──────────────────────────────────────────
  const isSequence = /^sequenceDiagram/i.test(code);
  if (isSequence) {
    // Suppression des subgraph (invalides dans les séquences)
    code = code.replace(/^\s*subgraph\s.*$/gm, '');

    // Suppression des apostrophes dans les messages flèche
    code = code.replace(/(->+[^:\n]*:[^\n]*?)'/g, '$1');

    // Équilibrage des blocs alt/opt/loop/par/critical/break et end
    const opens  = (code.match(/^\s*(alt|opt|loop|par|critical|break)\b/gm) || []).length;
    const closes = (code.match(/^\s*end\s*$/gm) || []).length;
    const diff = opens - closes;

    if (diff > 0) {
      code = code + '\n' + 'end\n'.repeat(diff);
    } else if (diff < 0) {
      let toRemove = -diff;
      code = code.replace(/\n\s*end\s*$/gm, (m) => {
        if (toRemove > 0) { toRemove--; return ''; }
        return m;
      });
    }
  }

  // ── Nettoyage final ──────────────────────────────────────────────────────
  // Suppression des espaces en fin de ligne
  code = code.replace(/[ \t]+$/gm, '');
  // Réduction des lignes vides multiples à deux maximum
  code = code.replace(/\n{3,}/g, '\n\n');

  return code.trim();
}
