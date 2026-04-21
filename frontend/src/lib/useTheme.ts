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
 * useTheme.ts — Gestion du thème sombre/clair
 *
 * Stocke la préférence en localStorage et applique data-theme sur <html>.
 */

import { useState, useEffect, useCallback } from "react";

type Theme = "dark" | "light";

const KEY = "promethee_theme";

function getInitial(): Theme {
  const saved = localStorage.getItem(KEY) as Theme | null;
  if (saved === "dark" || saved === "light") return saved;
  return "dark";
}

function apply(theme: Theme) {
  document.documentElement.setAttribute("data-theme", theme);
  localStorage.setItem(KEY, theme);
}

export function useTheme() {
  const [theme, setTheme] = useState<Theme>(getInitial);

  useEffect(() => {
    apply(theme);
  }, [theme]);

  const toggle = useCallback(() => {
    setTheme((t) => (t === "dark" ? "light" : "dark"));
  }, []);

  return { theme, isDark: theme === "dark", toggle };
}
