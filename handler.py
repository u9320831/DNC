import datetime
import pathlib
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Callable, Dict, Optional
import asyncio

import engine
import spoof
from engine import Generate
from spoof import NewNym, Spoof

@dataclass
class Core:
    port: int = 0
    control_port: int = 0
    torcc_path: str = ""
    t_start: int = 0
    tpls: Dict[str, engine.RequestTemplate] = field(default_factory=dict)

    def __post_init__(self):
        curr_dir = pathlib.Path(__file__).parent.resolve()
        tpl_dir = curr_dir / "templates"
        if tpl_dir.exists():
            self.tpls = engine.load_templates_from_folder(str(tpl_dir))
        else:
            print(f"[-] Missing folder: {tpl_dir}")

    def gen_dict(self, length: int = 3, charset_opts: Optional[dict] = None):
        if charset_opts:
            return Generate(length, **charset_opts)
        return Generate(length)

    def pipeline(
        self,
        pseudos: list,
        tpl_name: str,
        on_success: Optional[Callable[[str, int], None]] = None,
        on_taken: Optional[Callable[[str, int], None]] = None,
    ):
        tpl = self.tpls.get(tpl_name)
        if not tpl:
            print(f"[-] Template '{tpl_name}' not found.")
            return

        q = deque(pseudos)
        while q:
            username = q.popleft()
            self.t_start = int(datetime.datetime.today().timestamp())

            try:
                out = asyncio.run(
                    engine.run_template(
                        template=tpl,
                        pseudo=username,
                        port=self.port,
                        control_port=self.control_port,
                    )
                )
            except Exception as e:
                print(f"[!] Error {username} (Port: {self.port}): {e}")
                q.append(username)
                time.sleep(2)
                continue

            status = out.get("status")
            if status == "available":
                if on_success: on_success(username, self.port)
            elif status == "taken":
                if on_taken: on_taken(username, self.port)
            elif status == "rate_limited":
                q.append(username)
                time.sleep(1)
            else:
                q.append(username)
                time.sleep(2)

            # Rotation Tor
            res = NewNym(self.control_port)
            if res:
                self.t_start = int(time.time())
            else:
                Spoof(self.torcc_path, self.port)
                self.t_start = int(time.time())