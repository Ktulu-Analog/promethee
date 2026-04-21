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
crypto.py — Chiffrement applicatif AES-256-GCM pour la base SQLite

Architecture
------------
Chaque valeur chiffrée est autonome : elle embarque le sel Scrypt et le
nonce AES-GCM, ce qui permet de changer de clé ou de migrer sans base de
données annexe.

Format d'un blob chiffré (binaire, stocké en base64 dans SQLite) :
  ┌──────────────┬────────────┬──────────────────────────────────────────┐
  │ magic (5 B)  │ sel (32 B) │ nonce (12 B) │ ciphertext+tag (var. B)  │
  └──────────────┴────────────┴──────────────────────────────────────────┘
  - magic : b"KTULU" — identifie un blob chiffré par Prométhée
  - sel   : aléatoire par valeur — garantit que deux valeurs identiques
            produisent des chiffrés différents (résistance aux attaques
            par analyse de fréquence sur le sel)
  - nonce : 96 bits aléatoires pour AES-GCM
  - tag   : 128 bits d'authenticité AES-GCM, concaténé au ciphertext
            par la bibliothèque cryptography

Dérivation de clé
-----------------
  Scrypt(passphrase, sel, N=2^17, r=8, p=1) → clé de 32 octets
  N=2^17 (~131 072 itérations) : ~0,5 s sur un CPU moderne, rend les
  attaques par dictionnaire coûteuses sans pénaliser l'usage normal.
  Chaque valeur a son propre sel → chaque déchiffrement recalcule la clé.

  Pour les performances (milliers de messages à déchiffrer d'un coup),
  un cache LRU lie (passphrase_hash, sel) → clé dérivée. Ce cache est
  limité à 256 entrées et purgé à la fermeture.

Compatibilité
-------------
  - Les valeurs NON chiffrées (base existante, DB_ENCRYPTION=OFF) sont
    retournées telles quelles par decrypt() : aucune migration forcée.
  - is_encrypted(blob) permet de distinguer les deux formats.

Dépendances
-----------
  cryptography >= 3.0 (déjà dans requirements.txt via openai)
  → pip install cryptography
"""

import base64
import hashlib
import os
from functools import lru_cache
from typing import Optional

try:
    from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.exceptions import InvalidTag
    _CRYPTO_OK = True
except ImportError:
    _CRYPTO_OK = False

# ── Constantes ────────────────────────────────────────────────────────────────

MAGIC         = b"KTULU"         # 5 octets — marqueur de blob chiffré Prométhée
MAGIC_LEN     = len(MAGIC)       # 5
SALT_LEN      = 32               # octets — sel Scrypt par valeur
NONCE_LEN     = 12               # octets — nonce AES-GCM (96 bits, recommandé NIST)
SCRYPT_N      = 2 ** 17          # facteur de coût CPU/mémoire Scrypt
SCRYPT_R      = 8                # facteur de coût mémoire Scrypt
SCRYPT_P      = 1                # facteur de parallélisme Scrypt
KEY_LEN       = 32               # octets — AES-256

# Taille minimale d'un blob chiffré valide (sans ciphertext, juste les en-têtes)
_HEADER_LEN = MAGIC_LEN + SALT_LEN + NONCE_LEN   # 5 + 32 + 12 = 49

# ── Gestion d'erreur ──────────────────────────────────────────────────────────

class CryptoError(Exception):
    """Erreur de chiffrement/déchiffrement (passphrase incorrecte, blob corrompu)."""


class CryptoUnavailableError(CryptoError):
    """La bibliothèque 'cryptography' n'est pas installée."""


# ── Dérivation de clé avec cache ──────────────────────────────────────────────

def _derive_key(passphrase: bytes, salt: bytes) -> bytes:
    """
    Dérive une clé AES-256 depuis une passphrase et un sel via Scrypt.

    Le résultat est mis en cache (LRU 256 entrées) pour éviter de recalculer
    la clé lors du déchiffrement de milliers de messages de la même session.
    La clé du cache est (sha256(passphrase), sel) — la passphrase en clair
    n'est jamais stockée dans le cache.
    """
    return _derive_key_cached(hashlib.sha256(passphrase).digest(), salt)


@lru_cache(maxsize=256)
def _derive_key_cached(passphrase_hash: bytes, salt: bytes) -> bytes:
    """
    Version cachée de la dérivation — prend le hash de la passphrase, pas
    la passphrase elle-même, pour ne pas la conserver en mémoire du cache.
    """
    if not _CRYPTO_OK:
        raise CryptoUnavailableError(
            "Le module 'cryptography' est requis pour le chiffrement. "
            "Installez-le avec : pip install cryptography"
        )
    kdf = Scrypt(salt=salt, length=KEY_LEN, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P)
    return kdf.derive(passphrase_hash)   # on dérive depuis le hash, pas la passphrase brute


def clear_key_cache() -> None:
    """Purge le cache de clés dérivées. À appeler à la fermeture de l'application."""
    _derive_key_cached.cache_clear()


# ── API publique ──────────────────────────────────────────────────────────────

def is_encrypted(value: str) -> bool:
    """
    Retourne True si 'value' est un blob chiffré par ce module.
    Permet de distinguer les valeurs en clair (base existante) des valeurs chiffrées.
    """
    if not value:
        return False
    try:
        raw = base64.b85decode(value.encode())
        return raw[:MAGIC_LEN] == MAGIC
    except Exception:
        return False


def encrypt(plaintext: str, passphrase: str) -> str:
    """
    Chiffre 'plaintext' avec AES-256-GCM et retourne un blob base85.

    Chaque appel génère un sel et un nonce aléatoires → deux chiffrements
    du même texte produisent des blobs différents (sémantique IND-CPA).

    Raises
    ------
    CryptoUnavailableError : si 'cryptography' n'est pas installé.
    ValueError             : si passphrase est vide.
    """
    if not passphrase:
        raise ValueError("La passphrase ne peut pas être vide.")
    if not _CRYPTO_OK:
        raise CryptoUnavailableError(
            "Le module 'cryptography' est requis. pip install cryptography"
        )

    salt  = os.urandom(SALT_LEN)
    nonce = os.urandom(NONCE_LEN)
    key   = _derive_key(passphrase.encode("utf-8"), salt)

    aes = AESGCM(key)
    ciphertext = aes.encrypt(nonce, plaintext.encode("utf-8"), None)
    # ciphertext inclut le tag GCM de 128 bits en suffixe (comportement de la lib)

    blob = MAGIC + salt + nonce + ciphertext
    return base64.b85encode(blob).decode("ascii")


def decrypt(value: str, passphrase: str) -> str:
    """
    Déchiffre un blob produit par encrypt().

    Si 'value' n'est pas un blob chiffré (base existante en clair),
    la valeur est retournée telle quelle — migration transparente.

    Raises
    ------
    CryptoError : si la passphrase est incorrecte ou le blob corrompu.
    CryptoUnavailableError : si 'cryptography' n'est pas installé.
    """
    if not value:
        return value

    # Détecter si la valeur est un blob chiffré
    if not is_encrypted(value):
        return value   # valeur en clair — base existante, retour transparent

    if not _CRYPTO_OK:
        raise CryptoUnavailableError(
            "Le module 'cryptography' est requis. pip install cryptography"
        )
    if not passphrase:
        raise CryptoError("Passphrase manquante pour déchiffrer.")

    try:
        raw = base64.b85decode(value.encode())
    except Exception as e:
        raise CryptoError(f"Blob base85 invalide : {e}") from e

    if len(raw) < _HEADER_LEN + 1:
        raise CryptoError("Blob trop court pour être valide.")

    # Découper les composants
    magic      = raw[:MAGIC_LEN]
    salt       = raw[MAGIC_LEN : MAGIC_LEN + SALT_LEN]
    nonce      = raw[MAGIC_LEN + SALT_LEN : _HEADER_LEN]
    ciphertext = raw[_HEADER_LEN:]

    if magic != MAGIC:
        raise CryptoError("Marqueur magique invalide — blob corrompu.")

    key = _derive_key(passphrase.encode("utf-8"), salt)
    aes = AESGCM(key)

    try:
        plaintext = aes.decrypt(nonce, ciphertext, None)
    except InvalidTag as e:
        raise CryptoError(
            "Déchiffrement impossible : passphrase incorrecte ou données corrompues."
        ) from e
    except Exception as e:
        raise CryptoError(f"Erreur AES-GCM : {e}") from e

    return plaintext.decode("utf-8")


def verify_passphrase(passphrase: str, sentinel_encrypted: str) -> bool:
    """
    Vérifie une passphrase en tentant de déchiffrer un sentinel connu.
    Retourne True si le déchiffrement réussit, False sinon.

    Usage dans HistoryDB : un enregistrement 'sentinel' est stocké dans
    la table 'kv_store' à la création de la base chiffrée. Il permet de
    valider la passphrase sans avoir à déchiffrer un vrai message.
    """
    try:
        result = decrypt(sentinel_encrypted, passphrase)
        return result == _SENTINEL_PLAINTEXT
    except CryptoError:
        return False


_SENTINEL_PLAINTEXT = "prométhée-sentinel-v1"


def create_sentinel(passphrase: str) -> str:
    """Crée un sentinel chiffré pour vérification ultérieure de la passphrase."""
    return encrypt(_SENTINEL_PLAINTEXT, passphrase)
