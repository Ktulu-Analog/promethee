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
url_cache.py — Cache persistant pour les URLs fetchées
"""
import json
import hashlib
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional

_log = logging.getLogger(__name__)


class URLCache:
    """Cache des URLs fetchées avec expiration."""
    
    def __init__(self, cache_file: str = "url_cache.json", ttl_hours: int = 24):
        self.cache_file = Path(cache_file)
        self.ttl = timedelta(hours=ttl_hours)
        self._cache = self._load_cache()
    
    def _load_cache(self) -> dict:
        """Charge le cache depuis le disque."""
        if self.cache_file.exists():
            try:
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}
    
    def _save_cache(self):
        """Sauvegarde le cache sur disque."""
        try:
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(self._cache, f, ensure_ascii=False, indent=2)
        except Exception as e:
            _log.warning("[URLCache] Erreur sauvegarde : %s", e)
    
    def _hash_url(self, url: str) -> str:
        """Génère un hash de l'URL."""
        return hashlib.sha256(url.encode()).hexdigest()[:16]
    
    def get(self, url: str) -> Optional[dict]:
        """Récupère une URL du cache si elle existe et n'est pas expirée."""
        key = self._hash_url(url)
        
        if key not in self._cache:
            return None
        
        entry = self._cache[key]
        
        # Vérifier l'expiration
        cached_at = datetime.fromisoformat(entry["cached_at"])
        if datetime.now() - cached_at > self.ttl:
            # Expiré, supprimer
            del self._cache[key]
            self._save_cache()
            return None
        
        return {
            "url": entry["url"],
            "title": entry["title"],
            "content": entry["content"],
            "size": entry["size"],
            "cached_at": cached_at
        }
    
    def set(self, url: str, title: str, content: str):
        """Ajoute une URL au cache."""
        key = self._hash_url(url)
        
        self._cache[key] = {
            "url": url,
            "title": title,
            "content": content,
            "size": len(content),
            "cached_at": datetime.now().isoformat()
        }
        
        self._save_cache()
    
    def clear(self):
        """Vide complètement le cache."""
        self._cache = {}
        self._save_cache()
    
    def clear_expired(self):
        """Supprime les entrées expirées."""
        now = datetime.now()
        expired_keys = []
        
        for key, entry in self._cache.items():
            cached_at = datetime.fromisoformat(entry["cached_at"])
            if now - cached_at > self.ttl:
                expired_keys.append(key)
        
        for key in expired_keys:
            del self._cache[key]
        
        if expired_keys:
            self._save_cache()
        
        return len(expired_keys)
    
    def size(self) -> int:
        """Retourne le nombre d'entrées dans le cache."""
        return len(self._cache)
    
    def total_size_bytes(self) -> int:
        """Retourne la taille totale du contenu caché en octets."""
        return sum(entry["size"] for entry in self._cache.values())


# Instance globale
_url_cache = URLCache()


def get_url_cache() -> URLCache:
    """Retourne l'instance globale du cache."""
    return _url_cache
