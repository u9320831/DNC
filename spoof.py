import subprocess
import requests
from stem import Signal
from stem.control import Controller
import time
import threading
import datetime

def verif(port: int, timeout_sec: int = 5) -> dict:
    proxies = {
        "http": f"socks5h://127.0.0.1:{port}",
        "https": f"socks5h://127.0.0.1:{port}"
    }
    try:
        r = requests.get("https://check.torproject.org/api/ip", proxies=proxies, timeout=timeout_sec)
        return r.json()
    except Exception:
        return {}

def Spoof(torcc_path: str, port: int, timeout_sec: int = 30) -> int:
    if not torcc_path or not port:
        print("[-] Paramètres torcc_path ou port invalides.")
        return -1

    try:
        process = subprocess.Popen(
            ["Tor\\tor.exe", "-f", torcc_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            text=True,
            bufsize=1 
        )
    except FileNotFoundError:
        print("[-] Erreur : Impossible de trouver Tor\\tor.exe")
        return -1
    except Exception as e:
        print(f"[-] Erreur lors du lancement de Tor : {e}")
        return -1

    print(f"PID TOR lancé : {process.pid}")

    def read_logs():
        try:
            for line in iter(process.stdout.readline, ''):
                if line:
                    print(f"[{port}] {line.strip()}")
        except Exception:
            pass 
        finally:
            process.stdout.close()

    thread_logs = threading.Thread(target=read_logs, daemon=True)
    thread_logs.start()

    start_time = time.time()
    tor_ready = False

    print(f"[*] Attente de l'initialisation de Tor sur le port {port}...")
    
    while time.time() - start_time < timeout_sec:
        if process.poll() is not None:
            print(f"[-] Le processus Tor s'est arrêté de manière inattendue (Code de sortie : {process.poll()})")
            return -1

        status = verif(port, timeout_sec=3)
        if status and status.get("IsTor"):
            tor_ready = True
            break

        time.sleep(0.5)

    if tor_ready:
        print(f"[+] Nœud TOR initialisé avec succès (port : {port}, torcc : {torcc_path})")
        return process.pid
    else:
        print(f"[-] Timeout dépassé ({timeout_sec}s). Tor n'a pas pu s'initialiser correctement.")
        process.terminate()
        return -1

def NewNym(port: int, control_port: int, time_start: int, max_wait_ip: int = 15) -> int:
    nw_time = int(datetime.datetime.today().timestamp())
    
    sleep_duration = 10 - (nw_time - time_start)
    if sleep_duration > 0:
        time.sleep(sleep_duration)

    base_status = verif(port)
    bs_ip = base_status.get('IP', 'Inconnue')

    try:
        with Controller.from_port(port=control_port) as controller:
            controller.authenticate()
            controller.signal(Signal.NEWNYM)
    except Exception as e:
        print(f"[-] Impossible de se connecter au Control Port {control_port} : {e}")
        return -1
    
    check_start = time.time()
    while time.time() - check_start < max_wait_ip:
        nw_status = verif(port)
        nw_ip = nw_status.get('IP', bs_ip)

        if nw_ip != bs_ip and nw_ip != 'Inconnue':
            print(f"[+] Nouvelle ip alloué ({bs_ip} --> {nw_ip})")
            return 1
        else:
            print(f"[-] Attente du changement d'ip (port : {port}...)")
            time.sleep(1.5) 

    print(f"[-] Échec du changement d'IP (Timeout de {max_wait_ip}s dépassé pour le port {port})")
    return 0