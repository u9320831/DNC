import json
import threading
import shutil
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import customtkinter as ctk
import sys
from discord_webhook import DiscordWebhook
import os

import macro
import handler
from spoof import Spoof

def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except AttributeError:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

main_windows = ctk.CTk()
main_windows.title("DNC - By 𝗖𝗶𝗿𝗼🌕")
main_windows.geometry("800x600")
main_windows.resizable(False, False)
main_windows.iconbitmap(resource_path("ico\\main.ico"))
ctk.set_appearance_mode('dark')
ctk.set_default_color_theme('blue')

# ####################################### OutputFrame #######################################
OutputFrame = ctk.CTkScrollableFrame(main_windows, width=760, height=330)
OutputFrame.place(x=10, y=10)

# ####################################### Config #######################################
Config_Frame = ctk.CTkFrame(main_windows, width=780, height=230)
Config_Frame.place(x=10, y=360)

# ################### Provider Scrollable Frame
Provider_Frame = ctk.CTkScrollableFrame(Config_Frame, width=540, height=200)
Provider_Frame.place(x=210, y=10)


def log_to_gui(text, color="white"):
    def append_label():
        lbl = ctk.CTkLabel(
            OutputFrame, 
            text=text, 
            text_color=color, 
            font=("Consolas", 12)
        )
        lbl.pack(anchor="w", padx=10, pady=1)
        OutputFrame._parent_canvas.yview_moveto(1.0)
    
    main_windows.after(0, append_label)


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
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(initial_data, f, indent=4)
        except Exception as e:
            log_to_gui(f"[-] Erreur de création initiale du JSON : {e}", "#e74c3c")
            return {}

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
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
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
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

        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)

        log_to_gui(f"[-] Provider #{last_idx} supprimé.", "#e67e22")
        populate_provider_frame()
    except Exception as e:
        log_to_gui(f"[-] Erreur suppression : {e}", "#e74c3c")


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
                    content="@everyone `fsdfefs` est LIBRE !",
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


def chunk_list(lst, num_chunks):
    if num_chunks <= 0:
        return []
    avg = len(lst) / float(num_chunks)
    out = []
    last = 0.0
    while last < len(lst):
        out.append(lst[int(last):int(last + avg)])
        last += avg
    return out


def run_scanner_process():
    config_path = Path("config.json")
    
    # ... (Garde ton chargement de config intact) ...
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config_data = json.load(f)
        # Mise à jour des valeurs...
    except Exception as e:
        log_to_gui(f"[-] Erreur config : {e}", "#e74c3c")
        return

    cores = []
    providers = config_data.get("provider", {})
    
    for instance_name, settings in providers.items():
        # ... (Garde ta logique de création de liste cores) ...
        cores.append(handler.Core(port=int(settings["socks_port"]), control_port=int(settings["control_port"]), torcc_path=str(settings["torcc"])))

    if not cores:
        log_to_gui("[-] Aucun core Tor trouvé.", "#e74c3c")
        return

    # Préparation des pseudos
    fl_ = handler.Core().gen_dict(config_data['user_mode']['lenght'])
    parts = chunk_list(list(fl_), len(cores))

    log_to_gui("[*] Lancement des processus Tor...", "#3498db")
    for core in cores:
        Spoof(core.torcc_path, core.port)

    # CORRECTION : Le worker est simple, il exécute juste le pipeline
    def worker(data_worker):
        idx, core = data_worker
        try:
            core.pipeline(
                parts[idx], 
                tpl_name="discord", # Vérifie que ce template existe dans /templates
                on_success=display_free_pseudo,
                on_taken=display_taken_pseudo
            )
        except Exception as e:
            log_to_gui(f"[-] Erreur dans le thread {core.port} : {e}", "#e74c3c")

    log_to_gui("[*] Démarrage du scan multi-threadé...", "#3498db")
    
    # C'est ici que le multithreading est géré proprement
    with ThreadPoolExecutor(max_workers=len(cores)) as pool:
        pool.map(worker, enumerate(cores))

    def worker(data_worker):
        idx, core = data_worker
        # Utilise 'on_success' et 'on_taken' au lieu de '_callback'
        core.pipeline(
            parts[idx], 
            tpl_name="default", # Assure-toi d'avoir un template nommé 'default' ou change ici
            on_success=display_free_pseudo,
            on_taken=display_taken_pseudo)
        log_to_gui("[*] Démarrage du scan multi-threadé...", "#3498db")
        with ThreadPoolExecutor(max_workers=len(cores)) as pool:
            list(pool.map(worker, enumerate(cores)))


def on_start_click():
    threading.Thread(target=run_scanner_process, daemon=True).start()


def load_user_settings():
    config_path = Path("config.json")
    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
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
        except Exception as e:
            log_to_gui(f"[-] Impossible de pré-remplir les options utilisateur : {e}", "#e74c3c")


# ####################################### Controller #######################################
RemoveButton = ctk.CTkButton(main_windows, text="- Remove", width=60, height=30, command=on_remove_click)
RemoveButton.place(x=585, y=320)

AddButton = ctk.CTkButton(main_windows, text="+ Create", width=60, height=30, command=on_create_click)
AddButton.place(x=660, y=320)

StartButton = ctk.CTkButton(main_windows, text="Start", width=60, height=30, command=on_start_click)
StartButton.place(x=730, y=320)

# ################### Pseudo Length
PseudoLabel = ctk.CTkLabel(Config_Frame, text="Length :")
PseudoLabel.place(x=10, y=10)
PseudoEntry = ctk.CTkEntry(Config_Frame, placeholder_text="Ex : 4 ... ", height=10, width=145)
PseudoEntry.place(y=10, x=60)

# ################### Webhook
Webhook_Label = ctk.CTkLabel(Config_Frame, text="Webhook :")
Webhook_Label.place(x=10, y=45)
WebhookEntry = ctk.CTkEntry(Config_Frame, placeholder_text="https://discord.com/api/webhooks/...", height=10, width=130)
WebhookEntry.place(y=45, x=75)

populate_provider_frame()
load_user_settings()

main_windows.mainloop()