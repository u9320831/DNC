import asyncio
import orjson
import os
import random
import itertools
import string
from dataclasses import dataclass, field
from typing import Any, Dict, Literal, Optional
from curl_cffi.requests import AsyncSession, RequestsError
import re
import base64

from config import config
import spoof

BROWSER_FINGERPRINTS = ["chrome124", "chrome126", "safari17_0", "edge124"]

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
            with open(os.path.join(folder_path, filename), "rb") as f:
                try:
                    tpl = RequestTemplate(**orjson.loads(f.read()))
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

def get_dynamic_headers(browser_fingerprint: str) -> dict:
    version = re.search(r'\d+', browser_fingerprint).group() if re.search(r'\d+', browser_fingerprint) else "124"
    languages = ["fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7", "en-US,en;q=0.9", "es-ES,es;q=0.9,en;q=0.8"]
    
    properties = {
        "os": "Windows",
        "release_channel": "stable",
        "client_version": "1.0.9031",
        "os_version": "10.0.22621",
        "os_arch": "x64",
        "system_locale": "fr",
    }

    json_str = orjson.dumps(properties, option=orjson.OPT_INDENT_2)
    encoded_properties = base64.b64encode(json_str).decode()

    headers = {
        "X-Super-Properties": encoded_properties,
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "User-Agent": f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{version}.0.0.0 Safari/537.36",
        "sec-ch-ua": f'"Chromium";v="{version}", "Google Chrome";v="{version}"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "Referer": "https://discord.com/",
        "Origin": "https://discord.com",
        "Accept": "*/*",
        "Accept-Language": random.choice(languages),
        "Connection": "keep-alive",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache"
    }
    return headers

class SessionWrapper:
    def __init__(self, port: int, browser: str):
        self.port = port
        self.browser = browser 
        self.proxy = f"socks5h://127.0.0.1:{port}"
        self.headers = get_dynamic_headers(self.browser)
        self.session = self._create_session()
        self.request_count = 0
        self.max_requests_per_session = config.max_requests_per_session

    def _create_session(self):
        return AsyncSession(
            impersonate=self.browser, 
            proxies={"http": self.proxy, "https": self.proxy},
            headers=self.headers,
            timeout=20 
        )

    async def request(self, **kwargs):
        self.request_count += 1
        config.requests_per_session = self.request_count
        
        if self.request_count > self.max_requests_per_session:
            await self.reset()

        try:
            out = await self.session.request(**kwargs)
            return out
        finally:
            if hasattr(self.session, 'cookies'):
                self.session.cookies.clear()

    async def reset(self):
        try: await self.session.close()
        except: pass
        self.browser = random.choice(BROWSER_FINGERPRINTS)
        config.requests_per_session = 0
        self.headers = get_dynamic_headers(self.browser)
        self.session = self._create_session()
        self.request_count = 0

class RequestEngine:
    def __init__(self, total_concurrency: int = config.total_concurrency):
        self.semaphore = asyncio.Semaphore(total_concurrency)
        self.sessions: Dict[int, SessionWrapper] = {}

    async def _get_session(self, port: int) -> SessionWrapper:
        if port not in self.sessions:
            self.sessions[port] = SessionWrapper(port, random.choice(BROWSER_FINGERPRINTS))
        return self.sessions[port]

    async def execute(self, template, pseudo, port, control_port, variables):
        url = _inject_variables(template.url, variables)
        params = _inject_variables(template.params, variables) if template.params else None
        headers = _inject_variables(template.headers, variables) if template.headers else None
        payload = _inject_variables(template.payload, variables) if template.payload else None

        jitter = random.uniform(config.sleep_min, config.sleep_max) 
        await asyncio.sleep(jitter)

        attempt = 0
        while attempt < template.max_retries:
            async with self.semaphore:
                config.total_requests = getattr(config, "total_requests", 0) + 1

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

                    if response.status_code in [403, 429]:
                        config.blocked_requests += 1
                        await spoof.NewNymAsync(spoof.global_registry, control_port)
                        await wrapper.reset()
                        attempt += 1
                        await asyncio.sleep(random.uniform(config.sleep_min, config.sleep_max))
                        continue

                    if response.status_code not in template.expected_status:
                        raise RequestsError(f"Status {response.status_code}")

                    return {
                        "status": template.status_map.get(str(response.status_code), "taken"),
                        "http_code": response.status_code,
                        "data": response.json() if template.response_format == "json" else response.text
                    }

                except Exception as e:
                    attempt += 1
                    
                    if attempt >= template.max_retries:
                        config.blocked_requests += 1
                        return {"status": "failed", "error": str(e)}
                        
                    await spoof.NewNymAsync(spoof.global_registry, control_port)
                    wrapper = await self._get_session(port)
                    await wrapper.reset()
                    await asyncio.sleep(random.uniform(config.sleep_min, config.sleep_max))        

        return {"status": "failed", "error": "Max retries exceeded"}

_ENGINE = RequestEngine(total_concurrency=config.total_concurrency)

async def run_template(template, pseudo, port, control_port, variables=None) -> Dict[str, Any]:
    variables = variables or {}
    variables.setdefault("pseudo", pseudo)
    return await _ENGINE.execute(template, pseudo, port, control_port, variables)