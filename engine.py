import asyncio
import json
import os
import random
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Literal, Optional
from curl_cffi.requests import AsyncSession, RequestsError

# Import de ton module de rotation personnalisé
import spoof
import itertools,string
# Suivi du temps pour le cooldown Tor (évite de spammer NEWNYM inutilement)
TOR_TIMERS: Dict[int, int] = {}

# =====================================================================
# 1. STRUCTURE DES TEMPLATES ET INJECTION DE VARIABLES
# =====================================================================

class Generate:
    def __init__(self, length: int, charset: str = string.ascii_lowercase + string.digits):
        self.length = length
        self.charset = charset

    def __iter__(self):
        for combination in itertools.product(self.charset, repeat=self.length):
            yield "".join(combination)

    def __len__(self):
        return len(self.charset) ** self.length
    
@dataclass
class RequestTemplate:
    name: str
    url: str
    method: str = "GET"
    params: Optional[dict] = None
    headers: Optional[dict] = None
    payload: Any = None
    expected_status: list[int] = field(default_factory=lambda: [200, 201, 204])
    response_format: Literal["json", "text", "raw"] = "json"
    browser: Literal["chrome", "edge", "safari"] = "chrome"
    max_retries: int = 5
    retry_delay: float = 2.0
    timeout: int = 15
    status_map: Dict[str, str] = field(default_factory=lambda: {
        "200": "taken",
        "201": "taken",
        "204": "available"
    })


def load_template(source: str | dict) -> RequestTemplate:
    data = json.loads(source) if isinstance(source, str) else source
    return RequestTemplate(**data)


def load_templates_from_folder(folder_path: str) -> dict[str, RequestTemplate]:
    templates = {}
    if not os.path.exists(folder_path):
        return templates
    for filename in os.listdir(folder_path):
        if filename.endswith(".json"):
            with open(os.path.join(folder_path, filename), "r", encoding="utf-8") as f:
                try:
                    tpl = load_template(json.load(f))
                    templates[tpl.name] = tpl
                except Exception as e:
                    print(f"[-] Impossible de charger le template {filename} : {e}")
    return templates


def _inject_variables(value: Any, variables: Dict[str, Any]) -> Any:
    if isinstance(value, str):
        try:
            return value.format(**variables)
        except (KeyError, IndexError):
            return value
    elif isinstance(value, dict):
        return {k: _inject_variables(v, variables) for k, v in value.items()}
    elif isinstance(value, list):
        return [_inject_variables(v, variables) for v in value]
    return value


# =====================================================================
# 2. MOTEUR D'EXÉCUTION RÉSEAU AVEC APPEL À SPOOF.NEWNYM
# =====================================================================

async def wrapper(
    template: RequestTemplate,
    url: str,
    pseudo: str,
    port: int,
    control_port: int,  # Requis pour NewNym
    method: str = "GET",
    payload: Any = None,
    params: dict | None = None,
    headers: dict | None = None,
) -> Dict[str, Any]:

    proxies = {
        "http": f"socks5h://127.0.0.1:{port}",
        "https": f"socks5h://127.0.0.1:{port}",
    }

    actual_method = method.upper()
    base_headers = {}
    
    if actual_method in ["POST", "PUT", "PATCH"] and payload is not None and isinstance(payload, (dict, list)):
        base_headers["Content-Type"] = "application/json"
    
    base_headers.update({
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1"
    })

    if headers:
        base_headers.update(headers)

    attempt = 0

    while attempt < template.max_retries:
        try:
            async with AsyncSession(impersonate=template.browser, timeout=template.timeout, proxies=proxies) as session:
                
                request_kwargs = {
                    "method": actual_method,
                    "url": url,
                    "params": params,
                    "headers": base_headers,
                }
                
                if payload is not None:
                    if isinstance(payload, (dict, list)) and base_headers.get("Content-Type") == "application/json":
                        request_kwargs["json"] = payload
                    else:
                        request_kwargs["data"] = payload

                response = await session.request(**request_kwargs)
                
                # --- INTERCEPTION RELANCE TOR ---
                # Si le code retourné n'est pas dans la whitelist (200, 201, 204), on change d'IP
                if response.status_code not in [200, 201, 204]:
                    print(f"[!] Code HTTP {response.status_code} anormal pour '{pseudo}'. Lancement de spoof.NewNym...")
                    
                    # Récupération du timestamp du dernier changement d'IP sur ce port
                    last_time = TOR_TIMERS.get(port, 0)
                    
                    # Exécution asynchrone sécurisée de ta fonction spoof.NewNym externe
                    await asyncio.to_thread(spoof.NewNym, control_port)
                    
                    # Mise à jour du timer local
                    TOR_TIMERS[port] = int(time.time())
                    
                    # On simule une erreur réseau pour forcer le code à faire un retry immédiat sur la nouvelle IP
                    raise RequestsError(f"IP Tor bannie ou invalide ({response.status_code})", response=response)

                # Traduction classique si le code est valide
                status_str = str(response.status_code)
                verdict = template.status_map.get(status_str, "unknown")
                
                data_content = None
                if template.response_format == "json":
                    try:
                        data_content = response.json()
                    except ValueError:
                        data_content = response.text
                elif template.response_format == "text":
                    data_content = response.text
                else:
                    data_content = response.content

                return {
                    "status": verdict,
                    "http_code": response.status_code,
                    "data": data_content
                }

        except RequestsError as e:
            attempt += 1
            jitter = random.uniform(0.5, 1.5)
            current_delay = (template.retry_delay * attempt) + jitter
            
            print(f"[!] [{pseudo}] Échec circuit Tor (tentative {attempt}/{template.max_retries}) : {e}")
            
            if attempt >= template.max_retries:
                break
                
            await asyncio.sleep(current_delay)

        except Exception as e:
            attempt += 1
            # Si le proxy crash ou refuse la connexion (ex: circuit cassé), on force aussi un NewNym
            print(f"[!] [{pseudo}] Erreur critique (Port {port}). Appel d'urgence à spoof.NewNym...")
            last_time = TOR_TIMERS.get(port, 0)
            await asyncio.to_thread(spoof.NewNym, control_port)
            TOR_TIMERS[port] = int(time.time())
            
            if attempt >= template.max_retries:
                raise
            await asyncio.sleep(template.retry_delay)

    raise RuntimeError(f"[{pseudo}] Échec critique après {template.max_retries} tentatives avec rotations Tor sur le port {port}")


# =====================================================================
# 3. POINT D'ENTRÉE PRINCIPAL
# =====================================================================

async def run_template(
    template: RequestTemplate,
    pseudo: str,
    port: int,
    control_port: int,
    variables: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    variables = variables or {}
    variables.setdefault("pseudo", pseudo)

    resolved_url = _inject_variables(template.url, variables)
    resolved_params = _inject_variables(template.params, variables) if template.params else None
    resolved_headers = _inject_variables(template.headers, variables) if template.headers else None
    resolved_payload = _inject_variables(template.payload, variables) if template.payload else None

    return await wrapper(
        template=template,
        url=resolved_url,
        pseudo=pseudo,
        port=port,
        control_port=control_port,
        method=template.method,
        payload=resolved_payload,
        params=resolved_params,
        headers=resolved_headers
    )