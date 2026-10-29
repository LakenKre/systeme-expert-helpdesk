#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Console technicien Streamlit - Système Expert Helpdesk N1 (M2 MIAGE UFHB).
Lancement : streamlit run app_gui.py

Interface de démonstration : diagnostic guidé (chaînage arrière), chaînage avant,
administration de la base de règles, évaluation sur 30 cas et benchmark bruité.
"""

from __future__ import annotations

import html
import json
import re
import textwrap
from dataclasses import asdict
from pathlib import Path

import pandas as pd
import streamlit as st

from helpdesk_expert_system import (
    QUESTIONS_SYMPTOMES,
    HelpdeskInferenceEngine,
    Rule,
    RuleBaseAdminTool,
    build_domain_ontology,
    build_knowledge_base,
    evaluate_30_cases,
    run_noise_benchmark,
    ui_explanation,
)

st.set_page_config(
    page_title="Helpdesk N1 · Console technicien",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --------------------------------------------------------------------------- #
#  Référentiels d'affichage
# --------------------------------------------------------------------------- #

CATEGORIES = ["Réseau", "Impression", "Messagerie", "Sécurité/AD", "Poste/OS", "Applicatif"]

CATEGORY_LABELS = {
    "Réseau": "Réseau & connectivité",
    "Impression": "Impression",
    "Messagerie": "Messagerie",
    "Sécurité/AD": "Sécurité & AD",
    "Poste/OS": "Poste & système",
    "Applicatif": "Applicatif métier",
}

CERTAINTIES = [
    (1.0, "Oui, certain"),
    (0.8, "Probablement"),
    (0.5, "Peut-être"),
    (0.0, "Non"),
]

MONOGRAM_SVG = (
    '<svg viewBox="0 0 256 256" width="22" height="22" fill="none" aria-hidden="true" focusable="false">'
    '<g stroke="currentColor" stroke-width="22" stroke-linecap="round" stroke-linejoin="round">'
    '<path d="M56 36 V220"/><path d="M200 36 V220"/><path d="M56 128 H96"/><path d="M160 128 H200"/>'
    '</g><path d="M128 88 L168 128 L128 168 L88 128 Z M128 114 A14 14 0 1 0 128 142 A14 14 0 1 0 128 114 Z" '
    'fill="#0284C7" fill-rule="evenodd"/></svg>'
)

STEP_PREFIX = re.compile(r"^(\d+[.)]|[-–•])\s*")


# --------------------------------------------------------------------------- #
#  Utilitaires de rendu
# --------------------------------------------------------------------------- #

def esc(value) -> str:
    return html.escape(str(value), quote=True)


def fr(cf: float) -> str:
    """Nombre à deux décimales, virgule française."""
    return f"{float(cf):.2f}".replace(".", ",")


def pct(cf: float) -> str:
    return f"{float(cf) * 100:.0f}\u202f%"


def dec1(value: float) -> str:
    return f"{float(value):.1f}".replace(".", ",")


def block(markup: str) -> None:
    """Injecte un fragment HTML (dé-indenté pour éviter les blocs de code)."""
    st.markdown(textwrap.dedent(markup).strip(), unsafe_allow_html=True)


def confidence_band(cf: float) -> tuple[str, str]:
    if cf >= 0.85:
        return "Confiance élevée", "ok"
    if cf >= 0.60:
        return "Confiance moyenne", "warn"
    return "Confiance faible", "low"


def gauge(cf: float, tone: str = "ok") -> str:
    width = max(0.0, min(1.0, float(cf))) * 100
    return (
        f'<div class="hd-gauge hd-gauge--{tone}" role="img" '
        f'aria-label="Certitude {pct(cf)}">'
        f'<span style="width:{width:.1f}%"></span></div>'
    )


def rule_steps(resolution: str) -> list[str]:
    steps = []
    for line in (resolution or "").splitlines():
        line = line.strip()
        if line:
            steps.append(STEP_PREFIX.sub("", line).strip())
    return steps


def steps_markup(steps: list[str]) -> str:
    items = "".join(f"<li>{esc(step)}</li>" for step in steps)
    return f'<ol class="hd-steps">{items}</ol>'


def explanation_tree_markup(engine: HelpdeskInferenceEngine, rule: Rule, answers: dict[str, float] | None = None) -> str:
    inter_map = {r.conclusion: r for r in st.session_state.rules if not r.is_diagnostic}
    known = answers if answers is not None else {f: ft.cf for f, ft in engine.facts.items()}
    tree = ui_explanation(engine, rule, known, inter_map)
    cf = engine.get_fact_cf(rule.conclusion)
    weakest = min((engine.get_fact_cf(p) for p in rule.premises), default=0.0)
    raw_trace = engine.explain_conclusion(rule.conclusion)

    def render_child(node: dict) -> str:
        kind = node.get("kind", "observation")
        node_cf = node.get("cf", 0.0)
        label = esc(node.get("label", ""))
        fact = esc(node.get("fact", ""))
        children = node.get("children", [])

        if kind == "inference":
            sub_rule = node.get("rule")
            rule_badge = f" · Règle {esc(sub_rule.id)}" if sub_rule else ""
            subs = "".join(render_child(c) for c in children)
            return (
                '<div class="hd-trace-item hd-trace-item--inter">'
                '  <div class="hd-trace-item__line">'
                f'    <span class="hd-trace-tag hd-trace-tag--inter">Déduction intermédiaire{rule_badge}</span>'
                f'    <span class="hd-trace-item__cf">{fr(node_cf)}</span>'
                '  </div>'
                f'  <div class="hd-trace-item__label">{label}</div>'
                f'  <div class="hd-trace-item__key"><code>{fact}</code></div>'
                f'  <div class="hd-trace-subchain">{subs}</div>'
                '</div>'
            )
        else:
            return (
                '<div class="hd-trace-item hd-trace-item--obs">'
                '  <div class="hd-trace-item__line">'
                '    <span class="hd-trace-tag hd-trace-tag--obs">Observation constatée</span>'
                f'    <span class="hd-trace-item__cf">{fr(node_cf)}</span>'
                '  </div>'
                f'  <div class="hd-trace-item__label">{label}</div>'
                f'  <div class="hd-trace-item__key"><code>{fact}</code></div>'
                '</div>'
            )

    children_html = "".join(render_child(c) for c in tree.get("children", []))
    frame = engine.ontology.get(rule.category)
    frame_html = ""
    if frame:
        fi = frame.to_dict()
        frame_html = (
            '<div class="hd-trace-frame">'
            f'  <div class="hd-trace-frame__title">Cadre Ontologique · Domaine {esc(rule.category)}</div>'
            '  <div class="hd-trace-frame__grid">'
            f'    <div><span>SLA cible</span><strong>{fi.get("sla_heures", "—")} h</strong></div>'
            f'    <div><span>Droits admin</span><strong>{"Requis" if fi.get("droits_admin_requis") else "Non requis"}</strong></div>'
            f'    <div><span>Escalade N2</span><strong>{esc(fi.get("escalade_cible", "—"))}</strong></div>'
            '  </div>'
            '</div>'
        )

    return (
        '<div class="hd-trace-tree">'
        '  <div class="hd-trace-card hd-trace-card--root">'
        '    <div class="hd-trace-card__top">'
        '      <span class="hd-trace-tag hd-trace-tag--root">Diagnostic final retenu</span>'
        f'      <span class="hd-trace-badge hd-trace-badge--cf">CF combiné {fr(cf)}</span>'
        '    </div>'
        f'    <div class="hd-trace-card__title">{esc(rule.description)}</div>'
        '    <div class="hd-trace-calc">'
        '      <span>Calcul MYCIN :</span>'
        f'      <code>min(prémisses) [{fr(weakest)}] × règle {esc(rule.id)} [{fr(rule.cf)}] = {fr(cf)}</code>'
        '    </div>'
        '  </div>'
        '  <div class="hd-trace-chain">'
        f'    <div class="hd-trace-chain__header">Prémisses ayant validé la règle {esc(rule.id)} :</div>'
        f'    {children_html}'
        '  </div>'
        f'  {frame_html}'
        '  <details class="hd-trace-raw-details">'
        '    <summary>Afficher la trace brute console (format texte)</summary>'
        f'    <pre class="hd-trace-raw-code">{esc(raw_trace)}</pre>'
        '  </details>'
        '</div>'
    )


def note(kind: str, title: str, body: str) -> str:
    return (
        f'<div class="hd-note hd-note--{kind}">'
        f'<p class="hd-note__title">{esc(title)}</p>'
        f'<p class="hd-note__body">{body}</p>'
        f"</div>"
    )


def metric_grid(items: list[tuple[str, str, str]]) -> str:
    cells = "".join(
        f'<div class="hd-metric"><p class="hd-metric__label">{esc(label)}</p>'
        f'<p class="hd-metric__value">{esc(value)}</p>'
        f'<p class="hd-metric__hint">{esc(hint)}</p></div>'
        for label, value, hint in items
    )
    return f'<div class="hd-metrics">{cells}</div>'


def fact_label(fact: str) -> str:
    """Libellé humain d'un fait (symptôme ou fait intermédiaire)."""
    if fact in QUESTIONS_SYMPTOMES:
        return QUESTIONS_SYMPTOMES[fact]
    for rule in st.session_state.rules:
        if rule.conclusion == fact:
            return rule.description
    return fact.replace("_", " ").capitalize()


def conclusion_label(conclusion: str) -> str:
    if conclusion == "AUCUN_DIAGNOSTIC_ESCALADE_N2":
        return "Aucun diagnostic N1 — escalade Niveau 2"
    return fact_label(conclusion)


def flash(kind: str, title: str, body: str) -> None:
    st.session_state["_flash"] = (kind, title, body)


def render_flash() -> None:
    payload = st.session_state.pop("_flash", None)
    if payload:
        block(note(*payload))


def brand_markup() -> str:
    svg = MONOGRAM_SVG
    path = Path(__file__).with_name("static") / "brand.svg"
    if path.is_file():
        try:
            raw = path.read_text(encoding="utf-8")
            if "<svg" in raw:
                svg = raw.replace("<svg", '<svg class="hd-brand__svg"', 1)
        except OSError:
            pass
    return (
        '<div class="hd-brand">'
        f'<div class="hd-brand__mark">{svg}</div>'
        '<div class="hd-brand__text">'
        '<p class="hd-brand__name">Helpdesk N1</p>'
        '<p class="hd-brand__role">Console technicien</p>'
        "</div></div>"
    )


# --------------------------------------------------------------------------- #
#  Feuille de style (injectée une seule fois)
# --------------------------------------------------------------------------- #

CSS = """
<style>
:root {
  --ink: #0B1220;
  --muted: #54637A;
  --line: #DDE4EC;
  --canvas: #F5F7F9;
  --surface: #FFFFFF;
  --primary: #0F5C6B;
  --primary-hover: #0C4C59;
  --primary-soft: #E8F3F4;
  --accent: #B45309;
  --accent-soft: #FDF4E7;
  --success: #15803D;
  --success-soft: #EAF6EE;
  --danger: #B42318;
  --danger-soft: #FDECEA;
  --shadow: 0 1px 2px rgba(11, 18, 32, .06);
}

html, body, .stApp, [data-testid="stAppViewContainer"] {
  font-family: system-ui, "Segoe UI", Roboto, Arial, sans-serif;
  color: var(--ink);
  -webkit-font-smoothing: antialiased;
}
.stApp, [data-testid="stAppViewContainer"] { background: var(--canvas); }

/* ---- Chrome Streamlit : on garde la navigation, on retire le bruit ---- */
#MainMenu, footer, [data-testid="stToolbar"], [data-testid="stDecoration"],
[data-testid="stAppDeployButton"], [data-testid="stStatusWidget"] { display: none !important; }
[data-testid="stHeader"] { background: transparent; }
[data-testid="stSidebarNav"] { display: none; }

/* ---- Gabarit ---- */
[data-testid="stMainBlockContainer"] {
  max-width: 1180px;
  padding: 1.25rem 2.5rem 4rem;
}
[data-testid="stSidebar"] {
  background: var(--surface);
  border-right: 1px solid var(--line);
}
[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] {
  padding: 0.25rem 1rem 2rem;
}
[data-testid="stSidebarHeader"] { height: 44px; min-height: 44px; padding-bottom: 0; }
[data-testid="stSidebar"] [data-testid="stVerticalBlock"] { gap: 10px; }
[data-testid="stMain"] [data-testid="stVerticalBlock"] { gap: 12px; }
[data-testid="stHorizontalBlock"] { gap: 16px; }

/* ---- Typographie applicative ---- */
.hd-eyebrow {
  font-size: 12px;
  font-weight: 600;
  letter-spacing: .08em;
  text-transform: uppercase;
  color: var(--muted);
  margin: 0 0 8px;
}
.hd-head {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: start;
  gap: 16px 32px;
  padding-bottom: 20px;
  border-bottom: 1px solid var(--line);
}
.hd-head__main { min-width: 0; }
.hd-head h1 {
  font-size: 34px;
  line-height: 1.12;
  letter-spacing: -.02em;
  font-weight: 650;
  margin: 0;
  color: var(--ink);
}
.hd-lede {
  font-size: 14px;
  line-height: 1.6;
  color: var(--muted);
  margin: 12px 0 0;
  max-width: 68ch;
}
.hd-head__meta { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; padding-top: 24px; }

.hd-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: 999px;
  border: 1px solid var(--line);
  background: var(--surface);
  font-size: 12px;
  font-weight: 600;
  line-height: 1.5;
  color: var(--muted);
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
.hd-pill--primary { background: var(--primary-soft); border-color: transparent; color: var(--primary); }
.hd-pill--ok { background: var(--success-soft); border-color: transparent; color: var(--success); }
.hd-pill--warn { background: var(--accent-soft); border-color: transparent; color: var(--accent); }
.hd-pill--low { background: var(--danger-soft); border-color: transparent; color: var(--danger); }

/* ---- Cartes ---- */
.hd-card {
  background: var(--surface);
  border: none;
  border-radius: 12px;
  box-shadow: var(--shadow);
  padding: 20px 24px;
}
.hd-card__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}
.hd-card__head h3, .hd-card h3.hd-section-title {
  font-size: 16px;
  font-weight: 650;
  letter-spacing: -.01em;
  margin: 0;
  color: var(--ink);
}
.hd-card p:last-child { margin-bottom: 0; }

.hd-strip {
  display: flex;
  align-items: center;
  gap: 8px 20px;
  flex-wrap: wrap;
  background: var(--surface);
  border: none;
  border-radius: 12px;
  box-shadow: var(--shadow);
  padding: 12px 20px;
  font-size: 13px;
  color: var(--muted);
}
.hd-strip__lead { font-weight: 650; color: var(--ink); font-size: 14px; }
.hd-strip__sep { width: 1px; height: 14px; background: var(--line); }
.hd-strip b { color: var(--ink); font-weight: 600; font-variant-numeric: tabular-nums; }

/* ---- Question guidée ---- */
.hd-question-card { padding: 24px 28px; }
.hd-question__meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}
.hd-question {
  font-size: 26px;
  line-height: 1.32;
  letter-spacing: -.015em;
  font-weight: 600;
  margin: 14px 0 0;
  color: var(--ink);
  text-wrap: pretty;
}
.hd-question__hint { font-size: 13px; color: var(--muted); margin: 10px 0 0; }

/* ---- Résultat ---- */
.hd-result__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}
.hd-result__title {
  font-size: 26px;
  line-height: 1.28;
  letter-spacing: -.015em;
  font-weight: 650;
  margin: 0;
  color: var(--ink);
  max-width: 52ch;
  text-wrap: pretty;
}
.hd-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: .04em;
  text-transform: uppercase;
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
}
.hd-badge--ok { background: var(--success-soft); color: var(--success); }
.hd-badge--warn { background: var(--accent-soft); color: var(--accent); }
.hd-badge--low { background: var(--danger-soft); color: var(--danger); }

.hd-gauge {
  height: 6px;
  border-radius: 999px;
  background: var(--line);
  overflow: hidden;
  margin-top: 20px;
}
.hd-gauge > span { display: block; height: 100%; border-radius: 999px; background: var(--primary); }
.hd-gauge--ok > span { background: var(--success); }
.hd-gauge--warn > span { background: var(--accent); }
.hd-gauge--low > span { background: var(--danger); }

.hd-result__foot {
  display: flex;
  gap: 8px 28px;
  flex-wrap: wrap;
  margin-top: 12px;
  font-size: 13px;
  color: var(--muted);
}
.hd-result__foot b { color: var(--ink); font-weight: 650; font-variant-numeric: tabular-nums; }

/* ---- Étapes numérotées ---- */
.hd-steps { margin: 16px 0 0; padding: 0; list-style: none; counter-reset: hd-step; }
.hd-steps li {
  position: relative;
  padding-left: 34px;
  margin-bottom: 14px;
  font-size: 14px;
  line-height: 1.6;
  color: var(--ink);
  counter-increment: hd-step;
}
.hd-steps li::before {
  content: counter(hd-step);
  position: absolute;
  left: 0;
  top: 1px;
  width: 22px;
  height: 22px;
  border-radius: 999px;
  background: var(--primary-soft);
  color: var(--primary);
  font-size: 12px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  font-variant-numeric: tabular-nums;
}
.hd-steps li:last-child { margin-bottom: 0; }

.hd-method { margin: 12px 0 0; padding-left: 18px; display: grid; gap: 6px; }
.hd-method li { font-size: 13px; line-height: 1.6; color: var(--muted); }
.hd-method li::marker { color: var(--line); }

/* ---- Listes descriptives ---- */
.hd-meta-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 16px 24px;
  margin: 16px 0 0;
}
.hd-meta-grid dt {
  font-size: 12px;
  font-weight: 600;
  letter-spacing: .06em;
  text-transform: uppercase;
  color: var(--muted);
  margin-bottom: 4px;
}
.hd-meta-grid dd {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--ink);
  line-height: 1.5;
}

/* ---- Rail contextuel ---- */
.hd-meta-list { margin: 16px 0 0; display: grid; gap: 12px; }
.hd-meta-list dt {
  font-size: 11px;
  font-weight: 600;
  letter-spacing: .06em;
  text-transform: uppercase;
  color: var(--muted);
  margin-bottom: 2px;
}
.hd-meta-list dd { margin: 0; font-size: 13px; font-weight: 600; color: var(--ink); line-height: 1.45; }

.hd-rail-list { list-style: none; margin: 14px 0 0; padding: 0; display: grid; gap: 12px; }
.hd-rail-list li {
  display: flex;
  gap: 10px;
  font-size: 13px;
  line-height: 1.5;
  color: var(--muted);
}
.hd-rail-dot {
  flex: 0 0 6px;
  width: 6px;
  height: 6px;
  margin-top: 6px;
  border-radius: 999px;
  background: var(--line);
}
.hd-rail-list li.is-active { color: var(--ink); font-weight: 600; }
.hd-rail-list li.is-active .hd-rail-dot { background: var(--primary); }
.hd-rail-sep { height: 1px; background: var(--line); margin: 20px 0 16px; }
.hd-rail-note {
  margin: 16px 0 0;
  padding-top: 12px;
  border-top: 1px solid var(--line);
  font-size: 12px;
  color: var(--muted);
  font-variant-numeric: tabular-nums;
}

.hd-cf-value {
  margin: 12px 0 0;
  font-size: 13px;
  font-weight: 650;
  color: var(--ink);
  text-align: right;
  font-variant-numeric: tabular-nums;
}
[class*="st-key-cf_card"] [data-testid="stSliderThumbValue"] { display: none; }
[class*="st-key-cf_card"] [data-testid="stSlider"] { padding-top: 6px; }

/* ---- Arbre d'inférence (Pourquoi cette conclusion ?) ---- */
.hd-trace-tree {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 4px 0;
}
.hd-trace-card {
  background: var(--surface);
  border-radius: 10px;
  box-shadow: var(--shadow);
  padding: 16px 20px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.hd-trace-card--root {
  border-left: 4px solid var(--primary);
  background: var(--surface);
}
.hd-trace-card__top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.hd-trace-card__title {
  font-size: 15px;
  font-weight: 650;
  color: var(--ink);
  line-height: 1.4;
}
.hd-trace-tag {
  display: inline-flex;
  align-items: center;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: .06em;
  text-transform: uppercase;
  padding: 2px 8px;
  border-radius: 4px;
}
.hd-trace-tag--root { background: var(--primary-soft); color: var(--primary); }
.hd-trace-tag--obs { background: #E0F2FE; color: #0369A1; }
.hd-trace-tag--inter { background: #EDE9FE; color: #6D28D9; }
.hd-trace-badge--cf {
  font-size: 13px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  color: var(--ink);
  background: var(--canvas);
  padding: 3px 10px;
  border-radius: 999px;
}
.hd-trace-calc {
  font-size: 12px;
  color: var(--muted);
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  padding-top: 6px;
  border-top: 1px solid var(--line);
}
.hd-trace-calc code {
  font-family: ui-monospace, "Cascadia Mono", Consolas, monospace;
  font-size: 12px;
  background: var(--canvas);
  padding: 2px 6px;
  border-radius: 4px;
  color: var(--ink);
}

.hd-trace-chain {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding-left: 4px;
}
.hd-trace-chain__header {
  font-size: 12px;
  font-weight: 650;
  letter-spacing: .04em;
  text-transform: uppercase;
  color: var(--muted);
}
.hd-trace-item {
  background: var(--surface);
  border-radius: 8px;
  box-shadow: var(--shadow);
  padding: 12px 16px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.hd-trace-item--obs {
  border-left: 3px solid #0284C7;
}
.hd-trace-item--inter {
  border-left: 3px solid #7C3AED;
}
.hd-trace-item__line {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.hd-trace-item__cf {
  font-size: 12px;
  font-weight: 650;
  font-variant-numeric: tabular-nums;
  color: var(--ink);
}
.hd-trace-item__label {
  font-size: 13px;
  font-weight: 600;
  color: var(--ink);
  line-height: 1.45;
}
.hd-trace-item__key code {
  font-size: 11px;
  font-family: ui-monospace, monospace;
  color: var(--muted);
  background: var(--canvas);
  padding: 1px 5px;
  border-radius: 4px;
}
.hd-trace-subchain {
  margin-top: 8px;
  padding-left: 14px;
  border-left: 2px dashed var(--line);
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.hd-trace-frame {
  background: var(--surface);
  border-radius: 8px;
  box-shadow: var(--shadow);
  padding: 14px 18px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.hd-trace-frame__title {
  font-size: 12px;
  font-weight: 700;
  letter-spacing: .05em;
  text-transform: uppercase;
  color: var(--primary);
}
.hd-trace-frame__grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}
.hd-trace-frame__grid div {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.hd-trace-frame__grid span {
  font-size: 11px;
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: .04em;
}
.hd-trace-frame__grid strong {
  font-size: 13px;
  color: var(--ink);
}

.hd-trace-raw-details summary {
  font-size: 12px;
  color: var(--muted);
  cursor: pointer;
  padding: 4px 0;
}
.hd-trace-raw-details summary:hover {
  color: var(--ink);
}
.hd-trace-raw-code {
  margin-top: 8px;
  padding: 12px 14px;
  background: var(--canvas);
  border-radius: 6px;
  font-family: ui-monospace, "Cascadia Mono", Consolas, monospace;
  font-size: 11.5px;
  line-height: 1.55;
  color: var(--ink);
  white-space: pre;
  overflow-x: auto;
}

/* ---- Notes contextuelles ---- */
.hd-note {
  border: none;
  border-left: 3px solid var(--primary);
  border-radius: 8px;
  background: var(--surface);
  padding: 14px 18px;
  box-shadow: var(--shadow);
}
.hd-note--ok { border-left-color: var(--success); background: var(--success-soft); }
.hd-note--warn { border-left-color: var(--accent); background: var(--accent-soft); }
.hd-note--low { border-left-color: var(--danger); background: var(--danger-soft); }
.hd-note__title {
  margin: 0 0 4px;
  font-size: 13px;
  font-weight: 700;
  color: var(--ink);
}
.hd-note__body { margin: 0; font-size: 13px; line-height: 1.6; color: var(--muted); }
.hd-note__body b { color: var(--ink); }

.hd-empty {
  border: 1px dashed var(--line);
  border-radius: 12px;
  background: var(--surface);
  padding: 32px 24px;
  text-align: center;
}
.hd-empty p { margin: 0; font-size: 13px; color: var(--muted); line-height: 1.6; }
.hd-empty p:first-child { font-size: 14px; font-weight: 600; color: var(--ink); margin-bottom: 4px; }

/* ---- Métriques ---- */
.hd-metrics {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 16px;
}
.hd-metric {
  background: var(--surface);
  border: none;
  border-radius: 12px;
  box-shadow: var(--shadow);
  padding: 16px 20px;
}
.hd-metric__label {
  margin: 0;
  font-size: 12px;
  font-weight: 600;
  letter-spacing: .06em;
  text-transform: uppercase;
  color: var(--muted);
}
.hd-metric__value {
  margin: 6px 0 0;
  font-size: 26px;
  font-weight: 650;
  letter-spacing: -.02em;
  color: var(--ink);
  font-variant-numeric: tabular-nums;
}
.hd-metric__hint { margin: 4px 0 0; font-size: 12px; color: var(--muted); }

/* ---- Barres du benchmark ---- */
.hd-bars { list-style: none; margin: 20px 0 0; padding: 0; display: grid; gap: 18px; }
.hd-bars__row { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; }
.hd-bars__name { font-size: 13px; font-weight: 600; color: var(--ink); }
.hd-bars__val { font-size: 13px; font-weight: 650; color: var(--ink); font-variant-numeric: tabular-nums; }
.hd-bars__track {
  height: 6px;
  margin-top: 6px;
  border-radius: 999px;
  background: var(--canvas);
  border: 1px solid var(--line);
  overflow: hidden;
}
.hd-bars__fill { display: block; height: 100%; border-radius: 999px; background: var(--muted); }
.hd-bars__fill--expert { background: var(--primary); }
.hd-bars__range { margin: 6px 0 0; font-size: 12px; color: var(--muted); font-variant-numeric: tabular-nums; }

/* ---- Rails latéraux ---- */
.hd-brand { display: flex; align-items: center; gap: 12px; }
.hd-brand__mark {
  width: 40px;
  height: 40px;
  flex: 0 0 40px;
  border-radius: 8px;
  background: var(--primary);
  color: #FFFFFF;
  display: flex;
  align-items: center;
  justify-content: center;
}
.hd-brand__mark svg { width: 22px; height: 22px; display: block; }
.hd-brand__text { min-width: 0; }
.hd-brand__name {
  margin: 0;
  font-size: 16px;
  font-weight: 650;
  letter-spacing: -.01em;
  color: var(--ink);
  line-height: 1.2;
}
.hd-brand__role {
  margin: 2px 0 0;
  font-size: 12px;
  font-weight: 600;
  letter-spacing: .06em;
  text-transform: uppercase;
  color: var(--muted);
}

.hd-side-label {
  margin: 0 0 6px;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: .08em;
  text-transform: uppercase;
  color: var(--muted);
}
.hd-side-meta {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px 12px;
  margin: 0;
}
.hd-side-meta span {
  display: block;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: .06em;
  text-transform: uppercase;
  color: var(--muted);
  margin-bottom: 2px;
}
.hd-side-meta b {
  font-size: 13px;
  font-weight: 650;
  color: var(--ink);
  font-variant-numeric: tabular-nums;
}
.hd-side-esc { margin: 10px 0 0; font-size: 12px; line-height: 1.5; color: var(--muted); }
.hd-side-esc span {
  display: block;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: .06em;
  text-transform: uppercase;
  color: var(--muted);
  margin-bottom: 2px;
}
.hd-side-empty { margin: 0; font-size: 12px; line-height: 1.6; color: var(--muted); }

.hd-count {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin: 2px 0 10px;
}
.hd-count__value {
  font-size: 26px;
  font-weight: 650;
  letter-spacing: -.02em;
  color: var(--ink);
  font-variant-numeric: tabular-nums;
  line-height: 1;
}
.hd-count__label { font-size: 12px; color: var(--muted); }

.hd-facts { list-style: none; margin: 0; padding: 0; display: grid; gap: 8px; max-height: 192px; overflow-y: auto; }
.hd-facts li {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 10px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--line);
}
.hd-facts li:last-child { border-bottom: none; padding-bottom: 0; }
.hd-facts__label {
  font-size: 12px;
  line-height: 1.45;
  color: var(--muted);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.hd-facts__val {
  font-size: 12px;
  font-weight: 650;
  color: var(--ink);
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
}
.hd-facts__val--no { color: var(--muted); font-weight: 600; }

.hd-side-foot {
  margin: 4px 0 0;
  font-size: 12px;
  color: var(--muted);
  font-variant-numeric: tabular-nums;
}

.hd-hr { border: none; border-top: 1px solid var(--line); margin: 16px 0; }

.hd-foot {
  display: flex;
  justify-content: space-between;
  gap: 8px 24px;
  flex-wrap: wrap;
  border-top: 1px solid var(--line);
  margin-top: 40px;
  padding-top: 16px;
  font-size: 12px;
  color: var(--muted);
}

/* ---- Contrôles Streamlit ---- */
[data-testid="stTabs"] [data-baseweb="tab-list"] {
  gap: 4px;
  border-bottom: 1px solid var(--line);
  background: transparent;
}
[data-testid="stTabs"] [data-baseweb="tab"] {
  height: auto;
  padding: 10px 14px;
  border-radius: 8px 8px 0 0;
  background: transparent;
}
[data-testid="stTabs"] [data-baseweb="tab"] p {
  font-size: 14px;
  font-weight: 600;
  color: var(--muted);
  margin: 0;
}
[data-testid="stTabs"] [data-baseweb="tab"]:hover p { color: var(--ink); }
[data-testid="stTabs"] [data-baseweb="tab"][aria-selected="true"] p { color: var(--primary); }
[data-testid="stTabs"] [data-baseweb="tab-highlight"] { background-color: var(--primary); height: 2px; }
[data-testid="stTabs"] [data-baseweb="tab-border"] { display: none; }
[data-testid="stTabPanel"] { padding-top: 24px; }

[data-testid^="stBaseButton"] {
  border-radius: 8px;
  box-shadow: var(--shadow);
  font-weight: 600;
}
[data-testid^="stBaseButton"] p { font-size: 14px; font-weight: 600; }
[data-testid="stBaseButton-secondary"],
[data-testid="stBaseButton-secondaryFormSubmit"] {
  background: var(--surface);
  border: 1px solid var(--line);
  color: var(--ink);
}
[data-testid="stBaseButton-secondary"]:hover,
[data-testid="stBaseButton-secondaryFormSubmit"]:hover {
  border-color: var(--primary);
  background: var(--primary-soft);
  color: var(--primary);
}
[data-testid="stBaseButton-primary"],
[data-testid="stBaseButton-primaryFormSubmit"] {
  background: var(--primary);
  border: 1px solid var(--primary);
  color: #FFFFFF;
}
[data-testid="stBaseButton-primary"] p,
[data-testid="stBaseButton-primaryFormSubmit"] p { color: #FFFFFF; }
[data-testid="stBaseButton-primary"]:hover,
[data-testid="stBaseButton-primaryFormSubmit"]:hover {
  background: var(--primary-hover);
  border-color: var(--primary-hover);
}
[data-testid="stDownloadButton"] button {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 8px;
  box-shadow: var(--shadow);
  font-weight: 600;
}
[data-testid^="stBaseButton"]:disabled {
  background: var(--canvas) !important;
  border-color: var(--line) !important;
  color: var(--muted) !important;
  box-shadow: none;
  opacity: 1;
}
[data-testid^="stBaseButton"]:disabled p { color: var(--muted) !important; }

[data-testid="stWidgetLabel"] p {
  font-size: 13px;
  font-weight: 600;
  color: var(--ink);
}
[data-testid="stCaptionContainer"] p,
[data-testid="stCaptionContainer"] { font-size: 12px; color: var(--muted); }

[data-baseweb="input"], [data-baseweb="select"] > div, [data-baseweb="textarea"] {
  border-radius: 8px !important;
  border-color: var(--line) !important;
  background: var(--surface) !important;
}
[data-testid="stSelectbox"] [role="group"],
[data-testid="stMultiSelect"] [role="group"] {
  background: var(--surface) !important;
  border: 1px solid var(--line) !important;
  border-radius: 8px !important;
}
[data-testid="stSelectbox"] [role="group"]:focus-within,
[data-testid="stMultiSelect"] [role="group"]:focus-within {
  border-color: var(--primary) !important;
  box-shadow: 0 0 0 1px var(--primary);
}
[data-baseweb="input"]:focus-within, [data-baseweb="select"] > div:focus-within,
[data-baseweb="textarea"]:focus-within {
  border-color: var(--primary) !important;
  box-shadow: 0 0 0 1px var(--primary) !important;
}
[data-baseweb="tag"] { background: var(--primary-soft) !important; border-radius: 4px !important; max-width: 100%; }
[data-baseweb="tag"] span { color: var(--primary) !important; font-weight: 600; font-size: 12px !important; }
[data-testid="stMultiSelect"] [role="group"] {
  height: auto !important;
  min-height: 40px;
  padding: 6px 8px;
  overflow: visible;
}
[data-testid="stMultiSelectTagsContainer"] {
  flex-wrap: wrap;
  gap: 4px;
  height: auto;
  overflow: visible;
}
[data-testid="stMultiSelectTagsContainer"] > [role="group"] { flex-wrap: wrap; gap: 4px; }
[data-testid="stMultiSelectTagsContainer"] [role="group"] > span {
  height: 26px;
  max-width: 100%;
  font-size: 12px;
}

[data-testid="stExpander"] details {
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--surface);
  box-shadow: var(--shadow);
}
[data-testid="stExpander"] summary {
  padding: 10px 16px;
  font-size: 13px;
  font-weight: 600;
  color: var(--muted);
}
[data-testid="stExpander"] summary:hover { color: var(--primary); }
[data-testid="stExpander"] [data-testid="stExpanderDetails"] { padding: 0 16px 16px; }

[data-testid="stDataFrame"] {
  border: none;
  border-radius: 12px;
  overflow: hidden;
  background: var(--surface);
  box-shadow: var(--shadow);
}
[data-testid="stVerticalBlockBorderWrapper"] {
  background: var(--surface);
  border: none !important;
  border-radius: 12px;
  box-shadow: var(--shadow);
}
[data-testid="stStatus"] {
  border: none;
  border-radius: 8px;
  background: var(--surface);
  box-shadow: var(--shadow);
}

[data-testid="stProgress"] { margin: 2px 0 6px; }
[data-testid="stProgress"] p { font-size: 12px; color: var(--muted); margin: 0 0 6px; }
[data-testid="stProgressBarTrack"] {
  height: 6px !important;
  border-radius: 999px !important;
  background: var(--line) !important;
  overflow: hidden;
}
[data-testid="stProgressBarTrack"] > div {
  background: var(--primary) !important;
  border-radius: 999px !important;
  transition: transform .30s ease-out;
}

[data-testid="stMarkdownContainer"] code {
  background: var(--canvas);
  border: 1px solid var(--line);
  border-radius: 4px;
  padding: 1px 5px;
  font-size: 12px;
  color: var(--muted);
}
[data-testid="stMarkdownContainer"] p:last-child { margin-bottom: 0; }
[data-testid="stMarkdownContainer"]:has([class^="hd-"], [class*=" hd-"]) { margin-bottom: 0 !important; }
[data-testid="stMarkdownContainer"] hr { border-color: var(--line); }

/* ---- Focus et mouvement ---- */
:where(a, button, input, textarea, select, summary, [tabindex]):focus-visible {
  outline: 2px solid var(--primary);
  outline-offset: 2px;
}
@keyframes hd-rise {
  from { opacity: 0; transform: translateY(6px); }
  to { opacity: 1; transform: none; }
}
.hd-head, .hd-card, .hd-metric, .hd-strip, .hd-note, .hd-empty {
  animation: hd-rise .28s ease-out both;
}

/* ---- Petits écrans ---- */
@media (max-width: 760px) {
  [data-testid="stMainBlockContainer"] { padding: 1rem 1rem 3rem; }
  [data-testid="stHorizontalBlock"] { gap: 8px; }
  .hd-head { grid-template-columns: minmax(0, 1fr); }
  .hd-head__meta { padding-top: 0; justify-content: flex-start; }
  .hd-head h1 { font-size: 26px; }
  .hd-lede { font-size: 13px; }
  .hd-card { padding: 16px; }
  .hd-question-card { padding: 18px; }
  .hd-question { font-size: 20px; }
  .hd-result__title { font-size: 20px; }
  .hd-metric__value { font-size: 20px; }
  .hd-steps li { font-size: 13px; padding-left: 30px; }
  .hd-result__foot { gap: 6px 18px; }
}

@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: .001ms !important;
    animation-delay: 0ms !important;
    transition-duration: .001ms !important;
  }
}
</style>
"""


# --------------------------------------------------------------------------- #
#  État de session et montage
# --------------------------------------------------------------------------- #

def init_state() -> None:
    if "ontology" not in st.session_state:
        st.session_state.ontology = build_domain_ontology()
    if "rules" not in st.session_state:
        st.session_state.rules = build_knowledge_base()
    if "qa_answers" not in st.session_state:
        st.session_state.qa_answers = {}
    if "forward_results" not in st.session_state:
        st.session_state.forward_results = []
    if "forward_ran" not in st.session_state:
        st.session_state.forward_ran = False
    if "bench" not in st.session_state:
        st.session_state.bench = None


def expand_primaries(premises: list[str], inter_map: dict[str, Rule], seen: frozenset = frozenset()) -> list[str]:
    """Déplie les faits intermédiaires jusqu'aux symptômes observables."""
    out: list[str] = []
    for premise in premises:
        if premise in inter_map and premise not in seen:
            out.extend(expand_primaries(inter_map[premise].premises, inter_map, seen | {premise}))
        else:
            out.append(premise)
    return out


def chain_to(premise: str, target: str, inter_map: dict[str, Rule]) -> list[Rule] | None:
    """Chaîne de règles intermédiaires menant d'une prémisse jusqu'au fait cible."""
    rule = inter_map.get(premise)
    if rule is None:
        return None
    if target in rule.premises:
        return [rule]
    for sub in rule.premises:
        sub_chain = chain_to(sub, target, inter_map)
        if sub_chain is not None:
            return [rule, *sub_chain]
    return None


def render_header(rules: list[Rule]) -> None:
    block(f"""
    <div class="hd-head">
      <div class="hd-head__main">
        <p class="hd-eyebrow">M2 MIAGE · UFHB · Système expert</p>
        <h1>Console technicien</h1>
        <p class="hd-lede">Diagnostic guidé niveau 1 : chaînage avant et arrière, facteurs de
        certitude MYCIN, procédures de résolution et traçabilité des conclusions.</p>
      </div>
      <div class="hd-head__meta">
        <span class="hd-pill hd-pill--primary">{len(rules)} règles</span>
        <span class="hd-pill">Seuil CF 0,20</span>
        <span class="hd-pill">30 cas de test</span>
      </div>
    </div>
    """)


def render_sidebar(rules: list[Rule]) -> str:
    with st.sidebar:
        block(brand_markup())

        st.markdown('<p class="hd-side-label" style="margin-top:20px">Périmètre</p>',
                    unsafe_allow_html=True)
        categories = sorted({rule.category for rule in rules if rule.is_diagnostic})
        selected = st.selectbox(
            "Catégorie d'incident",
            categories,
            format_func=lambda value: CATEGORY_LABELS.get(value, value),
            key="category_select",
            label_visibility="collapsed",
        )
        frame = st.session_state.ontology.get(selected)
        if frame is not None:
            slots = frame.to_dict()
            block(f"""
            <div class="hd-side-meta">
              <div><span>SLA cible</span><b>{esc(slots.get('sla_heures', '—'))}\u202fh</b></div>
              <div><span>Droits admin</span><b>{'Requis' if slots.get('droits_admin_requis') else 'Non requis'}</b></div>
            </div>
            <p class="hd-side-esc"><span>Escalade</span>{esc(slots.get('escalade_cible', 'Support N2'))}</p>
            """)

        st.markdown('<hr class="hd-hr">', unsafe_allow_html=True)

        answers = st.session_state.qa_answers
        st.markdown('<p class="hd-side-label">Session en cours</p>', unsafe_allow_html=True)
        if answers:
            block(f"""
            <div class="hd-count">
              <span class="hd-count__value">{len(answers)}</span>
              <span class="hd-count__label">réponse{'s' if len(answers) > 1 else ''} enregistrée{'s' if len(answers) > 1 else ''}</span>
            </div>
            """)
            items = []
            for fact, cf in list(answers.items())[:4]:
                value = "Oui" if float(cf) >= 1.0 else ("Non" if float(cf) <= 0.0 else f"CF {fr(cf)}")
                extra = "" if float(cf) >= 1.0 else " hd-facts__val--no"
                items.append(
                    f'<li><span class="hd-facts__label">{esc(fact_label(fact))}</span>'
                    f'<span class="hd-facts__val{extra}">{esc(value)}</span></li>'
                )
            rest = len(answers) - 4
            more = f'<li><span class="hd-facts__label">… et {rest} autre{"s" if rest > 1 else ""}</span></li>' if rest > 0 else ""
            block(f'<ul class="hd-facts">{"".join(items)}{more}</ul>')
        else:
            block('<p class="hd-side-empty">Aucune réponse enregistrée. Le diagnostic guidé démarre au premier clic.</p>')

        if st.button("Réinitialiser la session", key="reset_btn", width="stretch", disabled=not answers):
            st.session_state.qa_answers = {}
            st.session_state.forward_results = []
            st.session_state.forward_ran = False
            st.rerun()

        st.markdown('<hr class="hd-hr">', unsafe_allow_html=True)
        block(f'<p class="hd-side-foot">{len(rules)} règles · MYCIN · 30 cas</p>')
    return selected


# --------------------------------------------------------------------------- #
#  Onglet 1 — Diagnostic guidé
# --------------------------------------------------------------------------- #

def _rail(category: str, candidates: list[Rule], answers: dict[str, float],
          active_ids: set[str]) -> None:
    """Rail contextuel : cadre ontologique et hypothèses du périmètre."""
    frame = st.session_state.ontology.get(category)
    slots = frame.to_dict() if frame is not None else {}

    parts = []
    for rule in candidates:
        klass = ' class="is-active"' if rule.id in active_ids else ""
        parts.append(f'<li{klass}><span class="hd-rail-dot"></span>'
                     f'<span>{esc(rule.description)}</span></li>')
    items = "".join(parts)

    block(f"""
    <div class="hd-card">
      <p class="hd-eyebrow">Cadre du périmètre</p>
      <h3 class="hd-section-title">{esc(CATEGORY_LABELS.get(category, category))}</h3>
      <dl class="hd-meta-list">
        <div><dt>SLA cible</dt><dd>{esc(slots.get('sla_heures', '—'))}\u202fh</dd></div>
        <div><dt>Droits administrateur</dt><dd>{'Requis' if slots.get('droits_admin_requis') else 'Non requis'}</dd></div>
        <div><dt>Escalade N2</dt><dd>{esc(slots.get('escalade_cible', 'Support Niveau 2'))}</dd></div>
      </dl>
      <div class="hd-rail-sep"></div>
      <p class="hd-eyebrow">Hypothèses du périmètre</p>
      <ul class="hd-rail-list">{items}</ul>
      <p class="hd-rail-note">{len(candidates)} diagnostics finaux · {len(answers)} fait{'s' if len(answers) > 1 else ''} collecté{'s' if len(answers) > 1 else ''}</p>
    </div>
    """)


def tab_diagnostic(engine: HelpdeskInferenceEngine, category: str) -> None:
    candidates = [rule for rule in st.session_state.rules
                  if rule.is_diagnostic and rule.category == category]
    inter_map = {rule.conclusion: rule for rule in st.session_state.rules if not rule.is_diagnostic}
    answers = st.session_state.qa_answers

    track: list[str] = []
    for diagnostic in candidates:
        for fact in expand_primaries(diagnostic.premises, inter_map):
            if fact not in track:
                track.append(fact)

    answered = [fact for fact in track if fact in answers]
    ratio = len(answered) / len(track) if track else 0.0
    st.progress(
        min(1.0, ratio),
        text=f"{len(answered)} réponse{'s' if len(answered) > 1 else ''} sur {len(track)} faits suivis dans ce périmètre",
    )

    # ---- Sélection de la question suivante (même logique que le moteur, faits primaires) ----
    next_fact = None
    active_rule = None
    for diagnostic in candidates:
        missing = None
        possible = True
        for fact in expand_primaries(diagnostic.premises, inter_map):
            if fact in answers:
                if answers[fact] < engine.threshold:
                    possible = False
                    break
            elif missing is None:
                missing = fact
        if possible and missing is not None:
            next_fact, active_rule = missing, diagnostic
            break

    current = engine.forward_chaining(answers)
    category_diags = [(rule, cf) for rule, cf in current if rule.category == category]

    main_col, rail_col = st.columns([2.1, 1], gap="large")

    with main_col:
        if category_diags:
            best, best_cf = category_diags[0]
            label, tone = confidence_band(best_cf)
            premise_cfs = {fact: engine.get_fact_cf(fact) for fact in best.premises}
            weakest = min(premise_cfs.values()) if premise_cfs else 0.0

            block(f"""
            <div class="hd-card">
              <div class="hd-result__head">
                <div>
                  <p class="hd-eyebrow">Diagnostic retenu</p>
                  <h2 class="hd-result__title">{esc(best.description)}</h2>
                </div>
                <span class="hd-badge hd-badge--{tone}">{esc(label)} · {pct(best_cf)}</span>
              </div>
              {gauge(best_cf, tone)}
              <div class="hd-result__foot">
                <span>CF combiné <b>{fr(best_cf)}</b></span>
                <span>Règle source <b>{esc(best.id)}</b></span>
                <span>Prémisse la plus faible <b>{fr(weakest)}</b></span>
              </div>
            </div>
            """)

            steps = rule_steps(best.resolution)
            if steps:
                block(f"""
                <div class="hd-card">
                  <p class="hd-eyebrow">Procédure</p>
                  <h3 class="hd-section-title">Résolution en {len(steps)} étape{'s' if len(steps) > 1 else ''}</h3>
                  {steps_markup(steps)}
                </div>
                """)

            premises_detail = " · ".join(
                f"{esc(fact_label(fact))} ({fr(cf)})" for fact, cf in premise_cfs.items()
            )
            block(f"""
            <div class="hd-card">
              <p class="hd-eyebrow">Lecture de la conclusion</p>
              <p class="hd-question__hint" style="margin-top:0">
                La règle <b>{esc(best.id)}</b> porte une certitude de {fr(best.cf)}. La prémisse la plus
                faible est établie à {fr(weakest)} : la certitude finale est le produit des deux, soit
                <b>{fr(best_cf)}</b>.
              </p>
              <dl class="hd-meta-grid">
                <div><dt>Prémisses retenues</dt><dd style="font-weight:500">{premises_detail}</dd></div>
                <div><dt>Fait conclu</dt><dd>{esc(best.conclusion)}</dd></div>
              </dl>
            </div>
            """)

            with st.expander("Pourquoi cette conclusion ? (trace d'inférence)", expanded=True):
                block(explanation_tree_markup(engine, best, answers))

            if len(category_diags) > 1:
                others = "".join(
                    f'<li><span class="hd-facts__label">{esc(rule.description)}</span>'
                    f'<span class="hd-facts__val">{fr(cf)}</span></li>'
                    for rule, cf in category_diags[1:5]
                )
                block(f"""
                <div class="hd-card">
                  <p class="hd-eyebrow">Autres conclusions retenues</p>
                  <ul class="hd-facts" style="max-height:none;margin-top:8px">{others}</ul>
                </div>
                """)

        elif next_fact is not None and active_rule is not None:
            step = len(answers) + 1
            block(f"""
            <div class="hd-card hd-question-card">
              <div class="hd-question__meta">
                <span class="hd-pill hd-pill--primary">Question {step}</span>
                <span class="hd-eyebrow" style="margin:0">{esc(CATEGORY_LABELS.get(category, category))}</span>
              </div>
              <p class="hd-question">{esc(fact_label(next_fact))}</p>
              <p class="hd-question__hint">Répondez selon ce que l'utilisateur constate réellement, pas selon l'hypothèse la plus probable.</p>
            </div>
            """)

            columns = st.columns(4, gap="small")
            for column, (cf, label) in zip(columns, CERTAINTIES):
                with column:
                    if st.button(
                        label,
                        key=f"answer_{next_fact}_{cf}",
                        width="stretch",
                        type="primary" if cf == 1.0 else "secondary",
                    ):
                        answers[next_fact] = cf
                        st.rerun()
                    st.caption(f"CF {fr(cf)}")

            chain: list[Rule] = []
            for premise in active_rule.premises:
                found = chain_to(premise, next_fact, inter_map)
                if found:
                    chain = found
                    break
            deepest = chain[-1] if chain else active_rule

            with st.expander("Pourquoi cette question ?"):
                chain_text = " → ".join(
                    f"{rule.id} ({esc(rule.description)})" for rule in [active_rule, *chain]
                )
                rows = []
                for premise in deepest.premises:
                    if premise in answers:
                        value = answers[premise]
                        state = (f"Confirmé · CF {fr(value)}" if value >= engine.threshold
                                 else f"Écarté · CF {fr(value)}")
                        tone = "ok" if value >= engine.threshold else "low"
                        rows.append(
                            f'<li><span class="hd-facts__label">{esc(fact_label(premise))}</span>'
                            f'<span class="hd-pill hd-pill--{tone}">{esc(state)}</span></li>'
                        )
                    else:
                        rows.append(
                            f'<li><span class="hd-facts__label">{esc(fact_label(premise))}</span>'
                            f'<span class="hd-pill">À vérifier</span></li>'
                        )
                block(f"""
                <dl class="hd-meta-grid" style="margin-top:0">
                  <div><dt>Hypothèse testée</dt><dd>{esc(active_rule.description)}</dd></div>
                  <div><dt>Règle visée</dt><dd>{esc(active_rule.id)} · CF {fr(active_rule.cf)}</dd></div>
                </dl>
                <p class="hd-eyebrow" style="margin-top:20px">Chaîne de raisonnement</p>
                <p class="hd-question__hint" style="margin-top:0">{chain_text}</p>
                <p class="hd-eyebrow" style="margin-top:20px">Prémisses du palier courant</p>
                <ul class="hd-facts" style="max-height:none">{''.join(rows)}</ul>
                """)

            block("""
            <div class="hd-card">
              <p class="hd-eyebrow">Méthode</p>
              <h3 class="hd-section-title">Chaînage arrière, une question à la fois</h3>
              <ul class="hd-method">
                <li>Le moteur part du diagnostic à prouver, puis remonte ses prémisses jusqu'aux symptômes observables.</li>
                <li>Il pose uniquement la première question dont la réponse manque, au lieu d'interroger sur tout.</li>
                <li>Chaque réponse est pondérée : sous le seuil de 0,20, la piste est écartée et l'utilisateur n'est plus sollicité.</li>
              </ul>
            </div>
            """)

        elif not answers:
            block(f"""
            <div class="hd-empty">
              <p>Aucune question disponible pour ce périmètre</p>
              <p>Les règles de la catégorie « {esc(CATEGORY_LABELS.get(category, category))} » ne comportent
              pas de symptôme interrogeable. Sélectionnez une autre catégorie dans la barre latérale.</p>
            </div>
            """)

        else:
            frame = st.session_state.ontology.get(category)
            slots = frame.to_dict() if frame is not None else {}
            block(f"""
            <div class="hd-card">
              <div class="hd-result__head">
                <div>
                  <p class="hd-eyebrow">Suite du traitement</p>
                  <h2 class="hd-result__title">Escalade vers le support Niveau 2</h2>
                </div>
                <span class="hd-pill hd-pill--warn">Hors périmètre N1</span>
              </div>
              <p class="hd-question__hint" style="margin-top:14px">
                Les réponses collectées ne permettent pas de conclure dans la catégorie
                « {esc(CATEGORY_LABELS.get(category, category))} ». Le dossier est transmis avec les faits
                déjà établis : aucune question supplémentaire n'est posée à l'utilisateur.
              </p>
              <dl class="hd-meta-grid">
                <div><dt>File d'escalade</dt><dd>{esc(slots.get('escalade_cible', 'Support Niveau 2'))}</dd></div>
                <div><dt>SLA cible</dt><dd>{esc(slots.get('sla_heures', '—'))}\u202fh</dd></div>
                <div><dt>Faits transmis</dt><dd>{len(answers)}</dd></div>
              </dl>
            </div>
            """)
            block(note(
                "warn",
                "Décision de refus assumée",
                "Le système ne force pas de diagnostic sous le seuil de 0,20 : mieux vaut une escalade "
                "explicite qu'une conclusion non étayée.",
            ))

    with rail_col:
        _rail(category, candidates, answers, {rule.id for rule, _ in category_diags})


# --------------------------------------------------------------------------- #
#  Onglet 2 — Chaînage avant
# --------------------------------------------------------------------------- #

def tab_forward(engine: HelpdeskInferenceEngine) -> None:
    st.markdown(
        '<p class="hd-eyebrow" style="margin-bottom:0">Chaînage avant</p>',
        unsafe_allow_html=True,
    )
    block("""
    <p class="hd-lede" style="margin-top:4px">Déclarez les symptômes observés et leur certitude.
    Le moteur combine les facteurs MYCIN, enchaîne les règles et classe les diagnostics par confiance.</p>
    """)

    form_col, side_col = st.columns([2.25, 1], gap="large")

    input_facts: dict[str, float] = {}
    with form_col:
        selected = st.multiselect(
            "Symptômes observés",
            options=list(QUESTIONS_SYMPTOMES.keys()),
            format_func=lambda key: QUESTIONS_SYMPTOMES[key],
            default=["ping_passerelle_ok", "ping_ip_externe_ok", "site_web_inaccessible_par_nom"],
            key="forward_symptoms",
            help="Les symptômes élémentaires issus de l'entretien avec l'utilisateur.",
        )

        if selected:
            with st.container(border=True, key="cf_card"):
                st.markdown('<p class="hd-side-label">Certitude déclarée par symptôme</p>',
                            unsafe_allow_html=True)
                for symptom in selected:
                    text_col, slider_col, value_col = st.columns([2.4, 1.5, 0.6])
                    with text_col:
                        block(f"""
                        <p class="hd-question__hint" style="margin:2px 0 2px;color:var(--ink);font-weight:600">
                          {esc(QUESTIONS_SYMPTOMES[symptom])}
                        </p>
                        <code>{esc(symptom)}</code>
                        """)
                    with slider_col:
                        input_facts[symptom] = st.slider(
                            "Certitude",
                            min_value=0.2,
                            max_value=1.0,
                            value=1.0,
                            step=0.05,
                            key=f"cf_{symptom}",
                            label_visibility="collapsed",
                        )
                    with value_col:
                        block(f'<p class="hd-cf-value">CF {fr(input_facts[symptom])}</p>')
        else:
            block(note(
                "warn",
                "Aucun symptôme sélectionné",
                "Choisissez au moins un symptôme dans la liste pour lancer un chaînage avant.",
            ))

        launch = st.button(
            "Exécuter le chaînage avant",
            key="forward_run",
            type="primary",
            width="content",
            disabled=not selected,
        )
        if launch and selected:
            results = engine.forward_chaining(input_facts)
            st.session_state.forward_results = sorted(results, key=lambda item: item[1], reverse=True)
            st.session_state.forward_ran = True

    with side_col:
        block(f"""
        <div class="hd-card">
          <p class="hd-eyebrow">Paramètres du chaînage</p>
          <h3 class="hd-section-title">Moteur MYCIN</h3>
          <dl class="hd-meta-list">
            <div><dt>Seuil d'activation</dt><dd>{fr(engine.threshold)}</dd></div>
            <div><dt>Symptômes déclarés</dt><dd>{len(selected)}</dd></div>
            <div><dt>Règles évaluées</dt><dd>{len(st.session_state.rules)}</dd></div>
          </dl>
          <div class="hd-rail-sep"></div>
          <p class="hd-rail-note">Chaque règle activée pondère son propre CF par la certitude
          minimale de ses prémisses, puis les conclusions sont triées par certitude décroissante.</p>
        </div>
        """)

    if not st.session_state.forward_ran:
        block("""
        <div class="hd-empty">
          <p>Aucun chaînage exécuté</p>
          <p>Sélectionnez des symptômes, ajustez leur certitude, puis lancez l'analyse pour obtenir
          les diagnostics atteints et leurs procédures.</p>
        </div>
        """)
        return

    results = st.session_state.forward_results
    if not results:
        block(note(
            "warn",
            "Aucun diagnostic au-dessus du seuil",
            "Aucune règle n'atteint un facteur de certitude de 0,20 avec ces observations : "
            "le dossier relève du support Niveau 2.",
        ))
        return

    block(f"""
    <div class="hd-strip">
      <span class="hd-strip__lead">{len(results)} diagnostic{'s' if len(results) > 1 else ''} retenu{'s' if len(results) > 1 else ''}</span>
      <span class="hd-strip__sep"></span>
      <span>{len(input_facts)} symptôme{'s' if len(input_facts) > 1 else ''} déclaré{'s' if len(input_facts) > 1 else ''}</span>
      <span>Tri par certitude décroissante</span>
    </div>
    """)

    for rank, (rule, cf) in enumerate(results, start=1):
        label, tone = confidence_band(cf)
        with st.container(border=True):
            block(f"""
            <div class="hd-result__head">
              <div>
                <p class="hd-eyebrow">Priorité {rank} · {esc(CATEGORY_LABELS.get(rule.category, rule.category))}</p>
                <h3 class="hd-result__title" style="font-size:20px">{esc(rule.description)}</h3>
              </div>
              <span class="hd-badge hd-badge--{tone}">{esc(label)} · {pct(cf)}</span>
            </div>
            {gauge(cf, tone)}
            <div class="hd-result__foot">
              <span>Règle <b>{esc(rule.id)}</b></span>
              <span>CF combiné <b>{fr(cf)}</b></span>
              <span>SLA <b>{esc((st.session_state.ontology.get(rule.category).to_dict().get('sla_heures', '—')) if st.session_state.ontology.get(rule.category) else '—')}\u202fh</b></span>
            </div>
            """)
            steps = rule_steps(rule.resolution)
            with st.expander(f"Procédure de résolution ({len(steps)} étapes)"):
                block(steps_markup(steps))
            with st.expander("Pourquoi cette conclusion ? (trace d'inférence)", expanded=True):
                block(explanation_tree_markup(engine, rule))


# --------------------------------------------------------------------------- #
#  Onglet 3 — Base de règles
# --------------------------------------------------------------------------- #

def tab_rules(admin_tool: RuleBaseAdminTool) -> None:
    rules = st.session_state.rules
    diagnostics = [rule for rule in rules if rule.is_diagnostic]
    intermediates = [rule for rule in rules if not rule.is_diagnostic]
    categories = sorted({rule.category for rule in rules})

    st.markdown('<p class="hd-eyebrow" style="margin-bottom:0">Base de connaissances</p>',
                unsafe_allow_html=True)
    block("""
    <p class="hd-lede" style="margin-top:4px">Inspection, audit et enrichissement des règles.
    Toute modification est immédiatement utilisée par le moteur d'inférence.</p>
    """)

    block(metric_grid([
        ("Règles", str(len(rules)), "Base active du moteur"),
        ("Diagnostics finaux", str(len(diagnostics)), "Conclusions proposables"),
        ("Règles intermédiaires", str(len(intermediates)), "Palier d'agrégation"),
        ("Catégories", str(len(categories)), "Périmètres couverts"),
    ]))

    render_flash()

    consistency = admin_tool.check_consistency()
    anomalies = consistency["doublons_premisses"] + consistency["faits_intermediaires_inutilises"]
    if anomalies:
        items = "".join(f"<li>{esc(item)}</li>" for item in anomalies)
        block(f"""
        <div class="hd-note hd-note--warn">
          <p class="hd-note__title">Audit de cohérence : {len(anomalies)} anomalie{'s' if len(anomalies) > 1 else ''}</p>
          <p class="hd-note__body">Ces points ne bloquent pas l'inférence mais fragilisent la lisibilité de la base.</p>
          <ul class="hd-facts" style="max-height:none;margin-top:10px">{items}</ul>
        </div>
        """)
    else:
        block(note(
            "ok",
            "Audit de cohérence : aucune anomalie",
            "Pas de doublon de prémisses, et chaque fait intermédiaire est consommé par au moins une règle.",
        ))

    st.markdown('<p class="hd-eyebrow" style="margin-top:12px">Explorer les règles</p>',
                unsafe_allow_html=True)
    search_col, category_col, type_col = st.columns([2, 1.4, 1.2])
    with search_col:
        search = st.text_input("Recherche", placeholder="Identifiant, conclusion ou description",
                               key="rule_search", label_visibility="collapsed")
    with category_col:
        category_filter = st.multiselect(
            "Catégories", options=categories, default=[], key="rule_cat_filter",
            label_visibility="collapsed", placeholder="Toutes les catégories",
        )
    with type_col:
        type_filter = st.selectbox(
            "Type", ["Tous les types", "Diagnostics finaux", "Règles intermédiaires"],
            key="rule_type_filter", label_visibility="collapsed",
        )

    filtered = rules
    if category_filter:
        filtered = [rule for rule in filtered if rule.category in category_filter]
    if type_filter == "Diagnostics finaux":
        filtered = [rule for rule in filtered if rule.is_diagnostic]
    elif type_filter == "Règles intermédiaires":
        filtered = [rule for rule in filtered if not rule.is_diagnostic]
    if search.strip():
        needle = search.strip().lower()
        filtered = [
            rule for rule in filtered
            if needle in rule.id.lower()
            or needle in rule.conclusion.lower()
            or needle in rule.description.lower()
            or needle in rule.category.lower()
        ]

    st.caption(f"{len(filtered)} règle{'s' if len(filtered) > 1 else ''} affichée{'s' if len(filtered) > 1 else ''} sur {len(rules)}")

    if filtered:
        table = pd.DataFrame([
            {
                "ID": rule.id,
                "Catégorie": CATEGORY_LABELS.get(rule.category, rule.category),
                "Type": "Diagnostic final" if rule.is_diagnostic else "Intermédiaire",
                "Prémisses (SI)": " ET ".join(rule.premises),
                "Conclusion (ALORS)": rule.conclusion,
                "CF": float(rule.cf),
                "Description": rule.description,
            }
            for rule in filtered
        ])
        st.dataframe(
            table,
            width="stretch",
            height=340,
            hide_index=True,
            column_config={
                "ID": st.column_config.TextColumn("ID", width="small"),
                "Catégorie": st.column_config.TextColumn("Catégorie", width="medium"),
                "Type": st.column_config.TextColumn("Type", width="small"),
                "Prémisses (SI)": st.column_config.TextColumn("Prémisses (SI)", width="large"),
                "Conclusion (ALORS)": st.column_config.TextColumn("Conclusion (ALORS)", width="medium"),
                "CF": st.column_config.ProgressColumn("CF", min_value=0.0, max_value=1.0, format="%.2f", width="small"),
                "Description": st.column_config.TextColumn("Description", width="large"),
            },
        )
    else:
        block("""
        <div class="hd-empty">
          <p>Aucune règle ne correspond au filtre</p>
          <p>Élargissez la recherche ou réinitialisez les filtres de catégorie et de type.</p>
        </div>
        """)

    left, right = st.columns([1.7, 1])

    with left:
        with st.container(border=True):
            st.markdown('<p class="hd-side-label">Nouvelle règle</p>', unsafe_allow_html=True)
            with st.form("add_rule_form", clear_on_submit=False):
                row = st.columns([1, 1.4])
                new_id = row[0].text_input("Identifiant", value=f"R{len(rules) + 1}", key="rule_id")
                new_cat = row[1].selectbox("Catégorie", CATEGORIES, key="rule_cat")
                new_prems = st.text_input(
                    "Prémisses (SI), séparées par des virgules",
                    key="rule_premises",
                    placeholder="ping_passerelle_ok, ping_ip_externe_ok",
                )
                row2 = st.columns([2, 1])
                new_concl = row2[0].text_input("Conclusion (ALORS)", key="rule_conclusion")
                new_cf = row2[1].slider("CF de la règle", 0.2, 1.0, 0.90, 0.05, key="rule_cf")
                new_desc = st.text_input("Description lisible", key="rule_desc")
                new_is_diag = st.checkbox("Diagnostic final", value=True, key="rule_diag")
                new_res = st.text_area(
                    "Procédure de résolution (une étape par ligne)",
                    key="rule_res",
                    height=110,
                )
                submitted = st.form_submit_button("Ajouter la règle", key="rule_submit", type="primary")

            if submitted:
                premise_list = [item.strip() for item in new_prems.split(",") if item.strip()]
                if not new_id.strip() or not premise_list or not new_concl.strip():
                    flash("low", "Règle incomplète",
                          "L'identifiant, au moins une prémisse et la conclusion sont obligatoires.")
                    st.rerun()
                else:
                    created = Rule(
                        new_id.strip(), new_cat, premise_list, new_concl.strip(),
                        float(new_cf), new_is_diag,
                        new_desc.strip() or new_concl.strip(),
                        new_res.strip(),
                    )
                    ok, message = admin_tool.add_rule(created)
                    flash("ok" if ok else "low",
                          "Règle ajoutée" if ok else "Ajout refusé",
                          esc(message))
                    if ok:
                        st.rerun()

    with right:
        with st.container(border=True):
            st.markdown('<p class="hd-side-label">Retirer une règle</p>', unsafe_allow_html=True)
            target = st.selectbox(
                "Règle à supprimer",
                [rule.id for rule in rules],
                format_func=lambda rule_id: next(
                    (f"{rule_id} · {rule.description}" for rule in rules if rule.id == rule_id), rule_id
                ),
                key="rule_delete",
                label_visibility="collapsed",
            )
            if st.button("Supprimer la règle sélectionnée", key="rule_delete_btn", width="stretch"):
                ok, message = admin_tool.delete_rule(target)
                flash("ok" if ok else "low",
                      "Règle supprimée" if ok else "Suppression impossible",
                      esc(message))
                st.rerun()

        with st.container(border=True):
            st.markdown('<p class="hd-side-label">Sauvegarde</p>', unsafe_allow_html=True)
            payload = json.dumps([asdict(rule) for rule in rules], indent=2, ensure_ascii=False)
            st.download_button(
                "Exporter les règles (JSON)",
                payload,
                file_name="regles_helpdesk.json",
                mime="application/json",
                key="rule_export",
                width="stretch",
            )
            st.caption(f"{len(rules)} règles · UTF-8 · jeu complet, filtres ignorés")


# --------------------------------------------------------------------------- #
#  Onglet 4 — Évaluation et benchmark
# --------------------------------------------------------------------------- #

def tab_evaluation(engine: HelpdeskInferenceEngine, rules: list[Rule]) -> None:
    st.markdown('<p class="hd-eyebrow" style="margin-bottom:0">Évaluation</p>', unsafe_allow_html=True)
    block("""
    <p class="hd-lede" style="margin-top:4px">Jeu de 30 cas de référence, puis mesure de la
    sensibilité du moteur au bruit comparée à trois classifieurs supervisés.</p>
    """)

    rows, correct = evaluate_30_cases(engine)
    total = len(rows) or 1
    block(metric_grid([
        ("Cas évalués", str(len(rows)), "Scénarios de référence"),
        ("Conformité", f"{correct}/{len(rows)}", f"{100 * correct / total:.0f}\u202f% des cas"),
        ("Règles en base", str(len(rules)), "Dont 32 diagnostics finaux"),
    ]))

    block(note(
        "warn",
        "Avertissement méthodologique",
        "Ces 30 cas sont écrits à partir des règles de la base. Ils vérifient la cohérence interne "
        "du raisonnement, pas la qualité du système sur des tickets réels.",
    ))

    table = pd.DataFrame([
        {
            "Cas": row["id"],
            "Scénario": row["desc"],
            "Attendu": conclusion_label(row["expected"]),
            "Prédit": conclusion_label(row["pred"]),
            "CF": float(row["cf"]),
            "Statut": "Conforme" if row["ok"] else "Écart",
        }
        for row in rows
    ])
    st.dataframe(
        table,
        width="stretch",
        height=380,
        hide_index=True,
        column_config={
            "Cas": st.column_config.TextColumn("Cas", width="small"),
            "Scénario": st.column_config.TextColumn("Scénario", width="large"),
            "Attendu": st.column_config.TextColumn("Attendu", width="medium"),
            "Prédit": st.column_config.TextColumn("Prédit", width="medium"),
            "CF": st.column_config.ProgressColumn("CF", min_value=0.0, max_value=1.0, format="%.2f", width="small"),
            "Statut": st.column_config.TextColumn("Statut", width="small"),
        },
    )
    st.caption("Statut « Conforme » : le diagnostic prédit est identique à l'attendu. "
               "Un écart est un signal d'alerte sur la base, pas une tolérance.")

    st.markdown('<p class="hd-eyebrow" style="margin-top:20px">Benchmark</p>', unsafe_allow_html=True)
    block("""
    <p class="hd-lede" style="margin-top:4px">Tickets simulés à partir des règles : 10\u202f% de symptômes
    omis, 15\u202f% de symptômes parasites, 10 tirages indépendants. Le protocole mesure la sensibilité
    au bruit ; il ne constitue pas une validation externe.</p>
    """)

    if st.button("Lancer le benchmark", key="bench_btn", type="primary", width="stretch"):
        with st.status("Benchmark en cours", expanded=True) as status:
            st.write("Génération des tickets bruités et entraînement des classifieurs…")
            benchmark = run_noise_benchmark(rules)
            st.session_state.bench = benchmark
            status.update(label="Benchmark terminé", state="complete", expanded=False)
        st.rerun()

    benchmark = st.session_state.bench
    if not benchmark:
        block("""
        <div class="hd-empty">
          <p>Aucune mesure disponible</p>
          <p>Lancez le benchmark pour comparer le système expert à LinearSVC, Random Forest et KNN
          sur les mêmes tickets bruités.</p>
        </div>
        """)
        return

    expert = benchmark.get("Système expert", (0.0, 0.0, 0.0))
    best_ml = max((value[0] for name, value in benchmark.items() if name != "Système expert"), default=0.0)
    gap = expert[0] - best_ml

    bars = []
    for name, (mean, low, high) in benchmark.items():
        tone = " hd-bars__fill--expert" if name == "Système expert" else ""
        bars.append(f"""
        <li>
          <div class="hd-bars__row">
            <span class="hd-bars__name">{esc(name)}</span>
            <span class="hd-bars__val">{dec1(mean)}\u202f%</span>
          </div>
          <div class="hd-bars__track"><span class="hd-bars__fill{tone}" style="width:{max(0.0, min(100.0, mean)):.1f}%"></span></div>
          <p class="hd-bars__range">Min {dec1(low)}\u202f% · Max {dec1(high)}\u202f%</p>
        </li>
        """)

    block(f"""
    <div class="hd-card">
      <div class="hd-card__head">
        <div>
          <p class="hd-eyebrow">Sensibilité au bruit</p>
          <h3 class="hd-section-title">Précision moyenne par modèle</h3>
        </div>
        <span class="hd-pill">{len(benchmark)} modèles · 10 tirages</span>
      </div>
      <ul class="hd-bars">{''.join(bars)}</ul>
    </div>
    """)

    block(note(
        "warn" if gap < 0 else "ok",
        "Lecture du résultat",
        f"Le système expert obtient <b>{dec1(expert[0])}\u202f%</b> de précision moyenne, contre "
        f"<b>{dec1(best_ml)}\u202f%</b> pour le meilleur classifieur. "
        + (
            "L'écart s'explique par la perte d'information des règles à seuil fixe face aux symptômes "
            "manquants ; l'avantage du système expert reste l'explicabilité de chaque conclusion."
            if gap < 0 else
            "Le système expert reste au niveau des classifieurs tout en produisant une justification lisible."
        ),
    ))

    stats = pd.DataFrame([
        {"Modèle": name, "Précision moyenne (%)": round(value[0], 1),
         "Min (%)": round(value[1], 1), "Max (%)": round(value[2], 1)}
        for name, value in benchmark.items()
    ])
    st.dataframe(stats, width="stretch", hide_index=True)


# --------------------------------------------------------------------------- #
#  Application
# --------------------------------------------------------------------------- #

def main() -> None:
    init_state()
    st.markdown(CSS, unsafe_allow_html=True)

    rules = st.session_state.rules
    ontology = st.session_state.ontology
    engine = HelpdeskInferenceEngine(rules, ontology)
    admin_tool = RuleBaseAdminTool(rules)

    render_header(rules)
    category = render_sidebar(rules)

    tab_1, tab_2, tab_3, tab_4 = st.tabs([
        "Diagnostic guidé",
        "Chaînage avant",
        "Base de règles",
        "Évaluation & benchmark",
    ])

    with tab_1:
        tab_diagnostic(engine, category)
    with tab_2:
        tab_forward(engine)
    with tab_3:
        tab_rules(admin_tool)
    with tab_4:
        tab_evaluation(engine, rules)

    block(f"""
    <div class="hd-foot">
      <span>Système expert helpdesk N1 · M2 MIAGE UFHB · démonstration académique</span>
      <span>{len(rules)} règles · chaînage avant et arrière · MYCIN</span>
    </div>
    """)


main()
