# Hermes Render Online 🪐

`hermes-render-online` est un serveur web léger conçu pour héberger l'Agent autonome **Hermes** en ligne sur Render. Ce projet vous permet de piloter Hermes à distance via une interface de chat moderne, sécurisée par mot de passe, et de le laisser exécuter des tâches autonomes (recherche web, lecture de pages, etc.).

Cette version est **100% gratuite**, hautement portable, et ne nécessite **aucune base de données payante** (l'historique de chat est stocké dans des cookies de session chiffrés et sécurisés).

---

## 📂 Structure du Projet

```text
hermes-render-online/
├── Dockerfile           # Configuration du conteneur (Python + support Playwright optionnel)
├── requirements.txt     # Dépendances Python (Flask, OpenAI, Requests, etc.)
├── main.py              # Serveur Flask & Boucle d'exécution de l'Agent Hermes
├── render.yaml          # Blueprint pour le déploiement automatique sur Render
├── README.md            # Ce fichier
├── templates/
│   └── index.html       # Page Web unique (Login et Interface de Chat)
└── static/
    └── style.css        # Styles premium sombres (Effets Glassmorphism & Animations)
```

---

## ⚡ Fonctionnalités Clés

1. **Sécurité d'Accès** : L'accès à l'interface est verrouillé par un mot de passe défini via la variable d'environnement `HERMES_PASSWORD`.
2. **Exécution Autonome (Tool Calling)** : Hermes dispose d'outils (`web_search` et `web_browse`) qu'il appelle de manière proactive pour répondre à vos directives.
3. **Console d'Exécution en Direct** : L'interface affiche en temps réel les étapes techniques qu'Hermes effectue (ex: *"Appel de l'outil web_search..."*) avant de vous donner sa réponse finale.
4. **Zéro Base de Données** : Pas de Postgres ou SQLite persistant. Les messages sont stockés dans la session de votre navigateur, ce qui évite tout coût ou expiration de base de données.
5. **Route de réveil (`/health`)** : Un endpoint léger pour surveiller le statut ou réveiller le conteneur Render sans lancer de processus lourd.

---

## 🛠️ Installation et Lancement en Local

### 1. Prérequis
Assurez-vous d'avoir Python 3.9+ installé sur votre machine.

### 2. Configuration des variables d'environnement
Créez un fichier `.env` à la racine du projet avec le contenu suivant :
```env
HERMES_PASSWORD=mon_mot_de_passe_securise
OPENAI_API_KEY=votre_cle_api_openai
SECRET_KEY=cle_session_aleatoire_pour_flask
PORT=5000
HERMES_MODE=local
```
*(Optionnel)* Si vous utilisez un autre fournisseur compatible OpenAI (comme OpenRouter), vous pouvez spécifier `OPENAI_BASE_URL` et `HERMES_MODEL` dans le fichier `.env`.

### 3. Installation et Lancement
Ouvrez votre terminal dans le dossier du projet :

```bash
# Installer les dépendances
pip install -r requirements.txt

# Lancer le serveur local
python main.py
```

Rendez-vous ensuite sur `http://localhost:5000` sur votre navigateur.

---

## 🚀 Déploiement en 1 clic sur Render

Grâce au fichier `render.yaml`, le déploiement sur Render est automatisé (Blueprint) :

1. Poussez ce projet sur votre dépôt **GitHub**.
2. Créez un compte sur **[Render.com](https://render.com/)** (aucune carte bancaire requise pour le plan gratuit).
3. Dans votre tableau de bord Render, cliquez sur **New +** > **Blueprint**.
4. Connectez votre dépôt GitHub.
5. Render va lire le fichier `render.yaml` et vous demander de remplir :
   - `HERMES_PASSWORD` : Le mot de passe pour accéder à votre interface.
   - `OPENAI_API_KEY` : Votre clé API OpenAI.
6. Cliquez sur **Approve** (Déployer).

Render va construire l'image Docker et lancer votre service. Vous obtiendrez une URL publique du type `https://hermes-render-online.onrender.com`.

---

## 🌐 Guide : Ajouter un Navigateur Headless (Playwright / Browser-use)

Par défaut, l'outil `web_browse` d'Hermes utilise la bibliothèque `requests` pour lire le contenu textuel des pages. Cela fonctionne pour les sites statiques, mais pas pour les applications modernes (React/Vue/SPAs) nécessitant l'exécution de JavaScript.

Si vous souhaitez qu'Hermes pilote un **vrai navigateur Chromium headless** en ligne, voici la marche à suivre :

### 1. Mettre à jour le Dockerfile
Dans votre `Dockerfile`, décommentez la section d'installation des dépendances système de Chromium et de Playwright :

```dockerfile
# Installer les dépendances de rendu et Playwright
RUN apt-get update && apt-get install -y --no-install-recommends \
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
    libxkbcommon0 libxcomposite1 libxdamage1 libxext6 libxfixes3 \
    libxrandr2 libgbm1 libasound2 libpangocairo-1.0-0 libpango-1.0-0 \
    && rm -rf /var/lib/apt/lists/*
RUN pip install playwright && playwright install --with-deps chromium
```

### 2. Ajouter `playwright` dans `requirements.txt`
Ajoutez la ligne suivante dans votre fichier `requirements.txt` :
```text
playwright>=1.40.0
```

### 3. Modifier `web_browse` dans `main.py`
Remplacez la fonction `web_browse` par une implémentation basée sur Playwright :

```python
from playwright.sync_api import sync_playwright

def web_browse(url: str) -> str:
    """
    Récupère le contenu d'une page web dynamique en exécutant le JS avec Playwright (headless).
    """
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
        
    try:
        with sync_playwright() as p:
            # Lancer le navigateur Chromium en mode headless (sans interface)
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            
            # Aller sur l'URL
            page.goto(url, timeout=15000, wait_until="load")
            
            # Récupérer le contenu textuel propre
            text_content = page.locator("body").inner_text()
            browser.close()
            
            return f"Contenu de {url} (extrait avec Playwright, tronqué à 3000 car.) :\n\n{text_content[:3000]}"
    except Exception as e:
        return f"Erreur de rendu Playwright pour {url}: {str(e)}"
```

> [!WARNING]
> **Limitations de mémoire sur Render Gratuit** : Le plan gratuit de Render alloue **512 MB de RAM** par conteneur. Lancer Chromium en arrière-plan peut parfois dépasser cette limite et provoquer un crash `Out Of Memory`. Si vous faites cette mise à niveau, il est fortement recommandé d'utiliser un modèle d'agent optimisé ou de passer à l'instance Render à $7/mois (Starter) qui offre 512 MB à 1 GB de RAM stables.
