import asyncio
import json
import os
import random
import itertools
import string
from dataclasses import dataclass, field
from typing import Any, Dict, Literal, Optional
from curl_cffi.requests import AsyncSession, RequestsError

import spoof

# =====================================================================
# 1. STRUCTURE DES TEMPLATES & GÉNÉRATEUR
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
        "200": "taken", "201": "taken", "204": "available"
    })

# =====================================================================
# 2. UTILS
# =====================================================================

def load_templates_from_folder(folder_path: str) -> dict[str, RequestTemplate]:
    templates = {}
    if not os.path.exists(folder_path): return templates
    for filename in os.listdir(folder_path):
        if filename.endswith(".json"):
            with open(os.path.join(folder_path, filename), "r", encoding="utf-8") as f:
                try:
                    tpl = RequestTemplate(**json.load(f))
                    templates[tpl.name] = tpl
                except Exception as e:
                    print(f"[-] Erreur chargement {filename} : {e}")
    return templates

def _inject_variables(value: Any, variables: Dict[str, Any]) -> Any:
    if isinstance(value, str):
        try: return value.format(**variables)
        except: return value
    elif isinstance(value, dict): return {k: _inject_variables(v, variables) for k, v in value.items()}
    elif isinstance(value, list): return [_inject_variables(v, variables) for v in value]
    return value

# =====================================================================
# 3. MOTEUR D'EXÉCUTION (PORT-AWARE)
# =====================================================================

class RequestEngine:
    def __init__(self, total_concurrency: int = 50):
        self.semaphore = asyncio.Semaphore(total_concurrency)
        self.locks: Dict[int, asyncio.Lock] = {}

    def _get_lock(self, control_port: int) -> asyncio.Lock:
        if control_port not in self.locks:
            self.locks[control_port] = asyncio.Lock()
        return self.locks[control_port]

    async def execute(self, template: RequestTemplate, pseudo: str, port: int, control_port: int, variables: Dict[str, Any]) -> Dict[str, Any]:
        url = _inject_variables(template.url, variables)
        params = _inject_variables(template.params, variables) if template.params else None
        headers = _inject_variables(template.headers, variables) if template.headers else None
        payload = _inject_variables(template.payload, variables) if template.payload else None

        proxies = {"http": f"socks5h://127.0.0.1:{port}", "https": f"socks5h://127.0.0.1:{port}"}
        
        attempt = 0
        while attempt < template.max_retries:
            async with self.semaphore:
                try:
                    async with AsyncSession(impersonate=template.browser, timeout=template.timeout, proxies=proxies) as session:
                        request_kwargs = {
                            "method": template.method.upper(),
                            "url": url,
                            "params": params,
                            "headers": headers or {},
                            "json": payload if isinstance(payload, (dict, list)) else None,
                            "data": payload if not isinstance(payload, (dict, list)) else None
                        }
                        
                        response = await session.request(**request_kwargs)

                        if response.status_code == 429:
                            raise Exception("Rate limited")

                        if response.status_code not in template.expected_status:
                            raise RequestsError(f"Status {response.status_code}")

                        return {
                            "status": template.status_map.get(str(response.status_code), "unknown"),
                            "http_code": response.status_code,
                            "data": response.json() if template.response_format == "json" else response.text
                        }

                except Exception as e:
                    attempt += 1
                    if attempt == 1:
                        print(f"[!] [{pseudo}] Erreur Port {port}: {e}. Rotation IP...")
                    
                    async with self._get_lock(control_port):
                        await asyncio.to_thread(spoof.NewNym, control_port)
                    
                    wait_time = template.retry_delay * (2 ** attempt) + random.uniform(0, 1)
                    await asyncio.sleep(wait_time)
                    
        raise RuntimeError(f"[{pseudo}] Échec après {template.max_retries} tentatives sur port {port}.")

_ENGINE = RequestEngine(total_concurrency=50) 

async def run_template(template: RequestTemplate, pseudo: str, port: int, control_port: int, variables: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    variables = variables or {}
    variables.setdefault("pseudo", pseudo)
    return await _ENGINE.execute(template, pseudo, port, control_port, variables)