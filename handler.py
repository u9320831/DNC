import pathlib
import asyncio
from dataclasses import dataclass, field
from typing import Callable, Dict, Optional
import engine
from engine import Generate

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

    # Note: On a transformé 'pipeline' pour gérer un SEUL pseudo, 
    # car le TorPool gère la distribution de la liste pour toi.
    async def pipeline(
        self,
        pseudo: str,
        tpl_name: str,
        on_success: Optional[Callable[[str, int], None]] = None,
        on_taken: Optional[Callable[[str, int], None]] = None,
    ):
        tpl = self.tpls.get(tpl_name)
        if not tpl:
            print(f"[-] Template '{tpl_name}' not found.")
            return

        # On attend directement la fonction async du moteur (sans asyncio.run)
        out = await engine.run_template(
            template=tpl,
            pseudo=pseudo,
            port=self.port,
            control_port=self.control_port,
        )

        status = out.get("status")
        
        if status == "available":
            if on_success: on_success(pseudo, self.port)
            return True # Succès
            
        elif status == "taken":
            if on_taken: on_taken(pseudo, self.port)
            return True # Succès (le scan a fonctionné)
            
        elif status == "rate_limited":
            # On lève une exception pour que le TorPool détecte l'erreur
            # et déclenche automatiquement un NEWNYM
            raise Exception("Rate limited")
            
        else:
            raise Exception(f"Unknown status: {status}")