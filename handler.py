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

@dataclass
class Core:
    port: int = 0
    control_port: int = 0
    torcc_path: str = ""
    fl: list = field(default_factory=list)
    time_start: int = 0

    def dictionnaire(self, length=3):
        return Generate(length)
        
    def pipeline(self, pseudos: list, on_success_callback=None):
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
                        if on_success_callback:
                            on_success_callback(pseudo, self.port)
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