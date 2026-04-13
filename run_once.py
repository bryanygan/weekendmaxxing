"""Run the deal-hunting pipeline once and open the dashboard."""

import sys
import webbrowser
from pathlib import Path

import requests


def main() -> None:
    # 1. Check Ollama
    print("[run_once] Checking Ollama...", end=" ")
    try:
        resp = requests.get("http://localhost:11434/api/tags", timeout=5)
        if resp.status_code == 200:
            print("Running")
        else:
            raise ConnectionError()
    except Exception:
        print("NOT RUNNING")
        print("  Install Ollama: https://ollama.com/download/windows")
        print("  Then run: ollama pull llama3.1:8b && ollama serve")
        sys.exit(1)

    # 2. Check config files
    print("[run_once] Checking configs...", end=" ")
    missing = []
    for cfg in ["config/destinations.json", "config/constraints.json", "config/settings.py"]:
        if not Path(cfg).exists():
            missing.append(cfg)
    if missing:
        print("MISSING")
        for m in missing:
            print(f"  - {m}")
        sys.exit(1)
    print("Found")

    # 3. Run pipeline
    from orchestrator.pipeline import run_pipeline

    summary = run_pipeline()

    # 4. Print summary
    print(f"\n[run_once] Summary: {summary}")

    # 5. Open dashboard
    dashboard = Path("data/dashboard.html")
    if dashboard.exists():
        print(f"[run_once] Dashboard: {dashboard}")
        print("[run_once] Opening in browser...")
        webbrowser.open(dashboard.resolve().as_uri())
    else:
        print("[run_once] No dashboard file generated.")


if __name__ == "__main__":
    main()
