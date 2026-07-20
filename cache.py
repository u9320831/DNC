import os
import orjson
from pathlib import Path

class SmartCache:
    def __init__(self, filepath: str = "cache.json"):
        self.filepath = Path(filepath)
        self.cache = self._load()
        self.counter = 0

    def _load(self) -> dict:
        if self.filepath.exists():
            try:
                with open(self.filepath, "rb") as f:
                    return orjson.loads(f.read())
            except Exception:
                return {}
        return {}

    def get(self, pseudo: str) -> str | None:
        """Renvoie le statut du pseudo s'il est déjà connu (ex: 'taken')."""
        return self.cache.get(pseudo)

    def set(self, pseudo: str, status: str):
        """Enregistre le statut d'un pseudo et sauvegarde périodiquement."""
        self.cache[pseudo] = status
        self.counter += 1
        
        # Sauvegarde automatique toutes les 50 découvertes pour éviter d'écrire à chaque requête
        if self.counter >= 50:
            self.save()
            self.counter = 0

    def save(self):
        """Sauvegarde définitive du cache sur le disque."""
        try:
            with open(self.filepath, "wb") as f:
                f.write(orjson.dumps(self.cache, option=orjson.OPT_INDENT_2))
        except Exception as e:
            print(f"[-] Erreur de sauvegarde du cache : {e}")

# Instance globale partagée
global_cache = SmartCache()