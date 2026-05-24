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
 * useArtifactPanel.ts
 *
 * Détecte automatiquement les "artefacts" dans les messages IA et gère
 * l'état du panneau (ouverture, index actif, auto-open).
 *
 * La logique d'extraction est entièrement déléguée à src/lib/artifacts.ts —
 * ce hook se concentre sur l'état React pur.
 *
 * Logique d'ouverture automatique :
 *   - S'ouvre dès qu'un artefact riche est détecté dans le dernier message IA
 *   - Ne se ferme PAS automatiquement (l'utilisateur garde le contrôle)
 *   - Toggle manuel toujours disponible
 */

import { useMemo, useRef, useEffect, useState } from "react";
import type { ChatMessage } from "./useAgentStream";
import { buildArtifactList } from "../lib/artifacts";

// ── Ré-export des types depuis artifacts.ts pour rétro-compatibilité ─────────
// Les composants qui importaient depuis ce hook continuent de fonctionner.
export type { ArtifactKind, Artifact } from "../lib/artifacts";

// ── Types locaux ──────────────────────────────────────────────────────────────

export interface ArtifactPanelState {
  artifacts: import("../lib/artifacts").Artifact[];
  activeIdx: number;
  isOpen: boolean;
  autoOpened: boolean;
}

// ── Hook ───────────────────────────────────────────────────────────────────

export function useArtifactPanel(messages: ChatMessage[], isGenerating: boolean) {
  const [panelOpen, setPanelOpen]   = useState(false);
  const [activeIdx, setActiveIdx]   = useState(0);
  const [autoOpened, setAutoOpened] = useState(false);

  // Mémoïse la liste complète d'artefacts (stable tant que messages ne change pas)
  const artifacts = useMemo(
    () => buildArtifactList(messages),
    [messages],
  );

  // Suivi du dernier messageId pour lequel on a fait l'auto-open
  const lastAutoMsgIdRef = useRef<string | null>(null);

  // Auto-ouverture : surveille les nouveaux artefacts après la génération.
  // Pointe sur le premier artefact spécifique (index 1), pas sur le synthétique.
  useEffect(() => {
    if (isGenerating) return;
    if (artifacts.length <= 1) return; // seulement le "full" → pas d'auto-open

    const last = artifacts[artifacts.length - 1];
    if (last.messageId === lastAutoMsgIdRef.current) return;

    lastAutoMsgIdRef.current = last.messageId;
    setActiveIdx(artifacts.length - 1); // dernier artefact spécifique
    setPanelOpen(true);
    setAutoOpened(true);
  }, [artifacts, isGenerating]);

  // Reset autoOpened après toggle manuel
  const toggle = () => {
    setPanelOpen((v) => {
      if (v) setAutoOpened(false);
      return !v;
    });
  };

  const selectArtifact = (idx: number) => setActiveIdx(idx);

  return {
    artifacts,
    activeIdx,
    panelOpen,
    autoOpened,
    toggle,
    selectArtifact,
  };
}
