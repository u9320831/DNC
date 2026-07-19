import pathlib
import asyncio
from dataclasses import dataclass, field
from typing import Callable, Dict, Optional
import engine
from engine import Generate
import spoof
import random

@dataclass
class Core:
    port: int = 0
    control_port: int = 0
    torcc_path: str = ""
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

    async def pipeline(
            self,
            pseudo: str,
            tpl_name: str,
            on_success: Optional[Callable[[str, int], None]] = None,
            on_taken: Optional[Callable[[str, int], None]] = None,
        ) -> bool:
            tpl = self.tpls.get(tpl_name)
            if not tpl:
                print(f"[-] Template '{tpl_name}' not found.")
                return False

            # On encapsule l'appel réseau pour intercepter les levées d'exceptions de l'engine
            try:
                out = await engine.run_template(
                    template=tpl,
                    pseudo=pseudo,
                    port=self.port,
                    control_port=self.control_port,
                )
            except Exception as e:
                # Si l'engine lève une RuntimeError (fin de retries, rate limit persistant, etc.)
                print(f"[-] Échec de l'engine pour {pseudo} (Port {self.port}): {e}")
                return False

            # Double sécurité au cas où l'engine renverrait quand même un truc vide
            if out is None:
                print(f"[-] Erreur critique : L'engine a renvoyé une réponse vide (None) pour {pseudo}")
                return False

            status = out.get("status")
            
            if status == "available":
                if on_success: 
                    on_success(pseudo, self.port)
                return True
                
            elif status == "taken":
                if on_taken: 
                    on_taken(pseudo, self.port)
                return True
                
            else:
                if out.get("status") == "failed" and out.get("error") == "Status 0":
                    await spoof.NewNymAsync(spoof.global_registry, self.control_port)    
                    print(f"[*]Warning (Ip bloqué -> Timeout ,Port :{self.control_port})")
                    
                    ip = spoof.get_current_ip(self.control_port)
                    if ip:
                        spoof.global_registry.Update(ip=ip, blocked=True, ratelimit=False)

                if out.get("status") == "failed" and out.get("error") == "Rate limited": 
                    await spoof.NewNymAsync(spoof.global_registry, self.control_port)    
                    print(f"[*]Warning (Ratelimit -> Timeout ,Port :{self.control_port})")
                    
                    ip = spoof.get_current_ip(self.control_port)
                    if ip:
                        spoof.global_registry.Update(ip=ip, blocked=False, ratelimit=True, duration=300)

                return False