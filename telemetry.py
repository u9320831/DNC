import psutil
import picologging as logging
import time
import orjson
import csv
from dataclasses import dataclass, field
from typing import Dict, Any, List
from datetime import datetime, timezone
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger()

@dataclass
class Telemetry:
    TorData: Dict[int, Any] = field(default_factory=dict)
    history: List[Dict[str, Any]] = field(default_factory=list)
    process_name: str = "tor"

    def snapshot(self) -> Dict[str, Any]:
        total_rss = 0
        total_vms = 0
        cpu_total = 0.0
        self.TorData.clear()

        for proc in psutil.process_iter(['pid', 'name', 'memory_info', 'cpu_percent',
                                          'create_time', 'num_threads']):
            try:
                name = proc.info['name'] or ""
                if self.process_name.lower() in name.lower():
                    mem = proc.info['memory_info']
                    cpu = proc.info['cpu_percent'] or 0.0

                    total_rss += mem.rss
                    total_vms += mem.vms
                    cpu_total += cpu

                    self.TorData[proc.info['pid']] = {
                        "rss_mb": round(mem.rss / (1024 * 1024), 2),
                        "vms_mb": round(mem.vms / (1024 * 1024), 2),
                        "cpu_percent": cpu,
                        "num_threads": proc.info['num_threads'],
                        "uptime_s": round(time.time() - proc.info['create_time'], 1),
                    }
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue

        record = {
            "timestamp": datetime.now(timezone.utc),
            "n_instances": len(self.TorData),
            "total_rss_mb": round(total_rss / (1024 * 1024), 2),
            "total_vms_mb": round(total_vms / (1024 * 1024), 2),
            "total_cpu_percent": round(cpu_total, 2),
            "per_pid": {str(pid): data for pid, data in self.TorData.items()},
        }
        self.history.append(record)
        return record

    def save_csv(self, path: str = "tor_dataset.csv"):
        file_exists = Path(path).exists()
        with open(path, "a", newline="") as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(["timestamp", "n_instances", "total_rss_mb",
                                  "total_vms_mb", "total_cpu_percent"])
            for r in self.history:
                writer.writerow([r["timestamp"].isoformat(), r["n_instances"],
                                  r["total_rss_mb"], r["total_vms_mb"], r["total_cpu_percent"]])

    def save_json(self, path: str = "tor_dataset.jsonl"):
        with open(path, "ab") as f:  
            for r in self.history:
                f.write(orjson.dumps(r, option=orjson.OPT_NAIVE_UTC) + b"\n")
        self.history.clear()  


def collect_loop(interval_s: int = 30, duration_s: int = 3600):
    telemetry = Telemetry()
    end_time = time.time() + duration_s

    while time.time() < end_time:
        record = telemetry.snapshot()
        logger.info(f"{record['timestamp'].isoformat()} | instances={record['n_instances']} "
                     f"| RSS={record['total_rss_mb']}MB | CPU={record['total_cpu_percent']}%")
        telemetry.save_json()
        time.sleep(interval_s)


# if __name__ == "__main__":
#     collect_loop(interval_s=10, duration_s=3600)