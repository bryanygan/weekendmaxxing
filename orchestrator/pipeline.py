"""Pipeline — end-to-end orchestration of the deal-hunting workflow."""

import asyncio
import json
import os
import traceback
from datetime import datetime
from pathlib import Path

from agents.cost_agent import CostAgent
from agents.flight_agent import FlightAgent
from agents.hotel_agent import HotelAgent
from agents.recommendation_agent import RecommendationAgent
from notifications.desktop_notify import notify_deals
from notifications.email_notify import notify_deals_email
from notifications.local_dashboard import render_no_deals_page, write_dashboard
from orchestrator.deal_scorer import score_deal
from orchestrator.state_manager import (
    get_price_drop, init_db, is_duplicate, log_run, record_price, save_deal,
)

SCORE_THRESHOLD = float(os.getenv("DEAL_SCORE_THRESHOLD", "55"))


def run_pipeline(aggressive: bool = False) -> dict:
    """Execute the full search-score-recommend pipeline and return a summary dict."""
    summary = {
        "started_at": "",
        "finished_at": "",
        "deals_found": 0,
        "deals_notified": 0,
    }

    try:
        # 1. Load configs
        print("[Pipeline] Loading config...")
        destinations_data = json.loads(
            Path("config/destinations.json").read_text(encoding="utf-8")
        )
        constraints = json.loads(
            Path("config/constraints.json").read_text(encoding="utf-8")
        )
        destinations = destinations_data["destinations"]

        # 2. Init DB
        print("[Pipeline] Initializing database...")
        init_db()

        # 3. Record start
        started_at = datetime.now().isoformat()
        summary["started_at"] = started_at

        # 4. Instantiate agents
        flight_agent = FlightAgent(constraints)
        hotel_agent = HotelAgent(constraints)
        cost_agent = CostAgent()
        rec_agent = RecommendationAgent()

        # 5. Flight search
        print("[Pipeline] Running flight search...")
        flight_deals = asyncio.run(flight_agent.run(destinations))
        if not flight_deals:
            print("[Pipeline] No valid flights found. Aborting.")
            render_no_deals_page()
            summary["finished_at"] = datetime.now().isoformat()
            log_run(started_at, summary["finished_at"], 0, 0)
            return summary

        # 6. Hotel search
        print("[Pipeline] Running hotel search...")
        enriched_deals = asyncio.run(hotel_agent.run(flight_deals))
        if not enriched_deals:
            print("[Pipeline] No hotels found. Aborting.")
            render_no_deals_page()
            summary["finished_at"] = datetime.now().isoformat()
            log_run(started_at, summary["finished_at"], 0, 0)
            return summary

        # 7. Cost estimation
        print("[Pipeline] Estimating costs...")
        for deal in enriched_deals:
            cost_agent.compute_full_budget(deal)

        # 8. Score deals
        print("[Pipeline] Scoring deals...")
        for deal in enriched_deals:
            deal["score"] = score_deal(deal, constraints)

        # 9. Filter by threshold
        scored = [d for d in enriched_deals if d.get("score", 0) >= SCORE_THRESHOLD]

        # 10. Sort by score desc
        scored.sort(key=lambda d: d.get("score", 0), reverse=True)

        # 11. Top 10
        top_deals = scored[:10]

        # 12. Recommendations
        print("[Pipeline] Generating recommendations...")
        top_deals = rec_agent.generate_batch(top_deals)

        summary["deals_found"] = len(top_deals)

        # 12.5 Record price history for all scored deals
        for deal in top_deals:
            record_price(deal)
            drop = get_price_drop(deal)
            if drop is not None:
                deal["price_drop"] = round(drop, 2)
                if drop > 0:
                    print(f"[Pipeline] Price DROP: {deal.get('destination')} down ${drop:.0f}")

        # 13. Separate new vs seen
        new_deals = [d for d in top_deals if not is_duplicate(d)]
        summary["deals_notified"] = len(new_deals)

        # 14. Save and render
        for d in new_deals:
            save_deal(d)

        write_dashboard(top_deals)

        # 14.5 Notifications for new deals
        if new_deals:
            notify_deals(new_deals)
            notify_deals_email(new_deals)

        # 15. Log summary
        print(
            f"[Pipeline] {len(flight_deals)} flights -> "
            f"{len(enriched_deals)} with hotels -> "
            f"{len(scored)} scored -> "
            f"{len(new_deals)} new"
        )

        # 16. Finish
        summary["finished_at"] = datetime.now().isoformat()
        log_run(started_at, summary["finished_at"], summary["deals_found"], summary["deals_notified"])

    except Exception:
        print(f"[Pipeline] ERROR:\n{traceback.format_exc()}")
        render_no_deals_page()
        summary["finished_at"] = datetime.now().isoformat()

    return summary
