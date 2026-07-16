from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor
from collections import deque
import sys
import asyncio 
import datetime
import time
import json
import pathlib

######################################## Modules ########################################
from engine import Generate, Requests
from spoof import Spoof, NewNym

config_path = pathlib.Path("config.json")

if config_path.exists():
    try:
        with open('config.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print(f"[-] Impossible de lire config.json : {e}")
        data = {}
else:
    templates_ = {
        "user_mode": {
            "length": 3,
            "webhook_url": ""
        },
        "provider": {}
    }

    try:
        with open("config.json", "w", encoding='utf-8') as config_file:
            json.dump(templates_, config_file, indent=4)
        data = templates_
        print("[+] Fichier config.json créé avec succès.")
    except Exception as e:
        print(f"[-] Erreur lors de la création de config.json : {e}")



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
                out = asyncio.run(Requests(port=self.port, pseudo=pseudo, torcc_path=self.torcc_path))
            except Exception as e:
                print(f"[-] Erreur inattendue lors de l'exécution de Requests pour {pseudo} (port: {self.port}) : {e}")
                queue_pseudos.append(pseudo) 
                time.sleep(2)
                continue

            status = out.get('status')
            data = out.get('data', {})

            if status in (200, 201, 204):
                if isinstance(data, dict) and "taken" in data:
                    if data["taken"] is False:
                        print(f"[+] Success : {pseudo} --> Libre ! (port: {self.port})")
                    else:
                        print(f"[-] Success : {pseudo} --> Déjà pris (port: {self.port})")
                else:
                    print(f"[!] Réponse invalide de Discord pour {pseudo} (port: {self.port}). Ré-essai...")
                    queue_pseudos.append(pseudo)
                    time.sleep(1)

            elif status == 429:
                print(f"[!] Reprise de {pseudo} (remis en file d'attente suite à un Rate Limit)")
                queue_pseudos.append(pseudo)
                time.sleep(1)
                
            else:
                print(f"[!] Erreur de traitement pour {pseudo} (Status: {status}). Remis en file d'attente.")
                queue_pseudos.append(pseudo)
                time.sleep(2)

            result = NewNym(
                port=self.port, 
                control_port=self.control_port, 
                time_start=self.time_start
            )

            if result == 1:
                self.time_start = int(time.time())
            elif result == 0:
                print(f"[!] Le changement d'IP a timeout sur le port {self.port}. Tentative de Spoof...")
                Spoof(self.torcc_path, self.port)
                self.time_start = int(time.time())
######################################## Configuration des Cores ########################################

cores = []

config_path = pathlib.Path("config.json")

if config_path.exists():
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config_data = json.load(f)
            
        providers = config_data.get("provider", {})
        
        for instance_name, settings in providers.items():
            socks_port = settings.get("socks_port")
            control_port = settings.get("control_port")
            torcc_path = settings.get("torcc") 
            
            if socks_port and control_port and torcc_path:
                cores.append(
                    Core(
                        port=int(socks_port),
                        control_port=int(control_port),
                        torcc_path=str(torcc_path)
                    )
                )
                
    except Exception as e:
        print(f"[-] Erreur lors de la lecture des providers dans config.json : {e}")
else:
    print("[-] config.json introuvable. Impossible de charger les instances Tor.")

cores.sort(key=lambda c: c.port)

print(f"[+] {len(cores)} Cores Tor chargés depuis config.json :")
for core in cores:
    print(f"  -> Port: {core.port} | Control: {core.control_port} | Path: {core.torcc_path}")

fl_ = Core().dictionnaire(data['user_mode']['lenght'])

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