# � DNC - Discord Name Checker

DNC est un outil d'automatisation et de vérification multi-threadé conçu pour scanner la disponibilité des pseudonymes Discord avec un niveau élevé de discrétion et de stabilité.

> Si l'application tourne en arrière-plan, il s'agit généralement du processus Tor. Vous pouvez la fermer sans risque si vous ne souhaitez plus l'utiliser.

---

## ✨ Ce que fait DNC

DNC combine plusieurs mécanismes pour améliorer la fiabilité du scan :

- 🔁 Multi-threading et parallélisme
- 🌐 Rotation d'identité Tor via NewNym
- 🧠 Optimisation dynamique des paramètres de requêtes
- 🛡️ Gestion de blocages et de rate limits
- 🖥️ Interface graphique moderne avec CustomTkinter
- 🔔 Notifications Discord via webhook
- 💾 Sauvegarde automatique des préférences et des résultats

---

## 🚀 Fonctionnalités principales

- **Scan rapide de pseudos Discord** avec plusieurs instances Tor configurables
- **Contournement des rate limits** grâce à la rotation de circuits et au spoofing
- **Optimisation en temps réel** des paramètres de requête selon les métriques observées
- **Interface élégante et intuitive** pour un usage simple
- **Persistance des réglages** dans un fichier de configuration JSON

---

## 📦 Installation

### Prérequis

- Python 3.10+
- Un dossier Tor prêt à l'emploi à la racine du projet

### 1. Cloner le dépôt

```bash
git clone https://github.com/u9320831/DNC.git
cd DNC
```

### 2. Installer les dépendances

```bash
pip install -r requirements.txt
```

### 3. Lancer l'application

```bash
python DNC.py
```

---

## 🛠️ Version compilée

Si vous préférez utiliser l'application sans installer Python :

1. Ouvrez la section **Releases** du dépôt GitHub
2. Téléchargez le fichier `DNC.exe`
3. Placez-le dans le dossier de votre choix
4. Lancez-le

> Une configuration initiale sera créée automatiquement dans le même dossier si nécessaire.

---

## ⚙️ Configuration

Le fichier `config.json` est généré automatiquement à la racine du projet. Exemple de structure :

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

## 📁 Structure du projet

- `DNC.py` : point d'entrée principal
- `handler.py` / `engine.py` : logique des requêtes
- `spoof.py` : gestion Tor et rotation d'identité
- `optimizer.py` / `optimizer_memory.py` : optimisation adaptative
- `templates/` : modèles de requêtes
- `Tor/` : binaires et données Tor

---

## 🧠 Notes importantes

- Cet outil est destiné à un usage personnel et responsable.
- Le comportement peut varier selon la stabilité des instances Tor et des services ciblés.
- Une bonne configuration réseau et Tor est essentielle pour des résultats optimaux.

---

## ❤️ Crédits

Développé avec passion par **Ciro**.
