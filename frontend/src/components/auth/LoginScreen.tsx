/**
 * ============================================================================
 * Prométhée — Assistant IA avancé
 * ============================================================================
 * Auteur  : Pierre COUGET
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
 * LoginScreen.tsx — Écran de connexion / inscription
 *
 * Layout deux colonnes inspiré MinIO :
 *  - Gauche  : panneau décoratif animé avec logo, tagline et particules
 *  - Droite  : formulaire login / register / setup-admin
 */

import React, { useState, useEffect, useRef } from "react";
const logoSrc = "/logo.png";

// Polices système — aucune dépendance externe

interface Props {
  onLogin:       (username: string, password: string) => Promise<void>;
  onRegister:    (username: string, email: string, password: string) => Promise<void>;
  onSetupAdmin?: (username: string, email: string, password: string) => Promise<void>;
  adminExists?:  boolean;  // false = premier démarrage, afficher le setup admin
  error:         string | null;
  loading:       boolean;
}

// ── Particle Canvas ────────────────────────────────────────────────────────────

function ParticleCanvas() {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d")!;

    const COLORS = ["#d4813d", "#7aafd4", "#c06070", "#5aaa7a", "#9a7ad4"];
    const NODES = 52;
    interface P { x:number;y:number;vx:number;vy:number;r:number;alpha:number;color:string; }
    const particles: P[] = [];

    const resize = () => { canvas.width = canvas.offsetWidth; canvas.height = canvas.offsetHeight; };
    resize();
    window.addEventListener("resize", resize);

    for (let i = 0; i < NODES; i++) {
      particles.push({
        x: Math.random() * canvas.width,
        y: Math.random() * canvas.height,
        vx: (Math.random() - 0.5) * 0.45,
        vy: (Math.random() - 0.5) * 0.45,
        r: Math.random() * 2.2 + 1,
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
          if (dist < 130) {
            ctx.beginPath();
            ctx.moveTo(particles[i].x, particles[i].y);
            ctx.lineTo(particles[j].x, particles[j].y);
            ctx.strokeStyle = `rgba(180,160,220,${(1 - dist / 130) * 0.22})`;
            ctx.lineWidth = 0.8;
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

  return <canvas ref={canvasRef} style={{ position:"absolute", inset:0, width:"100%", height:"100%", opacity:0.75 }} />;
}

// ── CRT Glitch Canvas ──────────────────────────────────────────────────────────
// Rendu canvas avec effet tube cathodique :
//  - scanlines permanentes légères
//  - barrel distortion douce (simulée par vignette + perspective)
//  - parasites horizontaux aléatoires (bandes décalées)
//  - légère instabilité verticale de balayage

interface CRTGlitchProps {
  src: string;
  width: number;
  height: number;
  style?: React.CSSProperties;
}

function CRTGlitchCanvas({ src, width, height, style }: CRTGlitchProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const imgRef    = useRef<HTMLImageElement | null>(null);
  const stateRef  = useRef({
    // Glitch scheduling
    nextGlitchAt: performance.now() + 8000 + Math.random() * 12000,
    glitchEnd:    0,
    active:       false,
    // Parasite bands actives pendant un glitch
    bands: [] as Array<{ y: number; h: number; shift: number; alpha: number }>,
    // Scan-jitter : léger tremblement vertical de balayage
    jitter: 0,
    // Phase du scan line
    scanPhase: 0,
  });

  useEffect(() => {
    const img = new Image();
    img.src = src;
    img.onload = () => { imgRef.current = img; };
    imgRef.current = img;
  }, [src]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d")!;
    let animId: number;

    const W = width;
    const H = height;
    canvas.width  = W;
    canvas.height = H;

    // Offscreen pour lire les pixels source
    const off    = document.createElement("canvas");
    off.width    = W; off.height = H;
    const offCtx = off.getContext("2d")!;

    const draw = (now: number) => {
      const s = stateRef.current;

      // ── Déclencher un nouveau glitch ──
      if (!s.active && now >= s.nextGlitchAt) {
        s.active    = true;
        s.glitchEnd = now + 60 + Math.random() * 120;  // 60-180ms
        s.jitter    = (Math.random() - 0.5) * 2.5;
      }

      // ── Fin de glitch ──
      if (s.active && now >= s.glitchEnd) {
        s.active       = false;
        s.bands        = [];
        s.jitter       = 0;
        s.nextGlitchAt = now + 8000 + Math.random() * 12000;
      }

      // Re-randomiser les bandes à CHAQUE frame pendant le glitch
      if (s.active) {
        const nb = 1 + Math.floor(Math.random() * 3);
        s.bands = Array.from({ length: nb }, () => ({
          y:     Math.random() * H,
          h:     1 + Math.random() * 10,
          shift: (Math.random() - 0.5) * 26,
          alpha: 0.5 + Math.random() * 0.4,
        }));
      }

      const inGlitch = s.active;

      // Phase scan lente
      s.scanPhase = (s.scanPhase + 0.4) % H;

      ctx.clearRect(0, 0, W, H);

      const img = imgRef.current;
      if (!img || !img.complete) { animId = requestAnimationFrame(draw); return; }

      // ── Dessiner l'image source sur offscreen ──
      offCtx.clearRect(0, 0, W, H);
      offCtx.drawImage(img, 0, 0, W, H);

      // ── Rendu principal avec éventuel scan-jitter ──
      const jy = inGlitch ? s.jitter : 0;
      ctx.drawImage(off, 0, jy, W, H);

      // ── Bandes de parasites (décalage horizontal de tranches) ──
      if (inGlitch) {
        s.bands.forEach(b => {
          // Lire la tranche source
          const sy = Math.max(0, Math.round(b.y));
          const sh = Math.min(Math.round(b.h), H - sy);
          if (sh <= 0) return;
          try {
            const slice = offCtx.getImageData(0, sy, W, sh);
            // Coller décalée
            ctx.save();
            ctx.globalAlpha = b.alpha;
            const tmpC = document.createElement("canvas");
            tmpC.width = W; tmpC.height = sh;
            tmpC.getContext("2d")!.putImageData(slice, 0, 0);
            ctx.drawImage(tmpC, b.shift, sy + jy);
            ctx.restore();
          } catch { /* cross-origin safety */ }
        });
      }

      // ── Scanlines ──
      // Lignes paires légèrement assombries — effet phosphore
      ctx.save();
      for (let y = 0; y < H; y += 3) {
        const intensity = inGlitch ? 0.18 : 0.10;
        ctx.fillStyle = `rgba(0,0,0,${intensity})`;
        ctx.fillRect(0, y, W, 1);
      }
      ctx.restore();

      // ── Ligne de balayage lumineuse (phosphore qui descend) ──
      const scanY = (s.scanPhase + (inGlitch ? jy * 3 : 0)) % H;
      const scanGrd = ctx.createLinearGradient(0, scanY - 4, 0, scanY + 4);
      scanGrd.addColorStop(0,   "rgba(180,220,255,0)");
      scanGrd.addColorStop(0.5, `rgba(180,220,255,${inGlitch ? 0.18 : 0.06})`);
      scanGrd.addColorStop(1,   "rgba(180,220,255,0)");
      ctx.save();
      ctx.fillStyle = scanGrd;
      ctx.fillRect(0, scanY - 4, W, 8);
      ctx.restore();

      // ── Vignette circulaire (barrel distortion simulée) ──
      const vgrd = ctx.createRadialGradient(W/2, H/2, H * 0.25, W/2, H/2, H * 0.75);
      vgrd.addColorStop(0, "rgba(0,0,0,0)");
      vgrd.addColorStop(1, "rgba(0,0,0,0.55)");
      ctx.save();
      ctx.fillStyle = vgrd;
      ctx.fillRect(0, 0, W, H);
      ctx.restore();

      // ── Légère teinte phosphore verdâtre pendant le glitch ──
      if (inGlitch) {
        ctx.save();
        ctx.globalAlpha = 0.06;
        ctx.fillStyle = "#88ffcc";
        ctx.fillRect(0, 0, W, H);
        ctx.restore();
      }

      animId = requestAnimationFrame(draw);
    };

    animId = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(animId);
  }, [width, height]);

  return (
    <canvas
      ref={canvasRef}
      style={{ display:"block", ...style }}
    />
  );
}

// ── Logo animé ─────────────────────────────────────────────────────────────────

function AnimatedLogo() {
  return (
    <div style={{ position:"relative", width:256, height:256, marginBottom:8 }}>
      {/* Halo pulsant */}
      <div style={{
        position:"absolute", inset:-36, borderRadius:"50%",
        background:"radial-gradient(circle, rgba(255,255,255,0.18) 0%, transparent 70%)",
        animation:"pulse 3s ease-in-out infinite",
      }} />
      {/* Anneau orbital */}
      <div style={{
        position:"absolute", inset:-16, borderRadius:"50%",
        border:"1px solid rgba(212,129,61,0.22)",
        animation:"spin 14s linear infinite",
      }}>
        {[0,60,120,180,240,300].map(deg => (
          <div key={deg} style={{
            position:"absolute", width:5, height:5, borderRadius:"50%",
            background: deg % 120 === 0 ? "#d4813d" : "#7aafd4",
            top:"50%", left:"50%",
            transform:`rotate(${deg}deg) translateX(100px) translate(-50%,-50%)`,
            boxShadow:`0 0 6px ${deg % 120 === 0 ? "#d4813d" : "#7aafd4"}`,
          }} />
        ))}
      </div>
      {/* Canvas CRT */}
      <CRTGlitchCanvas
        src={logoSrc}
        width={256}
        height={256}
        style={{
          borderRadius:"50%",
          filter:"drop-shadow(0 0 16px rgba(255,255,255,0.55))",
        }}
      />
    </div>
  );
}

// ── Titre avec effet CRT ───────────────────────────────────────────────────────

function GlitchTitle() {
  const divRef  = useRef<HTMLDivElement>(null);
  const stateRef = useRef({
    nextGlitchAt: performance.now() + 9000 + Math.random() * 13000,
    glitchEnd: 0,
    bands: [] as Array<{ frac: number; shift: number; height: number }>,
    jitter: 0,
  });
  // On force un re-render via un compteur pour piloter les classes CSS
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let animId: number;
    const loop = (now: number) => {
      const s = stateRef.current;
      const wasGlitch = s.glitchEnd > 0 && now >= s.glitchEnd;

      if (now >= s.nextGlitchAt && s.glitchEnd === 0) {
        s.glitchEnd = now + 60 + Math.random() * 120;  // court : 60-180ms
        s.jitter = (Math.random() - 0.5) * 3;
        setTick(t => t + 1);
      }

      const inGlitch = now < s.glitchEnd;

      // Re-randomiser les bandes à chaque frame pendant le glitch
      if (inGlitch) {
        s.bands = Array.from({ length: 1 + Math.floor(Math.random() * 3) }, () => ({
          frac:   Math.random(),
          shift:  (Math.random() - 0.5) * 18,
          height: 2 + Math.random() * 10,
        }));
        setTick(t => t + 1);  // re-render pour afficher les nouvelles bandes
      }

      // Transition glitch → normal : une seule fois
      if (!inGlitch && wasGlitch) {
        s.bands = [];
        s.jitter = 0;
        s.glitchEnd = 0;
        s.nextGlitchAt = now + 8000 + Math.random() * 14000;
        setTick(t => t + 1);
      }

      animId = requestAnimationFrame(loop);
    };
    animId = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(animId);
  }, []);

  const s = stateRef.current;
  const now = performance.now();
  const inGlitch = now < s.glitchEnd;

  return (
    <div ref={divRef} style={{
      position:"relative",
      margin:"18px 0 4px",
      overflow:"hidden",
      lineHeight:1.2,
    }}>
      {/* Texte principal */}
      <h1 style={{
        margin:0, fontSize:40, fontWeight:800,
        fontFamily:"'Segoe UI', 'Ubuntu', 'Cantarell', system-ui, sans-serif", letterSpacing:"-0.5px",
        background:"#ffffff",
        WebkitBackgroundClip:"text", WebkitTextFillColor:"transparent",
        transform: inGlitch ? `translateY(${s.jitter}px)` : "none",
        transition: inGlitch ? "none" : "transform 0.1s ease",
        whiteSpace:"nowrap",
        display:"block",
      }}>PROMÉTHÉE</h1>

      {/* Bandes de parasites CSS par-dessus le texte */}
      {inGlitch && s.bands.map((b, i) => (
        <div key={i} aria-hidden style={{
          position:"absolute",
          top: `calc(${b.frac * 100}% - ${b.height/2}px)`,
          left:0, right:0,
          height: b.height,
          overflow:"hidden",
          transform:`translateX(${b.shift}px)`,
          // Reproduire le texte décalé via clip
          pointerEvents:"none",
        }}>
          <h1 style={{
            margin:0, fontSize:50, fontWeight:800,
            fontFamily:"'Segoe UI', 'Ubuntu', 'Cantarell', system-ui, sans-serif", letterSpacing:"-0.5px",
            background:"#ffffff",
            WebkitBackgroundClip:"text", WebkitTextFillColor:"transparent",
            opacity:0.8,
            whiteSpace:"nowrap",
            lineHeight:1.2,
            // Repositionner pour que le bon morceau soit visible dans le clip
            transform:`translateY(calc(-${b.frac * 100}% + ${b.height/2}px - ${s.jitter}px))`,
          }}>PROMÉTHÉE</h1>
        </div>
      ))}

      {/* Scanline horizontale fine qui traverse */}
      {inGlitch && (
        <div aria-hidden style={{
          position:"absolute", left:0, right:0,
          top:"50%", height:1,
          background:"rgba(180,240,255,0.35)",
          transform:`translateY(${s.jitter * 2}px)`,
          pointerEvents:"none",
        }} />
      )}
    </div>
  );
}

const FEATURES = [
  { icon:"⚡", label:"Moteur IA multi-modèles" },
  { icon:"🇫🇷", label:"Albert API" },
  { icon:"🏛️", label:"API Légifrance, Judilibre, Data.gouv, Grist, Docs" },
  { icon:"🔧", label:"Outils & Agents autonomes" },
  { icon:"📁", label:"Système de fichiers virtuel" },
  { icon:"🇫🇷", label:"Stockage S3 par Garage" },
];

// ── Main ───────────────────────────────────────────────────────────────────────

export function LoginScreen({ onLogin, onRegister, onSetupAdmin, adminExists = true, error, loading }: Props) {
  // Si aucun admin n'existe encore, forcer le mode setup
  const [mode, setMode] = useState<"login" | "register" | "setup-admin">(
    adminExists === false ? "setup-admin" : "login"
  );

  // Resynchroniser si adminExists change (chargement asynchrone)
  useEffect(() => {
    if (adminExists === false) setMode("setup-admin");
  }, [adminExists]);
  const [username, setUsername]   = useState("");
  const [email, setEmail]         = useState("");
  const [password, setPassword]   = useState("");
  const [password2, setPassword2] = useState("");
  const [localErr, setLocalErr]   = useState<string|null>(null);
  const [focused, setFocused]     = useState<string|null>(null);
  const [mounted, setMounted]     = useState(false);

  useEffect(() => { const t = setTimeout(() => setMounted(true), 60); return () => clearTimeout(t); }, []);

  const visibleError = localErr || error;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLocalErr(null);
    if (mode === "setup-admin") {
      if (password !== password2) { setLocalErr("Les mots de passe ne correspondent pas."); return; }
      if (password.length < 8)    { setLocalErr("Minimum 8 caractères requis."); return; }
      if (onSetupAdmin) await onSetupAdmin(username.trim(), email.trim(), password);
    } else if (mode === "register") {
      if (password !== password2) { setLocalErr("Les mots de passe ne correspondent pas."); return; }
      if (password.length < 8)    { setLocalErr("Minimum 8 caractères requis."); return; }
      await onRegister(username.trim(), email.trim(), password);
    } else {
      await onLogin(username.trim(), password);
    }
  }

  const inputStyle = (name: string): React.CSSProperties => ({
    width:"100%", padding:"10px 14px", boxSizing:"border-box",
    background: focused === name ? "rgba(255,255,255,0.07)" : "rgba(255,255,255,0.04)",
    border:`1px solid ${focused === name ? "rgba(212,129,61,0.7)" : "rgba(255,255,255,0.1)"}`,
    borderRadius:8, color:"#e4e2ec", fontSize:14, outline:"none",
    transition:"all 0.2s ease",
    boxShadow: focused === name ? "0 0 0 3px rgba(212,129,61,0.12)" : "none",
  });

  const labelStyle: React.CSSProperties = {
    fontSize:11, fontWeight:600, color:"#6a6a78",
    letterSpacing:"0.08em", textTransform:"uppercase",
  };

  return (
    <>
      <style>{`
        @keyframes pulse   { 0%,100%{transform:scale(1);opacity:1}50%{transform:scale(1.12);opacity:0.7} }
        @keyframes spin    { from{transform:rotate(0deg)}to{transform:rotate(360deg)} }
        @keyframes fadeUp  { from{opacity:0;transform:translateY(18px)}to{opacity:1;transform:translateY(0)} }
        @keyframes fadeRight{ from{opacity:0;transform:translateX(-18px)}to{opacity:1;transform:translateX(0)} }
        .prom-btn:hover:not(:disabled){background:linear-gradient(135deg,#e08f4a,#cf7a35)!important;transform:translateY(-1px);box-shadow:0 6px 20px rgba(212,129,61,0.4)!important;}
        .prom-btn:active:not(:disabled){transform:translateY(0)!important;}
        .prom-feat:hover{transform:translateX(4px);background:rgba(255,255,255,0.055)!important;}
        .prom-switch:hover{color:#e08f4a!important;}
        input:-webkit-autofill,input:-webkit-autofill:hover,input:-webkit-autofill:focus{
          -webkit-text-fill-color:#e4e2ec!important;
          -webkit-box-shadow:0 0 0 1000px #1a1a1e inset!important;
        }
      `}</style>

      <div style={{ minHeight:"100vh", display:"flex", background:"#0d0d0f", fontFamily:"system-ui, 'Segoe UI', 'Ubuntu', sans-serif" }}>

        {/* LEFT */}
        <div style={{
          flex:"0 0 67%", position:"relative", display:"flex", flexDirection:"column",
          alignItems:"center", justifyContent:"center", overflow:"hidden",
          background:"#00010a",
          borderRight:"1px solid rgba(255,255,255,0.05)",
        }}>
          {/* Nébuleuse centrale — halo bleu diffus */}
          <div style={{ position:"absolute", inset:0, pointerEvents:"none",
            background:"radial-gradient(ellipse 80% 60% at 50% 48%, rgba(18,60,140,0.55) 0%, rgba(8,25,80,0.3) 40%, transparent 70%)",
          }} />
          {/* Nuage cosmique haut-gauche */}
          <div style={{ position:"absolute", width:560, height:420, borderRadius:"50%", pointerEvents:"none",
            background:"radial-gradient(ellipse at 40% 55%, rgba(30,80,180,0.22) 0%, rgba(10,30,100,0.12) 45%, transparent 70%)",
            top:"-8%", left:"-12%", transform:"rotate(-15deg)",
            filter:"blur(32px)",
          }} />
          {/* Nuage cosmique bas-droit */}
          <div style={{ position:"absolute", width:480, height:380, borderRadius:"50%", pointerEvents:"none",
            background:"radial-gradient(ellipse at 55% 45%, rgba(20,60,160,0.2) 0%, rgba(5,20,90,0.1) 50%, transparent 72%)",
            bottom:"-5%", right:"-8%", transform:"rotate(20deg)",
            filter:"blur(28px)",
          }} />
          {/* Voile violet très subtil pour la profondeur */}
          <div style={{ position:"absolute", width:300, height:300, borderRadius:"50%", pointerEvents:"none",
            background:"radial-gradient(circle, rgba(60,30,120,0.12) 0%, transparent 70%)",
            top:"30%", right:"15%",
            filter:"blur(40px)",
          }} />

          <ParticleCanvas />

          <div style={{
            position:"relative", zIndex:1, display:"flex", flexDirection:"column",
            alignItems:"center", textAlign:"center", padding:"0 52px",
            animation: mounted ? "fadeRight 0.7s ease forwards" : "none",
            opacity: mounted ? 1 : 0,
          }}>
            <AnimatedLogo />

            <GlitchTitle />

            <p style={{ margin:"0 0 32px", fontSize:11, letterSpacing:"0.25em", color:"#7aafd4", textTransform:"uppercase", fontWeight:500 }}>
              Votre assistant IA au quotidien
            </p>

            <div style={{ width:44, height:1, background:"linear-gradient(90deg,transparent,rgba(212,129,61,0.7),transparent)", marginBottom:28 }} />

            <div style={{ display:"flex", flexDirection:"column", gap:8, alignSelf:"stretch" }}>
              {FEATURES.map((f, i) => (
                <div key={i} className="prom-feat" style={{
                  display:"flex", alignItems:"center", gap:12,
                  padding:"10px 16px", borderRadius:10,
                  background:"rgba(255,255,255,0.03)",
                  border:"1px solid rgba(255,255,255,0.06)",
                  transition:"all 0.2s ease",
                  whiteSpace:"nowrap",
                  animation: mounted ? `fadeRight ${0.5 + i * 0.1}s ease forwards` : "none",
                }}>
                  <span style={{ fontSize:17, flexShrink:0 }}>{f.icon}</span>
                  <span style={{ fontSize:13, color:"#b0adb8", fontWeight:500, whiteSpace:"nowrap" }}>{f.label}</span>
                </div>
              ))}
            </div>
          </div>

          <div style={{ position:"absolute", bottom:22, fontSize:12, color:"rgba(255,255,255,0.78)", letterSpacing:"0.1em" }}>
            Pierre COUGET - 2026 - logiciel sous licence AGPL 3.0
          </div>
        </div>

        {/* RIGHT */}
        <div style={{
          flex:1, display:"flex", alignItems:"center", justifyContent:"center",
          padding:"40px 32px",
          animation: mounted ? "fadeUp 0.6s ease forwards" : "none",
          opacity: mounted ? 1 : 0,
          position:"relative",
        }}>
          <div style={{ width:"100%", maxWidth:400 }}>

            <div style={{ marginBottom:34 }}>
              <h2 style={{ margin:"0 0 6px", fontSize:26, fontWeight:700, fontFamily:"'Segoe UI', 'Ubuntu', 'Cantarell', system-ui, sans-serif", color:"#e4e2ec" }}>
                {mode === "login" ? "Bienvenue" : mode === "setup-admin" ? "Initialisation" : "Créer un compte"}
              </h2>
              <p style={{ margin:0, fontSize:14, color:"#6a6a78" }}>
                {mode === "login"
                  ? "Connectez-vous à votre espace Prométhée"
                  : mode === "setup-admin"
                  ? "Créez le premier compte administrateur"
                  : "Rejoignez l'espace Prométhée"}
              </p>
              {mode === "setup-admin" && (
                <div style={{ marginTop:10, padding:"8px 12px", background:"rgba(212,129,61,0.1)", border:"1px solid rgba(212,129,61,0.3)", borderRadius:8, fontSize:12, color:"#d4813d" }}>
                  🛡 Aucun administrateur n'existe encore. Ce compte aura les droits complets.
                </div>
              )}
            </div>

            <form onSubmit={handleSubmit} style={{ display:"flex", flexDirection:"column", gap:16 }}>

              <div style={{ display:"flex", flexDirection:"column", gap:6 }}>
                <label style={labelStyle}>Identifiant</label>
                <input style={inputStyle("username")} type="text" placeholder="Votre nom d'utilisateur"
                  value={username} onChange={e => setUsername(e.target.value)}
                  onFocus={() => setFocused("username")} onBlur={() => setFocused(null)}
                  autoFocus autoComplete="username" required />
              </div>

              {mode !== "login" && (
                <div style={{ display:"flex", flexDirection:"column", gap:6 }}>
                  <label style={labelStyle}>Email</label>
                  <input style={inputStyle("email")} type="email" placeholder="votre@email.fr"
                    value={email} onChange={e => setEmail(e.target.value)}
                    onFocus={() => setFocused("email")} onBlur={() => setFocused(null)}
                    autoComplete="email" required />
                </div>
              )}

              <div style={{ display:"flex", flexDirection:"column", gap:6 }}>
                <label style={labelStyle}>Mot de passe</label>
                <input style={inputStyle("password")} type="password"
                  placeholder={mode === "register" ? "Au moins 8 caractères" : "Votre mot de passe"}
                  value={password} onChange={e => setPassword(e.target.value)}
                  onFocus={() => setFocused("password")} onBlur={() => setFocused(null)}
                  autoComplete={mode === "register" ? "new-password" : "current-password"} required />
              </div>

              {mode !== "login" && (
                <div style={{ display:"flex", flexDirection:"column", gap:6 }}>
                  <label style={labelStyle}>Confirmer le mot de passe</label>
                  <input style={inputStyle("password2")} type="password" placeholder="Répétez le mot de passe"
                    value={password2} onChange={e => setPassword2(e.target.value)}
                    onFocus={() => setFocused("password2")} onBlur={() => setFocused(null)}
                    autoComplete="new-password" required />
                </div>
              )}

              {visibleError && (
                <div style={{
                  display:"flex", alignItems:"center", gap:8,
                  padding:"10px 14px",
                  background:"rgba(200,60,60,0.08)", border:"1px solid rgba(200,60,60,0.25)",
                  borderRadius:8, fontSize:13, color:"#e07878",
                }}>
                  <span>⚠</span><span>{visibleError}</span>
                </div>
              )}

              <button type="submit" className="prom-btn" disabled={loading} style={{
                marginTop:6, padding:"12px",
                background: loading ? "rgba(212,129,61,0.35)" : "linear-gradient(135deg,#d4813d,#bf7030)",
                color:"#fff", border:"none", borderRadius:9,
                fontSize:14, fontWeight:700, fontFamily:"'Segoe UI', 'Ubuntu', 'Cantarell', system-ui, sans-serif",
                letterSpacing:"0.04em", cursor: loading ? "not-allowed" : "pointer",
                transition:"all 0.2s ease",
                boxShadow:"0 4px 14px rgba(212,129,61,0.22)",
                display:"flex", alignItems:"center", justifyContent:"center", gap:8,
              }}>
                {loading ? (
                  <>
                    <span style={{ display:"inline-block", width:14, height:14, border:"2px solid rgba(255,255,255,0.3)", borderTop:"2px solid #fff", borderRadius:"50%", animation:"spin 0.8s linear infinite" }} />
                    Connexion…
                  </>
                ) : (
                  mode === "login" ? "Se connecter →" : mode === "setup-admin" ? "Créer l'administrateur →" : "Créer le compte →"
                )}
              </button>
            </form>

            {mode !== "setup-admin" && (
              <div style={{ marginTop:28, paddingTop:24, borderTop:"1px solid rgba(255,255,255,0.07)", display:"flex", alignItems:"center", justifyContent:"center", gap:8 }}>
                <span style={{ fontSize:13, color:"#52525c" }}>
                  {mode === "login" ? "Pas encore de compte ?" : "Déjà un compte ?"}
                </span>
                <button className="prom-switch" onClick={() => { setMode(m => m === "login" ? "register" : "login"); setLocalErr(null); }} type="button" style={{
                  background:"none", border:"none", color:"#d4813d",
                  fontSize:13, fontWeight:600, cursor:"pointer", padding:0,
                  transition:"color 0.2s ease",
                }}>
                  {mode === "login" ? "S'inscrire" : "Se connecter"}
                </button>
              </div>
            )}

          </div>

          {/* Liens légaux — bas droite */}
          <div style={{
            position:"absolute", bottom:18, right:24,
            display:"flex", flexDirection:"row", alignItems:"center", gap:18,
          }}>
            <a
              href="https://www.gnu.org/licenses/agpl-3.0.fr.html"
              target="_blank"
              rel="noopener noreferrer"
              style={{
                display:"flex", alignItems:"center", gap:6,
                fontSize:11, color:"rgba(255,255,255,0.28)", textDecoration:"none",
                letterSpacing:"0.04em", transition:"color 0.2s ease",
              }}
              onMouseEnter={e => (e.currentTarget.style.color = "#d4813d")}
              onMouseLeave={e => (e.currentTarget.style.color = "rgba(255,255,255,0.28)")}
            >
              {/* Shield icon */}
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
              </svg>
              Licence AGPL 3.0
            </a>
            <a
              href="https://github.com/Ktulu-Analog/promethee"
              target="_blank"
              rel="noopener noreferrer"
              style={{
                display:"flex", alignItems:"center", gap:6,
                fontSize:11, color:"rgba(255,255,255,0.28)", textDecoration:"none",
                letterSpacing:"0.04em", transition:"color 0.2s ease",
              }}
              onMouseEnter={e => (e.currentTarget.style.color = "#d4813d")}
              onMouseLeave={e => (e.currentTarget.style.color = "rgba(255,255,255,0.28)")}
            >
              {/* GitHub icon */}
              <svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor">
                <path d="M12 0C5.37 0 0 5.37 0 12c0 5.3 3.438 9.8 8.205 11.385.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61-.546-1.385-1.335-1.755-1.335-1.755-1.087-.744.084-.729.084-.729 1.205.084 1.838 1.236 1.838 1.236 1.07 1.835 2.809 1.305 3.495.998.108-.776.417-1.305.76-1.605-2.665-.3-5.466-1.332-5.466-5.93 0-1.31.465-2.38 1.235-3.22-.135-.303-.54-1.523.105-3.176 0 0 1.005-.322 3.3 1.23.96-.267 1.98-.399 3-.405 1.02.006 2.04.138 3 .405 2.28-1.552 3.285-1.23 3.285-1.23.645 1.653.24 2.873.12 3.176.765.84 1.23 1.91 1.23 3.22 0 4.61-2.805 5.625-5.475 5.92.42.36.81 1.096.81 2.22 0 1.606-.015 2.896-.015 3.286 0 .315.21.69.825.57C20.565 21.795 24 17.295 24 12c0-6.63-5.37-12-12-12z"/>
              </svg>
              GitHub — Prométhée
            </a>
            <a
              href="mailto:ktulu.analog@gmail.com"
              style={{
                display:"flex", alignItems:"center", gap:6,
                fontSize:11, color:"rgba(255,255,255,0.28)", textDecoration:"none",
                letterSpacing:"0.04em", transition:"color 0.2s ease",
              }}
              onMouseEnter={e => (e.currentTarget.style.color = "#d4813d")}
              onMouseLeave={e => (e.currentTarget.style.color = "rgba(255,255,255,0.28)")}
            >
              {/* Mail icon */}
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <rect x="2" y="4" width="20" height="16" rx="2"/>
                <path d="M2 7l10 7 10-7"/>
              </svg>
              ktulu.analog@gmail.com
            </a>
          </div>

        </div>

      </div>
    </>
  );
}
