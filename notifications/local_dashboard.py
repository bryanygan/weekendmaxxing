"""Local dashboard — renders deal results to a self-contained HTML report."""

from datetime import datetime
from pathlib import Path


def _score_color(score: float) -> str:
    if score >= 70:
        return "#22c55e"
    if score >= 55:
        return "#eab308"
    return "#ef4444"


def _stars(rating: float) -> str:
    full = int(rating)
    return "\u2605" * full + "\u2606" * (5 - full)


def _timing_label(outbound_date: str) -> str:
    try:
        from datetime import datetime as dt
        day = dt.strptime(outbound_date, "%Y-%m-%d").strftime("%A")
        if day == "Friday":
            return "Friday Evening"
        if day == "Saturday":
            return "Early Saturday"
    except (ValueError, TypeError):
        pass
    return ""


def _render_stays_table(stays: list[dict]) -> str:
    if not stays:
        return "<p>No alternative stays.</p>"
    rows = ""
    for s in stays[:5]:
        rows += (
            f"<tr><td>{s.get('name','')}</td>"
            f"<td>${s.get('total_price',0):.0f}</td>"
            f"<td>{s.get('rating',0):.1f}</td>"
            f"<td>{s.get('type','')}</td></tr>"
        )
    return (
        '<table style="width:100%;border-collapse:collapse;font-size:0.85em;">'
        "<tr><th>Name</th><th>Total</th><th>Rating</th><th>Type</th></tr>"
        f"{rows}</table>"
    )


def _render_card(deal: dict) -> str:
    score = deal.get("score", 0)
    color = _score_color(score)
    dest = deal.get("destination", "Unknown")
    outbound = deal.get("outbound_date", "")
    ret = deal.get("return_date", "")
    is_train = deal.get("transport_type") == "train"
    transport_icon = "\U0001f682" if is_train else "\u2708\ufe0f"
    transport_label = "Train" if is_train else "Flight"
    airline = deal.get("airline", deal.get("operator", ""))
    price_usd = deal.get("price_usd", 0)
    layovers = deal.get("layovers", 0)
    stops = "Direct" if is_train and layovers == 0 else ("Nonstop" if layovers == 0 else f"{layovers} stop{'s' if layovers > 1 else ''}")
    od = deal.get("outbound_depart", "")
    oa = deal.get("outbound_arrive", "")
    rd = deal.get("return_depart", "")
    ra = deal.get("return_arrive", "")
    best = deal.get("best_stay", {})
    hotel_name = best.get("name", "N/A")
    hotel_total = best.get("total_price", 0)
    hotel_rating = best.get("rating", 0)
    est_total = deal.get("estimated_total", deal.get("total_trip_cost", 0))
    hours = deal.get("hours_at_destination", 0)
    timing = _timing_label(outbound)
    recs = deal.get("recommendations", "")
    all_stays = deal.get("all_stays", [])
    source = deal.get("source", "")
    stay_source = best.get("source", "")
    price_drop = deal.get("price_drop")

    drop_html = ""
    if price_drop is not None and price_drop > 0:
        drop_html = f' <span style="color:#22c55e;font-weight:700;">&darr; ${price_drop:.0f} drop</span>'
    elif price_drop is not None and price_drop < 0:
        drop_html = f' <span style="color:#ef4444;">&uarr; ${abs(price_drop):.0f} increase</span>'

    source_html = ""
    if source or stay_source:
        parts = [s for s in [source, stay_source] if s]
        source_html = f'<div class="meta">Sources: {" + ".join(parts)}</div>'

    return f"""
    <div class="card" style="border-left:4px solid {color};">
      <div class="card-header">
        <h2>{dest}</h2>
        <span class="badge" style="background:{color};">{score}</span>
      </div>
      <div class="meta">{outbound} &rarr; {ret} &middot; {timing}</div>
      <div class="line"><span class="label">{transport_icon} {transport_label}:</span>
        <span class="mono">${price_usd:.0f} &middot; {airline} &middot; {stops} &middot; {od}&rarr;{oa} / {rd}&rarr;{ra}</span>
      </div>
      <div class="line"><span class="label">Hotel:</span>
        <span class="mono">{hotel_name} &middot; ${hotel_total:.0f} &middot; {_stars(hotel_rating)}</span>
      </div>
      <div class="total">Estimated Total: ${est_total:.2f}{drop_html}</div>
      <div class="meta">{hours:.1f} hours at destination</div>
      {source_html}
      <details><summary>Recommendations</summary><pre class="recs">{recs}</pre></details>
      <details><summary>All Stays ({len(all_stays)})</summary>{_render_stays_table(all_stays)}</details>
    </div>"""


CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body { background: #0d0d0d; color: #e0e0e0; font-family: -apple-system, sans-serif; padding: 1.5rem; }
h1 { font-size: 1.6rem; margin-bottom: 0.25rem; }
.subtitle { color: #888; margin-bottom: 1rem; font-size: 0.9rem; }
.count-badge { display: inline-block; background: #333; padding: 0.2rem 0.7rem;
  border-radius: 999px; font-size: 0.85rem; margin-bottom: 1.5rem; }
.card { background: #1a1a1a; border-radius: 8px; padding: 1.2rem; margin-bottom: 1rem; }
.card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem; }
.card h2 { font-size: 1.2rem; }
.badge { color: #000; font-weight: 700; padding: 0.15rem 0.6rem; border-radius: 4px; font-size: 0.9rem; }
.meta { color: #888; font-size: 0.85rem; margin-bottom: 0.4rem; }
.line { margin: 0.3rem 0; }
.label { color: #aaa; font-size: 0.85rem; }
.mono { font-family: 'Cascadia Code', 'Fira Code', monospace; font-size: 0.85rem; }
.total { font-size: 1.1rem; font-weight: 700; color: #22c55e; margin: 0.5rem 0; font-family: monospace; }
details { margin-top: 0.5rem; }
summary { cursor: pointer; color: #888; font-size: 0.85rem; }
.recs { white-space: pre-wrap; font-size: 0.82rem; color: #ccc; margin-top: 0.4rem; }
table { margin-top: 0.4rem; }
th, td { text-align: left; padding: 0.25rem 0.6rem; border-bottom: 1px solid #333; color: #ccc; }
th { color: #888; }
.empty { text-align: center; padding: 3rem; color: #666; }
footer { text-align: center; color: #555; font-size: 0.75rem; margin-top: 2rem; }
@media (max-width: 640px) { body { padding: 0.75rem; } .card { padding: 0.8rem; } }
"""


def write_dashboard(deals: list[dict], output_path: str = "data/dashboard.html") -> str:
    """Generate a self-contained HTML dashboard and return the output path."""
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    sorted_deals = sorted(deals, key=lambda d: d.get("score", 0), reverse=True)

    if not sorted_deals:
        body = '<div class="empty">No deals found this run.</div>'
    else:
        body = "\n".join(_render_card(d) for d in sorted_deals)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="600">
<title>Weekend Deal Hunter</title>
<style>{CSS}</style>
</head>
<body>
<h1>\u2708\ufe0f Weekend Deal Hunter</h1>
<div class="subtitle">Origin: PHL &middot; Scanned {now}</div>
<div class="count-badge">{len(sorted_deals)} deals found this run</div>
{body}
<footer>Generated by Weekend Deal Hunter &middot; data/deals.db</footer>
</body>
</html>"""

    Path(output_path).write_text(html, encoding="utf-8")
    return output_path


def render_no_deals_page(output_path: str = "data/dashboard.html") -> str:
    """Write a minimal 'no deals' HTML page with timestamp."""
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Weekend Deal Hunter</title>
<style>{CSS}</style>
</head>
<body>
<h1>\u2708\ufe0f Weekend Deal Hunter</h1>
<div class="subtitle">Origin: PHL &middot; {now}</div>
<div class="empty">
  <p>No deals found this run.</p>
  <p style="margin-top:1rem;color:#555;">The pipeline will run again in approximately 6 hours.</p>
</div>
<footer>Generated by Weekend Deal Hunter &middot; data/deals.db</footer>
</body>
</html>"""

    Path(output_path).write_text(html, encoding="utf-8")
    return output_path
