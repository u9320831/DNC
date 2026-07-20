import asyncio
import picologging as logging
from dataclasses import dataclass, field
from sklearn.ensemble import IsolationForest 
import orjson
import psutil
import numpy as np
from pathlib import Path
import shutil
import time
import os
from config import config

import macro
import telemetry

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger()

@dataclass
class Manager:
    path: Path = field(default_factory=lambda: Path("config.json"))

    def __post_init__(self):
        if not self.path.exists():
            try:
                initial_data = {
                    "user_mode": {
                        "length": 4,
                        "webhook_url": "",
                        "charset": "0123456789abcdefghijklmnopqrstuvwxyz._"
                    },
                    "provider": {}
                }
                with open(self.path, "wb") as f:
                    f.write(orjson.dumps(initial_data, option=orjson.OPT_INDENT_2))
            except Exception as e:
                logging.info(f"Erreur de création initiale du JSON : {e}")

        try:
            with open(self.path, "rb") as f:
                self.data = orjson.loads(f.read())
        except Exception as e:
            logging.info(f"[-] Erreur de lecture du JSON : {e}")
            self.data = {"user_mode": {}, "provider": {}}

    def _add(self):
        providers = self.data.get("provider", {})

        if providers:
            indexes = [int(k) for k in providers.keys()]
            next_idx = max(indexes) + 1
            last_provider = providers[str(max(indexes))]
            next_socks = last_provider["socks_port"] + 2
            next_control = last_provider["control_port"] + 2
        else:
            next_idx = 0
            next_socks = 9050
            next_control = 9051

        result = macro.MacroTorcc(str(next_socks), str(next_control), str(next_idx))

        if result != 1:
            logging.info(f"[-] Échec de génération du torcc pour le Provider #{next_idx}")
            return

        tor_exe = "Tor\\tor.exe" 
        torcc_path = f"Tor\\torcc{next_idx}"

        try:
            import subprocess
            proc = subprocess.Popen(
                [tor_exe, "-f", torcc_path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        except Exception as e:
            logging.info(f"[-] Erreur lors du lancement physique de Tor pour le Provider #{next_idx} : {e}")
            return

        self.data["provider"][str(next_idx)] = {
            "socks_port": next_socks,
            "control_port": next_control,
            "torcc": torcc_path,
            "pid": proc.pid
        }

        with open(self.path, "wb") as f:
            f.write(orjson.dumps(self.data, option=orjson.OPT_INDENT_2))

        logging.info(f"[+] Provider #{next_idx} créé, lancé (PID {proc.pid}) et sauvegardé avec succès !")

    def _remove(self):
        providers = self.data.get("provider", {})

        if not providers:
            logging.info("Aucun provider à supprimer dans le fichier de configuration.")
            return

        indexes = [int(k) for k in providers.keys()]
        last_idx = max(indexes)
        str_last_idx = str(last_idx)

        provider_settings = providers.get(str_last_idx, {})
        pid = provider_settings.get("pid")

        if pid:
            try:
                proc = psutil.Process(pid)
                proc.kill()
                proc.wait(timeout=10)  
            except psutil.NoSuchProcess:
                logging.info(f"[~] PID {pid} déjà terminé.")
            except psutil.TimeoutExpired:
                logging.warning(f"[!] PID {pid} ne répond pas après kill, nouvelle tentative...")
                try:
                    proc.kill()
                    proc.wait(timeout=5)
                except Exception as e:
                    logging.error(f"[-] Impossible de tuer le PID {pid} : {e}")

            if psutil.pid_exists(pid):
                logging.error(f"[-] Le process {pid} est toujours vivant, abandon de la suppression des fichiers.")
                return
        else:
            logging.info("[~] Aucun PID enregistré pour ce provider, suppression directe des fichiers.")

        time.sleep(0.5)

        tor_dir = Path("Tor")
        data_dir = tor_dir / f"data{last_idx}"
        torcc_file = tor_dir / f"torcc{last_idx}"

        if torcc_file.exists():
            for attempt in range(5):
                try:
                    torcc_file.unlink()
                    break
                except PermissionError:
                    if attempt == 4:
                        raise
                    time.sleep(0.3)

        if data_dir.exists() and data_dir.is_dir():
            for attempt in range(10):
                try:

                    if os.path.exists(data_dir):
                        shutil.rmtree(data_dir)
                    break
                except PermissionError:
                    if attempt < 9:
                        time.sleep(0.5)  
                    else:
                        print(f"[!] Avertissement : Impossible de nettoyer le dossier {data_dir} (verrouillé).")
                    break

        del self.data["provider"][str_last_idx]

        with open(self.path, "wb") as f:
            f.write(orjson.dumps(self.data, option=orjson.OPT_INDENT_2))

        logging.info(f"[-] Provider #{last_idx} supprimé.")

    def live(self):
        provider_ = self.data.get("provider", {})
        return len(provider_)

class TorAnomalyManager:
    def __init__(self, contamination: float = 0.05, warmup_s: int = 300):
        self.model = IsolationForest(contamination=contamination, random_state=42)
        self.warmup_s = warmup_s 

    def analyze_and_mitigate(self, tor_data: dict):
        if not tor_data:
            return []

        mature_pids = [
            pid for pid, info in tor_data.items()
            if info["uptime_s"] >= self.warmup_s
        ]

        if len(mature_pids) < 5:
            return []

        features = []
        for pid in mature_pids:
            info = tor_data[pid]
            features.append([
                info["rss_mb"],
                info["cpu_percent"],
                info["num_threads"],
                info["uptime_s"]
            ])

        X = np.array(features)
        predictions = self.model.fit_predict(X)

        anomalous_pids = []
        for pid, pred in zip(mature_pids, predictions):
            if pred == -1:
                anomalous_pids.append(pid)
                self.terminate_instance(pid)

        return anomalous_pids

    def terminate_instance(self, pid: int):
        try:
            proc = psutil.Process(pid)
            proc.terminate()
            print(f"[-] Isolation Forest : Instance Tor anormale (PID {pid}) stoppée en live.")
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    def can_add_instance(self) -> bool:
        mem = psutil.virtual_memory()
        cpu = psutil.cpu_percent(interval=None)

        if mem.percent < config.SAFE_MEMORY_LOCK and cpu < config.SAFE_CPU_LOCK:
            return True
        return False

def _controllers(interval_s: int = 30, duration_s: int = 3600):
    manager = Manager()
    telemetry_ = telemetry.Telemetry()
    anomaly_manager = TorAnomalyManager(contamination=0.03)
    end_time = time.time() + duration_s

    while time.time() < end_time:
        record = telemetry_.snapshot()  
        
        logger.info(f"{record['timestamp'].isoformat()} | instances={record['n_instances']} "
                    f"| RSS={record['total_rss_mb']}MB | CPU={record['total_cpu_percent']}%")
        
        flagged_pids = anomaly_manager.analyze_and_mitigate(telemetry_.TorData)
        if flagged_pids:
            logger.warning(f"[!] Instances Tor isolées et purgées : {flagged_pids}")
            for _ in flagged_pids:
                manager._remove()

        if anomaly_manager.can_add_instance():
            logger.info("[+] Ressources suffisantes détectées : Lancement d'une nouvelle instance Tor...")
            manager._add()
        else:
            logger.info("[~] Ressources limites ou saturées : Aucun ajout d'instance pour le moment.")

        time.sleep(interval_s)