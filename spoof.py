import subprocess
import requests
from stem import Signal
from stem.control import Controller

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

def NewNym(control_port: int) -> bool:
    try:
        with Controller.from_port(port=control_port) as controller:
            controller.authenticate()
            controller.signal(Signal.NEWNYM)
            return True
    except Exception:
        return False