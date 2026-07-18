import subprocess
import requests
from stem import Signal
from stem.control import Controller
import threading

def verif(port: int, timeout_sec: int = 5) -> dict:
    proxies = {"http": f"socks5h://127.0.0.1:{port}", "https": f"socks5h://127.0.0.1:{port}"}
    try:
        r = requests.get("https://check.torproject.org/api/ip", proxies=proxies, timeout=timeout_sec)
        return r.json()
    except Exception:
        return {}

def Spoof(torcc_path: str, port: int) -> int:
    try:
        process = subprocess.Popen(
            ["Tor\\tor.exe", "-f", torcc_path],
            stdout=subprocess.DEVNULL, 
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        return process.pid
    except Exception as e:
        print(f"[-] Erreur Tor {port} : {e}")
        return -1

_CONTROLLERS = {}
_LOCKS = {}

def get_controller(control_port: int):
    """Récupère le contrôleur en cache ou en crée un si nécessaire."""
    if control_port not in _CONTROLLERS:
        # Création d'un verrou pour éviter les collisions si plusieurs threads appellent en même temps
        _LOCKS[control_port] = threading.Lock()
        
        try:
            ctrl = Controller.from_port(port=control_port)
            ctrl.authenticate()
            _CONTROLLERS[control_port] = ctrl
        except Exception as e:
            print(f"[-] Erreur de connexion au contrôleur {control_port} : {e}")
            return None
            
    return _CONTROLLERS[control_port]

def NewNym(control_port: int) -> bool:
    """Envoie le signal sans fermer la connexion."""
    with _LOCKS.get(control_port, threading.Lock()): # Utilise le verrou associé au port
        try:
            ctrl = get_controller(control_port)
            if ctrl and ctrl.is_alive():
                ctrl.signal(Signal.NEWNYM)
                return True
            else:
                # Si le contrôleur est mort, on tente de le supprimer pour qu'il soit recréé au prochain appel
                if control_port in _CONTROLLERS:
                    del _CONTROLLERS[control_port]
                return False
        except Exception as e:
            print(f"[-] Erreur lors du signal NewNym sur le port {control_port} : {e}")
            return False