import orjson
import threading
import shutil
from pathlib import Path
import customtkinter as ctk
import asyncio
import string
import sys
import os
import spoof
import handler
import macro
import engine
from discord_webhook import DiscordWebhook
import tor_locker

# --- Initialisation UI ---
main_windows = ctk.CTk()
main_windows.title("DNC - By 𝗖𝗶𝗿𝗼🌕")
main_windows.geometry("800x650")
ctk.set_appearance_mode('dark')
ctk.set_default_color_theme('blue')

main_windows.grid_rowconfigure(1, weight=1)
main_windows.grid_columnconfigure(0, weight=1)

def create_stat_card(parent, col, title):
    frame = ctk.CTkFrame(parent, height=50)
    frame.grid(row=0, column=col, padx=10, pady=10, sticky="ew")
    frame.grid_columnconfigure(0, weight=1)
    ctk.CTkLabel(frame, text=title, font=("Arial", 12)).grid(row=0, column=0)
    lbl = ctk.CTkLabel(frame, text="0", font=("Arial", 20, "bold"))
    lbl.grid(row=1, column=0)
    return lbl

# --- OUTPUT & MIDDLE ---
OutputFrame = ctk.CTkTextbox(main_windows, font=("Consolas", 12))
OutputFrame.grid(row=1, column=0, padx=10, pady=5, sticky="nsew")
OutputFrame.configure(state="disabled")

Middle_Frame = ctk.CTkFrame(main_windows, height=200)
Middle_Frame.grid(row=2, column=0, padx=10, pady=5, sticky="ew")

Settings_Frame = ctk.CTkFrame(Middle_Frame, fg_color="transparent")
Settings_Frame.pack(side="left", padx=20, pady=10)
PseudoEntry = ctk.CTkEntry(Settings_Frame, placeholder_text="Length")
PseudoEntry.pack(pady=5)
PseudoEntry.bind("<KeyRelease>", lambda e: on_switch_change())
WebhookEntry = ctk.CTkEntry(Settings_Frame, placeholder_text="Webhook URL")
WebhookEntry.pack(pady=5)

NumSwitch = ctk.CTkSwitch(Settings_Frame, text="0-9")
NumSwitch.select()
NumSwitch.pack(anchor="w")
CharSwitch = ctk.CTkSwitch(Settings_Frame, text="A-Z")
CharSwitch.pack(anchor="w")
SymSwitch = ctk.CTkSwitch(Settings_Frame, text=".,_")
SymSwitch.pack(anchor="w")

def on_switch_change():
    charset = get_selected_chars()

NumSwitch.configure(command=on_switch_change)
CharSwitch.configure(command=on_switch_change)
SymSwitch.configure(command=on_switch_change)

Provider_Frame = ctk.CTkScrollableFrame(Middle_Frame, height=150, width=300)
Provider_Frame.pack(side="right", padx=20, pady=10)

def log_to_gui(text, color="white"):
    OutputFrame.configure(state="normal")
    OutputFrame.insert("end", text + "\n")
    OutputFrame.see("end") # Auto-scroll
    OutputFrame.configure(state="disabled")

def get_selected_chars():
    chars = ""
    if NumSwitch.get(): chars += string.digits
    if CharSwitch.get(): chars += string.ascii_lowercase
    if SymSwitch.get(): chars += "._"
    return chars

def load_providers():
    config_path = Path("config.json")
    if not config_path.exists():
        try:
            initial_data = {
                "user_mode": {
                    "lenght": 4,
                    "webhook_url": ""
                },
                "provider": {}
            }
            with open(config_path, "wb") as f:
                f.write(orjson.dumps(initial_data, option=orjson.OPT_INDENT_2))
        except Exception as e:
            log_to_gui(f"[-] Erreur de création initiale du JSON : {e}", "#e74c3c")
            return {}

    try:
        with open(config_path, "rb") as f:
            data = orjson.loads(f.read())
            return data.get("provider", {})
    except Exception as e:
        log_to_gui(f"[-] Erreur de lecture du JSON : {e}", "#e74c3c")
        return {}

def populate_provider_frame():
    for widget in Provider_Frame.winfo_children():
        widget.destroy()

    providers = load_providers()
    sorted_providers = sorted(providers.items(), key=lambda x: int(x[0]))

    for idx, info in sorted_providers:
        item_frame = ctk.CTkFrame(Provider_Frame, fg_color="transparent")
        item_frame.pack(fill="x", pady=2, padx=5)

        label_text = f"Provider #{idx}  |  Socks: {info['socks_port']}  |  Control: {info['control_port']}"
        lbl = ctk.CTkLabel(item_frame, text=label_text, font=("Consolas", 11))
        lbl.pack(side="left", padx=5)

def on_create_click():
    providers = load_providers()
    if providers:
        indexes = [int(k) for k in providers.keys()]
        next_idx = max(indexes) + 1
        last_provider = providers[str(max(indexes))]
        next_socks = last_provider["socks_port"] + 2
        next_control = last_provider["control_port"] + 2
    else:
        next_idx = 0
        next_socks = 9050
        next_control = 9051

    result = macro.MacroTorcc(str(next_socks), str(next_control), str(next_idx))
    if result == 1:
        log_to_gui(f"[+] Provider #{next_idx} créé avec succès !", "#2ecc71")
        populate_provider_frame()

def on_remove_click():
    config_path = Path("config.json")
    if not config_path.exists():
        return
    try:
        with open(config_path, "rb") as f:
            data = orjson.loads(f.read())
        
        providers = data.get("provider", {})
        if not providers:
            return

        indexes = [int(k) for k in providers.keys()]
        last_idx = max(indexes)
        str_last_idx = str(last_idx)

        tor_dir = Path("Tor")
        data_dir = tor_dir / f"data{last_idx}"
        torcc_file = tor_dir / f"torcc{last_idx}"
        if torcc_file.exists():
            torcc_file.unlink()
        if data_dir.exists() and data_dir.is_dir():
            shutil.rmtree(data_dir)

        del data["provider"][str_last_idx]

        with open(config_path, "wb") as f:
            f.write(orjson.dumps(data, option=orjson.OPT_INDENT_2))

        log_to_gui(f"[-] Provider #{last_idx} supprimé.", "#e67e22")
        populate_provider_frame()
    except Exception as e:
        log_to_gui(f"[-] Erreur suppression : {e}", "#e74c3c")

async def run_scanner_process():
    config_path = Path("config.json")
    try:
        with open(config_path, "r") as f:
            config_data = orjson.loads(f.read())
    except Exception as e:
        log_to_gui(f"[-] Erreur config : {e}", "#e74c3c")
        return

    charset = get_selected_chars()
    if not charset:
        log_to_gui("[-] Aucun caractère sélectionné !", "#e74c3c")
        return
    
    try:
        length = int(PseudoEntry.get())
    except:
        log_to_gui("[-] Longueur invalide !", "#e74c3c")
        return
    
    config_data['user_mode']['length'] = length
    config_data['user_mode']['charset'] = charset
    try:
        with open(config_path, "wb") as f:
            f.write(orjson.dumps(config_data, option=orjson.OPT_INDENT_2))
    except Exception as e:
        log_to_gui(f"[-] Erreur sauvegarde config : {e}", "#e74c3c")

    templates = handler.load_templates_from_folder("templates")
    discord_tpl = templates.get("discord")
    
    if not discord_tpl:
        log_to_gui("[-] Erreur : Template 'discord.json' introuvable dans le dossier 'templates' !", "#e74c3c")
        return

    instances_data = []
    
    for idx, (name, settings) in enumerate(config_data.get("provider", {}).items()):
        port = int(settings["socks_port"])
        torcc = str(settings["torcc"])
        
        spoof.Spoof(torcc, port)
        
        instances_data.append(spoof.TorInstance(
            idx=idx,
            socks_port=port,
            control_port=int(settings["control_port"]),
            control_cookie_path=settings.get("cookie_path")
        ))

    async def task_handler(session, instance, task, queue):
        pseudo = task["pseudo"]
        
        try:
            result = await handler.run_template(
                template=discord_tpl, 
                pseudo=pseudo, 
                port=instance.socks_port, 
                control_port=instance.control_port
            )
            
            if result.get("status") == "available":
                display_free_pseudo(pseudo, instance.socks_port)
            else:
                display_taken_pseudo(pseudo, instance.socks_port)
                
        except Exception as e:
            print(f"[!] Échec temporaire pour {pseudo} ({e}) -> Remis en fin de file.")
            pool.add_task({"pseudo": pseudo})
    
    pool = spoof.TorPool(instances_data, task_handler)
    
    generator = handler.Generate(length, charset)
    for pseudo in generator:
        pool.add_task({"pseudo": pseudo})
    
    scan_task = asyncio.create_task(pool.run(workers_per_instance=25))
    controller_task = asyncio.create_task(asyncio.to_thread(tor_locker._controllers))
    
    await asyncio.gather(scan_task, controller_task)

def display_free_pseudo(pseudo, port):
    if "pris" in pseudo.lower() or "taken" in pseudo.lower():
        log_to_gui(f"[-] Taken   : {pseudo} (Port: {port})", "#e74c3c")
        return

    log_to_gui(f"[+] Success : {pseudo} est LIBRE ! (Port: {port})", "#2ecc71")

    def send_discord():
        webhook_url = WebhookEntry.get().strip()
        if webhook_url: 
            try:
                webhook = DiscordWebhook(
                    url=webhook_url, 
                    content=f"@everyone `{pseudo}` est LIBRE !",
                    username="DNC./",
                    avatar_url="https://raw.githubusercontent.com/u9320831/DNC/main/ico/pp.jpg",
                    color="03b2f8"
                    
                )
                webhook.execute()
            except Exception as e:
                log_to_gui(f"[-] Impossible d'envoyer le webhook Discord : {e}", "#e74c3c")

    threading.Thread(target=send_discord, daemon=True).start()

def display_taken_pseudo(pseudo, port):
    log_to_gui(f"[-] Taken   : {pseudo} (Port: {port})", "#e74c3c")

# --- Footer & Boutons ---
Footer_Frame = ctk.CTkFrame(main_windows, fg_color="transparent")
Footer_Frame.grid(row=3, column=0, padx=10, pady=10, sticky="ew")

ctk.CTkButton(Footer_Frame, text="Start Scan", command=lambda: threading.Thread(target=lambda: asyncio.run(run_scanner_process()), daemon=True).start()).pack(side="right", padx=5)
ctk.CTkButton(Footer_Frame, text="+ Create", command=on_create_click).pack(side="right", padx=5)
ctk.CTkButton(Footer_Frame, text="- Remove", command=on_remove_click).pack(side="right", padx=5)

def load_user_settings():
    config_path = Path("config.json")
    if config_path.exists():
        try:
            with open(config_path, "rb") as f:
                data = orjson.loads(f.read())
                user_mode = data.get("user_mode", {})
                
                # Récupération de la longueur
                length = user_mode.get("lenght")
                if length is not None:
                    PseudoEntry.delete(0, "end")
                    PseudoEntry.insert(0, str(length))
                
                # Récupération du Webhook
                webhook_url = user_mode.get("webhook_url")
                if webhook_url:
                    WebhookEntry.delete(0, "end")
                    WebhookEntry.insert(0, str(webhook_url))
                
                # Récupération du charset et mise à jour des switches
                charset = user_mode.get("charset", "")
                if charset:
                    NumSwitch.deselect()
                    CharSwitch.deselect()
                    SymSwitch.deselect()
                    
                    if any(c in charset for c in string.digits):
                        NumSwitch.select()
                    if any(c in charset for c in string.ascii_lowercase):
                        CharSwitch.select()
                    if any(c in charset for c in "._"):
                        SymSwitch.select()
                    
        except Exception as e:
            log_to_gui(f"[-] Impossible de pré-remplir les options utilisateur : {e}", "#e74c3c")

populate_provider_frame()
load_user_settings()

main_windows.mainloop()