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

BROWSER_FINGERPRINTS = [
    "chrome110", "chrome120", "edge110", "edge120", 
    "safari15_5", "safari16_0", "safari17_0", "firefox110"
]

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

class SessionWrapper:
    def __init__(self, port: int, browser: str):
        self.port = port
        self.browser = browser
        self.proxy = f"socks5h://127.0.0.1:{port}"
        self.session = AsyncSession(impersonate=browser, proxies={"http": self.proxy, "https": self.proxy})
        self.request_count = 0
        self.max_requests_per_session = 100

    async def request(self, **kwargs):
        self.request_count += 1
        if self.request_count > self.max_requests_per_session:
            await self.reset()
        return await self.session.request(**kwargs)

    async def reset(self):
        try: await self.session.close()
        except: pass
        new_browser = random.choice(BROWSER_FINGERPRINTS)
        self.browser = new_browser
        self.session = AsyncSession(impersonate=new_browser, proxies={"http": self.proxy, "https": self.proxy})
        self.request_count = 0

class RequestEngine:
    def __init__(self, total_concurrency: int = 150):
        self.semaphore = asyncio.Semaphore(total_concurrency)
        self.sessions: Dict[int, SessionWrapper] = {}
        self.locks: Dict[int, asyncio.Lock] = {}

    def _get_lock(self, control_port: int) -> asyncio.Lock:
        if control_port not in self.locks:
            self.locks[control_port] = asyncio.Lock()
        return self.locks[control_port]

    async def _get_session(self, port: int) -> SessionWrapper:
        if port not in self.sessions:
            self.sessions[port] = SessionWrapper(port, random.choice(BROWSER_FINGERPRINTS))
        return self.sessions[port]

    async def execute(self, template, pseudo, port, control_port, variables):
        url = _inject_variables(template.url, variables)
        params = _inject_variables(template.params, variables) if template.params else None
        headers = _inject_variables(template.headers, variables) if template.headers else None
        payload = _inject_variables(template.payload, variables) if template.payload else None

        attempt = 0
        while attempt < template.max_retries:
            async with self.semaphore:
                try:
                    wrapper = await self._get_session(port)
                    response = await wrapper.request(
                        method=template.method.upper(),
                        url=url,
                        params=params,
                        headers=headers or {},
                        json=payload if isinstance(payload, (dict, list)) else None,
                        data=payload if not isinstance(payload, (dict, list)) else None,
                        timeout=template.timeout
                    )

                    if response.status_code == 429:
                        raise Exception("Rate limited")
                    if response.status_code not in template.expected_status:
                        raise RequestsError(f"Status {response.status_code}")

                    return {
                        "status": template.status_map.get(str(response.status_code), "taken"),
                        "http_code": response.status_code,
                        "data": response.json() if template.response_format == "json" else response.text
                    }

                except Exception as e:
                    attempt += 1
                    async with self._get_lock(control_port):
                        await asyncio.to_thread(spoof.NewNym, control_port)
                    
                    wrapper = await self._get_session(port)
                    await wrapper.reset()
                    
                    await asyncio.sleep(template.retry_delay + random.uniform(0.5, 1.5))
        
        raise RuntimeError(f"Échec {pseudo} sur {port}")

_ENGINE = RequestEngine(total_concurrency=150)

async def run_template(template, pseudo, port, control_port, variables=None) -> Dict[str, Any]:
    variables = variables or {}
    variables.setdefault("pseudo", pseudo)
    return await _ENGINE.execute(template, pseudo, port, control_port, variables)