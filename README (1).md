# Système Expert Helpdesk Niveau 1 (M2 MIAGE - UFHB)

Cours d'Intelligence Artificielle - Dr GBAME Gbede Sylvain

## Contenu
- `helpdesk_expert_system.py` : frames, 42 règles, moteur MYCIN (chaînage avant et arrière), explication, administration des règles, évaluation sur 30 cas, benchmark face à Scikit-learn, CLI et application Flask.
- `app_gui.py` : interface graphique Streamlit à 4 onglets.

## Installation
```bash
pip install -r requirements.txt
```

## Exécution
```bash
python helpdesk_expert_system.py          # évaluation (30 cas) + benchmark
python helpdesk_expert_system.py --cli    # mode interactif (chaînage arrière, commande "why")
python helpdesk_expert_system.py --web    # application Flask sur http://127.0.0.1:5000
streamlit run app_gui.py                  # interface Streamlit sur http://localhost:8501
```

## Points d'honnêteté à annoncer à la soutenance
- Les 30 cas de test sont écrits avec les règles : ils mesurent la cohérence interne, pas la qualité externe.
- Les tickets du benchmark ML sont générés à partir des règles : c'est une étude de sensibilité au bruit, pas une validation.
- Les chiffres du benchmark sont calculés par le code (moyenne sur 10 tirages) et varient légèrement d'une exécution à l'autre.
