#!/usr/bin/env python3
"""
logview.py — Lecteur de logs Prométhée AI
==========================================
Affiche les logs de manière lisible et colorée dans le terminal.

Usage :
  python logview.py                  # tous les logs, temps réel
  python logview.py -f               # follow (tail -f)
  python logview.py -n 100           # 100 dernières lignes
  python logview.py -l WARNING       # filtrer par niveau minimum
  python logview.py -m rag           # filtrer par module (ex: rag, ltm, session)
  python logview.py --tokens         # uniquement le log tokens/coûts
  python logview.py --today          # logs d'aujourd'hui seulement
  python logview.py --errors         # erreurs et warnings uniquement
  python logview.py --stats          # résumé statistique
"""

import re
import sys
import time
import argparse
from pathlib import Path
from datetime import datetime, date
from collections import defaultdict

# ── Chemins des fichiers de log ───────────────────────────────────────────────
_SCRIPT_DIR   = Path(__file__).resolve().parent
_LOG_MAIN     = _SCRIPT_DIR / "logs" / "promethee.log"
_LOG_TOKENS   = Path.home() / ".promethee" / "logs" / "tokens.log"

# ── Codes ANSI ────────────────────────────────────────────────────────────────
class C:
    RESET   = "\033[0m"
    BOLD    = "\033[1m"
    DIM     = "\033[2m"

    BLACK   = "\033[30m"
    RED     = "\033[31m"
    GREEN   = "\033[32m"
    YELLOW  = "\033[33m"
    BLUE    = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN    = "\033[36m"
    WHITE   = "\033[37m"

    BR_RED     = "\033[91m"
    BR_GREEN   = "\033[92m"
    BR_YELLOW  = "\033[93m"
    BR_BLUE    = "\033[94m"
    BR_MAGENTA = "\033[95m"
    BR_CYAN    = "\033[96m"
    BR_WHITE   = "\033[97m"

    BG_RED    = "\033[41m"
    BG_YELLOW = "\033[43m"

def _c(text, *codes):
    return "".join(codes) + str(text) + C.RESET

def _no_color(text, *codes):
    return str(text)

# Désactiver les couleurs si pas de TTY
if not sys.stdout.isatty():
    _c = _no_color

# ── Patterns de parsing ───────────────────────────────────────────────────────

# Format promethee.log : "2026-01-15 14:23:01 DEBUG    core.database — message"
_RE_MAIN = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+"
    r"(?P<level>[A-Z]+)\s+"
    r"(?P<module>\S+)\s+—\s+"
    r"(?P<msg>.+)$"
)

# Format tokens.log : "2026-01-15 14:23:01 [context] prompt=... completion=..."
_RE_TOKEN = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+(?P<msg>.+)$"
)

# Patterns dans les messages pour enrichissement
_RE_TOKEN_STATS = re.compile(
    r"\[(?P<ctx>[^\]]+)\]\s+prompt=(?P<prompt>\d+)\s+completion=(?P<comp>\d+)"
    r"\s+total=(?P<total>\d+)\s+calls=(?P<calls>\d+)\s+pct=(?P<pct>[\d.]+)%"
    r"\s+cost=(?P<cost>[\d.]+)€(?P<rest>.*)"
)
_RE_TRIM      = re.compile(r"\[trim_history\]")
_RE_TRUNCATE  = re.compile(r"\[truncate_tool_result\]")
_RE_COMPRESS  = re.compile(r"\[compress_tool_result\]")
_RE_TOOL_CALL = re.compile(r"\[tool[_ ]")
_RE_AGENT     = re.compile(r"agent_loop|stream_chat")
_RE_RAG       = re.compile(r"\[RAG\]|\[Albert\]")
_RE_LTM       = re.compile(r"\[LTM\]|\[long_term\]|promethee\.long_term")
_RE_SESSION   = re.compile(r"\[session_memory\]|promethee\.session")
_RE_STARTUP   = re.compile(r"\[Config\]|promethee\.startup")

# ── Niveaux de log ────────────────────────────────────────────────────────────
LEVEL_ORDER = {"DEBUG": 0, "INFO": 1, "WARNING": 2, "ERROR": 3, "CRITICAL": 4}

def _level_color(level: str) -> str:
    return {
        "DEBUG":    _c(f"{level:<8}", C.DIM, C.WHITE),
        "INFO":     _c(f"{level:<8}", C.BR_GREEN),
        "WARNING":  _c(f"{level:<8}", C.BR_YELLOW, C.BOLD),
        "ERROR":    _c(f"{level:<8}", C.BR_RED, C.BOLD),
        "CRITICAL": _c(f"{level:<8}", C.BG_RED, C.WHITE, C.BOLD),
    }.get(level, _c(f"{level:<8}", C.WHITE))


def _module_color(module: str) -> str:
    """Colore le nom du module selon sa catégorie."""
    m = module.lower()
    if "rag" in m or "albert" in m:        color = C.BR_CYAN
    elif "ltm" in m or "long_term" in m:   color = C.BR_MAGENTA
    elif "session" in m:                   color = C.BR_BLUE
    elif "llm" in m or "stream" in m:      color = C.YELLOW
    elif "tool" in m or "skill" in m:      color = C.BR_YELLOW
    elif "database" in m or "db" in m:     color = C.CYAN
    elif "startup" in m or "config" in m:  color = C.GREEN
    elif "ui" in m or "panel" in m:        color = C.DIM + C.WHITE
    else:                                  color = C.WHITE

    # Raccourcir les noms de modules longs
    short = module
    short = short.replace("promethee.", "")
    short = short.replace("core.", "")
    short = short.replace("ui.panels.chat.", "chat.")
    short = short.replace("ui.widgets.", "ui.")
    return _c(f"{short:<28}", color)


def _format_msg(msg: str, level: str) -> str:
    """Enrichit visuellement le message selon son contenu."""

    # Erreurs et warnings en priorité (avant les icônes de module)
    if level in ("ERROR", "CRITICAL"):
        return _c("💥  " + msg, C.BR_RED, C.BOLD)
    if level == "WARNING":
        return _c("⚠  " + msg, C.BR_YELLOW)

    # Tokens stats → affichage tabulaire
    m = _RE_TOKEN_STATS.search(msg)
    if m:
        ctx    = m.group("ctx")
        prompt = int(m.group("prompt"))
        comp   = int(m.group("comp"))
        total  = int(m.group("total"))
        calls  = int(m.group("calls"))
        pct    = float(m.group("pct"))
        cost   = float(m.group("cost"))
        rest   = m.group("rest")

        pct_color = C.BR_GREEN if pct < 50 else (C.BR_YELLOW if pct < 80 else C.BR_RED)
        cost_color = C.BR_GREEN if cost < 0.01 else (C.BR_YELLOW if cost < 0.05 else C.BR_RED)

        co2 = ""
        co2_m = re.search(r"co2=\[([0-9.]+)-([0-9.]+)\]kgCO2", rest)
        if co2_m:
            co2 = f"  🌱 CO₂ [{float(co2_m.group(1)):.4f}–{float(co2_m.group(2)):.4f}] kg"

        return (
            f"  {_c('◈ TOKENS', C.BOLD, C.CYAN)}  "
            f"{_c(ctx, C.BOLD)}  "
            f"{_c(f'prompt={prompt:,}', C.DIM)}  "
            f"{_c(f'compl={comp:,}', C.DIM)}  "
            f"{_c(f'total={total:,}', C.WHITE, C.BOLD)}  "
            f"calls={calls}  "
            f"ctx={_c(f'{pct:.1f}%', pct_color)}  "
            f"coût={_c(f'{cost:.6f}€', cost_color)}"
            f"{co2}"
        )

    # Trim historique
    if _RE_TRIM.search(msg):
        return _c("✂  " + msg, C.YELLOW)

    # Troncature résultat outil
    if _RE_TRUNCATE.search(msg):
        return _c("⤵  " + msg, C.BR_YELLOW)

    # Compression
    if _RE_COMPRESS.search(msg):
        return _c("⟳  " + msg, C.BR_MAGENTA)

    # RAG / Albert
    if _RE_RAG.search(msg):
        return _c("🔍  " + msg, C.BR_CYAN)

    # LTM
    if _RE_LTM.search(msg):
        return _c("🧠  " + msg, C.BR_MAGENTA)

    # Démarrage / config
    if _RE_STARTUP.search(msg):
        return _c("⚙  " + msg, C.GREEN)

    return msg


# ── Parsers de lignes ─────────────────────────────────────────────────────────

def _parse_main_line(line: str) -> dict | None:
    m = _RE_MAIN.match(line.rstrip())
    if not m:
        return None
    return {
        "ts":     m.group("ts"),
        "level":  m.group("level").strip(),
        "module": m.group("module"),
        "msg":    m.group("msg"),
        "raw":    line,
        "source": "main",
    }

def _parse_token_line(line: str) -> dict | None:
    m = _RE_TOKEN.match(line.rstrip())
    if not m:
        return None
    # Déduire le niveau depuis les brackets
    msg = m.group("msg")
    level = "INFO"
    if re.search(r"error|erreur|échec", msg, re.I):
        level = "ERROR"
    elif re.search(r"warn|attention", msg, re.I):
        level = "WARNING"
    elif re.search(r"prompt=\d+", msg):
        level = "DEBUG"
    return {
        "ts":     m.group("ts"),
        "level":  level,
        "module": "promethee.tokens",
        "msg":    msg,
        "raw":    line,
        "source": "tokens",
    }


# ── Formatage final d'une entrée ──────────────────────────────────────────────

def _render(entry: dict, show_source: bool = False) -> list[str]:
    ts     = _c(entry["ts"], C.DIM)
    level  = _level_color(entry["level"])
    module = _module_color(entry["module"])
    msg    = _format_msg(entry["msg"], entry["level"])

    src = ""
    if show_source:
        label = "TOK" if entry["source"] == "tokens" else "APP"
        src = _c(f"[{label}] ", C.DIM)

    lines = [f"{ts}  {level}  {module}  {src}{msg}"]

    # Continuer les lignes de traceback (indentées)
    return lines


def _render_separator(label: str = "") -> str:
    w = 100
    if label:
        pad = (w - len(label) - 2) // 2
        return _c("─" * pad + f" {label} " + "─" * pad, C.DIM)
    return _c("─" * w, C.DIM)


# ── Filtres ───────────────────────────────────────────────────────────────────

def _matches(entry: dict, args) -> bool:
    # Niveau minimum
    if args.level:
        min_lvl = LEVEL_ORDER.get(args.level.upper(), 0)
        entry_lvl = LEVEL_ORDER.get(entry["level"], 0)
        if entry_lvl < min_lvl:
            return False

    # Filtre module
    if args.module:
        if args.module.lower() not in entry["module"].lower() and \
           args.module.lower() not in entry["msg"].lower():
            return False

    # Filtre today
    if args.today:
        today_str = date.today().isoformat()
        if not entry["ts"].startswith(today_str):
            return False

    # Filtre errors only
    if args.errors:
        if entry["level"] not in ("WARNING", "ERROR", "CRITICAL"):
            return False

    # Filtre grep
    if args.grep:
        combined = entry["module"] + " " + entry["msg"]
        if args.grep.lower() not in combined.lower():
            return False

    return True


# ── Lecture fichiers ──────────────────────────────────────────────────────────

def _read_file(path: Path, parser, n: int | None = None) -> list[dict]:
    """Lit un fichier log (+ archives .1 .2 ...) et retourne les entrées parsées."""
    if not path.exists():
        return []

    # Collecter les fichiers (principal + rotations)
    files = [path]
    for i in range(1, 6):
        arc = path.with_suffix(f".log.{i}") if path.suffix == ".log" else Path(str(path) + f".{i}")
        if not arc.exists():
            # Essayer l'autre forme
            arc2 = Path(str(path) + f".{i}")
            if arc2.exists():
                files.append(arc2)
        else:
            files.append(arc)

    entries = []
    pending_raw = []  # lignes de traceback

    def _flush_pending():
        if pending_raw and entries:
            entries[-1]["traceback"] = "\n".join(pending_raw)
        pending_raw.clear()

    # Lire en ordre chronologique (archives d'abord, puis le fichier actuel)
    for f in reversed(files):
        try:
            with open(f, encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    e = parser(line)
                    if e:
                        _flush_pending()
                        entries.append(e)
                    elif line.startswith((" ", "\t")) and entries:
                        # Ligne de continuation (traceback)
                        pending_raw.append(line.rstrip())
        except OSError:
            pass
    _flush_pending()

    if n is not None:
        entries = entries[-n:]
    return entries


# ── Stats ─────────────────────────────────────────────────────────────────────

def _print_stats(main_entries: list[dict], token_entries: list[dict]):
    all_entries = main_entries + token_entries

    print()
    print(_c("═" * 80, C.BOLD))
    print(_c("  STATISTIQUES DES LOGS PROMÉTHÉE", C.BOLD, C.BR_WHITE))
    print(_c("═" * 80, C.BOLD))

    # Distribution par niveau
    by_level = defaultdict(int)
    for e in all_entries:
        by_level[e["level"]] += 1

    print(f"\n{_c('Distribution par niveau :', C.BOLD)}")
    for lvl in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
        n = by_level.get(lvl, 0)
        if n == 0:
            continue
        bar = "█" * min(n // max(max(by_level.values()) // 30, 1), 40)
        print(f"  {_level_color(lvl)}  {_c(bar, C.CYAN)}  {n}")

    # Distribution par module
    by_module = defaultdict(int)
    for e in main_entries:
        mod = e["module"].replace("promethee.", "").replace("core.", "")
        by_module[mod] += 1

    print(f"\n{_c('Top 10 modules les plus actifs :', C.BOLD)}")
    sorted_mods = sorted(by_module.items(), key=lambda x: -x[1])[:10]
    for mod, n in sorted_mods:
        print(f"  {_c(f'{mod:<35}', C.CYAN)}  {n} lignes")

    # Stats tokens
    total_cost = 0.0
    total_tokens = 0
    token_calls = 0
    for e in token_entries:
        m = _RE_TOKEN_STATS.search(e["msg"])
        if m:
            total_cost   += float(m.group("cost"))
            total_tokens += int(m.group("total"))
            token_calls  += int(m.group("calls"))

    if token_calls > 0:
        print(f"\n{_c('Statistiques tokens/coûts :', C.BOLD)}")
        print(f"  Appels LLM trackés : {_c(token_calls, C.BR_WHITE, C.BOLD)}")
        print(f"  Tokens totaux      : {_c(f'{total_tokens:,}', C.BR_WHITE, C.BOLD)}")
        print(f"  Coût total         : {_c(f'{total_cost:.4f} €', C.BR_YELLOW, C.BOLD)}")
        print(f"  Coût moyen/appel   : {_c(f'{total_cost/token_calls:.6f} €', C.DIM)}")

    # Plage temporelle
    if all_entries:
        first_ts = all_entries[0]["ts"]
        last_ts  = all_entries[-1]["ts"]
        print(f"\n{_c('Plage temporelle :', C.BOLD)}")
        print(f"  Premier log : {_c(first_ts, C.DIM)}")
        print(f"  Dernier log : {_c(last_ts, C.GREEN)}")
        print(f"  Total lignes: {_c(len(all_entries), C.BR_WHITE, C.BOLD)}")

    print()


# ── Affichage interactif ──────────────────────────────────────────────────────

def _print_entry(entry: dict, show_source: bool = False):
    for line in _render(entry, show_source):
        print(line)
    # Afficher le traceback si présent
    if "traceback" in entry:
        for tb_line in entry["traceback"].split("\n"):
            print(_c("  │ " + tb_line, C.DIM, C.RED))


def _print_entries(entries: list[dict], show_source: bool = False):
    if not entries:
        print(_c("  (aucune entrée)", C.DIM))
        return
    prev_date = None
    for entry in entries:
        cur_date = entry["ts"][:10]
        if cur_date != prev_date:
            print()
            print(_render_separator(cur_date))
            prev_date = cur_date
        _print_entry(entry, show_source)


# ── Follow mode ───────────────────────────────────────────────────────────────

def _follow(paths_parsers: list[tuple[Path, callable]], args):
    """tail -f sur plusieurs fichiers simultanément."""
    handles = {}
    for path, parser in paths_parsers:
        if path.exists():
            try:
                fh = open(path, encoding="utf-8", errors="replace")
                fh.seek(0, 2)  # aller en fin de fichier
                handles[path] = (fh, parser)
            except OSError:
                pass

    if not handles:
        print(_c("Aucun fichier de log trouvé. Lance l'application d'abord.", C.BR_YELLOW))
        return

    print(_c(f"📡 Surveillance de {len(handles)} fichier(s) — Ctrl+C pour quitter", C.GREEN, C.BOLD))
    print(_render_separator())

    try:
        while True:
            found = False
            for path, (fh, parser) in handles.items():
                while True:
                    line = fh.readline()
                    if not line:
                        break
                    e = parser(line)
                    if e and _matches(e, args):
                        show_src = len(handles) > 1
                        _print_entry(e, show_src)
                        found = True
            if not found:
                time.sleep(0.2)
    except KeyboardInterrupt:
        print(_c("\n\n  Arrêt du suivi.", C.DIM))
    finally:
        for _, (fh, _) in handles.items():
            fh.close()


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(
        description="Lecteur de logs Prométhée AI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("-f", "--follow",  action="store_true", help="Suivre en temps réel (tail -f)")
    p.add_argument("-n", "--lines",   type=int, default=None, metavar="N", help="Afficher les N dernières lignes")
    p.add_argument("-l", "--level",   default=None, metavar="LEVEL", help="Niveau minimum : DEBUG|INFO|WARNING|ERROR")
    p.add_argument("-m", "--module",  default=None, metavar="MODULE", help="Filtrer par module (rag, ltm, session, tool…)")
    p.add_argument("-g", "--grep",    default=None, metavar="PATTERN", help="Filtrer par texte libre dans module+message")
    p.add_argument("--tokens",        action="store_true", help="Uniquement le log tokens/coûts")
    p.add_argument("--app",           action="store_true", help="Uniquement le log applicatif")
    p.add_argument("--today",         action="store_true", help="Logs du jour seulement")
    p.add_argument("--errors",        action="store_true", help="Warnings et erreurs uniquement")
    p.add_argument("--stats",         action="store_true", help="Afficher un résumé statistique")
    p.add_argument("--no-color",      action="store_true", help="Désactiver les couleurs")
    args = p.parse_args()

    # Désactiver les couleurs
    if args.no_color:
        global _c
        _c = _no_color

    # Vérifier les fichiers disponibles
    files_info = []
    if not args.tokens:
        if not _LOG_MAIN.exists():
            print(_c(f"⚠  Fichier introuvable : {_LOG_MAIN}", C.BR_YELLOW))
        else:
            files_info.append((_LOG_MAIN, _parse_main_line, "applicatif"))

    if not args.app:
        if not _LOG_TOKENS.exists():
            print(_c(f"ℹ  Pas encore de log tokens : {_LOG_TOKENS}", C.DIM))
        else:
            files_info.append((_LOG_TOKENS, _parse_token_line, "tokens"))

    if not files_info:
        print(_c("Aucun fichier de log disponible.", C.BR_RED))
        sys.exit(1)

    # Mode follow
    if args.follow:
        _follow([(f[0], f[1]) for f in files_info], args)
        return

    # Mode stats
    if args.stats:
        main_e  = _read_file(_LOG_MAIN, _parse_main_line) if not args.tokens else []
        token_e = _read_file(_LOG_TOKENS, _parse_token_line) if not args.app else []
        _print_stats(main_e, token_e)
        return

    # Lecture normale
    show_source = len(files_info) > 1

    # Calculer N par fichier
    n_per_file = args.lines  # None = tout lire

    all_entries = []
    for path, parser, _ in files_info:
        entries = _read_file(path, parser, n=n_per_file)
        all_entries.extend(entries)

    # Trier chronologiquement (les deux fichiers peuvent être entremêlés)
    all_entries.sort(key=lambda e: e["ts"])

    # Filtrer
    filtered = [e for e in all_entries if _matches(e, args)]

    # Appliquer -n après fusion et tri
    if args.lines:
        filtered = filtered[-args.lines:]

    # Afficher
    if not filtered:
        print(_c("  Aucune entrée correspondant aux filtres.", C.DIM))
    else:
        _print_entries(filtered, show_source)
        print()
        total_w = len(filtered)
        total_e = sum(1 for e in filtered if e["level"] == "ERROR")
        total_warn = sum(1 for e in filtered if e["level"] == "WARNING")
        summary_parts = [_c(f"{total_w} lignes affichées", C.DIM)]
        if total_e:
            summary_parts.append(_c(f"{total_e} erreur(s)", C.BR_RED))
        if total_warn:
            summary_parts.append(_c(f"{total_warn} warning(s)", C.BR_YELLOW))
        print("  " + "  ·  ".join(summary_parts))
        print()


if __name__ == "__main__":
    main()
