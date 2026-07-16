from curl_cffi.requests import AsyncSession
import sys
import string
import itertools
import asyncio
import sys
from curl_cffi.requests import AsyncSession

######################################## Modules ########################################

from spoof import Spoof

def Validity(pseudo : str) -> bool:
    USERNAME_CHARS = string.ascii_lowercase + string.digits + "_" + "."

    if not (2 <= len(pseudo) <= 32):
        return False
    if ".." in pseudo:
        return False
    if pseudo.startswith(".") or pseudo.endswith("."):
        return False
    return all(c in USERNAME_CHARS for c in pseudo)

def Generate(lenght : int) -> list:
    fl = []
    char = string.ascii_lowercase + string.digits + "_" + "."
    
    for char in itertools.product(char, repeat=lenght):
        pseudo = "".join(char)
        if Validity(pseudo):
            fl.append(pseudo)

    print(f"Listes de pseudos initialisé (longeur :{lenght})")
    return fl

async def Requests(pseudo: str, port: int, torcc_path: str) -> dict:
    BASE_URL = "https://discord.com/api/v9"
    ENDPOINT = "unique-username/username-attempt-unauthed"
    url = f"{BASE_URL}/{ENDPOINT}"

    payload = {"username": pseudo}
    proxies = {
        "http": f"socks5h://127.0.0.1:{port}",
        "https": f"socks5h://127.0.0.1:{port}"
    }

    while True:
        try:
            async with AsyncSession(impersonate="chrome", proxies=proxies, timeout=10) as session:
                response = await session.post(
                    url, 
                    json=payload,
                    headers={"Content-Type": "application/json"} 
                ) 
                
                if response.status_code == 429:
                    try:
                        retry_after = response.json().get("retry_after", 5)
                    except Exception:
                        retry_after = 5

                    if retry_after > 15:
                        print(f"[-] Rate Limit trop long ({retry_after}s) sur le port {port} pour '{pseudo}'. Rotation requise.")
                        return {"status": 429, "data": "RateLimit"}
                    
                    print(f"[-] Rate Limit détecté sur le port {port}. Pause de {retry_after}s...")
                    await asyncio.sleep(retry_after)
                    continue 

                elif response.status_code == 503:
                    print(f"[#] Réanimation initiée pour le nœud Tor sur le port {port}...")
                    new_pid = Spoof(torcc_path, port)
                    if new_pid == -1:
                        print(f"[-] Impossible de réanimer Tor sur le port {port}. Pause de 10s...")
                        await asyncio.sleep(10)
                    else:
                        await asyncio.sleep(5)
                    continue

                elif response.status_code in (200, 201, 204):
                    try:
                        response_data = response.json()
                    except Exception:
                        response_data = {}

                    return {
                        "status": response.status_code,
                        "data": response_data
                    }

                else:
                    print(f"[-] Code HTTP inattendu ({response.status_code}) pour {pseudo} sur le port {port}. Retry...")
                    await asyncio.sleep(4)
                    continue
                
        except Exception as e:
            error_msg = str(e)
            
            if any(x in error_msg for x in ["curl: (7)", "Failed to connect", "timeout", "Timeout"]):
                print(f"[!] Le proxy Tor sur le port {port} semble mort ou lent. Tentative de réanimation...")
                new_pid = Spoof(torcc_path, port)
                await asyncio.sleep(5)
                continue 

            print(f"[-] Problème réseau temporaire sur le port {port} ('{pseudo}') : {error_msg}. Relancement...", file=sys.stderr)
            await asyncio.sleep(3)
            continue