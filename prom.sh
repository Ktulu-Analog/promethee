#!/usr/bin/env bash
# =============================================================================
#  prom.sh — Script utilitaire pour la gestion de la stack Prométhée AI
# =============================================================================
#  Usage : ./prom.sh <commande> [options]
#
#  Commandes disponibles :
#    build      Reconstruire un ou tous les containers
#    up         Démarrer la stack (ou un service)
#    down       Arrêter et supprimer les containers
#    restart    Redémarrer un service
#    logs       Afficher les logs d'un service
#    status     État de tous les containers
#    shell      Ouvrir un shell dans le container promethee
#    clean      Supprimer les images non utilisées
#    help       Afficher cette aide
# =============================================================================

set -euo pipefail

# ── Couleurs ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# ── Services connus ───────────────────────────────────────────────────────────
ALL_SERVICES="promethee qdrant garage garage-config garage-init"
BUILD_SERVICES="promethee garage-init"   # services avec un Dockerfile

# ── Helpers ───────────────────────────────────────────────────────────────────
info()    { printf "%b\n" "${BLUE}[INFO]${NC}  $*"; }
success() { printf "%b\n" "${GREEN}[OK]${NC}    $*"; }
warn()    { printf "%b\n" "${YELLOW}[WARN]${NC}  $*"; }
error()   { printf "%b\n" "${RED}[ERR]${NC}   $*" >&2; }
header()  { printf "%b\n" "\n${BOLD}${CYAN}▶ $*${NC}"; }

die() {
    error "$*"
    exit 1
}

require_service_arg() {
    # Vérifie qu'un nom de service a été passé et qu'il est valide
    local svc="${1:-}"
    [[ -z "$svc" ]] && die "Précisez un service. Services disponibles : $ALL_SERVICES"
    echo "$ALL_SERVICES" | grep -qw "$svc" || die "Service inconnu : '$svc'. Services disponibles : $ALL_SERVICES"
}

# ── Commande : help ───────────────────────────────────────────────────────────
cmd_help() {
    local B="$BOLD" C="$CYAN" N="$NC"
    printf "\n"
    printf "%b\n" "${B}prom.sh${N} — Utilitaire de gestion de la stack Prométhée AI"
    printf "\n"
    printf "%b\n" "${B}USAGE${N}"
    printf "  ./prom.sh <commande> [options]\n"
    printf "\n"
    printf "%b\n" "${B}COMMANDES${N}"
    printf "\n"
    printf "  %b\n" "${C}build${N} [service] [--no-cache] [--backend-only] [--frontend-only]"
    printf "      Reconstruit le(s) container(s).\n"
    printf "      Sans argument   → reconstruit toute la stack (promethee + garage-init)\n"
    printf "      [service]       → reconstruit uniquement ce service\n"
    printf "      --no-cache      → force la reconstruction sans cache Docker\n"
    printf "      --backend-only  → ne reconstruit que le stage Python (via --target app)\n"
    printf "      --frontend-only → force la recompilation du stage Node (invalide le cache npm)\n"
    printf "\n"
    printf "      Exemples :\n"
    printf "        ./prom.sh build                        # tout reconstruire (avec cache)\n"
    printf "        ./prom.sh build promethee              # seulement promethee (avec cache)\n"
    printf "        ./prom.sh build promethee --no-cache   # seulement promethee, sans cache\n"
    printf "        ./prom.sh build --no-cache             # tout, sans cache\n"
    printf "\n"
    printf "  %b\n" "${C}up${N} [service] [--build]"
    printf "      Démarre la stack complète ou un service spécifique.\n"
    printf "      --build → reconstruit avant de démarrer\n"
    printf "\n"
    printf "      Exemples :\n"
    printf "        ./prom.sh up                    # démarrer toute la stack\n"
    printf "        ./prom.sh up promethee          # démarrer uniquement promethee\n"
    printf "        ./prom.sh up promethee --build  # reconstruire et démarrer promethee\n"
    printf "\n"
    printf "  %b\n" "${C}down${N} [--volumes]"
    printf "      Arrête et supprime les containers.\n"
    printf "      --volumes → supprime aussi les volumes Docker (⚠️  perte de données !)\n"
    printf "\n"
    printf "  %b\n" "${C}restart${N} <service>"
    printf "      Redémarre un service sans rebuild.\n"
    printf "      Exemple : ./prom.sh restart promethee\n"
    printf "\n"
    printf "  %b\n" "${C}logs${N} [service] [-n <lignes>] [-f]"
    printf "      Affiche les logs. Sans service → logs de promethee.\n"
    printf "      -n <N>  → afficher les N dernières lignes (défaut : 100)\n"
    printf "      -f      → suivre en temps réel\n"
    printf "\n"
    printf "      Exemples :\n"
    printf "        ./prom.sh logs                  # 100 dernières lignes de promethee\n"
    printf "        ./prom.sh logs qdrant -n 50     # 50 dernières lignes de qdrant\n"
    printf "        ./prom.sh logs promethee -f     # suivi temps réel de promethee\n"
    printf "\n"
    printf "  %b\n" "${C}status${N}"
    printf "      Affiche l'état de tous les containers de la stack.\n"
    printf "\n"
    printf "  %b\n" "${C}shell${N} [service]"
    printf "      Ouvre un shell bash interactif dans le container (défaut : promethee).\n"
    printf "\n"
    printf "  %b\n" "${C}clean${N} [--all]"
    printf "      Supprime les images Docker orphelines (dangling).\n"
    printf "      --all → supprime aussi les images non utilisées par la stack.\n"
    printf "\n"
    printf "  %b\n" "${C}help${N}"
    printf "      Affiche ce message.\n"
    printf "\n"
    printf "%b\n" "${B}SERVICES DISPONIBLES${N}"
    printf "  promethee, qdrant, garage, garage-config, garage-init\n"
    printf "\n"
}

# ── Commande : build ──────────────────────────────────────────────────────────
cmd_build() {
    local service=""
    local no_cache=false
    local backend_only=false
    local frontend_only=false
    local extra_args=()

    # Parsing des arguments
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --no-cache)     no_cache=true ;;
            --backend-only) backend_only=true ;;
            --frontend-only) frontend_only=true ;;
            -*)             die "Option inconnue : $1" ;;
            *)
                [[ -z "$service" ]] || die "Un seul service à la fois. Usage : build [service] [options]"
                echo "$BUILD_SERVICES" | grep -qw "$1" \
                    || die "Service non buildable : '$1'. Services avec Dockerfile : $BUILD_SERVICES"
                service="$1"
                ;;
        esac
        shift
    done

    # Options contradictoires
    $backend_only && $frontend_only && die "--backend-only et --frontend-only sont incompatibles."
    ($backend_only || $frontend_only) && [[ -n "$service" && "$service" != "promethee" ]] \
        && die "--backend-only / --frontend-only ne s'appliquent qu'au service promethee."

    $no_cache && extra_args+=("--no-cache")

    # --frontend-only : on invalide le cache npm en passant un build-arg horodaté
    $frontend_only && extra_args+=("--build-arg" "CACHE_BUST=$(date +%s)")

    # --backend-only : on cible uniquement le stage Python (skip le stage Node)
    # Attention : --target n'est possible qu'en build direct, pas via compose.
    # On passe par docker build directement dans ce cas.
    if $backend_only; then
        header "Build backend-only (stage Python) de promethee"
        warn "Mode --backend-only : build direct via docker build (bypass compose)"
        docker build \
            "${extra_args[@]}" \
            --target app \
            -t promethee-docker-promethee:latest \
            .
        success "Image promethee reconstruite (stage Python uniquement)."
        warn "Pensez à relancer le container : ./prom.sh restart promethee"
        return
    fi

    if [[ -n "$service" ]]; then
        header "Build du service : ${service}"
        docker compose build "${extra_args[@]}" "$service"
        success "Service '$service' reconstruit."
    else
        header "Build de toute la stack"
        docker compose build "${extra_args[@]}"
        success "Stack reconstruite."
    fi
}

# ── Commande : up ─────────────────────────────────────────────────────────────
cmd_up() {
    local service=""
    local do_build=false

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --build) do_build=true ;;
            -*)      die "Option inconnue : $1" ;;
            *)
                [[ -z "$service" ]] || die "Un seul service à la fois."
                echo "$ALL_SERVICES" | grep -qw "$1" \
                    || die "Service inconnu : '$1'."
                service="$1"
                ;;
        esac
        shift
    done

    local compose_args=("-d")
    $do_build && compose_args+=("--build")

    if [[ -n "$service" ]]; then
        header "Démarrage du service : ${service}"
        docker compose up "${compose_args[@]}" "$service"
        success "Service '$service' démarré."
    else
        header "Démarrage de la stack complète"
        docker compose up "${compose_args[@]}"
        success "Stack démarrée."
        echo ""
        printf "%b\n" "  ${GREEN}→ Application${NC}  http://localhost:${SERVER_PORT:-8000}"
        printf "%b\n" "  ${GREEN}→ Qdrant UI${NC}    http://localhost:6333/dashboard"
        printf "%b\n" "  ${GREEN}→ Garage S3${NC}    http://localhost:3900"
    fi
}

# ── Commande : down ───────────────────────────────────────────────────────────
cmd_down() {
    local rm_volumes=false

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --volumes) rm_volumes=true ;;
            *) die "Option inconnue : $1" ;;
        esac
        shift
    done

    if $rm_volumes; then
        warn "⚠️  Suppression des volumes — toutes les données seront perdues !"
        read -r -p "Confirmer ? [y/N] " confirm
        [[ "${confirm,,}" == "y" ]] || { info "Annulé."; return; }
        header "Arrêt et suppression des containers + volumes"
        docker compose down -v
    else
        header "Arrêt et suppression des containers"
        docker compose down
    fi
    success "Stack arrêtée."
}

# ── Commande : restart ────────────────────────────────────────────────────────
cmd_restart() {
    require_service_arg "${1:-}"
    local service="$1"
    header "Redémarrage du service : ${service}"
    docker compose restart "$service"
    success "Service '$service' redémarré."
}

# ── Commande : logs ───────────────────────────────────────────────────────────
cmd_logs() {
    local service="promethee"
    local lines=100
    local follow=false

    while [[ $# -gt 0 ]]; do
        case "$1" in
            -f)     follow=true ;;
            -n)
                shift
                [[ "$1" =~ ^[0-9]+$ ]] || die "-n attend un nombre entier."
                lines="$1"
                ;;
            -*)     die "Option inconnue : $1" ;;
            *)
                echo "$ALL_SERVICES" | grep -qw "$1" \
                    || die "Service inconnu : '$1'."
                service="$1"
                ;;
        esac
        shift
    done

    header "Logs de ${service} (${lines} lignes)"
    if $follow; then
        docker compose logs -f --tail="$lines" "$service"
    else
        docker compose logs --tail="$lines" "$service"
    fi
}

# ── Commande : status ─────────────────────────────────────────────────────────
cmd_status() {
    header "État de la stack Prométhée"
    docker compose ps
}

# ── Commande : shell ──────────────────────────────────────────────────────────
cmd_shell() {
    local service="${1:-promethee}"
    echo "$ALL_SERVICES" | grep -qw "$service" || die "Service inconnu : '$service'."

    header "Shell dans le container : ${service}"
    # promethee tourne en utilisateur non-root ; on essaie bash puis sh
    docker compose exec "$service" bash 2>/dev/null \
        || docker compose exec "$service" sh
}

# ── Commande : clean ──────────────────────────────────────────────────────────
cmd_clean() {
    local clean_all=false
    [[ "${1:-}" == "--all" ]] && clean_all=true

    header "Nettoyage des images Docker"
    if $clean_all; then
        warn "Suppression de toutes les images non utilisées..."
        docker image prune -a -f
    else
        info "Suppression des images orphelines (dangling)..."
        docker image prune -f
    fi
    success "Nettoyage terminé."
}

# ── Point d'entrée ────────────────────────────────────────────────────────────
main() {
    # Vérifier que docker compose est disponible
    docker compose version &>/dev/null || die "docker compose n'est pas disponible."

    # Se positionner dans le répertoire du script (où se trouve docker-compose.yml)
    cd "$(dirname "$(realpath "$0")")"
    [[ -f "docker-compose.yml" ]] || die "docker-compose.yml introuvable dans $(pwd). Placez prom.sh à la racine du projet."

    local cmd="${1:-help}"
    shift || true

    case "$cmd" in
        build)   cmd_build   "$@" ;;
        up)      cmd_up      "$@" ;;
        down)    cmd_down    "$@" ;;
        restart) cmd_restart "$@" ;;
        logs)    cmd_logs    "$@" ;;
        status)  cmd_status  "$@" ;;
        shell)   cmd_shell   "$@" ;;
        clean)   cmd_clean   "$@" ;;
        help|-h|--help) cmd_help ;;
        *) error "Commande inconnue : '$cmd'"; cmd_help; exit 1 ;;
    esac
}

main "$@"
