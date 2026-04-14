"""Phase 0 smoke tests — verify project scaffold integrity."""

import importlib
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


# --- Directory existence ---

@pytest.mark.parametrize("dirname", [
    "agents", "orchestrator", "scrapers", "utils",
    "notifications", "config", "data", "tests",
])
def test_directory_exists(dirname):
    assert (ROOT / dirname).is_dir(), f"Missing directory: {dirname}"


# --- JSON configs load without error ---

def test_destinations_json_loads():
    path = ROOT / "config" / "destinations.json"
    data = json.loads(path.read_text())
    assert data["origin"]["iata"] == "PHL"
    assert len(data["destinations"]) >= 10
    for dest in data["destinations"]:
        assert "iata" in dest
        assert "avg_flight_min" in dest


def test_constraints_json_loads():
    path = ROOT / "config" / "constraints.json"
    data = json.loads(path.read_text())
    assert data["budget"]["max_total_usd"] > 0
    assert data["min_hours_at_dest"] == 24
    assert data["max_layovers"] == 1
    assert data["hotel_min_rating"] == 3.5
    assert len(data["timing"]["outbound_windows"]) == 2


# --- All stub modules import without error ---

@pytest.mark.parametrize("module_path", [
    "agents.flight_agent",
    "agents.hotel_agent",
    "agents.cost_agent",
    "agents.recommendation_agent",
    "orchestrator.pipeline",
    "orchestrator.deal_scorer",
    "orchestrator.state_manager",
    "scrapers.google_flights",
    "scrapers.booking",
    "utils.llm",
    "utils.json_extractor",
    "notifications.local_dashboard",
    "config.settings",
])
def test_stub_imports(module_path):
    mod = importlib.import_module(module_path)
    assert mod is not None


# --- settings.py loads defaults correctly ---

def test_settings_defaults(monkeypatch):
    # Clear any env vars that might interfere
    monkeypatch.delenv("USE_LOCAL_LLM", raising=False)
    monkeypatch.delenv("LOCAL_LLM_URL", raising=False)
    monkeypatch.delenv("LOCAL_LLM_MODEL", raising=False)

    # Re-import to pick up cleared env
    import config.settings as settings_module
    importlib.reload(settings_module)

    assert settings_module.USE_LOCAL_LLM is True
    assert settings_module.LOCAL_LLM_URL == "http://localhost:11434/api/chat"
    assert settings_module.LOCAL_LLM_MODEL == "llama3.1:8b"


def test_api_settings_defaults(monkeypatch):
    monkeypatch.delenv("AMADEUS_API_KEY", raising=False)
    monkeypatch.delenv("AMADEUS_API_SECRET", raising=False)
    monkeypatch.delenv("KIWI_API_KEY", raising=False)
    monkeypatch.delenv("SERPAPI_API_KEY", raising=False)

    import config.settings as settings_module
    importlib.reload(settings_module)

    assert settings_module.AMADEUS_API_KEY == ""
    assert settings_module.AMADEUS_API_SECRET == ""
    assert settings_module.KIWI_API_KEY == ""
    assert settings_module.SERPAPI_API_KEY == ""
