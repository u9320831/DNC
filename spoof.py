import asyncio
import subprocess
import logging
import sys
import random
from curl_cffi.requests import AsyncSession
from dataclasses import dataclass
from typing import Optional, Callable
from stem.control import Controller
from stem import ControllerError
import time
import pandas as pd
import socket
from dataclasses import asdict
from collections import defaultdict

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
        # On utilise 'ip' au lieu de 'idx' pour plus de clarté
        if ip not in self.registry:
            self.Init_Ip(ip)
        
        state = self.registry[ip]
        state.ratelimits = ratelimit
        state.blocked = blocked
        
        if ratelimit or blocked:
            state.resume_at = time.time() + duration
        else:
            state.resume_at = 0.0

    def Show(self, ip: str): # On attend toujours l'IP ici
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
        # L'utilisation de socks5h force la résolution DNS via Tor[cite: 8]
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
                        # On passe self.queue au handler pour permettre la réinjection[cite: 8, 16]
                        await self.handler(session, instance, task, self.queue)
                        if random.random() < 0.15:
                            await TorController(instance).new_identity()
                    except Exception as e:
                        logger.error(f"Erreur task {task.get('pseudo')}: {e}")
                        await TorController(instance).new_identity()
                        # Réinjection automatique en cas d'échec[cite: 8, 16]
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

def get_current_ip(control_port: int) -> str | None:
    """
    Récupère l'IP du noeud de sortie Tor en interrogeant directement 
    le Control Port via un socket TCP brut, sans utiliser stem.
    """
    try:
        # On ouvre un socket basique avec un timeout court (3 sec)
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(3.0)
            s.connect(('127.0.0.1', control_port))
            
            # Utilisation de makefile pour lire facilement ligne par ligne
            f = s.makefile('rw', encoding='utf-8')
            
            # 1. Authentification (force "rien")
            f.write('AUTHENTICATE ""\r\n')
            f.flush()
            if "250 OK" not in f.readline():
                return None

            # 2. Récupérer les circuits pour trouver le noeud de sortie
            f.write('GETINFO circuit-status\r\n')
            f.flush()
            
            exit_fingerprint = None
            while True:
                line = f.readline()
                if not line or line.strip() == "250 OK":
                    break
                
                # On cherche le premier circuit construit (BUILT)
                # Exemple de réponse Tor : "1 BUILT $A,$B,$C PURPOSE=GENERAL"
                if " BUILT " in line:
                    parts = line.split()
                    if len(parts) > 2:
                        path = parts[2] # Le chemin, ex: "$FP1,$FP2,$FP3"
                        nodes = path.split(',')
                        last_node = nodes[-1] # Le dernier noeud est la sortie
                        
                        # Nettoyage : retirer le '$' et tout nom après '~' ou '='
                        clean_fingerprint = last_node.replace('$', '').split('~')[0].split('=')[0]
                        
                        if len(clean_fingerprint) == 40: # Un fingerprint fait 40 caractères
                            exit_fingerprint = clean_fingerprint
                            break
            
            # Vider le buffer des lignes restantes de la commande circuit-status
            while line and line.strip() != "250 OK":
                line = f.readline()

            if not exit_fingerprint:
                return None

            # 3. Demander les infos réseau de ce noeud spécifique pour avoir son IP
            f.write(f'GETINFO ns/id/{exit_fingerprint}\r\n')
            f.flush()
            
            ip = None
            while True:
                line = f.readline()
                if not line or line.strip() == "250 OK":
                    break
                
                # La ligne avec l'IP commence toujours par "r "
                # Exemple : "r nickname base_id base_dig 2026-07-19 12:00:00 192.168.1.1 9001 0"
                if line.startswith("r "):
                    r_parts = line.split()
                    if len(r_parts) >= 7:
                        ip = r_parts[6] # L'IP se trouve en 7ème position
                        
            # 4. Fermeture ultra-propre pour éviter le WinError 10038
            f.write('QUIT\r\n')
            f.flush()
            
            return ip

    except Exception:
        # En cas de SocketClosed ou autre problème de connexion
        return None

# 1. On crée un dictionnaire de verrous (un par port)
# Cela garantit qu'une seule tâche ne parle à un port Tor à la fois.
port_locks = defaultdict(asyncio.Lock)

async def NewNymAsync(registry, control_port: int, wait: float = 0.5, max_retries: int = 1):
    """
    Tente d'obtenir une IP propre via rotation avec verrouillage de port.
    """
    
    # On récupère le verrou spécifique à ce port
    async with port_locks[control_port]:
        
        async def send_signal():
            try:
                reader, writer = await asyncio.open_connection("127.0.0.1", control_port)
                writer.write(b"SIGNAL NEWNYM\r\n")
                await writer.drain()
                # On attend une réponse rapide pour confirmer que Tor est vivant
                await reader.read(1024) 
                writer.close()
                await writer.wait_closed()
                return True
            except Exception as e:
                print(f"[-] Erreur socket sur {control_port}: {e}")
                return False

        for attempt in range(max_retries):
            success = await send_signal()
            
            if not success:
                continue
                
            await asyncio.sleep(wait) 
            
            # 2. Récupération de l'IP (Assurez-vous que cette fonction est rapide)
            new_ip = get_current_ip(control_port) 
            
            # 3. Vérification registre
            output = registry.Show(new_ip)
            if output is None:
                registry.Init_Ip(new_ip)
                output = registry.Show(new_ip)

            now = time.time()

            # --- Logique de validation ---
            
            # Cas A: IP saine
            if not output.blocked and not output.ratelimits:
                return new_ip

            # Cas B: IP en Rate Limit
            elif output.ratelimits:
                remaining = output.resume_at - now
                if 0 < remaining <= 5:
                    await asyncio.sleep(remaining)
                    return new_ip
                else:
                    # Trop long, on force une autre boucle
                    continue

            # Cas C: IP bloquée
            elif output.blocked:
                # Continue la boucle pour tenter une nouvelle rotation
                continue
        return None