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
workers.py — Workers PyQt6 pour threading
Couche Qt qui utilise les services du core.
"""
from PyQt6.QtCore import QThread, pyqtSignal
from core import llm_service, tools_engine, rag_engine


class StreamWorker(QThread):
    """Worker pour le streaming simple."""
    token_received = pyqtSignal(str)
    finished_signal = pyqtSignal(str)
    error_signal = pyqtSignal(str)
    token_usage = pyqtSignal(object)   # émet un TokenUsage

    def __init__(self, messages, system_prompt="", model=None, parent=None):
        super().__init__(parent)
        self.messages = messages
        self.system_prompt = system_prompt
        self.model = model
        self._full = ""
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            self._full = llm_service.stream_chat(
                messages=self.messages,
                system_prompt=self.system_prompt,
                model=self.model,
                on_token=lambda token: (
                    self.token_received.emit(token) if not self._cancelled else None
                ),
                on_usage=lambda u: (
                    self.token_usage.emit(u) if not self._cancelled else None
                ),
            )
            if not self._cancelled:
                self.finished_signal.emit(self._full)
        except Exception as e:
            if not self._cancelled:
                self.error_signal.emit(str(e))


class AgentWorker(QThread):
    """Worker pour la boucle agent avec tool-use."""
    token_received = pyqtSignal(str)
    tool_called = pyqtSignal(str, str)   # (tool_name, args_json)
    tool_result = pyqtSignal(str, str)   # (tool_name, result)
    tool_image  = pyqtSignal(str, str)   # (mime_type, base64_data)
    tool_progress = pyqtSignal(str)      # message de progression intermédiaire
    finished_signal = pyqtSignal(str)
    error_signal = pyqtSignal(str)
    token_usage    = pyqtSignal(object)  # émet un TokenUsage (mis à jour à chaque appel)
    context_event  = pyqtSignal(str)     # émet un message quand la compression se déclenche
    memory_event   = pyqtSignal(str)     # émet un message de mémoire de session (consolidation, pinning)
    compression_stats = pyqtSignal(object)  # émet un dict {type, before, after, saved, pct}
    family_routing = pyqtSignal(object)  # émet un dict {family, label, model, backend}
                                         # family=="" → retour au modèle principal
    model_usage    = pyqtSignal(object)  # émet un dict {model, prompt, completion, role}

    def __init__(
        self,
        messages,
        system_prompt="",
        model=None,
        use_tools=True,
        max_iterations=8,
        disable_context_management=False,
        parent=None,
    ):
        super().__init__(parent)
        self.messages = messages
        self.system_prompt = system_prompt
        self.model = model
        self.use_tools = use_tools
        self.max_iterations = max_iterations
        self.disable_context_management = disable_context_management
        self._final_text = ""
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        # Installer le callback de progression pour les outils
        tools_engine.set_tool_progress_callback(
            lambda msg: self.tool_progress.emit(msg) if not self._cancelled else None
        )
        # Installer le callback d'événements de compression de contexte
        llm_service.set_context_event_callback(
            lambda msg: self.context_event.emit(msg) if not self._cancelled else None
        )
        llm_service.set_memory_event_callback(
            lambda msg: self.memory_event.emit(msg) if not self._cancelled else None
        )
        llm_service.set_compression_stats_callback(
            lambda stats: self.compression_stats.emit(stats) if not self._cancelled else None
        )
        llm_service.set_family_routing_callback(
            lambda info: self.family_routing.emit(info) if not self._cancelled else None
        )
        llm_service.set_model_usage_callback(
            lambda info: self.model_usage.emit(info) if not self._cancelled else None
        )

        try:
            self._final_text = llm_service.agent_loop(
                messages=self.messages,
                system_prompt=self.system_prompt,
                model=self.model,
                use_tools=self.use_tools,
                max_iterations=self.max_iterations,
                disable_context_management=self.disable_context_management,
                on_tool_call=lambda name, args: (
                    self.tool_called.emit(name, args) if not self._cancelled else None
                ),
                on_tool_result=lambda name, result: (
                    self.tool_result.emit(name, result) if not self._cancelled else None
                ),
                on_image=lambda mime, b64: (
                    self.tool_image.emit(mime, b64) if not self._cancelled else None
                ),
                on_token=lambda token: (
                    self.token_received.emit(token) if not self._cancelled else None
                ),
                on_usage=lambda u: (
                    self.token_usage.emit(u) if not self._cancelled else None
                ),
            )
            if not self._cancelled:
                self.finished_signal.emit(self._final_text)
        except Exception as e:
            if not self._cancelled:
                self.error_signal.emit(str(e))
        finally:
            tools_engine.set_tool_progress_callback(None)
            llm_service.set_context_event_callback(None)
            llm_service.set_memory_event_callback(None)
            llm_service.set_compression_stats_callback(None)
            llm_service.set_family_routing_callback(None)
            llm_service.set_model_usage_callback(None)


class IngestWorker(QThread):
    """
    Worker pour l'ingestion RAG.

    Annulation
    ──────────
    cancel() positionne _cancelled=True. La boucle d'ingestion vérifie ce
    flag entre chaque fichier : le fichier en cours de traitement par
    rag_engine.ingest_file() se termine normalement (l'API RAG n'expose pas
    d'interruption intra-fichier), puis le worker s'arrête proprement sans
    émettre finished().

    Cela évite qu'une ingestion d'un PDF lourd bloque la fermeture de
    l'application ou le changement de conversation indéfiniment.
    """
    progress = pyqtSignal(int, int)  # (done, total)
    finished = pyqtSignal(int)       # chunks total
    error    = pyqtSignal(str)

    def __init__(self, paths: list[str], conv_id: str = None, parent=None):
        super().__init__(parent)
        self.paths     = paths
        self.conv_id   = conv_id
        self._cancelled = False

    def cancel(self):
        """Demande l'arrêt après le fichier en cours."""
        self._cancelled = True

    def run(self):
        total_chunks = 0
        for i, path in enumerate(self.paths):
            if self._cancelled:
                break
            try:
                chunks = rag_engine.ingest_file(path, self.conv_id)
                total_chunks += chunks
                self.progress.emit(i + 1, len(self.paths))
            except Exception as e:
                self.error.emit(f"{path}: {e}")
        if not self._cancelled:
            self.finished.emit(total_chunks)
