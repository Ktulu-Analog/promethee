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
 * ThemeSwitch.tsx
 *
 * Portage fidèle du ThemeSwitch Qt (theme_switch.py) en React + Canvas.
 *
 * Géométrie identique :
 *   W=72  H=32  R=13(thumb)  PAD=3
 *
 * Rendu :
 *   - Track : interpolation de couleur entre thème clair et sombre
 *   - Thumb : glisse avec transition CSS
 *   - Icônes soleil/lune dans le track et dans le thumb
 *   - Animation fluide (260ms InOutCubic — remplacé par CSS transition)
 */

import React, { useRef, useEffect } from "react";

interface Props {
  isDark: boolean;
  onToggle: () => void;
}

// Géométrie (pixels logiques)
const W = 72, H = 32, R = 13, PAD = 3;

function lerp(a: number, b: number, t: number) {
  return a + (b - a) * t;
}
function lerpColor(
  [r1, g1, b1]: [number, number, number],
  [r2, g2, b2]: [number, number, number],
  t: number
): string {
  return `rgb(${Math.round(lerp(r1,r2,t))},${Math.round(lerp(g1,g2,t))},${Math.round(lerp(b1,b2,t))})`;
}

const TRACK_LIGHT: [number,number,number] = [226, 223, 216];
const TRACK_DARK:  [number,number,number] = [38,  38,  42 ];
const BORDER_LIGHT:[number,number,number] = [196, 192, 184];
const BORDER_DARK: [number,number,number] = [72,  72,  78 ];
const THUMB_LIGHT: [number,number,number] = [255, 255, 255];
const THUMB_DARK:  [number,number,number] = [232, 229, 223];

function drawSun(
  ctx: CanvasRenderingContext2D,
  cx: number, cy: number,
  r = 4.5, alpha = 1,
  color = "rgba(255,195,50,"
) {
  if (alpha <= 0) return;
  const a = alpha;
  const col = `rgba(255,195,50,${a})`;
  // Disque central
  ctx.beginPath();
  ctx.arc(cx, cy, r, 0, Math.PI * 2);
  ctx.fillStyle = col;
  ctx.fill();
  // Rayons
  ctx.strokeStyle = col;
  ctx.lineWidth = 1.4;
  ctx.lineCap = "round";
  for (let i = 0; i < 8; i++) {
    const angle = (i * Math.PI) / 4;
    ctx.beginPath();
    ctx.moveTo(cx + Math.cos(angle) * (r + 1.5), cy + Math.sin(angle) * (r + 1.5));
    ctx.lineTo(cx + Math.cos(angle) * (r + 3.5), cy + Math.sin(angle) * (r + 3.5));
    ctx.stroke();
  }
}

function drawMoon(
  ctx: CanvasRenderingContext2D,
  cx: number, cy: number,
  r = 5.5, alpha = 1
) {
  if (alpha <= 0) return;
  const col = `rgba(180,185,230,${alpha})`;
  // Croissant = grand disque - petit disque (décalé)
  ctx.save();
  ctx.beginPath();
  ctx.arc(cx, cy, r, 0, Math.PI * 2);
  ctx.clip();
  ctx.fillStyle = col;
  ctx.fill();
  // Effacer la partie "cut"
  const offX = cx + r * 0.42;
  const offY = cy - r * 0.55;
  const cutR = r * 0.82;
  ctx.globalCompositeOperation = "destination-out";
  ctx.beginPath();
  ctx.arc(offX, offY, cutR, 0, Math.PI * 2);
  ctx.fill();
  ctx.restore();
}

function drawSwitch(
  ctx: CanvasRenderingContext2D,
  pos: number  // 0 = clair, 1 = sombre
) {
  const dpr = window.devicePixelRatio || 1;
  ctx.clearRect(0, 0, (W + 4) * dpr, (H + 4) * dpr);
  ctx.scale(dpr, dpr);

  const ox = 2, oy = 2;

  // ── Track ────────────────────────────────────────────────────────────
  const trackCol   = lerpColor(TRACK_LIGHT,  TRACK_DARK,  pos);
  const borderCol  = lerpColor(BORDER_LIGHT, BORDER_DARK, pos);
  const trackR     = H / 2;

  ctx.beginPath();
  ctx.moveTo(ox + trackR, oy);
  ctx.arcTo(ox + W, oy, ox + W, oy + H, trackR);
  ctx.arcTo(ox + W, oy + H, ox, oy + H, trackR);
  ctx.arcTo(ox, oy + H, ox, oy, trackR);
  ctx.arcTo(ox, oy, ox + W, oy, trackR);
  ctx.closePath();
  ctx.fillStyle = trackCol;
  ctx.fill();
  ctx.strokeStyle = borderCol;
  ctx.lineWidth = 1;
  ctx.stroke();

  // ── Soleil (gauche du track) ─────────────────────────────────────────
  const sunCx = ox + H / 2;
  const sunCy = oy + H / 2;
  drawSun(ctx, sunCx, sunCy, 4.5, 1 - pos);

  // ── Lune (droite du track) ───────────────────────────────────────────
  const moonCx = ox + W - H / 2;
  const moonCy = oy + H / 2;
  drawMoon(ctx, moonCx, moonCy, 5.5, pos);

  // ── Thumb ────────────────────────────────────────────────────────────
  const travel = W - 2 * PAD - 2 * R;
  const cx = ox + PAD + R + pos * travel;
  const cy = oy + H / 2;

  // Ombre
  ctx.beginPath();
  ctx.arc(cx + 1, cy + 2, R, 0, Math.PI * 2);
  ctx.fillStyle = "rgba(0,0,0,0.14)";
  ctx.fill();

  // Corps
  const thumbCol = lerpColor(THUMB_LIGHT, THUMB_DARK, pos);
  ctx.beginPath();
  ctx.arc(cx, cy, R, 0, Math.PI * 2);
  ctx.fillStyle = thumbCol;
  ctx.fill();
  ctx.strokeStyle = "rgba(0,0,0,0.1)";
  ctx.lineWidth = 1;
  ctx.stroke();

  // Icône dans le thumb
  if (pos < 0.5) {
    drawSun(ctx, cx, cy, 5.5, (0.5 - pos) * 2, "rgba(220,140,30,");
  } else {
    drawMoon(ctx, cx, cy, 5.0, (pos - 0.5) * 2);
  }
}

export function ThemeSwitch({ isDark, onToggle }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const posRef = useRef(isDark ? 1 : 0);
  const animRef = useRef<number | null>(null);
  const startRef = useRef<number | null>(null);
  const fromRef = useRef(posRef.current);
  const toRef = useRef(posRef.current);

  // Anime vers la cible
  function animateTo(target: number) {
    fromRef.current = posRef.current;
    toRef.current = target;
    startRef.current = null;
    if (animRef.current) cancelAnimationFrame(animRef.current);

    function step(ts: number) {
      if (startRef.current === null) startRef.current = ts;
      const elapsed = ts - startRef.current;
      const duration = 260;
      let t = Math.min(elapsed / duration, 1);
      // InOutCubic easing
      t = t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
      posRef.current = lerp(fromRef.current, toRef.current, t);
      redraw();
      if (elapsed < duration) {
        animRef.current = requestAnimationFrame(step);
      } else {
        posRef.current = target;
        redraw();
      }
    }
    animRef.current = requestAnimationFrame(step);
  }

  function redraw() {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const dpr = window.devicePixelRatio || 1;
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    drawSwitch(ctx, posRef.current);
  }

  // Synchroniser avec isDark
  useEffect(() => {
    const target = isDark ? 1 : 0;
    animateTo(target);
  }, [isDark]);

  // Setup canvas DPR
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const dpr = window.devicePixelRatio || 1;
    canvas.width = (W + 4) * dpr;
    canvas.height = (H + 4) * dpr;
    redraw();
    return () => {
      if (animRef.current) cancelAnimationFrame(animRef.current);
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      width={W + 4}
      height={H + 4}
      style={{
        width: W + 4,
        height: H + 4,
        cursor: "pointer",
        display: "block",
        flexShrink: 0,
      }}
      onClick={onToggle}
      title="Basculer thème clair / sombre"
    />
  );
}
