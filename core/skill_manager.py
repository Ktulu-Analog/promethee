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
core/skill_manager.py — Gestionnaire de skills pour Prométhée AI
=================================================================

Un skill est un fichier Markdown (.md) stocké dans ~/.promethee/skills/.
Il contient des instructions, conventions ou guides de bonnes pratiques
que le LLM peut consulter à la demande ou qui peuvent être injectés
automatiquement dans le prompt système.

Deux modes d'utilisation
─────────────────────────
1. Skills épinglés (pinned) — injection statique
   Définis dans prompts.yml sous la clé ``skills`` d'un profil.
   Leur contenu est injecté dans le prompt système à chaque session,
   juste après le prompt du profil. Toujours présents en contexte.

   Cas d'usage : conventions de nommage, style rédactionnel maison,
   schéma de base de données métier, protocoles internes.

2. Skills dynamiques — consultation à la demande
   Exposés via les outils ``skill_read`` et ``skill_list`` (skill_tools.py).
   Le LLM décide lui-même de les consulter quand il juge qu'il en a besoin,
   exactement comme Claude lit un SKILL.md avant de générer du code.

   Cas d'usage : guides procéduraux longs, templates de documents,
   requêtes SQL spécialisées, protocoles métier conditionnels.

Structure du répertoire ./skills/
─────────────────────────────────────────────
    ./skills/
    ├── conventions_nommage.md      # Conventions de fichiers internes
    ├── style_redactionnel.md       # Guide de style pour les exports
    ├── schema_bdd_production.md    # Schéma SQL de la base de prod
    ├── workflow_legifrance.md      # Protocole de consultation juridique
    └── template_cr_reunion.md     # Template compte-rendu de réunion

Format d'un fichier skill
─────────────────────────
    ---
    name: Conventions de nommage
    description: Règles de nommage des fichiers et dossiers dans l'organisation
    tags: [nommage, fichiers, organisation]
    version: 1.0
    ---

    # Conventions de nommage

    ## Fichiers de rapport
    Format : YYYYMM_NOM_v{version}.docx
    ...

Le frontmatter YAML est optionnel mais recommandé. Sans frontmatter,
le nom du skill est déduit du nom de fichier (sans extension, espaces
remplacés par des underscores).

Intégration dans prompts.yml
─────────────────────────────
    prompts:
      Expert juridique:
        prompt: |
          Tu es un expert en droit administratif...
        skills:
          pinned:
            - workflow_legifrance       # nom de fichier sans .md
            - conventions_nommage
        tools:
          disabled:
            - audio_tools

API publique
─────────────
    from core.skill_manager import get_skill_manager

    sm = get_skill_manager()
    sm.list_skills()                    # tous les skills disponibles
    sm.read_skill("conventions_nommage")# contenu d'un skill
    sm.build_pinned_block(["a", "b"])   # bloc texte pour injection prompt
    sm.skills_dir                       # chemin du répertoire
"""

import logging
import re
from pathlib import Path
from typing import Optional

import yaml

_log = logging.getLogger("promethee.skill_manager")

# ── Répertoire par défaut ──────────────────────────────────────────────────
_SKILLS_DIR = Path(__file__).parent.parent / "skills"

# Taille maximale d'un skill injecté dans le prompt système (caractères).
# Valeur choisie pour couvrir la quasi-totalité des skills du projet
# (16 skills, dont les plus longs à ~17k chars sont encore tronqués mais
# conservent leurs sections essentielles) tout en maintenant les profils
# les plus chargés (GPEC, Administratif) sous 60k chars de system_prompt —
# soit moins de 15% d'une fenêtre de 128k tokens.
_SKILL_MAX_CHARS = 10_000

# Taille maximale d'un skill retourné via l'outil skill_read
_SKILL_READ_MAX_CHARS = 12_000


class SkillInfo:
    """Métadonnées d'un skill."""

    __slots__ = ("slug", "name", "description", "tags", "version", "path", "size")

    def __init__(self, slug: str, name: str, description: str,
                 tags: list[str], version: str, path: Path, size: int):
        self.slug        = slug
        self.name        = name
        self.description = description
        self.tags        = tags
        self.version     = version
        self.path        = path
        self.size        = size

    def to_dict(self) -> dict:
        return {
            "slug":        self.slug,
            "name":        self.name,
            "description": self.description,
            "tags":        self.tags,
            "version":     self.version,
            "size_chars":  self.size,
        }


class SkillManager:
    """
    Gestionnaire de skills Prométhée.

    Parameters
    ----------
    skills_dir : Path, optional
        Répertoire des fichiers skill. Défaut : ~/.promethee/skills/
    """

    def __init__(self, skills_dir: Path | None = None):
        self.skills_dir = Path(skills_dir) if skills_dir else _SKILLS_DIR
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        self._cache: dict[str, SkillInfo] = {}
        self._refresh()

    # ── Découverte ─────────────────────────────────────────────────────────

    def _refresh(self) -> None:
        """Relit le répertoire et met à jour le cache des métadonnées."""
        self._cache = {}
        for md_file in sorted(self.skills_dir.glob("*.md")):
            slug = md_file.stem
            try:
                content = md_file.read_text(encoding="utf-8")
                info    = self._parse_frontmatter(slug, content, md_file)
                self._cache[slug] = info
            except Exception as e:
                _log.warning("[skill_manager] Erreur lecture %s : %s", md_file, e)

    def _parse_frontmatter(self, slug: str, content: str, path: Path) -> SkillInfo:
        """
        Extrait les métadonnées du frontmatter YAML si présent.
        Fallback sur les valeurs déduites du slug si absent.
        """
        name        = slug.replace("_", " ").replace("-", " ").title()
        description = ""
        tags: list[str] = []
        version     = "1.0"

        # Détecter le frontmatter --- ... ---
        fm_match = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
        if fm_match:
            try:
                fm = yaml.safe_load(fm_match.group(1)) or {}
                name        = str(fm.get("name",        name))
                description = str(fm.get("description", description))
                tags        = list(fm.get("tags",       tags))
                version     = str(fm.get("version",     version))
            except yaml.YAMLError:
                pass  # frontmatter invalide → garder les valeurs par défaut

        # Si pas de description dans le frontmatter, chercher la première ligne
        # non-titre du contenu comme description courte
        if not description:
            body = content[fm_match.end():] if fm_match else content
            for line in body.splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    description = line[:120]
                    break

        return SkillInfo(
            slug=slug,
            name=name,
            description=description,
            tags=tags,
            version=version,
            path=path,
            size=len(content),
        )

    # ── API publique ───────────────────────────────────────────────────────

    def refresh(self) -> None:
        """Relit le répertoire (après ajout/suppression de fichiers)."""
        self._refresh()

    def list_skills(self) -> list[SkillInfo]:
        """Retourne la liste de tous les skills disponibles."""
        return list(self._cache.values())

    def get_info(self, slug: str) -> SkillInfo | None:
        """Retourne les métadonnées d'un skill par son slug, ou None."""
        return self._cache.get(slug)

    def exists(self, slug: str) -> bool:
        """Retourne True si un skill avec ce slug existe."""
        return slug in self._cache

    def read_skill(self, slug: str, max_chars: int = _SKILL_READ_MAX_CHARS) -> str:
        """
        Retourne le contenu complet d'un skill.

        Parameters
        ----------
        slug : str
            Nom du fichier skill sans extension (.md).
        max_chars : int
            Limite de taille (défaut : 12 000 chars). Troncature avec indicateur.

        Returns
        -------
        str
            Contenu Markdown du skill, éventuellement tronqué.

        Raises
        ------
        FileNotFoundError
            Si le slug ne correspond à aucun skill connu.
        """
        if slug not in self._cache:
            # Essayer un refresh avant d'échouer
            self._refresh()
        if slug not in self._cache:
            return ""

        info    = self._cache[slug]
        content = info.path.read_text(encoding="utf-8")

        if len(content) > max_chars:
            content = (
                content[:max_chars].rstrip()
                + f"\n\n[… skill tronqué : {len(content):,} → {max_chars:,} chars]"
            )

        return content

    def build_pinned_block(
        self,
        slugs: list[str],
        max_chars_per_skill: int = _SKILL_MAX_CHARS,
    ) -> str:
        """
        Construit le bloc texte à injecter dans le prompt système
        pour les skills épinglés d'un profil.

        Le bloc est encadré par des délimiteurs lisibles par le LLM.
        Les skills manquants sont signalés par une note sans lever d'exception
        (un fichier supprimé ne doit pas bloquer l'application).

        Parameters
        ----------
        slugs : list[str]
            Liste des slugs des skills épinglés.
        max_chars_per_skill : int
            Limite par skill pour l'injection (défaut : 6 000 chars).

        Returns
        -------
        str
            Bloc prêt à être concaténé au prompt système.
            Chaîne vide si la liste est vide ou si tous les skills sont absents.
        """
        if not slugs:
            return ""

        self._refresh()  # fraîcheur garantie à chaque session

        parts: list[str] = []
        for slug in slugs:
            if slug not in self._cache:
                _log.warning(
                    "[skill_manager] Skill épinglé '%s' introuvable — ignoré", slug
                )
                continue
            try:
                content = self.read_skill(slug, max_chars=max_chars_per_skill)
                info    = self._cache[slug]
                parts.append(
                    f"### Skill : {info.name}\n\n{content}"
                )
            except Exception as e:
                _log.error("[skill_manager] Erreur lecture skill épinglé '%s' : %s", slug, e)

        if not parts:
            return ""

        header = (
            "── Skills actifs (guides de bonnes pratiques à respecter) "
            "──────────────────────"
        )
        footer = (
            "── Fin des skills "
            "────────────────────────────────────────────────────────────"
        )
        return "\n\n" + header + "\n\n" + "\n\n---\n\n".join(parts) + "\n\n" + footer

    def save_skill(self, slug: str, content: str) -> SkillInfo:
        """
        Crée ou met à jour un skill.

        Parameters
        ----------
        slug : str
            Identifiant unique (nom de fichier sans .md).
            Ne peut contenir que des lettres, chiffres, tirets et underscores.
        content : str
            Contenu Markdown complet (avec frontmatter optionnel).

        Returns
        -------
        SkillInfo
            Métadonnées du skill créé/mis à jour.
        """
        # Valider le slug
        if not re.match(r"^[a-zA-Z0-9_\-]+$", slug):
            raise ValueError(
                f"Slug invalide : '{slug}'. "
                "Utiliser uniquement lettres, chiffres, tirets et underscores."
            )

        path = self.skills_dir / f"{slug}.md"
        path.write_text(content, encoding="utf-8")
        self._refresh()
        return self._cache[slug]

    def delete_skill(self, slug: str) -> None:
        """
        Supprime un skill du répertoire.

        Parameters
        ----------
        slug : str
            Slug du skill à supprimer.

        Raises
        ------
        FileNotFoundError
            Si le skill n'existe pas.
        """
        if slug not in self._cache:
            return  # slug inconnu — pas d'erreur
        self._cache[slug].path.unlink()
        del self._cache[slug]


# ── Instance globale ───────────────────────────────────────────────────────

_skill_manager: SkillManager | None = None


def get_skill_manager() -> SkillManager:
    """Retourne l'instance globale du gestionnaire de skills (lazy init)."""
    global _skill_manager
    if _skill_manager is None:
        _skill_manager = SkillManager()
    return _skill_manager
