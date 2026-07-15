from curl_cffi.requests import AsyncSession
import sys
import string
import itertools
import asyncio
import sys
from curl_cffi.requests import AsyncSession

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

async def Requests(pseudo: str, port: int) -> dict:
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
            async with AsyncSession(impersonate="chrome", proxies=proxies, timeout=12) as session:
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
                        print(f"[-] Rate Limit ({retry_after}s) sur le port {port} pour '{pseudo}'.")

                        return {"status": 429, "data": "RateLimit - IP à changer"}
                    
                    print(f"[-] Petit Rate Limit détecté sur le port {port}. Pause de {retry_after}s...")
                    await asyncio.sleep(retry_after)
                    continue

                print(f"[+] Requête envoyée {pseudo} (port: {port}) - Status: {response.status_code}")
                try:
                    response_data = response.json()
                except Exception:
                    response_data = response.text
                    
                return {
                    "status": response.status_code,
                    "data": response_data
                }
                
        except Exception as e:
            error_msg = str(e)
            
            if "curl: (7)" in error_msg or "Failed to connect" in error_msg:
                return {"status": 503, "data": "Tor proxy is dead"}

            print(f"[-] Problème réseau temporaire sur le port {port} ('{pseudo}') : Lancement d'une nouvelle tentative...", file=sys.stderr)
            await asyncio.sleep(3)
            continue