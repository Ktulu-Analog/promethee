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
 * useSplitPane.ts
 *
 * Gestion du split-pane redimensionnable par drag.
 *
 * Retourne :
 *   - leftWidth    : largeur en px du panneau gauche (chat)
 *   - onDragStart  : handler à attacher au séparateur (mousedown)
 *   - isDragging   : true pendant le drag (pour curseur global)
 *
 * Contraintes :
 *   - Largeur min gauche : 360px
 *   - Largeur min droite : 280px
 *   - Mémorise la dernière position dans sessionStorage
 */

import { useState, useEffect, useRef, useCallback } from "react";

const STORAGE_KEY = "promethee.splitPane.leftWidth";
const MIN_LEFT  = 360;
const MIN_RIGHT = 280;
const DEFAULT_RATIO = 0.58; // 58% pour le chat par défaut

export function useSplitPane(containerRef: React.RefObject<HTMLDivElement>) {
  const getDefaultWidth = () => {
    const stored = sessionStorage.getItem(STORAGE_KEY);
    if (stored) {
      const v = parseInt(stored, 10);
      if (!isNaN(v) && v >= MIN_LEFT) return v;
    }
    return Math.round((window.innerWidth - 240) * DEFAULT_RATIO); // 240 = sidebar
  };

  const [leftWidth, setLeftWidth] = useState<number>(getDefaultWidth);
  const [isDragging, setIsDragging] = useState(false);
  const startXRef   = useRef(0);
  const startWRef   = useRef(0);

  const onDragStart = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    startXRef.current = e.clientX;
    startWRef.current = leftWidth;
    setIsDragging(true);
  }, [leftWidth]);

  useEffect(() => {
    if (!isDragging) return;

    const onMouseMove = (e: MouseEvent) => {
      const container = containerRef.current;
      if (!container) return;
      const totalWidth = container.offsetWidth;
      const delta      = e.clientX - startXRef.current;
      const newLeft    = startWRef.current + delta;
      const maxLeft    = totalWidth - MIN_RIGHT;
      const clamped    = Math.max(MIN_LEFT, Math.min(maxLeft, newLeft));
      setLeftWidth(clamped);
    };

    const onMouseUp = () => {
      setIsDragging(false);
      // Persiste pour la session
      sessionStorage.setItem(STORAGE_KEY, String(leftWidth));
    };

    window.addEventListener("mousemove", onMouseMove);
    window.addEventListener("mouseup", onMouseUp);
    return () => {
      window.removeEventListener("mousemove", onMouseMove);
      window.removeEventListener("mouseup", onMouseUp);
    };
  }, [isDragging, containerRef, leftWidth]);

  // Sauvegarde dès que leftWidth change (en dehors du drag aussi)
  useEffect(() => {
    if (!isDragging) {
      sessionStorage.setItem(STORAGE_KEY, String(leftWidth));
    }
  }, [leftWidth, isDragging]);

  return { leftWidth, onDragStart, isDragging };
}
