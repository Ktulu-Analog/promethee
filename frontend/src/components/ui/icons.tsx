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
 * icons.tsx
 *
 * Portage de tous les templates SVG inline de conversation_sidebar.py.
 * Chaque icône est un composant React fonctionnel qui accepte color et size.
 *
 * Utilisation :
 *   <IconFolder color="var(--text-muted)" size={14} open />
 *   <IconChat   color="var(--text-muted)" size={14} />
 */

import React from "react";

interface IconProps {
  color?: string;
  size?: number;
  style?: React.CSSProperties;
}

function Svg({ size = 14, children, style }: { size?: number; children: React.ReactNode; style?: React.CSSProperties }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 16 16"
      width={size}
      height={size}
      style={{ flexShrink: 0, display: "block", ...style }}
    >
      {children}
    </svg>
  );
}

export function IconHamburger({ color = "currentColor", size = 14 }: IconProps) {
  return (
    <Svg size={size}>
      <rect x="1" y="3"    width="14" height="1.8" rx="0.9" fill={color} />
      <rect x="1" y="7.1"  width="14" height="1.8" rx="0.9" fill={color} />
      <rect x="1" y="11.2" width="14" height="1.8" rx="0.9" fill={color} />
    </Svg>
  );
}

export function IconFolder({ color = "currentColor", size = 14, open = false }: IconProps & { open?: boolean }) {
  return (
    <Svg size={size}>
      <path
        d="M1 4.5C1 3.7 1.7 3 2.5 3H6l1.5 2H13.5C14.3 5 15 5.7 15 6.5V12.5C15 13.3 14.3 14 13.5 14H2.5C1.7 14 1 13.3 1 12.5V4.5Z"
        stroke={color}
        strokeWidth="1.3"
        fill={open ? color : "none"}
        fillOpacity={open ? 0.18 : 0}
        strokeLinejoin="round"
      />
    </Svg>
  );
}

export function IconChat({ color = "currentColor", size = 14 }: IconProps) {
  return (
    <Svg size={size}>
      <path
        d="M2 3C2 2.45 2.45 2 3 2H13C13.55 2 14 2.45 14 3V10C14 10.55 13.55 11 13 11H9L6 14V11H3C2.45 11 2 10.55 2 10V3Z"
        stroke={color}
        strokeWidth="1.3"
        fill="none"
        strokeLinejoin="round"
      />
    </Svg>
  );
}

export function IconTrash({ color = "currentColor", size = 14 }: IconProps) {
  return (
    <Svg size={size}>
      <path
        d="M2 4h12M5 4V2h6v2M6 7v5M10 7v5M3 4l1 9h8l1-9"
        stroke={color}
        strokeWidth="1.4"
        strokeLinecap="round"
        strokeLinejoin="round"
        fill="none"
      />
    </Svg>
  );
}

export function IconRag({ color = "currentColor", size = 14 }: IconProps) {
  return (
    <Svg size={size}>
      <rect x="2" y="2"  width="5" height="6" rx="1" stroke={color} strokeWidth="1.4" fill="none" />
      <rect x="9" y="2"  width="5" height="6" rx="1" stroke={color} strokeWidth="1.4" fill="none" />
      <rect x="2" y="10" width="5" height="4" rx="1" stroke={color} strokeWidth="1.4" fill="none" />
      <rect x="9" y="10" width="5" height="4" rx="1" stroke={color} strokeWidth="1.4" fill="none" />
    </Svg>
  );
}

export function IconTools({ color = "currentColor", size = 14 }: IconProps) {
  return (
    <Svg size={size}>
      <path
        d="M9.5 2a3.5 3.5 0 0 1 0 5L4 13a1.5 1.5 0 0 1-2-2L7.5 5.5A3.5 3.5 0 0 1 9.5 2z"
        stroke={color}
        strokeWidth="1.4"
        fill="none"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </Svg>
  );
}

export function IconMonitoring({ color = "currentColor", size = 14 }: IconProps) {
  return (
    <Svg size={size}>
      <rect x="1" y="2" width="14" height="10" rx="1.5" stroke={color} strokeWidth="1.4" fill="none" />
      <path d="M4 14h8M8 12v2" stroke={color} strokeWidth="1.4" strokeLinecap="round" />
      <polyline points="3,9 5,5 7,7 9,4 11,6 13,3" stroke={color} strokeWidth="1.3" fill="none" strokeLinecap="round" strokeLinejoin="round" />
    </Svg>
  );
}

export function IconModelUsage({ color = "currentColor", size = 14 }: IconProps) {
  return (
    <Svg size={size}>
      <rect x="1"  y="10" width="3" height="5"  rx="0.8" stroke={color} strokeWidth="1.3" fill="none" />
      <rect x="5"  y="7"  width="3" height="8"  rx="0.8" stroke={color} strokeWidth="1.3" fill="none" />
      <rect x="9"  y="4"  width="3" height="11" rx="0.8" stroke={color} strokeWidth="1.3" fill="none" />
      <rect x="13" y="1"  width="2" height="14" rx="0.8" stroke={color} strokeWidth="1.3" fill="none" />
    </Svg>
  );
}

export function IconSettings({ color = "currentColor", size = 14 }: IconProps) {
  return (
    <Svg size={size}>
      <circle cx="8" cy="8" r="2.2" stroke={color} strokeWidth="1.4" fill="none" />
      <path
        d="M8 1v2M8 13v2M1 8h2M13 8h2M3.05 3.05l1.41 1.41M11.54 11.54l1.41 1.41M11.54 4.46l-1.41 1.41M4.46 11.54l-1.41 1.41"
        stroke={color}
        strokeWidth="1.4"
        strokeLinecap="round"
        fill="none"
      />
    </Svg>
  );
}

export function IconPlus({ color = "currentColor", size = 14 }: IconProps) {
  return (
    <Svg size={size}>
      <line x1="8" y1="2" x2="8" y2="14" stroke={color} strokeWidth="1.6" strokeLinecap="round" />
      <line x1="2" y1="8" x2="14" y2="8" stroke={color} strokeWidth="1.6" strokeLinecap="round" />
    </Svg>
  );
}

export function IconChevronRight({ color = "currentColor", size = 12 }: IconProps) {
  return (
    <Svg size={size}>
      <polyline points="5,3 11,8 5,13" fill="none" stroke={color} strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </Svg>
  );
}

export function IconChevronDown({ color = "currentColor", size = 12 }: IconProps) {
  return (
    <Svg size={size}>
      <polyline points="3,5 8,11 13,5" fill="none" stroke={color} strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </Svg>
  );
}

export function IconProfiles({ color = "currentColor", size = 14 }: IconProps) {
  return (
    <Svg size={size}>
      <circle cx="8" cy="6" r="2.8" stroke={color} strokeWidth="1.4" fill="none" />
      <path d="M2.5 14c0-3 2.5-5 5.5-5s5.5 2 5.5 5" stroke={color} strokeWidth="1.4" strokeLinecap="round" fill="none" />
    </Svg>
  );
}

export function IconIngest({ color = "currentColor", size = 14 }: IconProps) {
  return (
    <Svg size={size}>
      {/* Livre ouvert */}
      <path
        d="M8 13C6.5 12 3.5 12 1.5 13L1.5 4C3.5 3 6.5 3 8 4C9.5 3 12.5 3 14.5 4L14.5 13C12.5 12 9.5 12 8 13Z"
        stroke={color} strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" fill="none"
      />
      <line x1="8" y1="4" x2="8" y2="13" stroke={color} strokeWidth="1.3" strokeLinecap="round"/>
      {/* Nœuds réseau */}
      <circle cx="5.5" cy="1.8" r="1.1" stroke={color} strokeWidth="1.2" fill="none"/>
      <circle cx="8"   cy="1"   r="1.1" stroke={color} strokeWidth="1.2" fill="none"/>
      <circle cx="10.5" cy="1.8" r="1.1" stroke={color} strokeWidth="1.2" fill="none"/>
      {/* Liaisons entre nœuds */}
      <line x1="6.6"  y1="1.6" x2="6.9"  y2="1.3" stroke={color} strokeWidth="1.1" strokeLinecap="round"/>
      <line x1="9.1"  y1="1.3" x2="9.4"  y2="1.6" stroke={color} strokeWidth="1.1" strokeLinecap="round"/>
    </Svg>
  );
}

export function IconVfs({ color = "currentColor", size = 14 }: IconProps) {
  return (
    <Svg size={size}>
      <path
        d="M1 4C1 3.4 1.4 3 2 3H5.5L7 5H14C14.6 5 15 5.4 15 6V13C15 13.6 14.6 14 14 14H2C1.4 14 1 13.6 1 13V4Z"
        stroke={color} strokeWidth="1.3" fill="none" strokeLinejoin="round"
      />
      <circle cx="12" cy="10.5" r="2" fill={color} fillOpacity="0.25" stroke={color} strokeWidth="1.1"/>
      <line x1="12" y1="9.3" x2="12" y2="11.7" stroke={color} strokeWidth="1.2" strokeLinecap="round"/>
      <line x1="10.8" y1="10.5" x2="13.2" y2="10.5" stroke={color} strokeWidth="1.2" strokeLinecap="round"/>
    </Svg>
  );
}
