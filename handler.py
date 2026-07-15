from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor
from collections import deque
import sys
import asyncio 
import datetime
import time
import json

######################################## Modules ########################################
from engine import Generate, Requests
from spoof import Spoof, NewNym

with open('config.json','r') as f:
    data = json.load(f)

free_pseudo = []

result = {
    "fail": 0,
    "success": 0
}

@dataclass
class Core:
    port: int = 0
    control_port: int = 0
    torcc_path: str = ""
    fl: list = field(default_factory=list)
    time_start: int = 0

    def dictionnaire(self, length=3):
        return Generate(length)
        
    def pipeline(self, pseudos: list):
        queue_pseudos = deque(pseudos)

        while queue_pseudos:
            pseudo = queue_pseudos.popleft() 
            self.time_start = int(datetime.datetime.today().timestamp())

            try:
                out = asyncio.run(Requests(port=self.port, pseudo=pseudo))
            except Exception as e:
                print(f"[-] Erreur inattendue lors de l'exécution de Requests pour {pseudo} (port: {self.port}) : {e}")
                queue_pseudos.append(pseudo) 
                time.sleep(2)
                continue

            status_code = out.get("status")
            data = out.get("data")

            if status_code == 503:
                print(f"[#] Réanimation initiée pour le nœud Tor sur le port {self.port}...")
                queue_pseudos.appendleft(pseudo) 
                
                new_pid = Spoof(self.torcc_path, self.port)
                if new_pid == -1:
                    print(f"[-] Impossible de réanimer Tor sur le port {self.port}.")
                    time.sleep(10)
                continue 

            elif status_code == 429:
                print(f"[-] Code 429 reçu pour {pseudo} sur le port {self.port}.")
                queue_pseudos.append(pseudo) 
                NewNym(self.port, self.control_port, time_start=self.time_start)
                continue

            elif status_code in (200, 201, 204):
                if not isinstance(data, dict):
                    data = {}

                if not data.get("taken"):
                    print(f"[+] Success : {pseudo} --> Not Used (port: {self.port})")
                    free_pseudo.append(pseudo)
                else:
                    print(f"[-] Success : {pseudo} --> Already Used (port: {self.port})")

                result["success"] += 1
                
                NewNym(self.port, self.control_port, time_start=self.time_start)

            else:
                print(f"[-] Code HTTP inattendu ({status_code}) pour {pseudo} sur le port {self.port}")
                result["fail"] += 1


######################################## Configuration des Cores ########################################

cores = [
    Core(port=9050, control_port=9051, torcc_path="Tor/torcc1"),
    Core(port=9052, control_port=9053, torcc_path="Tor/torcc2"),
    Core(port=9054, control_port=9055, torcc_path="Tor/torcc3"),
    Core(port=9056, control_port=9057, torcc_path="Tor/torcc4"), 
    Core(port=9058, control_port=9059, torcc_path="Tor/torcc5"), 
]

fl_ = Core().dictionnaire(data['lenght'])

def chunk_list(lst, num_chunks):
    avg = len(lst) / float(num_chunks)
    out = []
    last = 0.0
    while last < len(lst):
        out.append(lst[int(last):int(last + avg)])
        last += avg
    return out

parts = chunk_list(fl_, len(cores))

######################################## Initialisation de Tor ########################################

print("[*] Lancement et initialisation des processus Tor...")
for core in cores:
    Spoof(core.torcc_path, core.port)

######################################## Exécution des Threads ########################################

def worker(data):
    idx, core = data
    try:
        core.pipeline(parts[idx])
    except Exception as e:
        print(f"[-] Erreur critique dans le thread {core.port} : {e}", file=sys.stderr)

print("[*] Démarrage du scan multi-threadé...")
with ThreadPoolExecutor(max_workers=len(cores)) as pool:
    list(pool.map(worker, enumerate(cores)))

print(f"\n[+] Travail terminé. Résultats finaux : {result}\nNot used pseudo : {free_pseudo}")