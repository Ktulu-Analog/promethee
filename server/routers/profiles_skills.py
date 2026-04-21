# ============================================================================
# Prométhée — Assistant IA avancé
# ============================================================================
# Auteur  : Pierre COUGET ktulu.analog@gmail.com
# Licence : GNU Affero General Public License v3.0 (AGPL-3.0)
#           https://www.gnu.org/licenses/agpl-3.0.html
# Année   : 2026
# ----------------------------------------------------------------------------
# Ce fichier fait partie du projet Prométhée.
# Vous pouvez le redistribuer et/ou le modifier selon les termes de la
# licence AGPL-3.0 publiée par la Free Software Foundation.
# ============================================================================

"""
routers/profiles_skills.py — Gestion des profils système et des skills

Portage de :
  - ui/widgets/profile_manager.py  (ProfileManager)
  - ui/widgets/profile_selector.py (ProfileEditorDialog, ProfileManagerDialog)
  - ui/widgets/skill_editor.py     (SkillManagerDialog, SkillEditorDialog)
  - core/skill_manager.py          (SkillManager)

Routes Profils :
    GET    /profiles                   Liste tous les profils
    POST   /profiles                   Crée un nouveau profil
    GET    /profiles/{name}            Récupère un profil (prompt + meta)
    PATCH  /profiles/{name}            Met à jour un profil existant
    DELETE /profiles/{name}            Supprime un profil

Routes Skills :
    GET    /skills                     Liste les skills (métadonnées)
    POST   /skills                     Crée un nouveau skill
    GET    /skills/{slug}              Récupère le contenu complet d'un skill
    PUT    /skills/{slug}              Met à jour le contenu d'un skill
    DELETE /skills/{slug}              Supprime un skill

Stockage :
    Profils → prompts.yml (à côté de .env, dans la racine du projet)
    Skills  → ~/.promethee/skills/<slug>.md  (identique à la version Qt)
"""

import re
import logging
from pathlib import Path
from typing import Optional, List

import yaml
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from server.deps import require_auth, require_admin

_log = logging.getLogger(__name__)
router = APIRouter()

_ROOT = Path(__file__).resolve().parent.parent.parent
_PROMPTS_FILE = _ROOT / "prompts.yml"
_SKILLS_DIR = _ROOT / "skills"


# ═══════════════════════════════════════════════════════════════════════════
# Helpers YAML (style bloc pour les prompts multilignes)
# ═══════════════════════════════════════════════════════════════════════════

class _BlockStr(str):
    pass


def _block_representer(dumper: yaml.Dumper, data: "_BlockStr") -> yaml.ScalarNode:
    # Style "|-" (bloc avec strip final) pour les chaînes multilignes :
    # évite les lignes vides finales parasites lors des re-sérialisations.
    style = "|-" if "\n" in data else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style=style)


yaml.add_representer(_BlockStr, _block_representer)


def _to_block(obj):
    if isinstance(obj, dict):
        return {k: _to_block(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_to_block(i) for i in obj]
    if isinstance(obj, str):
        return _BlockStr(obj)
    return obj


# ═══════════════════════════════════════════════════════════════════════════
# ProfileStore — équivalent de ProfileManager
# ═══════════════════════════════════════════════════════════════════════════

class _ProfileStore:
    def __init__(self, path: Path = _PROMPTS_FILE):
        self._path = path
        self._data: dict = {}
        self._load()

    def _load(self):
        if not self._path.exists():
            self._data = {"prompts": {"Aucun rôle": {"prompt": ""}}}
            return
        try:
            with open(self._path, encoding="utf-8") as f:
                raw = yaml.safe_load(f) or {}
            self._data = raw
            # Garantir "Aucun rôle"
            prompts = self._data.setdefault("prompts", {})
            if "Aucun rôle" not in prompts:
                prompts["Aucun rôle"] = {"prompt": ""}
            # Normaliser les prompts : supprimer les sauts de ligne excessifs
            # (>2 consecutifs) qui apparaissent quand un prompt YAML en style
            # flow (avec \n litteral) est relu puis re-serialise en style bloc.
            import re as _re
            for cfg in prompts.values():
                if isinstance(cfg, dict) and isinstance(cfg.get("prompt"), str):
                    cfg["prompt"] = _re.sub(r"\n{3,}", "\n\n", cfg["prompt"]).strip()
        except Exception as exc:
            _log.error("[profiles] chargement echoue : %s", exc)
            self._data = {"prompts": {"Aucun rôle": {"prompt": ""}}}

    def _save(self):
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._path, "w", encoding="utf-8") as f:
                yaml.dump(
                    _to_block(self._data),
                    f,
                    allow_unicode=True,
                    default_flow_style=False,
                    sort_keys=False,
                    width=120,
                )
        except Exception as exc:
            _log.error("[profiles] sauvegarde échouée : %s", exc)

    @property
    def _prompts(self) -> dict:
        return self._data.setdefault("prompts", {})

    def list(self) -> list[dict]:
        result = []
        for name, cfg in self._prompts.items():
            tools_cfg  = cfg.get("tools",  {}) or {}
            skills_cfg = cfg.get("skills", {}) or {}
            result.append({
                "name": name,
                "prompt": cfg.get("prompt", ""),
                "tool_families": {
                    "enabled": list(tools_cfg.get("enabled", [])),
                    "disabled": list(tools_cfg.get("disabled", [])),
                },
                "pinned_skills": list(skills_cfg.get("pinned", [])),
            })
        return result

    def get(self, name: str) -> dict | None:
        cfg = self._prompts.get(name)
        if cfg is None:
            return None
        # Garder le `or {}` : YAML peut sérialiser une clé absente ou nulle
        # comme None (ex : `tools: null`), ce qui ferait crasher .get() ci-dessous.
        tools_cfg  = cfg.get("tools",  {}) or {}
        skills_cfg = cfg.get("skills", {}) or {}
        return {
            "name": name,
            "prompt": cfg.get("prompt", ""),
            "tool_families": {
                "enabled": list(tools_cfg.get("enabled", [])),
                "disabled": list(tools_cfg.get("disabled", [])),
            },
            "pinned_skills": list(skills_cfg.get("pinned", [])),
        }

    def create(self, name: str, prompt: str, tool_families: dict, pinned_skills: list):
        if name in self._prompts:
            raise ValueError(f"Le profil '{name}' existe déjà.")
        self._prompts[name] = self._build_entry(prompt, tool_families, pinned_skills)
        self._save()

    def update(self, name: str, prompt: str, tool_families: dict, pinned_skills: list):
        if name not in self._prompts:
            raise KeyError(f"Profil '{name}' introuvable.")
        self._prompts[name] = self._build_entry(prompt, tool_families, pinned_skills)
        self._save()

    def delete(self, name: str):
        if name == "Aucun rôle":
            raise ValueError("Impossible de supprimer le profil 'Aucun rôle'.")
        if name not in self._prompts:
            raise KeyError(f"Profil '{name}' introuvable.")
        del self._prompts[name]
        self._save()

    @staticmethod
    def _build_entry(prompt: str, tool_families: dict, pinned_skills: list) -> dict:
        entry: dict = {"prompt": prompt}
        enabled = tool_families.get("enabled", [])
        disabled = tool_families.get("disabled", [])
        if enabled or disabled:
            entry["tools"] = {}
            if enabled:
                entry["tools"]["enabled"] = list(enabled)
            if disabled:
                entry["tools"]["disabled"] = list(disabled)
        if pinned_skills:
            entry["skills"] = {"pinned": list(pinned_skills)}
        return entry


_profile_store = _ProfileStore()


# ═══════════════════════════════════════════════════════════════════════════
# PersonalProfileStore — profils personnels par utilisateur
# ═══════════════════════════════════════════════════════════════════════════

_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"


class _PersonalProfileStore:
    """Profils personnels stockés par utilisateur dans data/{user_id}/personal_profiles.yml"""

    def _path(self, user_id: str) -> Path:
        user_dir = _DATA_DIR / user_id
        user_dir.mkdir(parents=True, exist_ok=True)
        return user_dir / "personal_profiles.yml"

    def _load(self, user_id: str) -> dict:
        path = self._path(user_id)
        if not path.exists():
            return {"profiles": {}}
        try:
            with open(path, encoding="utf-8") as f:
                raw = yaml.safe_load(f) or {}
            return raw if "profiles" in raw else {"profiles": raw}
        except Exception as exc:
            _log.error("[personal_profiles] chargement échoué pour %s : %s", user_id, exc)
            return {"profiles": {}}

    def _save(self, user_id: str, data: dict):
        path = self._path(user_id)
        try:
            with open(path, "w", encoding="utf-8") as f:
                yaml.dump(
                    _to_block(data),
                    f,
                    allow_unicode=True,
                    default_flow_style=False,
                    sort_keys=False,
                    width=120,
                )
        except Exception as exc:
            _log.error("[personal_profiles] sauvegarde échouée pour %s : %s", user_id, exc)

    def list(self, user_id: str) -> list[dict]:
        data = self._load(user_id)
        result = []
        for name, cfg in data.get("profiles", {}).items():
            tools_cfg  = cfg.get("tools",  {}) or {}
            skills_cfg = cfg.get("skills", {}) or {}
            result.append({
                "name": name,
                "prompt": cfg.get("prompt", ""),
                "tool_families": {
                    "enabled": list(tools_cfg.get("enabled", [])),
                    "disabled": list(tools_cfg.get("disabled", [])),
                },
                "pinned_skills": list(skills_cfg.get("pinned", [])),
                "is_personal": True,
            })
        return result

    def get(self, user_id: str, name: str) -> dict | None:
        data = self._load(user_id)
        cfg = data.get("profiles", {}).get(name)
        if cfg is None:
            return None
        tools_cfg  = cfg.get("tools",  {}) or {}
        skills_cfg = cfg.get("skills", {}) or {}
        return {
            "name": name,
            "prompt": cfg.get("prompt", ""),
            "tool_families": {
                "enabled": list(tools_cfg.get("enabled", [])),
                "disabled": list(tools_cfg.get("disabled", [])),
            },
            "pinned_skills": list(skills_cfg.get("pinned", [])),
            "is_personal": True,
        }

    def create(self, user_id: str, name: str, prompt: str, tool_families: dict, pinned_skills: list):
        data = self._load(user_id)
        profiles = data.setdefault("profiles", {})
        if name in profiles:
            raise ValueError(f"Le profil personnel '{name}' existe déjà.")
        profiles[name] = _ProfileStore._build_entry(prompt, tool_families, pinned_skills)
        self._save(user_id, data)

    def update(self, user_id: str, name: str, prompt: str, tool_families: dict, pinned_skills: list):
        data = self._load(user_id)
        profiles = data.get("profiles", {})
        if name not in profiles:
            raise KeyError(f"Profil personnel '{name}' introuvable.")
        profiles[name] = _ProfileStore._build_entry(prompt, tool_families, pinned_skills)
        self._save(user_id, data)

    def delete(self, user_id: str, name: str):
        data = self._load(user_id)
        profiles = data.get("profiles", {})
        if name not in profiles:
            raise KeyError(f"Profil personnel '{name}' introuvable.")
        del profiles[name]
        self._save(user_id, data)


_personal_profile_store = _PersonalProfileStore()


# ═══════════════════════════════════════════════════════════════════════════
# SkillStore — équivalent de SkillManager
# ═══════════════════════════════════════════════════════════════════════════

_SLUG_RE = re.compile(r"^[a-zA-Z0-9_\-]+$")
_FM_RE = re.compile(r"^---\s*\n([\s\S]*?)\n---\s*\n", re.MULTILINE)


class _SkillStore:
    def __init__(self, skills_dir: Path = _SKILLS_DIR):
        self._dir = skills_dir
        self._dir.mkdir(parents=True, exist_ok=True)

    def list(self) -> list[dict]:
        skills = []
        for path in sorted(self._dir.glob("*.md")):
            slug = path.stem
            info = self._parse_meta(path.read_text(encoding="utf-8"))
            info["slug"] = slug
            info["size"] = path.stat().st_size
            skills.append(info)
        return skills

    def exists(self, slug: str) -> bool:
        return (self._dir / f"{slug}.md").exists()

    def read(self, slug: str) -> str:
        path = self._dir / f"{slug}.md"
        if not path.exists():
            raise FileNotFoundError(f"Skill '{slug}' introuvable.")
        return path.read_text(encoding="utf-8")

    def save(self, slug: str, content: str):
        if not _SLUG_RE.match(slug):
            raise ValueError(f"Slug invalide : '{slug}'.")
        path = self._dir / f"{slug}.md"
        path.write_text(content, encoding="utf-8")

    def delete(self, slug: str):
        path = self._dir / f"{slug}.md"
        if not path.exists():
            raise FileNotFoundError(f"Skill '{slug}' introuvable.")
        path.unlink()

    @staticmethod
    def _parse_meta(content: str) -> dict:
        meta = {"name": "", "description": "", "tags": [], "version": "1.0"}
        match = _FM_RE.match(content)
        if not match:
            return meta
        try:
            fm = yaml.safe_load(match.group(1)) or {}
            meta["name"] = str(fm.get("name", ""))
            meta["description"] = str(fm.get("description", ""))
            tags = fm.get("tags", [])
            meta["tags"] = tags if isinstance(tags, list) else []
            meta["version"] = str(fm.get("version", "1.0"))
        except Exception:
            pass
        return meta


_skill_store = _SkillStore()


# ═══════════════════════════════════════════════════════════════════════════
# Schémas Pydantic
# ═══════════════════════════════════════════════════════════════════════════

class ToolFamilies(BaseModel):
    enabled: List[str] = []
    disabled: List[str] = []


class ProfileCreate(BaseModel):
    name: str
    prompt: str = ""
    tool_families: ToolFamilies = ToolFamilies()
    pinned_skills: List[str] = []


class ProfilePatch(BaseModel):
    prompt: Optional[str] = None
    tool_families: Optional[ToolFamilies] = None
    pinned_skills: Optional[List[str]] = None


class ProfileOut(BaseModel):
    name: str
    prompt: str
    tool_families: ToolFamilies
    pinned_skills: List[str]
    is_personal: bool = False


class SkillOut(BaseModel):
    slug: str
    name: str
    description: str
    tags: List[str]
    version: str
    size: int


class SkillCreate(BaseModel):
    slug: str
    content: str


class SkillContentOut(BaseModel):
    slug: str
    content: str


# ═══════════════════════════════════════════════════════════════════════════
# Routes — Profils
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/profiles", response_model=list[ProfileOut])
async def list_profiles(_ = Depends(require_auth)):
    """Liste tous les profils système."""
    _profile_store._load()  # Relire depuis le disque pour rester à jour
    return [ProfileOut(**p) for p in _profile_store.list()]


@router.post("/profiles", response_model=ProfileOut, status_code=status.HTTP_201_CREATED)
async def create_profile(payload: ProfileCreate, _ = Depends(require_admin)):
    """Crée un nouveau profil système."""
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Le nom du profil est requis.")
    if name == "Aucun rôle":
        raise HTTPException(status_code=422, detail="Ce nom est réservé.")
    try:
        _profile_store.create(
            name,
            payload.prompt,
            payload.tool_families.model_dump(),
            payload.pinned_skills,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return ProfileOut(**_profile_store.get(name))


@router.get("/profiles/{name}", response_model=ProfileOut)
async def get_profile(name: str, _ = Depends(require_auth)):
    """Récupère un profil par son nom."""
    profile = _profile_store.get(name)
    if not profile:
        raise HTTPException(status_code=404, detail=f"Profil '{name}' introuvable.")
    return ProfileOut(**profile)


@router.patch("/profiles/{name}", response_model=ProfileOut)
async def update_profile(name: str, payload: ProfilePatch, _ = Depends(require_admin)):
    """Met à jour un profil existant."""
    existing = _profile_store.get(name)
    if not existing:
        raise HTTPException(status_code=404, detail=f"Profil '{name}' introuvable.")

    new_prompt = payload.prompt if payload.prompt is not None else existing["prompt"]
    new_tf = payload.tool_families.model_dump() if payload.tool_families is not None else existing["tool_families"]
    new_ps = payload.pinned_skills if payload.pinned_skills is not None else existing["pinned_skills"]

    try:
        _profile_store.update(name, new_prompt, new_tf, new_ps)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return ProfileOut(**_profile_store.get(name))


@router.get("/profiles/{name}/system_prompt")
async def get_profile_system_prompt(name: str, _ = Depends(require_auth)):
    """
    Retourne le prompt système complet pour un profil : prompt du profil
    + bloc des skills épinglés injecté à la suite.

    Ce endpoint est appelé par ws_chat lors de l'assemblage du contexte
    avant chaque appel LLM. Le client n'a qu'à transmettre ``profile_name``
    dans le ChatPayload — l'assemblage est entièrement côté serveur.

    Réponse :
        { "system_prompt": str }   — prêt à passer à agent_loop()
    """
    _profile_store._load()
    profile = _profile_store.get(name)
    if not profile:
        raise HTTPException(status_code=404, detail=f"Profil '{name}' introuvable.")

    system_prompt = _build_system_prompt(profile)
    return {"system_prompt": system_prompt}


def _build_system_prompt(profile: dict) -> str:
    """
    Assemble le prompt système final d'un profil.

    Ordre des sections
    ──────────────────
    1. Prompt de base du profil  — identité, ton, règles métier.
    2. Directive d'usage des outils  — injectée si le profil a des outils actifs,
       pour ancrer le réflexe « appeler un outil plutôt que répondre de mémoire ».
    3. Skills épinglés  — guides procéduraux placés en dernier pour être les plus
       proches du message utilisateur dans la fenêtre de contexte, ce qui renforce
       leur prise en compte par le LLM.

    Cette fonction est aussi appelée directement par ws_chat pour éviter
    un aller-retour HTTP supplémentaire quand le profil est déjà chargé.

    Parameters
    ----------
    profile : dict
        Entrée retournée par _ProfileStore.get() :
        { name, prompt, tool_families, pinned_skills }

    Returns
    -------
    str
        Prompt système complet, prêt à passer à agent_loop().
    """
    from core.skill_manager import get_skill_manager

    parts: list[str] = []

    # 1. Prompt de base
    base_prompt = (profile.get("prompt") or "").strip()
    if base_prompt:
        parts.append(base_prompt)

    # 2. Directive d'usage des outils
    # Injectée si au moins une famille d'outils est active, afin de guider
    # le LLM vers l'appel d'outils plutôt que vers une réponse de mémoire —
    # ce qui corrige le comportement aléatoire observé avec tool_choice="auto".
    # Garder le `or {}` : tool_families peut être None si tools: null dans le YAML.
    tool_families = profile.get("tool_families") or {}
    has_enabled_tools = bool(tool_families.get("enabled")) or not tool_families.get("disabled")
    if has_enabled_tools:
        parts.append(
            "## Politique d'usage des outils\n"
            "- Pour toute question nécessitant des données réelles, récentes ou externes, "
            "utilise TOUJOURS un outil plutôt que de répondre de mémoire.\n"
            "- Si un outil peut fournir une réponse plus fiable ou vérifiable, appelle-le.\n"
            "- Ne réponds directement que si la question est clairement factuelle et stable "
            "(définitions, raisonnements, reformulations)."
        )

    # 3. Skills épinglés — en dernier pour proximité maximale avec le message user
    pinned_skills: list[str] = profile.get("pinned_skills") or []
    if pinned_skills:
        sm = get_skill_manager()
        skills_block = sm.build_pinned_block(pinned_skills)
        if skills_block:
            parts.append(skills_block)

    return "\n\n".join(parts)


# Export de _build_system_prompt pour ws_chat (évite l'aller-retour HTTP)
build_system_prompt = _build_system_prompt


@router.delete("/profiles/{name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_profile(name: str, _ = Depends(require_admin)):
    """Supprime un profil (sauf 'Aucun rôle')."""
    try:
        _profile_store.delete(name)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


# ═══════════════════════════════════════════════════════════════════════════
# Routes — Profils personnels (par utilisateur)
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/personal-profiles", response_model=list[ProfileOut])
async def list_personal_profiles(user: dict = Depends(require_auth)):
    """Liste les profils personnels de l'utilisateur courant."""
    return [ProfileOut(**p) for p in _personal_profile_store.list(user["id"])]


@router.post("/personal-profiles", response_model=ProfileOut, status_code=status.HTTP_201_CREATED)
async def create_personal_profile(payload: ProfileCreate, user: dict = Depends(require_auth)):
    """Crée un nouveau profil personnel pour l'utilisateur courant."""
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Le nom du profil est requis.")
    if name == "Aucun rôle":
        raise HTTPException(status_code=422, detail="Ce nom est réservé.")
    try:
        _personal_profile_store.create(
            user["id"],
            name,
            payload.prompt,
            payload.tool_families.model_dump(),
            payload.pinned_skills,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return ProfileOut(**_personal_profile_store.get(user["id"], name))


@router.get("/personal-profiles/{name}", response_model=ProfileOut)
async def get_personal_profile(name: str, user: dict = Depends(require_auth)):
    """Récupère un profil personnel par son nom."""
    profile = _personal_profile_store.get(user["id"], name)
    if not profile:
        raise HTTPException(status_code=404, detail=f"Profil personnel '{name}' introuvable.")
    return ProfileOut(**profile)


@router.patch("/personal-profiles/{name}", response_model=ProfileOut)
async def update_personal_profile(name: str, payload: ProfilePatch, user: dict = Depends(require_auth)):
    """Met à jour un profil personnel existant."""
    existing = _personal_profile_store.get(user["id"], name)
    if not existing:
        raise HTTPException(status_code=404, detail=f"Profil personnel '{name}' introuvable.")

    new_prompt = payload.prompt if payload.prompt is not None else existing["prompt"]
    new_tf = payload.tool_families.model_dump() if payload.tool_families is not None else existing["tool_families"]
    new_ps = payload.pinned_skills if payload.pinned_skills is not None else existing["pinned_skills"]

    try:
        _personal_profile_store.update(user["id"], name, new_prompt, new_tf, new_ps)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return ProfileOut(**_personal_profile_store.get(user["id"], name))


@router.delete("/personal-profiles/{name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_personal_profile(name: str, user: dict = Depends(require_auth)):
    """Supprime un profil personnel."""
    try:
        _personal_profile_store.delete(user["id"], name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


# ═══════════════════════════════════════════════════════════════════════════
# Routes — Skills
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/skills", response_model=list[SkillOut])
async def list_skills(_ = Depends(require_auth)):
    """Liste les skills disponibles (métadonnées, sans contenu complet)."""
    return [SkillOut(**s) for s in _skill_store.list()]


@router.post("/skills", response_model=SkillContentOut, status_code=status.HTTP_201_CREATED)
async def create_skill(payload: SkillCreate, _ = Depends(require_admin)):
    """Crée un nouveau skill (fichier Markdown)."""
    slug = payload.slug.strip()
    if not _SLUG_RE.match(slug):
        raise HTTPException(
            status_code=422,
            detail="Slug invalide. Utilisez uniquement lettres, chiffres, tirets et underscores.",
        )
    try:
        _skill_store.save(slug, payload.content)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return SkillContentOut(slug=slug, content=payload.content)


@router.get("/skills/{slug}", response_model=SkillContentOut)
async def get_skill(slug: str, _ = Depends(require_auth)):
    """Retourne le contenu complet d'un skill."""
    try:
        content = _skill_store.read(slug)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Skill '{slug}' introuvable.")
    return SkillContentOut(slug=slug, content=content)


@router.put("/skills/{slug}", response_model=SkillContentOut)
async def update_skill(slug: str, payload: SkillCreate, _ = Depends(require_admin)):
    """Met à jour le contenu d'un skill existant."""
    if not _skill_store.exists(slug):
        raise HTTPException(status_code=404, detail=f"Skill '{slug}' introuvable.")
    try:
        _skill_store.save(slug, payload.content)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return SkillContentOut(slug=slug, content=payload.content)


@router.delete("/skills/{slug}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_skill(slug: str, _ = Depends(require_admin)):
    """Supprime un skill."""
    try:
        _skill_store.delete(slug)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Skill '{slug}' introuvable.")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
