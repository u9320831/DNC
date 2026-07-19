from pathlib import Path
import json

def MacroTorcc(TorPort: str, TorControlPort: str, idx: str) -> int:
    # Utilisation de chemins d'accès propres et compatibles Windows/Linux
    tor_dir = Path("Tor")
    data_dir = tor_dir / f"data{idx}"
    torcc_path = tor_dir / f"torcc{idx}"

    # Correction du template (CookieAuthentication à 0 pour faciliter la vie de stem)
    templates = f"""SocksPort {TorPort}
ControlPort {TorControlPort}
GeoIPFile Tor/geoip
GeoIPv6File Tor/geoip6
DataDirectory Tor/data{idx}
CookieAuthentication 0

# Optimisation Performance Extrême
HardwareAccel 1
AvoidDiskWrites 1
ClientUseIPv6 0

# Gestion des Circuits et Timeouts
LearnCircuitBuildTimeout 0
CircuitBuildTimeout 10
NumEntryGuards 1
KeepalivePeriod 60

# Gestion de la Rotation
MaxCircuitDirtiness 60
NewCircuitPeriod 30

# Réduction de la verbosité pour gagner en CPU
Log warn stdout
DisableDebuggerAttachment 1

# Divers
EnforceDistinctSubnets 0
"""
    tor_dir.mkdir(exist_ok=True)

    with open(torcc_path, "w", encoding="utf-8") as torcc_file:
        torcc_file.write(templates)

    if not data_dir.exists():
        data_dir.mkdir(parents=True, exist_ok=True)

    config_path = Path("config.json")
    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as config_f:
                data = json.load(config_f)
            
            if "provider" not in data:
                data["provider"] = {}
            
            data["provider"][f"{idx}"] = {
                "socks_port": int(TorPort),
                "control_port": int(TorControlPort),
                "torcc": str(torcc_path)
            }

            with open(config_path, "w", encoding="utf-8") as config_f:
                json.dump(data, config_f, indent=4)

        except Exception as e:
            print(f"[-] Erreur lors de la mise à jour de config.json : {e}")
            return -1
            
    return 1