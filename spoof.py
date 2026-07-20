import asyncio
import subprocess
import logging
import sys
import random
from curl_cffi.requests import AsyncSession
from dataclasses import dataclass
from typing import Optional, Callable
import time
import socket
from collections import defaultdict
import os
import shutil

from macro import MacroTorcc 

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("spoof")

@dataclass
class ProxyState:
    id: str  
    resume_at: float = 0.0
    ratelimits: bool = False
    rate_for: float = 300
    blocked: bool = False

class ProxyRegistry:
    def __init__(self):
        self.registry = {}

    def Init_Ip(self, ip: str):
        self.registry[ip] = ProxyState(id=ip)

    def Update(self, ip: str, ratelimit: bool = False, blocked: bool = False, duration: int = 60):
        if ip not in self.registry:
            self.Init_Ip(ip)
        
        state = self.registry[ip]
        state.ratelimits = ratelimit
        state.blocked = blocked
        
        if ratelimit or blocked:
            state.resume_at = time.time() + duration
        else:
            state.resume_at = 0.0

    def Show(self, ip: str):
        return self.registry.get(ip)
    
global_registry = ProxyRegistry()

def Spoof(torcc_path: str, port: int) -> int:
    """Lance Tor avec des flags système pour cacher la fenêtre sur Windows."""
    cmd = ["tor", "-f", torcc_path]
    popen_args = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}

    if sys.platform == "win32":
        popen_args["creationflags"] = subprocess.CREATE_NO_WINDOW
        cmd = ["Tor\\tor.exe", "-f", torcc_path]

    try:
        process = subprocess.Popen(cmd, **popen_args)
        return process.pid
    except Exception as e:
        logger.error(f"[-] Erreur de lancement Tor (Port {port}): {e}")
        return -1

@dataclass
class TorInstance:
    idx: int
    socks_port: int
    control_port: int
    control_cookie_path: Optional[str] = None
    max_concurrency: int = 25

    @property
    def proxy_url(self) -> str:
        return f"socks5h://127.0.0.1:{self.socks_port}"

    def get_newnym_wait(self) -> float:
        """Retourne un délai dynamique pour laisser le circuit Tor se stabiliser."""
        return random.uniform(1, 2.0)

class TorController:
    def __init__(self, instance: TorInstance):
        self.instance = instance

    async def new_identity(self) -> None:
        await NewNymAsync(
            global_registry, 
            self.instance.control_port, 
            wait=self.instance.get_newnym_wait()
        )

class TorPool:
    def __init__(self, instances: list[TorInstance], handler: Callable):
        self.instances = instances
        self.handler = handler
        self.queue: asyncio.Queue = asyncio.Queue()
        self._stop_sentinel = object()

    def add_task(self, task: dict):
        self.queue.put_nowait(task)

    async def _worker(self, semaphore: asyncio.Semaphore, instance: TorInstance):
        browsers = ["chrome124", "chrome126", "edge124"]
        
        async with AsyncSession(
            impersonate=random.choice(browsers), 
            proxies={"http": instance.proxy_url, "https": instance.proxy_url},
            timeout=20
        ) as session:
            while True:
                task = await self.queue.get()
                if task is self._stop_sentinel:
                    self.queue.task_done()
                    break
                
                async with semaphore:
                    try:
                        await self.handler(session, instance, task, self.queue)
                        if random.random() < 0.15:
                            await TorController(instance).new_identity()
                    except Exception as e:
                        logger.error(f"Erreur task {task.get('pseudo')}: {e}")
                        await TorController(instance).new_identity()
                        await asyncio.sleep(1.0)
                        self.queue.put_nowait(task)
                
                self.queue.task_done()

    async def run(self, workers_per_instance: int = 1):
        tasks = []
        for inst in self.instances:
            sem = asyncio.Semaphore(inst.max_concurrency)
            for _ in range(workers_per_instance):
                tasks.append(asyncio.create_task(self._worker(sem, inst)))
        
        await self.queue.join()
        for _ in tasks: self.queue.put_nowait(self._stop_sentinel)
        await asyncio.gather(*tasks)

class TorManager:
    def __init__(self, initial_count=5, max_instances=20):
        self.active_processes = {}
        self.current_id_counter = 0 
        self.initial_count = initial_count
        self.max_instances = max_instances

    def start_initial_pool(self):
        print(f"[*] Démarrage du pool initial : {self.initial_count} instances...")
        for _ in range(self.initial_count):
            self.add_instance()

    def add_instance(self):
        if len(self.active_processes) >= self.max_instances:
            print("[!] Limite maximale d'instances atteinte.")
            return None

        self.current_id_counter += 1
        instance_id = self.current_id_counter
        
        MacroTorcc(instance_id)
        
        try:
            process = subprocess.Popen(
                ["Tor\\tor.exe" if sys.platform == "win32" else "tor", "-f", f"torcc{instance_id}"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            )
            self.active_processes[instance_id] = process
            print(f"[+] Instance {instance_id} démarrée avec succès (PID: {process.pid})")
            return instance_id
        except Exception as e:
            print(f"[-] Échec du lancement de l'instance {instance_id}: {e}")
            return None

    def remove_instance(self, instance_id):
        if instance_id in self.active_processes:
            process = self.active_processes[instance_id]
            print(f"[*] Arrêt de l'instance {instance_id}...")
            process.terminate()
            process.wait() 
            
            del self.active_processes[instance_id]
            
            try:
                if os.path.exists(f"torcc{instance_id}"):
                    os.remove(f"torcc{instance_id}")
                
                data_dir = f"Tor/data{instance_id}"
                if os.path.exists(data_dir):
                    shutil.rmtree(data_dir)
                    
                print(f"[+] Fichiers de l'instance {instance_id} nettoyés.")
            except Exception as e:
                print(f"[-] Erreur de nettoyage {instance_id}: {e}")

def get_current_ip(control_port: int) -> str | None:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(3.0)
            s.connect(('127.0.0.1', control_port))
            
            f = s.makefile('rw', encoding='utf-8')
            
            f.write('AUTHENTICATE ""\r\n')
            f.flush()
            if "250 OK" not in f.readline():
                return None

            f.write('GETINFO circuit-status\r\n')
            f.flush()
            
            exit_fingerprint = None
            while True:
                line = f.readline()
                if not line or line.strip() == "250 OK":
                    break
                
                if " BUILT " in line:
                    parts = line.split()
                    if len(parts) > 2:
                        path = parts[2]
                        nodes = path.split(',')
                        last_node = nodes[-1]
                        
                        clean_fingerprint = last_node.replace('$', '').split('~')[0].split('=')[0]
                        
                        if len(clean_fingerprint) == 40:
                            exit_fingerprint = clean_fingerprint
                            break
            
            while line and line.strip() != "250 OK":
                line = f.readline()

            if not exit_fingerprint:
                return None

            f.write(f'GETINFO ns/id/{exit_fingerprint}\r\n')
            f.flush()
            
            ip = None
            while True:
                line = f.readline()
                if not line or line.strip() == "250 OK":
                    break
                
                if line.startswith("r "):
                    r_parts = line.split()
                    if len(r_parts) >= 7:
                        ip = r_parts[6]
                        
            f.write('QUIT\r\n')
            f.flush()
            
            return ip

    except Exception:
        return None

port_locks = defaultdict(asyncio.Lock)

async def NewNymAsync(registry, control_port: int, wait: float = 0.5, max_retries: int = 5):
    """
    Tente d'obtenir une IP propre via rotation avec verrouillage de port 
    et gestion des retries pendant le démarrage de Tor.
    """
    async with port_locks[control_port]:
        
        async def send_signal():
            # On laisse plusieurs essais si le port n'est pas encore ouvert (démarrage de Tor)
            for attempt in range(max_retries):
                try:
                    reader, writer = await asyncio.open_connection("127.0.0.1", control_port)
                    writer.write(b"SIGNAL NEWNYM\r\n")
                    await writer.drain()
                    await reader.read(1024)
                    writer.close()
                    await writer.wait_closed()
                    return True
                except (ConnectionRefusedError, OSError):
                    # Tor est en train de démarrer, on patiente brièvement avant de réessayer
                    if attempt < max_retries - 1:
                        await asyncio.sleep(1.0)
                    else:
                        return False
                except Exception as e:
                    logger.warning(f"[-] Erreur inattendue sur le control port {control_port}: {e}")
                    return False
            return False

        success = await send_signal()
        if not success:
            logger.warning(f"[-] Control port {control_port} injoignable, instance ignorée désormais.")
            return None
            
        await asyncio.sleep(wait) 
        
        new_ip = get_current_ip(control_port) 
        if not new_ip:
            return None
            
        output = registry.Show(new_ip)
        if output is None:
            registry.Init_Ip(new_ip)
            output = registry.Show(new_ip)

        now = time.time()
        
        if not output.blocked and not output.ratelimits:
            return new_ip

        elif output.ratelimits:
            remaining = output.resume_at - now
            if 0 < remaining <= 5:
                await asyncio.sleep(remaining)
                return new_ip

        return new_ip