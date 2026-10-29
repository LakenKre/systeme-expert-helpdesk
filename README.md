# Système Expert Helpdesk Niveau 1

Projet de Master 2 MIAGE (Université Félix Houphouët-Boigny — 2026-2027)  
Cours d'Introduction à l'Intelligence Artificielle — Dr GBAME Gbede Sylvain  
Sujet 1 : Système expert de support informatique (IA symbolique)

---

## Présentation du projet

Ce système expert automatise le diagnostic et la résolution des pannes informatiques récurrentes de niveau 1 (accès réseau, imprimantes, messagerie Outlook, comptes Active Directory, postes de travail, progiciels ERP) :

* **Base de connaissances** : 42 règles de production (10 intermédiaires et 32 diagnostics finaux) et ontologie de cadres (*Frames*) avec gestion des SLA et cibles d'escalade N2.
* **Moteur d'inférence** : chaînage arrière pour le diagnostic guidé pas à pas et chaînage avant pour l'évaluation batch.
* **Incertitude & Explicabilité** : calcul des certitudes selon l'algèbre de Shortliffe (MYCIN) et justification récursive (« Pourquoi cette question ? » et « Pourquoi cette conclusion ? »).
* **Évaluation** : 30 cas d'incidents évalués à chaque démarrage (100 % de conformité) et benchmark de robustesse face à des modèles scikit-learn (LinearSVC, Random Forest, KNN).

---

## Installation

```bash
pip install -r requirements.txt
```

---

## Toutes les commandes

### 1. Démarrer les interfaces

| Interface | Commande | Accès | Description |
| :--- | :--- | :--- | :--- |
| **Lanceur tout-en-un** | `python lancer.py`<br>*(ou double-clic sur `lancer.bat`)* | Flask + Streamlit | Installe et lance les deux applications en simultané |
| **Point d'entrée universel** | `python main.py [--web/--gui/--cli/--eval]` | Variable | Lance l'interface ou le mode d'évaluation souhaité |
| **Application Web (Flask)** | `python helpdesk_expert_system.py --web` | `http://127.0.0.1:5000` | Interface principale pour la démo, avec 4 scénarios 1-clic |
| **Console Technicien (Streamlit)** | `streamlit run app_gui.py` | `http://localhost:8501` | Console métier : diagnostic guidé, chaînage avant, CRUD règles |
| **Mode interactif terminal (CLI)** | `python helpdesk_expert_system.py --cli` | Terminal | Diagnostic interactif en console avec la commande `why` |

### 2. Évaluation et tests

```bash
# Lancer l'évaluation des 30 cas et le benchmark scikit-learn dans la console
python helpdesk_expert_system.py

# Exécuter la suite de tests automatisés Streamlit (31 vérifications)
python tools/apptest_app_gui.py
```

### 3. Démonstrateur autonome

Le fichier [`docs/demo_interactive.html`](docs/demo_interactive.html) s'ouvre directement dans n'importe quel navigateur pour présenter l'ensemble des scénarios et le simulateur sans serveur local.

---

## Structure des fichiers

```text
├── main.py                    # Point d'entrée universel CLI/Web/GUI/Eval
├── helpdesk_expert_system.py  # Cœur du moteur (règles, frames, MYCIN, CLI et Flask)
├── app_gui.py                 # Console technicien Streamlit (4 onglets)
├── lancer.py / lancer.bat     # Démarrage automatique unifié
├── requirements.txt           # Dépendances (Flask, Streamlit, Scikit-learn, Pandas)
├── templates/                 # Vues HTML de l'application Flask
├── static/                    # Styles CSS et logotype vectoriel SVG
├── docs/demo_interactive.html # Démonstrateur interactif autonome
├── docs/screenshots/          # 16 captures d'écran des interfaces de test
└── tools/apptest_app_gui.py   # Suite de tests d'intégration (31/31 validés)
```
