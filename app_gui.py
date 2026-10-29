#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Interface graphique Streamlit - Système Expert Helpdesk N1 (M2 MIAGE UFHB)
Lancement : streamlit run app_gui.py
"""

import pandas as pd
import streamlit as st

from helpdesk_expert_system import (
    build_domain_ontology, build_knowledge_base, HelpdeskInferenceEngine,
    RuleBaseAdminTool, QUESTIONS_SYMPTOMES, Rule, evaluate_30_cases, run_noise_benchmark,
)

st.set_page_config(page_title="Système Expert Helpdesk N1 - M2 MIAGE", page_icon="🛠️", layout="wide")

if "ontology" not in st.session_state:
    st.session_state.ontology = build_domain_ontology()
if "rules" not in st.session_state:
    st.session_state.rules = build_knowledge_base()
if "qa_answers" not in st.session_state:
    st.session_state.qa_answers = {}

engine = HelpdeskInferenceEngine(st.session_state.rules, st.session_state.ontology)
admin_tool = RuleBaseAdminTool(st.session_state.rules)

st.title("🛠️ Système Expert de Support Informatique (Helpdesk Niveau 1)")
st.markdown("**Master 2 MIAGE – UFHB** | *Chaînage avant/arrière, facteurs de certitude de MYCIN, explicabilité*")

tab1, tab2, tab3, tab4 = st.tabs([
    "💬 1. Diagnostic guidé (chaînage arrière)",
    "⚡ 2. Multi-symptômes (chaînage avant)",
    "⚙️ 3. Administration des règles",
    "📊 4. Évaluation (30 cas) & benchmark",
])

# ------------------------------------------------------------------ ONGLET 1
with tab1:
    st.subheader("💬 Assistant de dépannage guidé")
    st.info("Choisissez un domaine : le système ne pose que les questions nécessaires pour prouver ou éliminer chaque panne.")

    col_cat, col_reset = st.columns([3, 1])
    with col_cat:
        categories = sorted({r.category for r in st.session_state.rules if r.is_diagnostic})
        selected_cat = st.selectbox("📂 Catégorie de l'incident :", categories)
    with col_reset:
        st.write("")
        st.write("")
        if st.button("🔄 Réinitialiser", width="stretch"):
            st.session_state.qa_answers = {}
            st.rerun()

    inter_rules_map = {r.conclusion: r for r in st.session_state.rules if not r.is_diagnostic}
    candidates = [r for r in st.session_state.rules if r.is_diagnostic and r.category == selected_cat]
    answers = st.session_state.qa_answers

    next_fact, active_rule, active_inter = None, None, None
    for diag in candidates:
        possible, missing, inter_ref = True, None, None
        for prem in diag.premises:
            if prem in inter_rules_map:
                inter = inter_rules_map[prem]
                for sub in inter.premises:
                    if sub in answers:
                        if answers[sub] < engine.threshold:
                            possible = False
                            break
                    elif missing is None:
                        missing, inter_ref = sub, inter
                if not possible:
                    break
            else:
                if prem in answers:
                    if answers[prem] < engine.threshold:
                        possible = False
                        break
                elif missing is None:
                    missing = prem
        if possible and missing is not None:
            next_fact, active_rule, active_inter = missing, diag, inter_ref
            break

    current = engine.forward_chaining(answers)
    cat_diags = [(r, cf) for r, cf in current if r.category == selected_cat]

    if cat_diags:
        best, cf = cat_diags[0]
        st.success(f"### ✅ Diagnostic identifié : {best.description}")
        st.progress(float(cf), text=f"Confiance MYCIN : {cf*100:.1f}% (CF = {cf})")
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("#### 🛠️ Procédure de résolution")
            st.code(best.resolution, language="text")
        with c2:
            st.markdown("#### 🔍 Pourquoi cette conclusion ?")
            st.code(engine.explain_conclusion(best.conclusion), language="text")
    elif next_fact is not None:
        st.markdown("---")
        st.markdown(f"### ❓ {QUESTIONS_SYMPTOMES.get(next_fact, next_fact)}")
        st.caption(f"Fait recherché : `{next_fact}`")
        b1, b2, b3, b4 = st.columns(4)
        if b1.button("✅ Oui, certain (CF = 1.0)", width="stretch", type="primary"):
            answers[next_fact] = 1.0
            st.rerun()
        if b2.button("👍 Probablement (CF = 0.8)", width="stretch"):
            answers[next_fact] = 0.8
            st.rerun()
        if b3.button("🤔 Peut-être (CF = 0.5)", width="stretch"):
            answers[next_fact] = 0.5
            st.rerun()
        if b4.button("❌ Non (CF = 0.0)", width="stretch"):
            answers[next_fact] = 0.0
            st.rerun()
        with st.expander("💡 Pourquoi cette question ?"):
            st.write(f"**Hypothèse testée :** `{active_rule.id}` — *{active_rule.description}* (CF règle = {active_rule.cf})")
            if active_inter:
                st.write(f"**Sous-objectif :** `{active_inter.id}` — *{active_inter.description}* (CF règle = {active_inter.cf})")
            st.write(f"**Prémisses requises :** `{', '.join(active_rule.premises)}`")
    else:
        st.warning("⚠️ Aucune règle N1 ne correspond dans cette catégorie. **Escalade vers le Support Niveau 2.**")

    if answers:
        with st.expander("📋 Faits collectés durant cette session"):
            st.json(answers)

# ------------------------------------------------------------------ ONGLET 2
with tab2:
    st.subheader("⚡ Chaînage avant et pondération MYCIN")
    selected_symptoms = st.multiselect(
        "🔍 Symptômes observés :", options=list(QUESTIONS_SYMPTOMES.keys()),
        format_func=lambda k: f"[{k}] {QUESTIONS_SYMPTOMES[k]}",
        default=["ping_passerelle_ok", "ping_ip_externe_ok", "site_web_inaccessible_par_nom"])

    input_facts = {}
    if selected_symptoms:
        st.markdown("##### 🎚️ Certitude (CF) de chaque symptôme :")
        cols = st.columns(min(3, len(selected_symptoms)))
        for i, sym in enumerate(selected_symptoms):
            with cols[i % len(cols)]:
                input_facts[sym] = st.slider(sym, 0.2, 1.0, 1.0, 0.05)

    if st.button("🚀 Exécuter le chaînage avant", type="primary"):
        results = engine.forward_chaining(input_facts)
        if results:
            for rule, cf in results:
                with st.container(border=True):
                    st.success(f"### ✅ [{rule.id} - {rule.category}] {rule.description}")
                    st.progress(float(cf), text=f"Certitude combinée : {cf*100:.1f}% (CF = {cf})")
                    ca, cb = st.columns(2)
                    with ca:
                        st.markdown("**🛠️ Procédure de résolution :**")
                        st.code(rule.resolution, language="text")
                    with cb:
                        st.markdown("**🔍 Pourquoi cette conclusion ?**")
                        st.code(engine.explain_conclusion(rule.conclusion), language="text")
        else:
            st.error("⚠️ Aucun diagnostic (CF < 0.20). Escalade vers le Support Niveau 2.")

# ------------------------------------------------------------------ ONGLET 3
with tab3:
    st.subheader(f"⚙️ Base de connaissances ({len(st.session_state.rules)} règles)")
    consistency = admin_tool.check_consistency()
    if not consistency["doublons_premisses"] and not consistency["faits_intermediaires_inutilises"]:
        st.success("✔️ Audit de cohérence : aucune anomalie détectée.")
    else:
        st.warning(f"Anomalies : {consistency}")

    st.dataframe(pd.DataFrame([{
        "ID": r.id, "Catégorie": r.category,
        "Type": "Diagnostic final" if r.is_diagnostic else "Intermédiaire",
        "Prémisses (SI)": " ET ".join(r.premises), "Conclusion (ALORS)": r.conclusion,
        "CF règle": r.cf, "Description": r.description} for r in st.session_state.rules]),
        width="stretch", height=320)

    col_add, col_del = st.columns(2)
    with col_add:
        with st.form("add_rule_form"):
            st.markdown("#### ➕ Ajouter une règle")
            new_id = st.text_input("ID (ex : R43)", value=f"R{len(st.session_state.rules) + 1}")
            new_cat = st.selectbox("Catégorie", ["Réseau", "Impression", "Messagerie", "Sécurité/AD", "Poste/OS", "Applicatif"])
            new_prems = st.text_input("Prémisses séparées par des virgules")
            new_concl = st.text_input("Conclusion")
            new_cf = st.slider("CF de la règle", 0.2, 1.0, 0.90, 0.05)
            new_is_diag = st.checkbox("Diagnostic final ?", value=True)
            new_desc = st.text_input("Description")
            new_res = st.text_area("Procédure de résolution")
            if st.form_submit_button("Ajouter"):
                prem_list = [p.strip() for p in new_prems.split(",") if p.strip()]
                if new_id and prem_list and new_concl:
                    ok, msg = admin_tool.add_rule(Rule(new_id, new_cat, prem_list, new_concl, new_cf,
                                                       new_is_diag, new_desc, new_res))
                    (st.success if ok else st.error)(msg)
                    if ok:
                        st.rerun()
    with col_del:
        st.markdown("#### 🗑️ Supprimer / exporter")
        to_del = st.selectbox("Règle à supprimer :", [r.id for r in st.session_state.rules])
        if st.button("Supprimer la règle sélectionnée"):
            ok, msg = admin_tool.delete_rule(to_del)
            if ok:
                st.success(msg)
                st.rerun()
        import json
        from dataclasses import asdict
        st.download_button("⬇️ Exporter les règles (JSON)",
                           json.dumps([asdict(r) for r in st.session_state.rules], indent=2, ensure_ascii=False),
                           file_name="regles_helpdesk.json", mime="application/json")

# ------------------------------------------------------------------ ONGLET 4
with tab4:
    st.subheader("📊 Évaluation (30 cas) et benchmark mesuré")
    rows, correct = evaluate_30_cases(engine)
    m1, m2, m3 = st.columns(3)
    m1.metric("Cas testés", f"{len(rows)}")
    m2.metric("Réussites du système expert", f"{correct}/{len(rows)} ({100*correct/len(rows):.1f}%)")
    m3.metric("Règles dans la base", f"{len(st.session_state.rules)}")
    st.caption("Ces 30 cas sont écrits avec les règles : ils prouvent la cohérence interne, pas la qualité externe.")
    st.dataframe(pd.DataFrame([{
        "Cas": r["id"], "Scénario": r["desc"], "Attendu": r["expected"],
        "Prédit": r["pred"], "CF MYCIN": r["cf"], "Résultat": "✅" if r["ok"] else "❌"} for r in rows]),
        width="stretch", height=350)

    st.markdown("---")
    st.markdown("#### 🤖 Benchmark sur tickets bruités (système expert mesuré vs Scikit-learn)")
    st.caption("10 % d'omission de symptômes, 15 % de symptôme parasite, 10 tirages. "
               "Tickets fabriqués à partir des règles : étude de sensibilité au bruit, pas validation.")
    if st.button("Lancer le benchmark"):
        with st.spinner("Calcul en cours..."):
            bench = run_noise_benchmark(st.session_state.rules)
        df = pd.DataFrame([{"Modèle": k, "Précision moyenne (%)": round(v[0], 1),
                            "Min (%)": round(v[1], 1), "Max (%)": round(v[2], 1)} for k, v in bench.items()])
        st.bar_chart(df.set_index("Modèle")["Précision moyenne (%)"])
        st.table(df)
