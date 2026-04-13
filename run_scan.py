"""Full scan with realistic mock scraped data + real Ollama LLM extraction."""

import json
import time
import asyncio
from datetime import datetime
from pathlib import Path

# ── Realistic scraped text (based on actual earlier scrapes) ──

FLIGHT_TEXT = {
    "BOS": (
        "Showing flights from PHL to BOS\n"
        "$189 - American Airlines - Nonstop - 1h 25m - 6:00 PM to 7:25 PM\n"
        "$159 - JetBlue - Nonstop - 1h 20m - 7:00 PM to 8:20 PM\n"
        "$245 - Delta - 1 stop - 3h 10m - 5:30 PM to 8:40 PM\n"
        "$139 - Frontier - Nonstop - 1h 30m - 8:00 AM to 9:30 AM\n"
        "$275 - United - 1 stop - 4h 15m - 6:15 PM to 10:30 PM"
    ),
    "DCA": (
        "Showing flights from PHL to DCA\n"
        "$125 - American Airlines - Nonstop - 1h 05m - 5:35 PM to 6:40 PM\n"
        "$149 - Delta - Nonstop - 1h 10m - 7:00 PM to 8:10 PM\n"
        "$89 - Frontier - Nonstop - 1h 00m - 8:00 AM to 9:00 AM\n"
        "$199 - JetBlue - 1 stop - 3h 30m - 6:00 PM to 9:30 PM"
    ),
    "MIA": (
        "Showing flights from PHL to MIA\n"
        "$149 - Spirit - Nonstop - 3h 05m - 6:30 PM to 9:35 PM\n"
        "$189 - American Airlines - Nonstop - 3h 10m - 7:15 PM to 10:25 PM\n"
        "$219 - JetBlue - Nonstop - 3h 00m - 5:30 PM to 8:30 PM\n"
        "$179 - Delta - 1 stop - 5h 45m - 6:00 PM to 11:45 PM\n"
        "$269 - United - Nonstop - 3h 15m - 8:00 AM to 11:15 AM"
    ),
    "BNA": (
        "Showing flights from PHL to BNA\n"
        "$129 - Spirit - Nonstop - 2h 25m - 7:45 PM to 9:10 PM\n"
        "$179 - American Airlines - Nonstop - 2h 20m - 6:00 PM to 7:20 PM\n"
        "$159 - Southwest - Nonstop - 2h 30m - 8:00 AM to 9:30 AM\n"
        "$219 - Delta - 1 stop - 4h 30m - 5:00 PM to 8:30 PM"
    ),
    "ORD": (
        "Showing flights from PHL to ORD\n"
        "$139 - Spirit - Nonstop - 2h 40m - 6:00 PM to 7:40 PM\n"
        "$169 - American Airlines - Nonstop - 2h 35m - 7:30 PM to 9:05 PM\n"
        "$149 - Frontier - Nonstop - 2h 45m - 8:00 AM to 9:45 AM\n"
        "$199 - United - Nonstop - 2h 30m - 5:45 PM to 7:15 PM"
    ),
    "CHS": (
        "Showing flights from PHL to CHS\n"
        "$159 - American Airlines - Nonstop - 1h 55m - 6:20 PM to 8:15 PM\n"
        "$139 - Frontier - Nonstop - 2h 00m - 7:30 PM to 9:30 PM\n"
        "$189 - Delta - 1 stop - 4h 10m - 5:30 PM to 9:40 PM\n"
        "$119 - Spirit - Nonstop - 1h 50m - 8:30 AM to 10:20 AM"
    ),
    "ATL": (
        "Showing flights from PHL to ATL\n"
        "$119 - Spirit - Nonstop - 2h 15m - 6:45 PM to 8:00 PM\n"
        "$159 - Delta - Nonstop - 2h 10m - 7:00 PM to 8:10 PM\n"
        "$179 - American Airlines - Nonstop - 2h 20m - 5:30 PM to 6:50 PM\n"
        "$139 - Frontier - Nonstop - 2h 25m - 8:00 AM to 9:25 AM"
    ),
}

HOTEL_TEXT = {
    "Boston": "Hotel search results for Boston\nThe Godfrey Hotel - 4.4/5 - 892 reviews - $169/night - $338 total - Downtown\nHI Boston Hostel - 4.1/5 - 1204 reviews - $59/night - $118 total - Chinatown\nMoxy Boston Downtown - 4.2/5 - 567 reviews - $139/night - $278 total - Theater District",
    "Washington DC": "Hotel search results for Washington DC\nPod DC - 4.3/5 - 1567 reviews - $109/night - $218 total - Penn Quarter\nHI Washington DC - 4.0/5 - 890 reviews - $49/night - $98 total - Downtown\ncitizenM Washington DC - 4.4/5 - 678 reviews - $139/night - $278 total - Capitol Hill",
    "Miami": "Hotel search results for Miami\nGenerator Miami - 4.2/5 - 1345 reviews - $89/night - $178 total - South Beach\nFreehand Miami - 4.3/5 - 987 reviews - $129/night - $258 total - Mid-Beach\nLife House Little Havana - 4.4/5 - 234 reviews - $109/night - $218 total - Little Havana",
    "Nashville": "Hotel search results for Nashville\nNashville Downtown Hostel - 3.9/5 - 321 reviews - $45/night - $90 total - SoBro\nGraduate Nashville - 4.4/5 - 1234 reviews - $139/night - $278 total - Midtown\nVirgin Hotels Nashville - 4.5/5 - 890 reviews - $149/night - $298 total - Music Row",
    "Chicago": "Hotel search results for Chicago\nHI Chicago - 4.1/5 - 1456 reviews - $55/night - $110 total - The Loop\nFreehand Chicago - 4.2/5 - 654 reviews - $99/night - $198 total - River North\nVirgin Hotels Chicago - 4.5/5 - 1567 reviews - $149/night - $298 total - River North",
    "Charleston": "Hotel search results for Charleston\nNot So Hostel - 4.3/5 - 567 reviews - $59/night - $118 total - Downtown\nThe Spectator Hotel - 4.6/5 - 890 reviews - $139/night - $278 total - French Quarter\nHotel Emeline - 4.5/5 - 345 reviews - $149/night - $298 total - Church Street",
    "Atlanta": "Hotel search results for Atlanta\nSocial Goat B&B - 4.5/5 - 234 reviews - $89/night - $178 total - East Atlanta\nThe Ellis Hotel - 4.3/5 - 789 reviews - $109/night - $218 total - Downtown\nHotel Clermont - 4.2/5 - 456 reviews - $119/night - $238 total - Poncey-Highland",
}

TRAIN_TEXT = {
    "Washington DC": "Amtrak Northeast Regional PHL to WAS\nTrain 171: Depart 16:45, Arrive 18:30, 1h45m, $49 one-way, $98 round-trip\nTrain 175: Depart 18:15, Arrive 20:00, 1h45m, $49 one-way, $98 round-trip\nSaturday: Depart 08:00, Arrive 09:45, $42 one-way, $84 round-trip\nReturn Sunday 17:00 arrive 18:45, $49\nReturn Sunday 19:00 arrive 20:45, $42",
    "Boston": "Amtrak Northeast Regional PHL to BOS\nTrain 171: Depart 17:00, Arrive 22:15, 5h15m, $69 one-way, $138 round-trip\nSaturday: Depart 07:30, Arrive 12:45, $59 one-way, $118 round-trip\nReturn Sunday 15:00 arrive 20:15, $69\nReturn Sunday 17:00 arrive 22:15, $59",
}


# ── Mock all scrapers ──

async def mock_flight_fetch(origin, dest_iata, out_date, ret_date):
    return FLIGHT_TEXT.get(dest_iata, "")

async def mock_hotel_fetch(city, checkin, checkout):
    for c, text in HOTEL_TEXT.items():
        if c.lower() in city.lower():
            return text
    return ""

async def mock_train_fetch(origin, dest, out_date, ret_date):
    for c, text in TRAIN_TEXT.items():
        if c.lower() in dest.lower():
            return text
    return ""

async def mock_septa_fetch(origin, dest, out_date, ret_date):
    return ""

async def no_wait(domain):
    pass


# Patch everything
import scrapers.google_flights as gf
import scrapers.kayak as ky
import scrapers.booking as bk
import scrapers.amtrak as am
import scrapers.septa as sp
import utils.rate_limiter as rl

gf.fetch_raw = mock_flight_fetch
ky.fetch_raw = mock_flight_fetch
bk.fetch_raw = mock_hotel_fetch
am.fetch_raw = mock_train_fetch
sp.fetch_raw = mock_septa_fetch
rl.limiter.wait = no_wait

import agents.flight_agent as fa
fa.FLIGHT_SOURCES = [("google_flights", gf), ("kayak", ky)]

import agents.hotel_agent as ha
ha.STAY_SOURCES = [("booking.com", bk)]

# 3 weekends
orig_fp = fa.FlightAgent.get_weekend_pairs
fa.FlightAgent.get_weekend_pairs = lambda self, n=3: orig_fp(self, 3)
import agents.train_agent as ta
orig_tp = ta.TrainAgent.get_weekend_pairs
ta.TrainAgent.get_weekend_pairs = lambda self, n=3: orig_tp(self, 3)

# Add Atlanta to destinations config
data = json.loads(Path("config/destinations.json").read_text())
cities = [d["city"] for d in data["destinations"]]
if "Atlanta" not in cities:
    data["destinations"].append({"city": "Atlanta", "iata": "ATL", "avg_flight_min": 150})
    Path("config/destinations.json").write_text(json.dumps(data, indent=2))

# ── RUN ──

Path("data/deals.db").unlink(missing_ok=True)

from orchestrator.pipeline import run_pipeline

start = time.time()
print("=" * 70)
print("WEEKEND DEAL HUNTER - Full Scan with Real LLM")
print(f"7 destinations x 3 weekends | Ollama llama3.1:8b")
print(f"Started: {datetime.now().strftime('%H:%M:%S')}")
print("=" * 70)

summary = run_pipeline()

elapsed = time.time() - start
print()
print("=" * 70)
print(f"PIPELINE COMPLETE in {elapsed / 60:.1f} minutes")
print(json.dumps(summary, indent=2))
print("=" * 70)

from orchestrator.state_manager import get_recent_deals
deals = get_recent_deals(limit=50)
print(f"\n{'=' * 70}")
print(f" TOP {len(deals)} BEST VALUE WEEKEND TRIPS FROM PHILADELPHIA")
print(f"{'=' * 70}\n")

for i, d in enumerate(sorted(deals, key=lambda x: x.get("score", 0), reverse=True), 1):
    transport = "TRAIN" if d.get("transport_type") == "train" else "FLIGHT"
    dest = d.get("destination", "?")
    score = d.get("score", 0)
    price = d.get("price_usd", 0)
    hotel = d.get("best_stay", {})
    hotel_name = hotel.get("name", "N/A")[:45]
    hotel_price = hotel.get("total_price", 0)
    hotel_rating = hotel.get("rating", 0)
    total = d.get("estimated_total", d.get("total_trip_cost", 0))
    extras = d.get("estimated_extras", 0)
    dates = f"{d.get('outbound_date', '')} -> {d.get('return_date', '')}"
    carrier = d.get("airline", d.get("operator", "?"))
    hours = d.get("hours_at_destination", 0)
    layovers = d.get("layovers", 0)
    stops = "Direct/Nonstop" if layovers == 0 else f"{layovers} stop"

    print(f"{'=' * 70}")
    print(f"  #{i} | {dest} | Score: {score}/100 | {transport}")
    print(f"{'=' * 70}")
    print(f"  Transport:  {carrier} ${price:.0f} round-trip | {stops}")
    print(f"  Dates:      {dates}")
    print(f"  Schedule:   Leave {d.get('outbound_depart', '?')}, arrive {d.get('outbound_arrive', '?')}")
    print(f"              Return {d.get('return_depart', '?')}, home by {d.get('return_arrive', '?')}")
    print(f"  Hotel:      {hotel_name}")
    print(f"              ${hotel_price:.0f} total ({hotel_rating:.1f}/5 stars)")
    print(f"  Time there: {hours:.0f} hours")
    print(f"  ---- Cost Breakdown ----")
    print(f"  Transport:     ${price:.0f}")
    print(f"  Hotel:         ${hotel_price:.0f}")
    print(f"  Food/Transit:  ${extras:.0f}")
    print(f"  EST. TOTAL:    ${total:.0f}")
    print()
    recs = d.get("recommendations", "")
    if recs and len(recs) > 20:
        print(f"  ---- What To Do ----")
        for line in recs.strip().split("\n")[:8]:
            if line.strip():
                print(f"  {line.strip()}")
    print()
