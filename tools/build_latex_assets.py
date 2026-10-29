"""Générateur d'assets graphiques haute résolution pour le rapport LaTeX du Système Expert Helpdesk.
Génère la couverture A4, le fond de la page 2, le logo 1024x1024 et le filigrane.
"""

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IMG_DIR = ROOT / "latex_rapport" / "images"
IMG_DIR.mkdir(parents=True, exist_ok=True)

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

def render_html_to_image(html_code: str, output_path: Path, width: int, height: int):
    temp_html = IMG_DIR / f"_temp_{output_path.stem}.html"
    temp_html.write_text(html_code, encoding="utf-8")
    
    cmd = [
        CHROME,
        "--headless=new",
        "--disable-gpu",
        "--hide-scrollbars",
        f"--window-size={width},{height}",
        f"--screenshot={str(output_path.resolve())}",
        f"file:///{str(temp_html.resolve()).replace(os.sep, '/')}"
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    if temp_html.exists():
        temp_html.unlink()
    print(f"[OK] Generated: {output_path.name} ({output_path.stat().st_size} bytes)")

# 1. LOGO 1024x1024 (Transparent)
html_logo = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
body {
  margin: 0;
  padding: 0;
  background: transparent;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 1024px;
  height: 1024px;
}
svg {
  width: 860px;
  height: 860px;
  filter: drop-shadow(0 20px 40px rgba(15, 92, 107, 0.35));
}
</style>
</head>
<body>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256">
  <g fill="none" stroke="#0F5C6B" stroke-width="22" stroke-linecap="round" stroke-linejoin="round">
    <path d="M56 36 V220"/>
    <path d="M200 36 V220"/>
    <path d="M56 128 H96"/>
    <path d="M160 128 H200"/>
  </g>
  <path d="M128 88 L168 128 L128 168 L88 128 Z M128 114 A14 14 0 1 0 128 142 A14 14 0 1 0 128 114 Z" fill="#0284C7" fill-rule="evenodd"/>
</svg>
</body>
</html>"""
render_html_to_image(html_logo, IMG_DIR / "logo_helpdesk_1024.png", 1024, 1024)

# 2. FILIGRANE 1024x1024 (Opacité ultra-faible pour l'arrière-plan LaTeX)
html_watermark = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
body {
  margin: 0;
  padding: 0;
  background: transparent;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 1024px;
  height: 1024px;
}
svg {
  width: 900px;
  height: 900px;
  opacity: 0.055;
}
</style>
</head>
<body>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256">
  <g fill="none" stroke="#0F5C6B" stroke-width="22" stroke-linecap="round" stroke-linejoin="round">
    <path d="M56 36 V220"/>
    <path d="M200 36 V220"/>
    <path d="M56 128 H96"/>
    <path d="M160 128 H200"/>
  </g>
  <path d="M128 88 L168 128 L128 168 L88 128 Z M128 114 A14 14 0 1 0 128 142 A14 14 0 1 0 128 114 Z" fill="#0F5C6B" fill-rule="evenodd"/>
</svg>
</body>
</html>"""
render_html_to_image(html_watermark, IMG_DIR / "watermark_helpdesk.png", 1024, 1024)

# 3. PAGE 1 : COUVERTURE FULL-BLEED A4 (1241 x 1755 px @ 150 DPI)
html_cover = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
* { box-sizing: border-box; }
body {
  margin: 0;
  width: 1241px;
  height: 1755px;
  background: radial-gradient(circle at 80% 20%, #157385 0%, #0B3B45 40%, #071F24 80%, #051417 100%);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  color: #FFFFFF;
  position: relative;
  overflow: hidden;
  padding: 80px 75px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
}
/* Décoration géométrique en filigrane */
.bg-grid {
  position: absolute;
  top: 0; left: 0; right: 0; bottom: 0;
  background-image: 
    linear-gradient(rgba(255, 255, 255, 0.03) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255, 255, 255, 0.03) 1px, transparent 1px);
  background-size: 40px 40px;
  pointer-events: none;
}
.bg-glow {
  position: absolute;
  top: -200px; right: -200px;
  width: 800px; height: 800px;
  background: radial-gradient(circle, rgba(2, 132, 199, 0.25) 0%, transparent 70%);
  border-radius: 50%;
  pointer-events: none;
}
.header-inst {
  position: relative;
  z-index: 2;
  border-bottom: 2px solid rgba(255, 255, 255, 0.15);
  padding-bottom: 30px;
}
.inst-title {
  font-size: 20px;
  font-weight: 800;
  letter-spacing: 0.15em;
  text-transform: uppercase;
  color: #B45309;
  margin: 0 0 8px 0;
}
.inst-sub {
  font-size: 15px;
  font-weight: 500;
  color: rgba(255, 255, 255, 0.8);
  letter-spacing: 0.05em;
  margin: 0;
}
.center-content {
  position: relative;
  z-index: 2;
  margin: 40px 0;
}
.badge-meta {
  display: inline-block;
  background: rgba(2, 132, 199, 0.2);
  border: 1px solid rgba(2, 132, 199, 0.5);
  color: #38BDF8;
  padding: 8px 20px;
  border-radius: 30px;
  font-size: 14px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  margin-bottom: 28px;
}
.main-title {
  font-size: 58px;
  font-weight: 900;
  line-height: 1.12;
  letter-spacing: -0.02em;
  margin: 0 0 24px 0;
  color: #FFFFFF;
  text-shadow: 0 4px 20px rgba(0,0,0,0.4);
}
.main-title span {
  color: #38BDF8;
}
.desc-text {
  font-size: 20px;
  line-height: 1.55;
  color: rgba(255, 255, 255, 0.85);
  max-width: 900px;
  margin: 0 0 40px 0;
  font-weight: 400;
}
.card-pills {
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
}
.card-pill {
  background: rgba(255, 255, 255, 0.08);
  backdrop-filter: blur(10px);
  border: 1px solid rgba(255, 255, 255, 0.15);
  padding: 12px 24px;
  border-radius: 12px;
  font-size: 15px;
  font-weight: 600;
  color: #FFFFFF;
}
.card-pill b {
  color: #FBBF24;
}
.footer-box {
  position: relative;
  z-index: 2;
  background: rgba(0, 0, 0, 0.4);
  backdrop-filter: blur(15px);
  border: 1px solid rgba(255, 255, 255, 0.15);
  border-radius: 16px;
  padding: 28px 36px;
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.footer-left p {
  margin: 0 0 6px 0;
  font-size: 16px;
}
.footer-left p strong {
  color: #FBBF24;
}
.footer-right {
  text-align: right;
  font-size: 14px;
  color: rgba(255, 255, 255, 0.7);
}
</style>
</head>
<body>
  <div class="bg-grid"></div>
  <div class="bg-glow"></div>

  <div class="header-inst">
    <p class="inst-title">UNIVERSITÉ FÉLIX HOUPHOUËT-BOIGNY · ABIDJAN</p>
    <p class="inst-sub">UFR Mathématiques & Informatique · Master 2 MIAGE · Année Académique 2026-2027</p>
  </div>

  <div class="center-content">
    <div class="badge-meta">Projet d'Intelligence Artificielle · Sujet N° 1</div>
    <h1 class="main-title">SYSTÈME EXPERT<br><span>HELPDESK NIVEAU 1</span></h1>
    <p class="desc-text">
      Automatisation du diagnostic d'infrastructure informatique, qualification ITIL des incidents,
      moteur d'inférence à base de règles avec gestion de l'incertitude selon l'algèbre de Shortliffe (MYCIN).
    </p>
    <div class="card-pills">
      <div class="card-pill"><b>42</b> Règles de production</div>
      <div class="card-pill"><b>30/30</b> Cas validés (100 %)</div>
      <div class="card-pill"><b>Double</b> Chaînage avant / arrière</div>
      <div class="card-pill"><b>3</b> Interfaces (Web, GUI, CLI)</div>
    </div>
  </div>

  <div class="footer-box">
    <div class="footer-left">
      <p>Enseignant responsable : <strong>Dr GBAME Gbede Sylvain</strong></p>
      <p style="font-size:14px;color:rgba(255,255,255,0.75);margin:0">Équipe Projet Master 2 MIAGE · Octobre 2026</p>
    </div>
    <div class="footer-right">
      <p style="margin:0;font-weight:600;color:#FFFFFF">Cahier de Conception & Recette Technique</p>
      <p style="margin:4px 0 0 0">Rapport exhaustif d'évaluation des 16 écrans</p>
    </div>
  </div>
</body>
</html>"""
render_html_to_image(html_cover, IMG_DIR / "cover_helpdesk.png", 1241, 1755)

# 4. PAGE 2 : FOND ÉLÉGANT AVEC VOILE SOMBRE (1241 x 1755 px)
html_page2 = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
body {
  margin: 0;
  width: 1241px;
  height: 1755px;
  background: linear-gradient(145deg, #071F24 0%, #0B3B45 50%, #0B1220 100%);
  position: relative;
  overflow: hidden;
}
.bg-grid {
  position: absolute;
  top: 0; left: 0; right: 0; bottom: 0;
  background-image: 
    linear-gradient(rgba(255, 255, 255, 0.02) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255, 255, 255, 0.02) 1px, transparent 1px);
  background-size: 32px 32px;
}
.circle-glow {
  position: absolute;
  top: 40%; left: 50%;
  transform: translate(-50%, -50%);
  width: 900px; height: 900px;
  background: radial-gradient(circle, rgba(15, 92, 107, 0.3) 0%, transparent 70%);
  border-radius: 50%;
}
</style>
</head>
<body>
  <div class="bg-grid"></div>
  <div class="circle-glow"></div>
</body>
</html>"""
render_html_to_image(html_page2, IMG_DIR / "page2_bg.png", 1241, 1755)

print("\nAll LaTeX visual assets generated successfully!")
