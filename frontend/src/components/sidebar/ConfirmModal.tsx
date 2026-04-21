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
 * ConfirmModal.tsx — Modale de confirmation générique (suppression, etc.)
 */

import React from "react";
import { createPortal } from "react-dom";

interface ConfirmModalProps {
  message: string;
  onConfirm: () => void;
  onCancel: () => void;
}

export function ConfirmModal({ message, onConfirm, onCancel }: ConfirmModalProps) {
  return createPortal(
    <div style={{
      position: "fixed", inset: 0,
      background: "rgba(0,0,0,0.55)",
      display: "flex", alignItems: "center", justifyContent: "center",
      zIndex: 2000,
    }}>
      <div style={{
        background: "var(--surface-bg)",
        border: "1px solid var(--border)",
        borderRadius: 12,
        padding: "24px 28px",
        width: 320, maxWidth: "90vw",
        boxShadow: "0 20px 60px rgba(0,0,0,0.5)",
        display: "flex", flexDirection: "column", gap: 16,
      }}>
        <div style={{ fontSize: 13, color: "var(--text-secondary)", lineHeight: 1.6 }}>
          {message}
        </div>
        <div style={{ display: "flex", justifyContent: "flex-end", gap: 10 }}>
          <button
            onClick={onCancel}
            style={{
              padding: "7px 16px",
              background: "var(--elevated-bg)",
              border: "1px solid var(--border)",
              borderRadius: 7,
              color: "var(--text-primary)",
              fontSize: 13, cursor: "pointer", fontFamily: "inherit",
            }}
          >
            Annuler
          </button>
          <button
            onClick={() => { onConfirm(); onCancel(); }}
            style={{
              padding: "7px 16px",
              background: "#c0392b",
              border: "none",
              borderRadius: 7,
              color: "#fff",
              fontSize: 13, fontWeight: 700, cursor: "pointer", fontFamily: "inherit",
            }}
          >
            Supprimer
          </button>
        </div>
      </div>
    </div>,
    document.body
  );
}
