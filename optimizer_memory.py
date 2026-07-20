import os
import orjson
from pathlib import Path
from config import config

class OptimizerMemory:
    def __init__(self, filepath: str = "optimizer_dataset.json", clear_on_start: bool = False):
        self.filepath = Path(filepath)
        
        if clear_on_start and self.filepath.exists():
            try:
                self.filepath.unlink()
                print("[Optimizer] Dataset précédent nettoyé au démarrage.")
            except Exception:
                pass
                
        self.dataset = self._load()

    def _load(self) -> list:
        if self.filepath.exists():
            try:
                with open(self.filepath, "rb") as f:
                    data = orjson.loads(f.read())
                    if not isinstance(data, list):
                        return []
                    for entry in data:
                        if isinstance(entry, dict):
                            entry.setdefault("requests_per_session", getattr(config, "requests_per_session", getattr(config, "max_requests_per_session", 100)))
                    return data
            except Exception as e:
                print(f"[Optimizer] Impossible de charger le dataset : {e}")
                return []
        return []

    def record_run(self, concurrency: int, sleep_min: float, sleep_max: float, success_score: float, block_rate: float):
        entry = {
            "concurrency": concurrency,
            "sleep_min": sleep_min,
            "sleep_max": sleep_max,
            "success_score": success_score,
            "block_rate": block_rate,
            "requests_per_session": getattr(config, "requests_per_session", getattr(config, "max_requests_per_session", 100))
        }
        self.dataset.append(entry)
        self.save()

    def ingest_external_data(self, file_path: str):
        path = Path(file_path)
        if not path.exists():
            print(f"[Optimizer] Fichier externe introuvable : {file_path}")
            return
        
        new_entries_count = 0
        try:
            with open(path, "rb") as f:
                for line in f:
                    if line.strip():
                        record = orjson.loads(line)
                        
                        n_instances = record.get("n_instances", 10)
                        total_cpu = record.get("total_cpu_percent", 0.0)
                        
                        success_score = max(0.0, 100.0 - total_cpu)
                        block_rate = min(1.0, total_cpu / 100.0)
                        
                        entry = {
                            "concurrency": n_instances,
                            "sleep_min": getattr(config, "sleep_min", 0.5),
                            "sleep_max": getattr(config, "sleep_max", 2.0),
                            "success_score": success_score,
                            "block_rate": block_rate,
                            "requests_per_session": getattr(config, "requests_per_session", getattr(config, "max_requests_per_session", 100))
                        }
                        
                        self.dataset.append(entry)
                        new_entries_count += 1
                        
            if new_entries_count > 0:
                self.save()
                print(f"[Optimizer] {new_entries_count} entrées de télémétrie ingérées depuis {file_path}.")
                
        except Exception as e:
            print(f"[Optimizer] Échec de l’ingestion du fichier {file_path} : {e}")

    def get_learning_recommendation(self, lookback: int = 20):
        if not self.dataset:
            return None

        history = [entry for entry in self.dataset if isinstance(entry, dict)]
        if not history:
            return None

        if lookback is not None:
            history = history[-max(1, lookback):]

        best_entry = None
        best_score = float("-inf")

        for index, entry in enumerate(history):
            success_score = float(entry.get("success_score", 0.0))
            block_rate = float(entry.get("block_rate", 0.0))
            requests_per_session = float(entry.get("requests_per_session", getattr(config, "max_requests_per_session", 100)))

            quality = success_score - (block_rate * 3.0)
            if requests_per_session > 0:
                quality += min(0.15, requests_per_session / max(1.0, float(getattr(config, "max_requests_per_session", 100))) * 0.15)

            recency_weight = 1.0 + (0.02 * (len(history) - index))
            weighted_score = quality * recency_weight

            if weighted_score > best_score:
                best_score = weighted_score
                best_entry = entry

        return best_entry

    def get_optimal_defaults(self):
        return self.get_learning_recommendation(lookback=None)

    def save(self):
        temp_path = self.filepath.with_suffix(".tmp")
        try:
            with open(temp_path, "wb") as f:
                f.write(orjson.dumps(self.dataset, option=orjson.OPT_INDENT_2))
            temp_path.replace(self.filepath)
        except Exception as e:
            print(f"[Optimizer] Échec de la sauvegarde du dataset : {e}")
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except:
                    pass

optimizer_memory = OptimizerMemory(clear_on_start=False)