#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Vérification fonctionnelle de la console Streamlit (AppTest).

Usage : python tools/apptest_app_gui.py

Couvre :
  1. démarrage sans exception et présence des 4 onglets ;
  2. clic sur « Oui, certain » 6 fois (le diagnostic guidé peut conclure avant) ;
  3. changement de catégorie dans la barre latérale ;
  4. ajout puis suppression d'une règle de test ;
  5. présence du bouton d'export JSON ;
  6. lancement du benchmark bruité.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from streamlit.testing.v1 import AppTest  # noqa: E402

TIMEOUT = 300
checks: list[tuple[str, bool, str]] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    checks.append((label, bool(condition), detail))
    print(("[OK]  " if condition else "[KO]  ") + label + (f" — {detail}" if detail else ""))


def no_exception(at: AppTest, step: str) -> bool:
    if at.exception:
        messages = "; ".join(getattr(item, "value", str(item)) for item in at.exception)
        check(f"Aucune exception ({step})", False, messages)
        return False
    check(f"Aucune exception ({step})", True)
    return True


at = AppTest.from_file(str(ROOT / "app_gui.py"), default_timeout=TIMEOUT)
at.run()
no_exception(at, "démarrage")

tabs = [tab.label for tab in at.tabs]
expected_tabs = ["Diagnostic guidé", "Chaînage avant", "Base de règles", "Évaluation & benchmark"]
check("4 onglets attendus", tabs == expected_tabs, " | ".join(tabs))

category = at.selectbox(key="category_select")
check("Sélecteur de catégorie en barre latérale",
      category is not None and category.value == "Applicatif",
      f"valeur initiale = {category.value if category else 'absente'}")

# --- 6 réponses « Oui, certain » (réinitialisation si le diagnostic conclut avant) ---
clicks = 0
resets = 0
guard = 0
while clicks < 6 and guard < 24:
    guard += 1
    oui = [button for button in at.button if button.label == "Oui, certain"]
    if oui:
        oui[0].click()
        at.run()
        clicks += 1
        if not no_exception(at, f"réponse Oui #{clicks}"):
            break
        answers = dict(at.session_state["qa_answers"])
        check(f"Réponse enregistrée (#{clicks})", len(answers) >= 1, f"{len(answers)} fait(s)")
    else:
        reset = at.sidebar.button(key="reset_btn")
        if not reset:
            check("Bouton de réinitialisation disponible", False, "introuvable")
            break
        reset.click()
        at.run()
        resets += 1
        if not no_exception(at, "réinitialisation"):
            break

check("6 clics « Oui, certain » exécutés", clicks == 6, f"{clicks} clics, {resets} réinitialisation(s)")
check("Diagnostic ou question affiché après les réponses",
      bool(at.markdown) and any("hd-result__title" in item.value or "hd-question" in item.value
                                for item in at.markdown),
      "carte de résultat ou question rendue")

# --- changement de catégorie ---
at.selectbox(key="category_select").select("Réseau")
at.run()
no_exception(at, "changement de catégorie")
selected_category = at.selectbox(key="category_select").value
check("Catégorie Réseau sélectionnée", selected_category == "Réseau",
      f"valeur = {selected_category}")
check("Périmètre Réseau affiché",
      any("Équipe Réseau" in item.value for item in at.markdown),
      "cible d'escalade Réseau présente")

# --- benchmark ---
before = at.session_state["bench"]
at.button(key="bench_btn").click()
at.run()
no_exception(at, "benchmark")
bench = at.session_state["bench"]
check("Benchmark exécuté", bench is not None and before is None,
      f"{len(bench)} modèles mesurés" if bench else "aucun résultat")
check("4 modèles comparés",
      bench is not None and set(bench) == {"Système expert", "LinearSVC", "Random Forest", "KNN (k=5)"},
      ", ".join(bench) if bench else "")

# --- export ---
downloads = at.get("download_button")
check("Export JSON disponible", len(downloads) == 1, f"{len(downloads)} bouton(s) de téléchargement")

# --- ajout d'une règle de test ---
initial_count = len(at.session_state["rules"])
at.text_input(key="rule_id").set_value("RTEST")
at.selectbox(key="rule_cat").set_value("Applicatif")
at.text_input(key="rule_premises").set_value("symptome_test_a, symptome_test_b")
at.text_input(key="rule_conclusion").set_value("conclusion_test_rtest")
at.text_input(key="rule_desc").set_value("Règle temporaire de vérification")
at.checkbox(key="rule_diag").set_value(True)
at.text_area(key="rule_res").set_value("1. Étape de test.\n2. Seconde étape de test.")
at.button(key="rule_submit").click()
at.run()
no_exception(at, "ajout de règle")
added = len(at.session_state["rules"])
check("Règle de test ajoutée", added == initial_count + 1, f"{initial_count} → {added} règles")
check("Message de confirmation affiché",
      any("Règle ajoutée" in item.value for item in at.markdown),
      "bandeau de succès")

# --- suppression de la règle de test ---
at.selectbox(key="rule_delete").select("RTEST")
at.button(key="rule_delete_btn").click()
at.run()
no_exception(at, "suppression de règle")
removed = len(at.session_state["rules"])
check("Règle de test supprimée", removed == initial_count, f"{added} → {removed} règles")
check("Aucune règle RTEST résiduelle",
      all(rule.id != "RTEST" for rule in at.session_state["rules"]),
      "base restaurée à l'identique")

# --- synthèse ---
failures = [label for label, ok, _ in checks if not ok]
print()
print(f"{len(checks) - len(failures)}/{len(checks)} vérifications réussies")
if failures:
    print("Échecs : " + ", ".join(failures))
    sys.exit(1)
print("AppTest : aucune exception, 4 onglets fonctionnels, cycle complet validé.")
