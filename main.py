"""Point d'entrée universel du Système Expert Helpdesk N1/N2.

Usage :
    python main.py --web        # Lance l'application web Flask (port 5000)
    python main.py --gui        # Lance la console Streamlit (port 8501)
    python main.py --cli        # Lance le mode diagnostic interactif console
    python main.py --eval       # Exécute l'évaluation des 30 cas et le benchmark ML
    python main.py              # Affiche l'aide et les commandes disponibles
"""

import sys
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

def main():
    args = sys.argv[1:]
    
    if not args or "--help" in args or "-h" in args:
        print(__doc__)
        print("Commandes directes disponibles :")
        print("  python main.py --web   -> Portail Web Utilisateur N1 (Flask)")
        print("  python main.py --gui   -> Console Technicien (Streamlit)")
        print("  python main.py --cli   -> Diagnostic interactif en console")
        print("  python main.py --eval  -> Évaluation des 30 cas & benchmark ML")
        print("\nOu utilisez les scripts directs :")
        print("  python lancer.py")
        print("  lancer.bat")
        return

    first = args[0]
    if first == "--web":
        from app_flask import create_flask_app
        app = create_flask_app()
        app.run(host="127.0.0.1", port=5000, debug=False)
    elif first == "--gui":
        subprocess.run(["streamlit", "run", str(BASE_DIR / "app_gui.py")])
    elif first == "--cli":
        import helpdesk_expert_system
        helpdesk_expert_system.interactive_cli()
    elif first in ("--eval", "--benchmark", "--test"):
        import helpdesk_expert_system
        helpdesk_expert_system.evaluate_expert_system_and_compare_ml()
    else:
        import helpdesk_expert_system
        helpdesk_expert_system.evaluate_expert_system_and_compare_ml()

if __name__ == "__main__":
    main()
