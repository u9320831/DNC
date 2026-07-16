# 🌕 DNC - Discord Name Checker

DNC est un outil d'automatisation et de vérification multi-threadé qui vous permet de scanner la disponibilité des pseudonymes Discord.
Note : Si l'application tourne en arrière-plan, c'est simplement le client Tor. Si l'application est fermée, vous pouvez arrêter le processus sans craindre
---

## 🚀 Fonctionnalités

*   **Multi-threading & Rotation IP :** Utilisation simultanée de plusieurs instances de Tor configurables.
*   **Contournement des Rate Limits :** Changement automatique d'identité Tor (NewNym) et spoofing après chaque vérification.
*   **Interface Graphique (GUI) Moderne :** Développée avec `CustomTkinter` pour un rendu élégant et intuitif.
*   **Sauvegarde automatique :** Conservation de vos réglages (longueur de pseudo, webhook Discord) dans un fichier `config.json`.
*   **Notifications Discord :** Alertes en temps réel par Webhook dès qu'un pseudo est disponible.

---

## 📦 Installation & Utilisation (Développeurs)

Si vous souhaitez exécuter le projet directement à partir des sources Python (`DNC.py`), suivez les étapes suivantes.

### Prérequis
*   [Python 3.10+](https://www.python.org/downloads/)
*   Le dossier `Tor` contenant les binaires de Tor configurés à la racine du projet.

### 1. Cloner le dépôt
```bash
git clone git@github.com:u9320831/DNC.git
cd DNC

```

### 2. Installer les dépendances

Utilisez le fichier `requirements.txt` pour installer toutes les bibliothèques requises d'un seul coup :

```bash
pip install -r requirements.txt

```

### 3. Lancer l'application

```bash
python DNC.py

```

---

## 🛠️ Utilisation de la version compilée (`DNC.exe`)

Si vous préférez utiliser l'application directement sans installer Python, vous pouvez exécuter le fichier pré-compilé.

1. Rendez-vous dans l'onglet **Releases** de ce GitHub (ou téléchargez directement le fichier `DNC.exe`).
2. Placez le fichier `DNC.exe` dans le dossier de votre choix.
3. Lancez `DNC.exe`.
> *Note : Un fichier `config.json` sera automatiquement généré à côté de l'exécutable lors du premier lancement pour stocker vos préférences.*

---

## 📝 Configuration JSON (`config.json`)

Le fichier de configuration est automatiquement généré à la racine. Voici sa structure par défaut :

```json
{
    "user_mode": {
        "lenght": 4,
        "webhook_url": ""
    },
    "provider": {}
}

```
---

*Développé avec 💙 par **𝗖𝗶𝗿𝗼🌕***
