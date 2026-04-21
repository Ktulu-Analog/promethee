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
 * SidebarFooter.tsx — Bouton avatar + menu utilisateur (settings, admin, déconnexion, à propos).
 */

import React, { useState, useRef, useEffect } from "react";
import { createPortal } from "react-dom";
import { useSettings } from "../../hooks/useSettings";
import { s } from "./sidebarStyles";

// ── ParticleCanvas ────────────────────────────────────────────────────────────

function ParticleCanvas() {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d")!;

    const COLORS = ["#d4813d", "#7aafd4", "#c06070", "#5aaa7a", "#9a7ad4"];
    const NODES = 38;
    interface P { x: number; y: number; vx: number; vy: number; r: number; alpha: number; color: string; }
    const particles: P[] = [];

    const resize = () => { canvas.width = canvas.offsetWidth; canvas.height = canvas.offsetHeight; };
    resize();
    window.addEventListener("resize", resize);

    for (let i = 0; i < NODES; i++) {
      particles.push({
        x: Math.random() * canvas.width,
        y: Math.random() * canvas.height,
        vx: (Math.random() - 0.5) * 0.4,
        vy: (Math.random() - 0.5) * 0.4,
        r: Math.random() * 2 + 0.8,
        alpha: Math.random() * 0.5 + 0.2,
        color: COLORS[Math.floor(Math.random() * COLORS.length)],
      });
    }

    let animId: number;
    const draw = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      for (let i = 0; i < particles.length; i++) {
        for (let j = i + 1; j < particles.length; j++) {
          const dx = particles[i].x - particles[j].x;
          const dy = particles[i].y - particles[j].y;
          const dist = Math.sqrt(dx * dx + dy * dy);
          if (dist < 100) {
            ctx.beginPath();
            ctx.moveTo(particles[i].x, particles[i].y);
            ctx.lineTo(particles[j].x, particles[j].y);
            ctx.strokeStyle = `rgba(180,160,220,${(1 - dist / 100) * 0.22})`;
            ctx.lineWidth = 0.7;
            ctx.stroke();
          }
        }
      }
      particles.forEach(p => {
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
        ctx.fillStyle = p.color + Math.round(p.alpha * 255).toString(16).padStart(2, "0");
        ctx.fill();
        const grd = ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, p.r * 5);
        grd.addColorStop(0, p.color + "44");
        grd.addColorStop(1, p.color + "00");
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.r * 5, 0, Math.PI * 2);
        ctx.fillStyle = grd;
        ctx.fill();
        p.x += p.vx; p.y += p.vy;
        if (p.x < 0 || p.x > canvas.width)  p.vx *= -1;
        if (p.y < 0 || p.y > canvas.height) p.vy *= -1;
      });
      animId = requestAnimationFrame(draw);
    };
    draw();
    return () => { cancelAnimationFrame(animId); window.removeEventListener("resize", resize); };
  }, []);

  return <canvas ref={canvasRef} style={{ position: "absolute", inset: 0, width: "100%", height: "100%", opacity: 0.7 }} />;
}

// ── LogoutConfirmModal ────────────────────────────────────────────────────────

function LogoutConfirmModal({ username, onConfirm, onCancel }: {
  username?: string;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  return createPortal(
    <div
      style={{
        position: "fixed", inset: 0, zIndex: 9999,
        background: "rgba(0,0,0,0.25)",
        backdropFilter: "blur(2px)",
        display: "flex", alignItems: "center", justifyContent: "center",
      }}
      onClick={onCancel}
    >
      <div
        style={{
          background: "var(--surface-bg)",
          border: "1px solid var(--border)",
          borderRadius: 12,
          boxShadow: "0 8px 40px rgba(0,0,0,0.4)",
          padding: "28px 28px 22px",
          width: "min(340px, 90vw)",
          display: "flex", flexDirection: "column", gap: 16,
        }}
        onClick={e => e.stopPropagation()}
      >
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 10 }}>
          <span style={{ fontSize: 32, lineHeight: 1 }}>⏻</span>
          <p style={{ margin: 0, fontSize: 16, fontWeight: 700, color: "var(--text-primary)", textAlign: "center" }}>
            Se déconnecter
          </p>
          <p style={{ margin: 0, fontSize: 13, color: "var(--text-secondary)", textAlign: "center", lineHeight: 1.5 }}>
            {username
              ? <>Voulez-vous vraiment vous déconnecter du compte <strong>{username}</strong>&nbsp;?</>
              : "Voulez-vous vraiment vous déconnecter ?"}
          </p>
        </div>

        <div style={{ display: "flex", gap: 10, marginTop: 4 }}>
          <button
            onClick={onCancel}
            style={{
              flex: 1, padding: "9px 0",
              background: "none",
              border: "1px solid var(--border, rgba(0,0,0,0.2))",
              borderRadius: 8, fontSize: 14, fontWeight: 500,
              color: "var(--text-secondary)", cursor: "pointer", fontFamily: "inherit",
            }}
          >
            Annuler
          </button>
          <button
            onClick={onConfirm}
            style={{
              flex: 1, padding: "9px 0",
              background: "var(--text-primary, #1a1a1e)",
              color: "var(--base-bg, #fff)",
              border: "none", borderRadius: 8, fontSize: 14, fontWeight: 600,
              cursor: "pointer", fontFamily: "inherit",
            }}
          >
            Déconnecter
          </button>
        </div>
      </div>
    </div>,
    document.body
  );
}

// ── AboutModal ────────────────────────────────────────────────────────────────

function AboutModal({ appTitle, appVersion, onClose }: {
  appTitle: string;
  appVersion: string;
  onClose: () => void;
}) {
  return createPortal(
    <div style={{
      position: "fixed", inset: 0,
      background: "rgba(0,0,0,0.65)",
      display: "flex", alignItems: "center", justifyContent: "center",
      zIndex: 2000,
    }}>
      <div style={{
        position: "relative",
        overflow: "hidden",
        background: "#00010a",
        border: "1px solid rgba(255,255,255,0.1)",
        borderRadius: 16,
        width: 360, maxWidth: "92vw",
        boxShadow: "0 24px 80px rgba(0,0,0,0.7)",
        display: "flex", flexDirection: "column", alignItems: "center",
        textAlign: "center",
      }}>

        {/* ── Fond nébuleux ── */}
        <div style={{ position: "absolute", inset: 0, pointerEvents: "none",
          background: "radial-gradient(ellipse 80% 60% at 50% 48%, rgba(18,60,140,0.55) 0%, rgba(8,25,80,0.3) 40%, transparent 70%)",
        }} />
        <div style={{ position: "absolute", width: "140%", height: "140%", borderRadius: "50%", pointerEvents: "none",
          background: "radial-gradient(ellipse at 40% 55%, rgba(30,80,180,0.22) 0%, rgba(10,30,100,0.12) 45%, transparent 70%)",
          top: "-20%", left: "-20%",
          filter: "blur(32px)",
        }} />
        <div style={{ position: "absolute", width: "120%", height: "120%", borderRadius: "50%", pointerEvents: "none",
          background: "radial-gradient(ellipse at 55% 45%, rgba(20,60,160,0.2) 0%, rgba(5,20,90,0.1) 50%, transparent 72%)",
          bottom: "-20%", right: "-20%",
          filter: "blur(28px)",
        }} />
        <div style={{ position: "absolute", width: 200, height: 200, borderRadius: "50%", pointerEvents: "none",
          background: "radial-gradient(circle, rgba(60,30,120,0.15) 0%, transparent 70%)",
          top: "20%", right: "10%",
          filter: "blur(40px)",
        }} />

        {/* ── Particules ── */}
        <ParticleCanvas />

        {/* ── Contenu ── */}
        <div style={{
          position: "relative", zIndex: 1,
          display: "flex", flexDirection: "column", alignItems: "center", gap: 12,
          padding: "32px 32px 28px",
          width: "100%", boxSizing: "border-box",
        }}>
          <div style={{ fontSize: 22, fontWeight: 700, color: "#e4e2ec", letterSpacing: "-0.01em" }}>
            {appTitle}
          </div>
          {appVersion && (
            <div style={{ fontSize: 12, color: "rgba(255,255,255,0.45)", letterSpacing: "0.08em" }}>
              v{appVersion}
            </div>
          )}

          <div style={{ width: 40, height: 1, background: "linear-gradient(90deg,transparent,rgba(212,129,61,0.7),transparent)", margin: "4px 0" }} />

          <div style={{ fontSize: 13, color: "rgba(255,255,255,0.55)", lineHeight: 1.7 }}>
            <div style={{ fontWeight: 500, color: "rgba(255,255,255,0.7)" }}>Pierre COUGET — 2026</div>
            <div style={{ marginTop: 4 }}>
              Distribué sous licence{" "}
              <a
                href="https://www.gnu.org/licenses/agpl-3.0.html"
                target="_blank"
                rel="noopener noreferrer"
                style={{ color: "#d4813d", textDecoration: "none", fontWeight: 600 }}
              >
                AGPL-3.0
              </a>
            </div>
          </div>

          <button
            onClick={onClose}
            style={{
              marginTop: 8,
              padding: "8px 28px",
              background: "rgba(255,255,255,0.07)",
              border: "1px solid rgba(255,255,255,0.15)",
              borderRadius: 8,
              color: "rgba(255,255,255,0.8)",
              fontSize: 13, cursor: "pointer", fontFamily: "inherit",
              transition: "background 0.2s, border-color 0.2s",
            }}
            onMouseEnter={e => { e.currentTarget.style.background = "rgba(212,129,61,0.18)"; e.currentTarget.style.borderColor = "rgba(212,129,61,0.5)"; }}
            onMouseLeave={e => { e.currentTarget.style.background = "rgba(255,255,255,0.07)"; e.currentTarget.style.borderColor = "rgba(255,255,255,0.15)"; }}
          >
            Fermer
          </button>
        </div>
      </div>
    </div>,
    document.body
  );
}

// ── SidebarFooter ─────────────────────────────────────────────────────────────

const menuItemStyle: React.CSSProperties = {
  display: "flex", alignItems: "center", gap: 10,
  padding: "9px 16px",
  background: "none", border: "none",
  width: "100%", textAlign: "left",
  fontSize: 13, color: "var(--text-primary)",
  cursor: "pointer", fontFamily: "inherit",
};

export interface SidebarFooterProps {
  isDark: boolean;
  toggleTheme: () => void;
  isAdmin?: boolean;
  onOpenAdmin?: () => void;
  onOpenSettings: () => void;
  onLogout?: () => void;
  currentUsername?: string;
  iconSize: number;
}

export function SidebarFooter({
  isDark, toggleTheme, isAdmin, onOpenAdmin, onOpenSettings, onLogout, currentUsername, iconSize,
}: SidebarFooterProps) {
  const [menuOpen, setMenuOpen] = useState(false);
  const [showLogoutModal, setShowLogoutModal] = useState(false);
  const [showAboutModal, setShowAboutModal] = useState(false);
  const { settings } = useSettings();
  const avatarRef = useRef<HTMLButtonElement>(null);
  const popupRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!menuOpen) return;
    function handleOutside(e: MouseEvent) {
      const target = e.target as Node;
      if (
        avatarRef.current && !avatarRef.current.contains(target) &&
        popupRef.current && !popupRef.current.contains(target)
      ) {
        setMenuOpen(false);
      }
    }
    document.addEventListener("mousedown", handleOutside);
    return () => document.removeEventListener("mousedown", handleOutside);
  }, [menuOpen]);

  const initial = currentUsername ? currentUsername.charAt(0).toUpperCase() : "?";
  const rect = avatarRef.current?.getBoundingClientRect();
  const popTop = rect ? rect.top - 8 : 0;
  const popLeft = rect ? rect.right + 10 : 60;

  return (
    <>
      <button style={s.railBtn} onClick={toggleTheme} title={isDark ? "Thème clair" : "Thème sombre"}>
        <span style={{ fontSize: iconSize, lineHeight: 1 }}>{isDark ? "☀️" : "🌙"}</span>
      </button>

      <div style={{ position: "relative" }}>
        <button
          ref={avatarRef}
          onClick={() => setMenuOpen(v => !v)}
          title={currentUsername ?? "Compte"}
          style={{
            width: 34, height: 34,
            borderRadius: "50%",
            border: menuOpen ? "2px solid var(--text-primary)" : "2px solid var(--border)",
            background: "var(--elevated-bg)",
            color: "var(--text-primary)",
            fontSize: 14, fontWeight: 700,
            cursor: "pointer",
            display: "flex", alignItems: "center", justifyContent: "center",
            transition: "border-color 0.15s",
            flexShrink: 0,
          }}
        >
          {initial}
        </button>
      </div>

      {menuOpen && createPortal(
        <div
          ref={popupRef}
          style={{
            position: "fixed",
            top: popTop,
            left: popLeft,
            transform: "translateY(-100%)",
            zIndex: 9999,
            background: "var(--elevated-bg)",
            border: "1px solid var(--border)",
            borderRadius: 12,
            boxShadow: "0 8px 32px rgba(0,0,0,0.4)",
            minWidth: 210,
            padding: "6px 0",
            display: "flex", flexDirection: "column",
          }}
        >
          {currentUsername && (
            <div style={{ padding: "10px 16px 8px", borderBottom: "1px solid var(--border)", marginBottom: 4 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <div style={{
                  width: 32, height: 32, borderRadius: "50%",
                  background: "var(--surface-bg)",
                  border: "1px solid var(--border)",
                  display: "flex", alignItems: "center", justifyContent: "center",
                  fontSize: 14, fontWeight: 700, color: "var(--text-primary)", flexShrink: 0,
                }}>
                  {initial}
                </div>
                <span style={{ fontSize: 13, fontWeight: 600, color: "var(--text-primary)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {currentUsername}
                </span>
              </div>
            </div>
          )}

          <button
            onMouseDown={(e) => { e.stopPropagation(); setMenuOpen(false); onOpenSettings(); }}
            style={menuItemStyle}
          >
            <span style={{ fontSize: 15 }}>⚙︎</span>
            Paramètres
          </button>

          {isAdmin && onOpenAdmin && (
            <button
              onMouseDown={(e) => { e.stopPropagation(); setMenuOpen(false); onOpenAdmin(); }}
              style={menuItemStyle}
            >
              <span style={{ fontSize: 15 }}>🛡</span>
              Administration
            </button>
          )}

          <div style={{ borderTop: "1px solid var(--border)", margin: "4px 0" }} />

          <button
            onMouseDown={(e) => { e.stopPropagation(); setMenuOpen(false); setShowAboutModal(true); }}
            style={menuItemStyle}
          >
            <span style={{ fontSize: 15 }}>ℹ️</span>
            À propos
          </button>

          {onLogout && (
            <>
              <div style={{ borderTop: "1px solid var(--border)", margin: "4px 0" }} />
              <button
                onMouseDown={(e) => { e.stopPropagation(); setMenuOpen(false); setShowLogoutModal(true); }}
                style={{ ...menuItemStyle, color: "#e07070" }}
              >
                <span style={{ fontSize: 15 }}>⏻</span>
                Se déconnecter
              </button>
            </>
          )}
        </div>,
        document.body
      )}

      {showLogoutModal && (
        <LogoutConfirmModal
          username={currentUsername}
          onConfirm={() => { setShowLogoutModal(false); onLogout?.(); }}
          onCancel={() => setShowLogoutModal(false)}
        />
      )}

      {showAboutModal && (
        <AboutModal
          appTitle={settings?.APP_TITLE ?? "Prométhée AI"}
          appVersion={settings?.APP_VERSION ?? ""}
          onClose={() => setShowAboutModal(false)}
        />
      )}
    </>
  );
}
