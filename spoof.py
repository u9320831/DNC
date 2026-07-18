import asyncio
import subprocess
import logging
import aiohttp
import socket
from aiohttp_socks import ProxyConnector
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional

# --- Configuration Logging ---
logger = logging.getLogger("spoof")

# ==========================================
# 1. Gestion des processus Tor (Original)
# ==========================================

def Spoof(torcc_path: str, port: int) -> int:
    """Lance le processus Tor."""
    try:
        process = subprocess.Popen(
            ["Tor\\tor.exe", "-f", torcc_path],
            stdout=subprocess.DEVNULL, 
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        return process.pid
    except Exception as e:
        print(f"[-] Erreur de lancement Tor sur le port {port} : {e}")
        return -1

# ==========================================
# 2. Framework Asynchrone (Intégré)
# ==========================================

@dataclass
class TorInstance:
    idx: int
    socks_port: int
    control_port: int
    control_password: Optional[str] = None
    control_cookie_path: Optional[str] = None
    max_concurrency: int = 5

    @property
    def proxy_url(self) -> str:
        return f"socks5://127.0.0.1:{self.socks_port}"

class TorController:
    def __init__(self, instance: TorInstance):
        self.instance = instance

    async def _send(self, writer, reader, line: str) -> str:
        writer.write((line + "\r\n").encode())
        await writer.drain()
        data = await reader.readline()
        return data.decode(errors="replace").strip()

    async def new_identity(self) -> None:
        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", self.instance.control_port)
            # Authentification simplifiée
            if self.instance.control_cookie_path:
                with open(self.instance.control_cookie_path, "rb") as f:
                    cookie_hex = f.read().hex()
                await self._send(writer, reader, f"AUTHENTICATE {cookie_hex}")
            else:
                await self._send(writer, reader, "AUTHENTICATE")
            
            await self._send(writer, reader, "SIGNAL NEWNYM")
            writer.close()
            await writer.wait_closed()
        except Exception as e:
            logger.error(f"Erreur NEWNYM instance {self.instance.idx}: {e}")

class TorPool:
    def __init__(self, instances: list[TorInstance], handler: Callable):
        self.instances = instances
        self.handler = handler
        self.queue: asyncio.Queue = asyncio.Queue()
        self.results = []
        self._stop_sentinel = object()

    def add_task(self, task: dict):
        self.queue.put_nowait(task)

    async def _worker(self, instance: TorInstance):
        connector = ProxyConnector.from_url(instance.proxy_url)
        async with aiohttp.ClientSession(connector=connector) as session:
            sem = asyncio.Semaphore(instance.max_concurrency)
            while True:
                task = await self.queue.get()
                if task is self._stop_sentinel:
                    self.queue.task_done()
                    break
                async with sem:
                    try:
                        res = await self.handler(session, instance, task)
                        self.results.append(res)
                    except Exception as e:
                        # Auto NEWNYM en cas d'erreur
                        await TorController(instance).new_identity()
                        self.results.append({"error": str(e), "task": task})
                self.queue.task_done()

    async def run(self, workers_per_instance: int = 1):
        tasks = [asyncio.create_task(self._worker(inst)) 
                 for inst in self.instances for _ in range(workers_per_instance)]
        await self.queue.join()
        for _ in tasks: self.queue.put_nowait(self._stop_sentinel)
        await asyncio.gather(*tasks)
        return self.results
    
def NewNym(control_port: int):
    try:
        with socket.create_connection(("127.0.0.1", control_port)) as sock:
            sock.sendall(b"AUTHENTICATE\r\nSIGNAL NEWNYM\r\n")
    except Exception as e:
        print(f"[-] Erreur dans spoof.NewNym (Port {control_port}): {e}")