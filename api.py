import asyncio
import os
import sys
import argparse
import string
from pathlib import Path

from config import config
import handler
import spoof
import tor_locker
from cache import global_cache
from optimizer import SmartOptimizer


def resolve_charset(value: str) -> str:
    if not value:
        return ""

    normalized = value.strip().lower()
    if normalized in {"c", "all", "tout", "tous"}:
        return string.digits + string.ascii_lowercase + "._"
    if normalized in {"l", "letters", "lettres", "letter"}:
        return string.ascii_lowercase
    if normalized in {"n", "numbers", "numeros", "chiffres", "nums"}:
        return string.digits

    return value


async def run_scan(length: int, charset: str, template_name: str = "discord", providers: list | None = None, webhook_url: str | None = None):
    config_path = Path("config.json")
    if not config_path.exists():
        raise FileNotFoundError("Le fichier config.json est absent.")

    try:
        with open(config_path, "rb") as f:
            config_data = __import__("orjson").loads(f.read())
    except Exception as e:
        raise RuntimeError(f"Impossible de lire config.json : {e}") from e

    resolved_charset = resolve_charset(charset)

    config_data.setdefault("user_mode", {})
    config_data["user_mode"]["length"] = length
    config_data["user_mode"]["charset"] = resolved_charset
    if webhook_url:
        config_data["user_mode"]["webhook_url"] = webhook_url

    try:
        with open(config_path, "wb") as f:
            f.write(__import__("orjson").dumps(config_data, option=__import__("orjson").OPT_INDENT_2))
    except Exception as e:
        raise RuntimeError(f"Impossible d’écrire config.json : {e}") from e

    templates = handler.load_templates_from_folder("templates")
    selected_template = templates.get(template_name)
    if not selected_template:
        raise FileNotFoundError(f"Template introuvable : {template_name}")

    instances_data = []
    provider_items = list((config_data.get("provider") or {}).items())
    if providers:
        provider_items = [item for item in provider_items if str(item[0]) in {str(p) for p in providers}]

    for idx, (name, settings) in enumerate(provider_items):
        port = int(settings["socks_port"])
        torcc = str(settings["torcc"])
        spoof.Spoof(torcc, port)
        instances_data.append(spoof.TorInstance(
            idx=idx,
            socks_port=port,
            control_port=int(settings["control_port"]),
            control_cookie_path=settings.get("cookie_path")
        ))

    if not instances_data:
        raise RuntimeError("Aucun provider Tor n’est configuré.")

    async def task_handler(session, instance, task, queue):
        pseudo = task["pseudo"]
        try:
            result = await handler.run_template(
                template=selected_template,
                pseudo=pseudo,
                port=instance.socks_port,
                control_port=instance.control_port,
            )
            global_cache.set(pseudo, "available" if result.get("status") == "available" else "taken")
            if result.get("status") == "available":
                print(f"[FOUND] {pseudo}")
        except Exception as exc:
            print(f"[ERROR] {pseudo}: {exc}")
            pool.add_task({"pseudo": pseudo})

    pool = spoof.TorPool(instances_data, task_handler)
    generator = handler.Generate(length, resolved_charset)

    skipped_count = 0
    added_count = 0
    for pseudo in generator:
        if global_cache.get(pseudo) == "taken":
            skipped_count += 1
            continue
        pool.add_task({"pseudo": pseudo})
        added_count += 1

    print(f"[INFO] Pseudos déjà traités ignorés : {skipped_count}")
    print(f"[INFO] Nouveaux pseudos à analyser : {added_count}")

    optimizer = SmartOptimizer(telemetry_instance=tor_locker)
    scan_task = asyncio.create_task(pool.run(workers_per_instance=config.workers_per_instance))
    controller_task = asyncio.create_task(asyncio.to_thread(tor_locker._controllers))
    optimizer_task = asyncio.create_task(optimizer.start_monitoring_loop(interval=3.0))

    await asyncio.gather(scan_task, controller_task, optimizer_task)
    global_cache.save()


def main():
    parser = argparse.ArgumentParser(description="Lancer DNC en mode ligne de commande")
    parser.add_argument("--length", type=int, required=True, help="Longueur du pseudo à tester")
    parser.add_argument("--charset", type=str, required=True, help="Jeu de caractères à utiliser (ex: abc123, c, l, n)")
    parser.add_argument("--webhook", type=str, default=None, help="URL du webhook Discord à utiliser")
    parser.add_argument("--template", type=str, default="discord", help="Nom du template JSON à utiliser")
    parser.add_argument("--provider", action="append", default=None, help="Limiter à un ou plusieurs providers (index)" )
    args = parser.parse_args()

    if not args.charset:
        parser.error("Le charset ne peut pas être vide")

    asyncio.run(run_scan(length=args.length, charset=args.charset, template_name=args.template, providers=args.provider, webhook_url=args.webhook))


if __name__ == "__main__":
    main()
