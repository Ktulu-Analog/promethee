# ============================================================================
# Prométhée — Assistant IA desktop
# ============================================================================
# Auteur  : Pierre COUGET
# Licence : GNU Affero General Public License v3.0 (AGPL-3.0)
#           https://www.gnu.org/licenses/agpl-3.0.html
# Année   : 2026
# ----------------------------------------------------------------------------
# Ce fichier fait partie du projet Prométhée.
# Vous pouvez le redistribuer et/ou le modifier selon les termes de la
# licence AGPL-3.0 publiée par la Free Software Foundation.
# ============================================================================

"""
session_memory.py — Mémoire de session pour la boucle agent

Complète les mécanismes de trim et de compression de llm_service.py par deux
approches complémentaires :

1. Consolidation périodique (memory consolidation)
   ─────────────────────────────────────────────────
   Tous les N tours agent (CONTEXT_CONSOLIDATION_EVERY), un appel LLM
   secondaire génère un résumé structuré de ce qui a été accompli jusqu'ici.
   Ce résumé est injecté en début de contexte et remplace les messages anciens
   qui auraient été écrêtés par le trim.

   Avantage vs trim seul : le LLM conserve une vue sémantique cohérente de
   l'historique même quand les messages bruts ont disparu. Le trim seul perd
   définitivement l'information ; la consolidation la condense.

   Avantage vs compression seule : la compression est mécanique et perd le
   raisonnement inter-tours. Le résumé conserve les faits importants,
   les décisions prises et les erreurs rencontrées.

2. Marquage des tool_results critiques (pinning)
   ───────────────────────────────────────────────
   La compression mécanique (_compress_agent_msgs) peut condenser un résultat
   que le LLM a cité explicitement dans son raisonnement, ou qui contient du
   code source. Le pinning détecte ces résultats et les protège.

   Deux voies de déclenchement du pinning :

   a) Détection de code (_is_code) — prioritaire et inconditionnelle.
      Si le résultat contient du code source (Python, SQL, JavaScript, shell,
      etc.), il est systématiquement marqué critique, qu'il soit ou non cité
      dans la réponse. Cela couvre aussi bien le code produit comme réponse
      finale que le code généré comme résultat intermédiaire d'un outil.
      Problème évité : la troncature et la compression du code produisent du code
      syntaxiquement invalide ou sémantiquement incohérent, ce qui est plus
      dangereux qu'un contenu textuel dégradé.

   b) Détection sémantique (_is_cited) — heuristique complémentaire.
      Si le contenu textuel de la réponse assistant contient le nom de l'outil
      ET une citation partielle de son résultat, le tour est marqué critique.

   Le marquage est conservateur : mieux vaut protéger un résultat inutile que
   de comprimer un résultat utile.

Intégration dans agent_loop
───────────────────────────
    from core.session_memory import SessionMemory

    memory = SessionMemory(client, model)
    ...
    # Après chaque tour :
    memory.record_tool_result(tool_name, result, assistant_text)
    msgs = memory.maybe_consolidate(msgs, iteration, on_event=_context_event)
    msgs = memory.apply_pinned_protection(msgs)

Les deux fonctions sont idempotentes et sans effet si les seuils ne sont
pas atteints.

Configuration (.env)
────────────────────
    CONTEXT_CONSOLIDATION_EVERY=8   # consolidation tous les N tours (0=désactivé)
    CONTEXT_CONSOLIDATION_MAX_CHARS=1500  # taille max du résumé injecté
    CONTEXT_PINNING_ENABLED=ON      # activation du marquage critique
"""

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Callable, Optional

_log = logging.getLogger("promethee.session_memory")


# ── Structures de données ─────────────────────────────────────────────────────

@dataclass
class _ToolRecord:
    """Enregistrement d'un appel d'outil dans la session."""
    turn:       int           # numéro de tour (0-based)
    tool_name:  str
    result:     str           # résultat brut (avant troncature)
    result_len: int           # longueur originale (même si tronqué dans msgs)
    pinned:     bool = False  # True = protégé contre la compression


# ── Prompt de consolidation ───────────────────────────────────────────────────

_CONSOLIDATION_SYSTEM = """\
Tu es un assistant qui synthétise l'historique passé d'une session de travail.
Réponds UNIQUEMENT en français, de manière concise et structurée.
Ne réponds rien d'autre que la synthèse demandée.
"""

_CONSOLIDATION_PROMPT = """\
Voici l'historique d'échanges passés entre un utilisateur et un assistant IA.
Ces échanges sont TERMINÉS. Génère un mémo de référence en MAXIMUM {max_chars} \
caractères couvrant :

1. **Sujets traités** : liste des questions/tâches abordées par l'utilisateur (passé).
2. **Résultats obtenus** : ce qui a été produit, trouvé ou résolu.
3. **Informations utiles** : données clés mentionnées (fichiers, valeurs, noms) \
qui pourraient être réutilisées.

Ce mémo sert uniquement de référence pour ne pas oublier le contexte passé.
L'assistant NE DOIT PAS ré-exécuter les actions déjà effectuées.

--- Historique passé ---
{history}
--- Fin ---
"""


# ── Classe principale ─────────────────────────────────────────────────────────

class SessionMemory:
    """
    Gestion de la mémoire de session pour la boucle agent.

    Parameters
    ----------
    client : OpenAI
        Client LLM déjà construit (partagé avec agent_loop).
    model : str
        Nom du modèle actif.
    consolidation_every : int
        Nombre de tours entre deux consolidations (0 = désactivé).
    consolidation_max_chars : int
        Taille maximale du résumé consolidé en caractères.
    pinning_enabled : bool
        Activer le marquage des tool_results critiques.
    """

    def __init__(
        self,
        client,
        model: str,
        consolidation_every: int = 8,
        consolidation_max_chars: int = 1500,
        pinning_enabled: bool = True,
        pressure_threshold: float = 0.70,
        model_max_tokens: int = 128_000,
    ):
        self._client          = client
        self._model           = model
        self._every           = consolidation_every
        self._max_chars       = consolidation_max_chars
        self._pinning         = pinning_enabled
        self._pressure_threshold = pressure_threshold
        self._model_max_tokens   = model_max_tokens

        # Historique des outils appelés dans la session
        self._records: list[_ToolRecord] = []

        # Records en attente de réévaluation du pinning (assistant_text était vide
        # au moment de l'enregistrement — le texte final arrive au tour suivant).
        self._pending_records: list[_ToolRecord] = []

        # Dernier résumé de consolidation produit (texte brut)
        self._last_summary: Optional[str] = None
        # Tour auquel la dernière consolidation a été effectuée
        self._last_consolidated_at: int = -1

    # ── API publique ──────────────────────────────────────────────────────────

    def record_tool_result(
        self,
        tool_name: str,
        result: str,
        assistant_text: str,
        turn: int,
    ) -> None:
        """
        Enregistre un appel d'outil et décide si son résultat doit être protégé.

        Deux voies de pinning, évaluées dans cet ordre :

        1. Détection de code (_is_code) — prioritaire et inconditionnelle.
           Si le résultat contient du code source, il est immédiatement marqué
           critique sans attendre la réponse de l'assistant. Cela couvre le code
           produit comme réponse finale ET le code intermédiaire généré par un
           outil au service d'une demande plus large.

        2. Détection sémantique (_is_cited) — complémentaire.
           Appliquée uniquement si la détection de code n'a pas déjà déclenché
           le pinning. Vérifie si la réponse assistant cite explicitement le
           résultat (nom de l'outil + extrait du contenu).

        Parameters
        ----------
        tool_name : str
            Nom de l'outil appelé.
        result : str
            Résultat retourné par l'outil (avant toute troncature).
        assistant_text : str
            Texte produit par l'assistant au tour courant (peut être vide
            si on est encore en cours de boucle).
        turn : int
            Numéro de tour (0-based).
        """
        record = _ToolRecord(
            turn=turn,
            tool_name=tool_name,
            result=result,
            result_len=len(result),
            pinned=False,
        )

        if not self._pinning:
            # Pinning désactivé : enregistrement direct, pas d'évaluation.
            self._records.append(record)
            return

        # ── Voie 0 : image générée — prioritaire absolue ──────────────────────
        # Un tool_result contenant "image_generated": true signale qu'une image
        # (matplotlib, etc.) a été produite et extraite par llm_service.
        # Ce résultat doit être protégé inconditionnellement : la compression
        # mécanique (_compress_agent_msgs) ne doit pas tronquer les métadonnées
        # associées (status, output…) qui donnent son contexte à l'image affichée.
        if self._has_image(result):
            record.pinned = True
            _log.info(
                "[session_memory] tour %d — %s marqué comme critique (image générée)",
                turn, tool_name,
            )
            self._records.append(record)
            return

        # ── Voie 1 : détection de code — prioritaire et inconditionnelle ─────
        # Si le résultat contient du code, on marque immédiatement sans attendre
        # la réponse de l'assistant (qui peut ne jamais arriver pour du code
        # intermédiaire non cité explicitement dans le texte final).
        if self._is_code(result):
            record.pinned = True
            _log.info(
                "[session_memory] tour %d — %s marqué comme critique (contient du code)",
                turn, tool_name,
            )
            self._records.append(record)
            return

        # ── Voie 2 : détection sémantique — complémentaire ───────────────────
        if assistant_text:
            # Texte assistant disponible : évaluation immédiate.
            record.pinned = self._is_cited(tool_name, result, assistant_text)
            if record.pinned:
                _log.info(
                    "[session_memory] tour %d — %s marqué comme critique (cité dans la réponse)",
                    turn, tool_name,
                )
            self._records.append(record)
        else:
            # Texte assistant absent (outil appelé en cours de boucle) :
            # différer la décision de marquage au tour suivant via flush_pending().
            self._pending_records.append(record)
            _log.debug(
                "[session_memory] tour %d — %s en attente de réévaluation de marquage",
                turn, tool_name,
            )

    def flush_pending(self, msgs: list[dict]) -> None:
        """
        Réévalue le marquage des records en attente en utilisant le dernier
        texte assistant disponible dans la liste de messages.

        Doit être appelé au début de chaque itération de la boucle agent,
        après que le tour précédent a produit sa réponse textuelle finale.

        Le texte assistant utilisé est celui du dernier message role=assistant
        qui contient du contenu textuel ("content" non vide).

        Note : les records déjà marqués pinned=True (détection de code dans
        record_tool_result) ne sont pas réévalués — leur protection est acquise.

        Parameters
        ----------
        msgs : list[dict]
            Messages courants de la boucle agent.
        """
        if not self._pending_records:
            return

        # Récupérer le dernier texte assistant non vide
        last_assistant_text = ""
        for m in reversed(msgs):
            if m.get("role") == "assistant":
                content = m.get("content") or ""
                if isinstance(content, str) and content.strip():
                    last_assistant_text = content
                    break
                elif isinstance(content, list):
                    # contenu multi-part
                    text = " ".join(
                        p.get("text", "") for p in content if isinstance(p, dict)
                    ).strip()
                    if text:
                        last_assistant_text = text
                        break

        for record in self._pending_records:
            # Ne pas réévaluer un record déjà marqué (ex : détection de code)
            if record.pinned:
                _log.debug(
                    "[session_memory] flush_pending — tour %d — %s déjà marqué (code), conservé",
                    record.turn, record.tool_name,
                )
            elif last_assistant_text:
                record.pinned = self._is_cited(
                    record.tool_name, record.result, last_assistant_text
                )
                if record.pinned:
                    _log.info(
                        "[session_memory] flush_pending — tour %d — %s marqué comme critique",
                        record.turn, record.tool_name,
                    )
            # Transférer dans _records qu'il y ait du texte ou non
            self._records.append(record)
            _log.debug(
                "[session_memory] flush_pending — tour %d — %s transféré (pinned=%s)",
                record.turn, record.tool_name, record.pinned,
            )

        self._pending_records.clear()

    def maybe_consolidate(
        self,
        msgs: list[dict],
        current_turn: int,
        on_event: Optional[Callable[[str], None]] = None,
        usage=None,
    ) -> list[dict]:
        """
        Déclenche une consolidation si le seuil de tours est atteint.

        La consolidation génère un résumé via un appel LLM secondaire et
        l'injecte au début du contexte sous forme d'un message système
        spécial (role="system", marqué comme consolidation).

        Le résumé précédent est remplacé s'il en existait un.

        Parameters
        ----------
        msgs : list[dict]
            Messages actuels de la boucle agent.
        current_turn : int
            Numéro du tour courant.
        on_event : Callable, optional
            Callback de notification vers l'UI.

        Returns
        -------
        list[dict]
            Messages avec le résumé consolidé injecté (ou msgs inchangé).
        """
        if current_turn == 0:
            return msgs
        if current_turn == self._last_consolidated_at:
            return msgs

        # ── Critère 1 : fréquence fixe ────────────────────────────────────
        periodic = (
            self._every > 0
            and (current_turn - self._last_consolidated_at) >= self._every
        )

        # ── Critère 2 : pression sur le contexte ─────────────────────────
        # Déclenché si prompt_tokens / model_max_tokens >= pressure_threshold.
        # Nécessite que usage.prompt soit disponible (donc > 0, après le 1er tour).
        pressure = False
        if (
            self._pressure_threshold > 0.0
            and usage is not None
            and getattr(usage, "prompt", 0) > 0
            and self._model_max_tokens > 0
        ):
            pct = usage.prompt / self._model_max_tokens
            if pct >= self._pressure_threshold:
                pressure = True
                _log.info(
                    "[session_memory] tour %d — pression contexte %.1f%% >= seuil %.0f%%",
                    current_turn, pct * 100, self._pressure_threshold * 100,
                )

        if not periodic and not pressure:
            return msgs

        trigger = "pression contexte" if pressure and not periodic else "fréquence"
        _log.info(
            "[session_memory] tour %d — déclenchement consolidation (%s)",
            current_turn, trigger,
        )
        if on_event:
            on_event(f"Mémoire : consolidation de la session en cours ({trigger})…")

        summary = self._generate_summary(msgs, usage=usage)

        # Toujours avancer le curseur, même en cas d'échec.
        # Sans cela, la consolidation est re-tentée à chaque tour suivant
        # dès que le seuil est atteint, provoquant une boucle infinie.
        self._last_consolidated_at = current_turn

        if not summary:
            _log.warning("[session_memory] consolidation échouée — résumé vide")
            return msgs

        self._last_summary = summary

        # Supprimer l'éventuel résumé précédent
        msgs = [m for m in msgs if not m.get("_is_consolidation")]

        # Injecter le nouveau résumé juste après le message système initial
        consolidation_msg = {
            "role": "system",
            "content": (
                "── Mémo des échanges passés (historique clos — ne pas ré-exécuter) ──\n\n"
                + summary
                + "\n\n── Fin du mémo ──"
            ),
            "_is_consolidation": True,  # marqueur interne, retiré avant l'envoi à l'API
        }

        # Trouver l'index d'insertion (après le 1er message système s'il existe)
        insert_at = 0
        for i, m in enumerate(msgs):
            if m.get("role") == "system" and not m.get("_is_consolidation"):
                insert_at = i + 1
                break

        msgs.insert(insert_at, consolidation_msg)

        n_tools = len([r for r in self._records if r.turn < current_turn])
        _log.info(
            "[session_memory] consolidation OK — %d chars, %d outils couverts",
            len(summary), n_tools,
        )
        if on_event:
            on_event(
                f"Mémoire : {n_tools} tour(s) consolidés ({len(summary):,} car.)"
            )

        return msgs

    def apply_pinned_protection(self, msgs: list[dict]) -> list[dict]:
        """
        Marque les tool_results critiques dans la liste de messages pour
        qu'ils soient exclus de la compression mécanique.

        Le marquage se fait via le champ ``_pinned=True`` sur le message.
        _compress_agent_msgs doit vérifier ce champ avant de comprimer.

        Parameters
        ----------
        msgs : list[dict]
            Messages de la boucle agent.

        Returns
        -------
        list[dict]
            Messages avec les tool_results critiques marqués.
        """
        if not self._pinning:
            return msgs

        pinned_tools = {r.tool_name for r in self._records if r.pinned}
        if not pinned_tools:
            return msgs

        result = []
        for m in msgs:
            if m.get("role") == "tool":
                # Retrouver le nom de l'outil via tool_call_id ou contenu
                # On peut aussi retrouver via les records si on a l'id
                tool_name = self._find_tool_name_for_msg(m, msgs)
                if tool_name and tool_name in pinned_tools:
                    result.append({**m, "_pinned": True})
                    continue
            result.append(m)

        return result

    def strip_internal_markers(self, msgs: list[dict]) -> list[dict]:
        """
        Retire les marqueurs internes (_is_consolidation, _pinned) avant
        l'envoi à l'API LLM.

        Parameters
        ----------
        msgs : list[dict]
            Messages avec marqueurs internes éventuels.

        Returns
        -------
        list[dict]
            Messages propres, sans champs privés.
        """
        clean = []
        for m in msgs:
            cm = {k: v for k, v in m.items() if not k.startswith("_")}
            clean.append(cm)
        return clean

    @property
    def last_summary(self) -> Optional[str]:
        """Dernier résumé de consolidation produit, ou None."""
        return self._last_summary

    @property
    def pinned_tool_names(self) -> set[str]:
        """Noms des outils dont les résultats sont protégés."""
        return {r.tool_name for r in self._records if r.pinned}

    # ── Internals ─────────────────────────────────────────────────────────────

    def _generate_summary(self, msgs: list[dict], usage=None) -> str:
        """
        Appelle le LLM pour générer un résumé de l'historique actuel.

        Utilise le mode streaming : gpt-oss-120 sur Albert retourne content=None
        en mode non-streaming (stream=False) quand des tool_calls ont transité
        dans la session courante.

        Le system prompt est préfixé dans le message user plutôt qu'envoyé
        comme role=system séparé, ce qui évite les rejets du backend sur
        un second message system hors contexte initial.

        usage : TokenUsage, optional
            Si fourni, les tokens consommés par la consolidation sont
            ajoutés à cet objet et apparaissent dans les métriques de session.

        Retourne une chaîne vide en cas d'échec.
        """
        # Construire une représentation textuelle légère de l'historique
        history_parts = []
        for m in msgs:
            role = m.get("role", "")
            content = m.get("content") or ""
            if role == "system" and m.get("_is_consolidation"):
                continue  # ne pas inclure l'ancien résumé dans le nouveau
            if role == "system":
                history_parts.append(f"[Système] {content[:300]}")
            elif role == "user":
                if isinstance(content, list):
                    text = " ".join(p.get("text", "") for p in content if isinstance(p, dict))
                else:
                    text = content
                history_parts.append(f"[Utilisateur] {text[:500]}")
            elif role == "assistant":
                if isinstance(content, str) and content:
                    history_parts.append(f"[Assistant] {content[:400]}")
                tool_calls = m.get("tool_calls", [])
                if tool_calls:
                    names = [tc.get("function", {}).get("name", "?") for tc in tool_calls]
                    history_parts.append(f"[Outils appelés] {', '.join(names)}")
            elif role == "tool":
                tc_content = content[:300] if len(content) > 300 else content
                history_parts.append(f"[Résultat outil] {tc_content}")

        history_text = "\n".join(history_parts)
        prompt = (
            _CONSOLIDATION_SYSTEM.strip()
            + "\n\n"
            + _CONSOLIDATION_PROMPT.format(
                max_chars=self._max_chars,
                history=history_text,
            )
        )

        try:
            stream_resp = self._client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
                stream=True,
                max_tokens=600,
                stream_options={"include_usage": True},
            )
            parts: list[str] = []
            for chunk in stream_resp:
                # Comptabiliser les tokens de consolidation dans le TokenUsage principal
                if usage is not None and hasattr(chunk, "usage") and chunk.usage:
                    usage.add(chunk.usage, streaming=True)
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                if delta and delta.content:
                    parts.append(delta.content)
            summary = "".join(parts)
            # Tronquer si le modèle a quand même dépassé
            if len(summary) > self._max_chars:
                summary = summary[:self._max_chars].rstrip() + "…"
            return summary.strip()
        except Exception as e:
            _log.error("[session_memory] erreur consolidation LLM : %s", e, exc_info=True)
            return ""

    @staticmethod
    def _is_code(result: str) -> bool:
        """
        Détecte si le résultat d'un outil contient du code source.

        Couvre les cas suivants :
          - Code Python (def, class, import, décorateurs, f-strings…)
          - SQL (SELECT, INSERT, CREATE, ALTER, WITH…)
          - JavaScript / TypeScript (function, const, let, var, =>, class…)
          - Shell / Bash (#!, commandes courantes, pipes, redirections)
          - Autres langages courants (struct, fn, pub, #include, package…)

        Stratégie : deux niveaux de détection.

          Niveau 1 — marqueurs forts (1 seul suffit) :
            Des séquences très caractéristiques d'un langage de programmation
            qui n'apparaissent quasi jamais dans du texte naturel.
            Ex : "def " suivi d'un identifiant et ":", "import " en début de
            ligne, "SELECT " suivi d'un mot, etc.

          Niveau 2 — marqueurs faibles (3 requis) :
            Des tokens présents dans du code mais aussi potentiellement dans
            du texte structuré. Le seuil de 3 réduit les faux positifs.

        L'évaluation porte sur les 2 000 premiers caractères du résultat pour
        limiter le coût sur les très longs résultats.
        """
        # Travailler sur un échantillon pour ne pas scanner des Mo de données
        sample = result[:2_000]

        # ── Niveau 1 : marqueurs forts ────────────────────────────────────────
        # Chaque pattern est suffisamment spécifique pour décider seul.
        STRONG_PATTERNS = [
            # Python
            re.compile(r"^\s*(def |async def )\s*\w+\s*\(", re.MULTILINE),
            re.compile(r"^\s*class \w+[\s:(]", re.MULTILINE),
            re.compile(r"^\s*(import |from \w+ import )", re.MULTILINE),
            re.compile(r"^\s*@\w+(\.\w+)*\s*(\(|$)", re.MULTILINE),   # décorateurs
            # SQL
            re.compile(r"\b(SELECT|INSERT INTO|UPDATE|DELETE FROM|CREATE TABLE"
                       r"|ALTER TABLE|DROP TABLE|WITH \w+ AS)\b",
                       re.IGNORECASE),
            # JavaScript / TypeScript
            re.compile(r"\b(const|let|var)\s+\w+\s*=", re.MULTILINE),
            re.compile(r"^\s*function\s+\w+\s*\(", re.MULTILINE),
            re.compile(r"=>\s*[\{(]", re.MULTILINE),                   # arrow function
            re.compile(r"^\s*export\s+(default\s+)?(function|class|const)", re.MULTILINE),
            # Shell
            re.compile(r"^#!(\/usr\/bin\/env\s+\w+|\/bin\/(ba)?sh)", re.MULTILINE),
            re.compile(r"^\s*(apt|pip|npm|yarn|cargo|go|docker)\s+\w+", re.MULTILINE),
            # C / C++ / Rust / Go
            re.compile(r"^\s*#include\s*[<\"]", re.MULTILINE),
            re.compile(r"\bfn\s+\w+\s*(<[^>]*>)?\s*\(", re.MULTILINE),  # Rust
            re.compile(r"^\s*func\s+\w+\s*\(", re.MULTILINE),            # Go
        ]
        if any(p.search(sample) for p in STRONG_PATTERNS):
            return True

        # ── Niveau 2 : marqueurs faibles (seuil 3) ───────────────────────────
        WEAK_MARKERS = [
            "return ",
            "raise ",
            "print(",
            "console.log(",
            "if (",
            "} else {",
            "elif ",
            "try:",
            "except ",
            "catch (",
            "for (",
            "while (",
            "null",
            "None",
            "True",
            "False",
            "self.",
            "this.",
            "//",      # commentaire ligne C/JS
            "/*",      # commentaire bloc
            "*/",
            "  # ",    # commentaire Python indenté
        ]
        score = sum(1 for m in WEAK_MARKERS if m in sample)
        return score >= 3

    @staticmethod
    def _has_image(result: str) -> bool:
        """
        Détecte si le résultat d'un outil signale une image générée.

        Retourne True si le JSON du résultat contient la clé
        ``"image_generated": true``, marqueur posé par llm_service
        après extraction de l'image matplotlib (ou autre outil graphique).

        La détection est volontairement stricte (JSON parsé, pas regex)
        pour éviter les faux positifs sur du texte contenant par hasard
        la chaîne "image_generated".
        """
        if '"image_generated"' not in result:
            # Optimisation rapide : évite le parse JSON sur la majorité des résultats
            return False
        try:
            parsed = json.loads(result)
            return isinstance(parsed, dict) and parsed.get("image_generated") is True
        except (json.JSONDecodeError, ValueError):
            return False

    @staticmethod
    def _is_cited(tool_name: str, result: str, assistant_text: str) -> bool:
        """
        Détecte si le résultat d'un outil est cité dans la réponse assistant.

        Heuristiques (ordre décroissant de certitude) :
          1. Le nom de l'outil apparaît dans la réponse.
          2. Un extrait significatif du résultat (premier token ou valeur numérique
             distincte) apparaît dans la réponse.

        Retourne True si au moins deux heuristiques se vérifient, ou si la
        première heuristique ET un extrait littéral > 15 chars se trouvent
        dans la réponse.
        """
        text_low   = assistant_text.lower()
        tool_low   = tool_name.lower().replace("_", " ")
        result_low = result.lower()

        # Heuristique 1 : nom de l'outil dans la réponse
        h1 = (tool_low in text_low) or (tool_name.lower() in text_low)

        # Heuristique 2 : extrait littéral du résultat (>15 chars, pas uniquement whitespace)
        h2 = False
        # Découper le résultat en tokens de mots pour trouver une phrase présente
        words = re.split(r"\s+", result.strip())
        if len(words) >= 5:
            # Chercher une fenêtre glissante de 5 mots dans la réponse
            for i in range(len(words) - 4):
                snippet = " ".join(words[i:i+5]).lower()
                if len(snippet) > 15 and snippet in text_low:
                    h2 = True
                    break

        # Heuristique 3 : valeur numérique spécifique du résultat dans la réponse
        h3 = False
        numbers = re.findall(r"\b\d+(?:[.,]\d+)?\b", result)
        significant = [n for n in numbers if len(n) >= 4]   # >= 4 chiffres = distinctif
        if significant:
            h3 = any(n in assistant_text for n in significant[:5])  # limiter à 5

        score = sum([h1, h2, h3])
        return score >= 2

    @staticmethod
    def _find_tool_name_for_msg(tool_msg: dict, all_msgs: list[dict]) -> Optional[str]:
        """
        Retrouve le nom de l'outil associé à un message role=tool en cherchant
        le tool_call_id correspondant dans les messages assistant précédents.
        """
        target_id = tool_msg.get("tool_call_id")
        if not target_id:
            return None
        for m in all_msgs:
            if m.get("role") != "assistant":
                continue
            for tc in m.get("tool_calls", []) or []:
                if tc.get("id") == target_id:
                    return tc.get("function", {}).get("name")
        return None
