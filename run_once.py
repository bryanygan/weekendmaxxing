"""Run the deal-hunting pipeline once and open the dashboard."""

import argparse
import json
import sys
import webbrowser
from pathlib import Path

import requests


def parse_args():
    parser = argparse.ArgumentParser(description="Weekend Deal Hunter — single run")
    parser.add_argument("--budget", type=int, help="Override max total budget in USD")
    parser.add_argument("--max-flight", type=int, help="Override max flight price in USD")
    parser.add_argument("--max-hotel", type=int, help="Override max hotel per night in USD")
    parser.add_argument("--weekends", type=int, default=6, help="Number of weekends to search (default: 6)")
    parser.add_argument("--threshold", type=float, help="Minimum deal score (0-100, default: 55)")
    parser.add_argument("--no-browser", action="store_true", help="Don't open dashboard in browser")
    parser.add_argument("--server", action="store_true", help="Start live dashboard server after run")
    parser.add_argument("--destinations", nargs="+", help="Only search specific cities (e.g. --destinations Boston Miami)")
    return parser.parse_args()


def apply_overrides(args):
    """Apply CLI argument overrides to config files and environment."""
    import os

    if args.threshold:
        os.environ["DEAL_SCORE_THRESHOLD"] = str(args.threshold)

    if any([args.budget, args.max_flight, args.max_hotel]):
        constraints_path = Path("config/constraints.json")
        constraints = json.loads(constraints_path.read_text(encoding="utf-8"))
        if args.budget:
            constraints["budget"]["max_total_usd"] = args.budget
            print(f"[run_once] Budget override: ${args.budget}")
        if args.max_flight:
            constraints["budget"]["max_flight_roundtrip"] = args.max_flight
            constraints["budget"]["max_flight_usd"] = args.max_flight
            print(f"[run_once] Max flight override: ${args.max_flight}")
        if args.max_hotel:
            constraints["budget"]["max_hotel_per_night_usd"] = args.max_hotel
            print(f"[run_once] Max hotel/night override: ${args.max_hotel}")
        constraints_path.write_text(json.dumps(constraints, indent=2), encoding="utf-8")

    if args.destinations:
        dest_path = Path("config/destinations.json")
        data = json.loads(dest_path.read_text(encoding="utf-8"))
        filtered = [d for d in data["destinations"]
                    if d["city"].lower() in [c.lower() for c in args.destinations]]
        if filtered:
            data["destinations"] = filtered
            dest_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
            print(f"[run_once] Searching only: {', '.join(d['city'] for d in filtered)}")
        else:
            print(f"[run_once] WARNING: no matching destinations for {args.destinations}")


def main() -> None:
    args = parse_args()

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

    # 3. Apply CLI overrides
    apply_overrides(args)

    # 4. Run pipeline
    from orchestrator.pipeline import run_pipeline

    summary = run_pipeline()

    # 5. Print summary
    print(f"\n[run_once] Summary: {summary}")

    # 6. Open dashboard
    dashboard = Path("data/dashboard.html")
    if dashboard.exists():
        print(f"[run_once] Dashboard: {dashboard}")
        if not args.no_browser and not args.server:
            print("[run_once] Opening in browser...")
            webbrowser.open(dashboard.resolve().as_uri())
    else:
        print("[run_once] No dashboard file generated.")

    # 7. Optionally start live server
    if args.server:
        print("[run_once] Starting live dashboard server...")
        from notifications.live_dashboard import app
        from config.settings import DASHBOARD_HOST, DASHBOARD_PORT
        print(f"[run_once] Dashboard at http://{DASHBOARD_HOST}:{DASHBOARD_PORT}")
        webbrowser.open(f"http://{DASHBOARD_HOST}:{DASHBOARD_PORT}")
        app.run(host=DASHBOARD_HOST, port=DASHBOARD_PORT, debug=False)


if __name__ == "__main__":
    main()
