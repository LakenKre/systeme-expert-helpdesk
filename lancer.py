#!/usr/bin/env python3
"""Lanceur unique du systeme expert helpdesk N1.

Une seule commande installe les dependances puis demarre les deux interfaces :

    python lancer.py

Etapes affichees : environnement Python, environnement virtuel, dependances,
auto-test du moteur, interface Flask, interface Streamlit.
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import os
import socket
import subprocess
import sys
import time
import webbrowser
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"
LOGS = ROOT / ".logs"
REQUIREMENTS = ROOT / "requirements.txt"
MARKER = VENV / ".requirements.sha256"
TOTAL_STEPS = 6


class LaunchError(RuntimeError):
    """Erreur bloquante presentee a l'utilisateur."""


# --------------------------------------------------------------------------
# Affichage
# --------------------------------------------------------------------------

def setup_console() -> None:
    """Force l'UTF-8 pour que les accents et les cadres s'affichent partout."""
    if sys.platform == "win32":
        try:
            ctypes.windll.kernel32.SetConsoleOutputCP(65001)
            ctypes.windll.kernel32.SetConsoleCP(65001)
        except Exception:
            pass
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def banner() -> None:
    print("=" * 64)
    print("  Systeme expert helpdesk N1 - lancement complet")
    print("=" * 64, flush=True)


def step(number: int, label: str) -> None:
    print(f"[{number}/{TOTAL_STEPS}] {label} ... ", end="", flush=True)


def ok(detail: str = "") -> None:
    print(f"OK{f' ({detail})' if detail else ''}", flush=True)


def fail(detail: str) -> None:
    print("ECHEC", flush=True)
    raise LaunchError(detail)


# --------------------------------------------------------------------------
# Etapes
# --------------------------------------------------------------------------

def check_python() -> str:
    if sys.version_info < (3, 9):
        fail(
            f"Python {sys.version.split()[0]} detecte, Python 3.9 ou plus est requis. "
            "Installez une version recente depuis https://www.python.org/downloads/."
        )
    return f"Python {sys.version.split()[0]}"


def venv_python() -> Path:
    if sys.platform == "win32":
        return VENV / "Scripts" / "python.exe"
    return VENV / "bin" / "python"


def ensure_venv() -> str:
    python = venv_python()
    if python.exists():
        return "deja cree"
    try:
        subprocess.run(
            [sys.executable, "-m", "venv", str(VENV)],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        fail(
            "impossible de creer .venv.\n"
            f"{exc.stdout or ''}{exc.stderr or ''}\n"
            "Astuce Debian/Ubuntu : sudo apt install python3-venv"
        )
    return ".venv cree"


def requirements_digest() -> str:
    return hashlib.sha256(REQUIREMENTS.read_bytes()).hexdigest()


def install_requirements(skip: bool) -> str:
    python = venv_python()
    digest = requirements_digest()
    if MARKER.exists() and MARKER.read_text(encoding="utf-8").strip() == digest:
        return "deja a jour"
    if skip:
        return "installation ignoree (--no-install)"

    cmd = [
        str(python), "-m", "pip", "install",
        "--disable-pip-version-check", "-q", "-r", str(REQUIREMENTS),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True, cwd=ROOT)
    except subprocess.CalledProcessError as exc:
        detail = (exc.stdout or "") + (exc.stderr or "")
        fail(
            "l'installation des dependances a echoue.\n"
            f"{detail.strip()[-1500:]}\n"
            "Verifiez la connexion reseau puis relancez : python lancer.py"
        )
    MARKER.write_text(digest, encoding="utf-8")
    return "requirements.txt installe"


SMOKE_TEST = """
import helpdesk_expert_system as h
rules = h.build_knowledge_base()
ontology = h.build_domain_ontology()
engine = h.HelpdeskInferenceEngine(rules, ontology)
rows, passed = h.evaluate_30_cases(engine)
assert len(rules) >= 40, f"seulement {len(rules)} regles"
assert passed == len(rows), f"{passed}/{len(rows)} cas reussis"
print(f"{len(rules)} regles, {len(ontology)} frames, {passed}/{len(rows)} cas")
"""


def smoke_test() -> str:
    try:
        proc = subprocess.run(
            [str(venv_python()), "-c", SMOKE_TEST],
            check=True,
            capture_output=True,
            text=True,
            cwd=ROOT,
            timeout=120,
            env=child_env(),
        )
    except subprocess.TimeoutExpired:
        fail("l'auto-test du moteur a depasse 120 secondes.")
    except subprocess.CalledProcessError as exc:
        fail(
            "l'auto-test du moteur a echoue.\n"
            f"{(exc.stderr or exc.stdout or '').strip()[-1500:]}"
        )
    return proc.stdout.strip().splitlines()[-1]


def child_env() -> dict:
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return env


# --------------------------------------------------------------------------
# Reseau et processus
# --------------------------------------------------------------------------

def port_is_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def pick_port(preferred: int) -> tuple[int, str]:
    for port in range(preferred, preferred + 20):
        if port_is_free(port):
            if port == preferred:
                return port, ""
            return port, f"port {preferred} occupe, bascule sur {port}"
    raise LaunchError(
        f"aucun port libre entre {preferred} et {preferred + 19}. "
        "Liberez un port ou utilisez --flask-port / --streamlit-port."
    )


def tail(path: Path, lines: int = 25) -> str:
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return "(journal indisponible)"
    return "\n".join(content.strip().splitlines()[-lines:])


def start_process(name: str, cmd: list[str], log_path: Path) -> subprocess.Popen:
    LOGS.mkdir(exist_ok=True)
    log_file = open(log_path, "w", encoding="utf-8", errors="replace")
    kwargs = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    try:
        return subprocess.Popen(
            cmd,
            cwd=ROOT,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            env=child_env(),
            **kwargs,
        )
    except OSError as exc:
        raise LaunchError(f"impossible de demarrer {name} : {exc}") from exc


def wait_ready(name: str, url: str, process: subprocess.Popen, log_path: Path,
               timeout: float = 60.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise LaunchError(
                f"{name} s'est arrete immediatement (code {process.returncode}).\n"
                f"Dernieres lignes de {log_path.name} :\n{tail(log_path)}"
            )
        try:
            with urlopen(url, timeout=2) as response:
                if response.status < 500:
                    return
        except (URLError, OSError):
            time.sleep(0.4)
    raise LaunchError(
        f"{name} ne repond pas sur {url} apres {int(timeout)} s.\n"
        f"Dernieres lignes de {log_path.name} :\n{tail(log_path)}"
    )


def stop_process(process: subprocess.Popen | None, name: str) -> None:
    if process is None or process.poll() is not None:
        return
    print(f"  arret de {name} ...", flush=True)
    try:
        if sys.platform == "win32":
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                capture_output=True,
                check=False,
            )
        else:
            process.terminate()
            process.wait(timeout=8)
    except Exception:
        try:
            process.kill()
        except Exception:
            pass


# --------------------------------------------------------------------------
# Interfaces
# --------------------------------------------------------------------------

def launch_flask(port: int) -> tuple[subprocess.Popen, int, str]:
    actual, note = pick_port(port)
    log_path = LOGS / "flask.log"
    cmd = [
        str(venv_python()), "-m", "flask",
        "--app", "helpdesk_expert_system:create_flask_app",
        "run",
        "--host", "127.0.0.1",
        "--port", str(actual),
        "--no-debugger",
        "--no-reload",
    ]
    process = start_process("Flask", cmd, log_path)
    wait_ready("Flask", f"http://127.0.0.1:{actual}/", process, log_path)
    return process, actual, note


def launch_streamlit(port: int) -> tuple[subprocess.Popen, int, str]:
    actual, note = pick_port(port)
    log_path = LOGS / "streamlit.log"
    cmd = [
        str(venv_python()), "-m", "streamlit", "run", "app_gui.py",
        "--server.address", "127.0.0.1",
        "--server.port", str(actual),
        "--server.headless", "true",
        "--browser.gatherUsageStats", "false",
    ]
    process = start_process("Streamlit", cmd, log_path)
    wait_ready(
        "Streamlit",
        f"http://127.0.0.1:{actual}/_stcore/health",
        process,
        log_path,
    )
    return process, actual, note


def summarize(flask_port: int, streamlit_port: int) -> None:
    print("-" * 64)
    print("  Interfaces pretes :")
    print(f"    Demo web (Flask)      http://127.0.0.1:{flask_port}")
    print(f"    Console (Streamlit)   http://127.0.0.1:{streamlit_port}")
    print(f"  Journaux : {LOGS.relative_to(ROOT)}\\flask.log et streamlit.log")
    print("  Ctrl+C pour arreter proprement les deux interfaces.")
    print("-" * 64, flush=True)


# --------------------------------------------------------------------------
# Programme
# --------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Installe et lance le systeme expert helpdesk N1.",
    )
    parser.add_argument("--flask-port", type=int, default=5000,
                        help="port de la demo web (defaut : 5000)")
    parser.add_argument("--streamlit-port", type=int, default=8501,
                        help="port de la console technicien (defaut : 8501)")
    parser.add_argument("--check-only", action="store_true",
                        help="installe et teste le moteur sans demarrer les interfaces")
    parser.add_argument("--no-browser", action="store_true",
                        help="ne pas ouvrir le navigateur")
    parser.add_argument("--no-install", action="store_true",
                        help="ne pas relancer pip si .venv existe")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    setup_console()
    banner()

    flask_process = None
    streamlit_process = None
    try:
        step(1, "Environnement Python")
        ok(check_python())

        step(2, "Environnement virtuel (.venv)")
        ok(ensure_venv())

        step(3, "Installation des dependances")
        ok(install_requirements(args.no_install))

        step(4, "Auto-test du moteur (regles, frames, 30 cas)")
        ok(smoke_test())

        if args.check_only:
            print("-" * 64)
            print("  Auto-test termine : aucune interface demarree (--check-only).")
            print("-" * 64, flush=True)
            return 0

        step(5, "Interface Flask (demo web)")
        flask_process, flask_port, note = launch_flask(args.flask_port)
        ok(f"http://127.0.0.1:{flask_port}{' · ' + note if note else ''}")

        step(6, "Interface Streamlit (console technicien)")
        streamlit_process, streamlit_port, note = launch_streamlit(args.streamlit_port)
        ok(f"http://127.0.0.1:{streamlit_port}{' · ' + note if note else ''}")

        summarize(flask_port, streamlit_port)

        if not args.no_browser:
            webbrowser.open(f"http://127.0.0.1:{flask_port}")
            webbrowser.open(f"http://127.0.0.1:{streamlit_port}")

        while True:
            time.sleep(1)
            for name, process in (("Flask", flask_process), ("Streamlit", streamlit_process)):
                if process.poll() is not None:
                    raise LaunchError(
                        f"{name} s'est arrete (code {process.returncode}). "
                        f"Consultez {LOGS / (name.lower() + '.log')}."
                    )
    except KeyboardInterrupt:
        print("\nArret demande.", flush=True)
        return 0
    except LaunchError as exc:
        print(f"\nERREUR : {exc}", file=sys.stderr, flush=True)
        return 1
    finally:
        stop_process(streamlit_process, "Streamlit")
        stop_process(flask_process, "Flask")


if __name__ == "__main__":
    sys.exit(main())
