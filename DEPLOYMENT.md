# Deployment Guide — Weekend Deal Hunter + ZR Bot

Deploy the deal hunter pipeline and Discord bot on a separate machine so it runs 24/7 and DMs you deals automatically.

## Architecture

```
┌─────────────────────────────────────────────┐
│              Your Server                     │
│                                              │
│  ┌──────────┐    ┌──────────────────────┐   │
│  │  Ollama   │◄───│  weekendmaxxing/     │   │
│  │ llama3.1  │    │  (deal pipeline)     │   │
│  └──────────┘    └──────────┬───────────┘   │
│                             │ imports        │
│                  ┌──────────▼───────────┐   │
│                  │  zrbot/               │   │
│                  │  (Discord bot)        │   │
│                  │  /deals command       │   │
│                  └──────────┬───────────┘   │
│                             │               │
└─────────────────────────────┼───────────────┘
                              │ DMs you
                              ▼
                        Discord App
```

Both repos live side by side on the server. The bot imports from the deal hunter at runtime via the `DEAL_HUNTER_PATH` environment variable.

## Prerequisites

- Python 3.12+
- Git
- 8GB+ RAM (Ollama needs ~5GB for llama3.1:8b)
- 10GB+ disk space (model weights + Chromium browser)

## Option A: Linux Server (Recommended)

### Automated Setup

SSH into your server and run:

```bash
curl -O https://raw.githubusercontent.com/bryanygan/weekendmaxxing/main/setup_server.sh
bash setup_server.sh
```

This script:
1. Installs Python, pip, git
2. Clones both repos to `~/bots/`
3. Creates a Python virtual environment with all dependencies
4. Installs Playwright Chromium
5. Installs Ollama and pulls llama3.1:8b
6. Creates systemd services for auto-start on boot

### Configure

Edit the bot's environment file:

```bash
nano ~/bots/zrbot/.env
```

Fill in your values (see [Environment Variables](#environment-variables) below).

### Start

```bash
sudo systemctl start ollama
sudo systemctl start zrbot
```

### Verify

```bash
# Check Ollama is running
curl http://localhost:11434/api/tags

# Check bot logs
sudo journalctl -u zrbot -f

# In Discord
/dealstatus
```

### Management

```bash
# View live logs
sudo journalctl -u zrbot -f

# Restart bot (after pulling updates)
sudo systemctl restart zrbot

# Stop bot
sudo systemctl stop zrbot

# Check status
sudo systemctl status zrbot
sudo systemctl status ollama
```

### Updating

```bash
cd ~/bots/weekendmaxxing && git pull
cd ~/bots/zrbot && git pull
sudo systemctl restart zrbot
```

---

## Option B: Windows Machine

### Automated Setup

1. Install [Python 3.12+](https://python.org/downloads) — check "Add Python to PATH"
2. Install [Git for Windows](https://git-scm.com/download/win)
3. Install [Ollama for Windows](https://ollama.com/download/windows)
4. Open Command Prompt and run:

```batch
cd %USERPROFILE%
mkdir bots
cd bots
git clone https://github.com/bryanygan/weekendmaxxing.git
git clone https://github.com/bryanygan/zrbot.git
weekendmaxxing\setup_windows.bat
```

### Configure

Edit `%USERPROFILE%\bots\zrbot\.env` with Notepad — fill in your values.

### Start

Open two terminals:

```batch
REM Terminal 1 — Ollama
ollama serve

REM Terminal 2 — Bot
cd %USERPROFILE%\bots\zrbot
set DEAL_HUNTER_PATH=%USERPROFILE%\bots\weekendmaxxing
python bot.py
```

### Auto-Start on Boot (Optional)

Create a batch file at `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\start_bot.bat`:

```batch
@echo off
start /min cmd /c "ollama serve"
timeout /t 10 /nobreak >nul
cd /d %USERPROFILE%\bots\zrbot
set DEAL_HUNTER_PATH=%USERPROFILE%\bots\weekendmaxxing
python bot.py
```

---

## Manual Setup (Any OS)

If the automated scripts don't work for your environment:

```bash
# 1. Clone repos side by side
mkdir ~/bots && cd ~/bots
git clone https://github.com/bryanygan/weekendmaxxing.git
git clone https://github.com/bryanygan/zrbot.git

# 2. Install Python dependencies
pip install -r weekendmaxxing/requirements.txt
pip install -r zrbot/requirements.txt

# 3. Install Playwright browser
playwright install chromium

# 4. Install Ollama (https://ollama.com) and pull the model
ollama pull llama3.1:8b

# 5. Create data directories
mkdir -p weekendmaxxing/data

# 6. Configure the bot
cp zrbot/.env.example zrbot/.env
# Edit zrbot/.env with your values

# 7. Start Ollama
ollama serve &

# 8. Start the bot
cd zrbot
export DEAL_HUNTER_PATH=~/bots/weekendmaxxing
python bot.py
```

---

## Environment Variables

Create a `.env` file in the `zrbot/` directory with these values:

```env
# Discord Bot (required)
DISCORD_TOKEN=your_bot_token_here
OWNER_ID=your_discord_user_id
CLIENT_ID=your_bot_client_id
GUILD_ID=your_server_id

# Vouch counter channels
TARGET_CHANNEL_ID=your_vouch_channel_id
NOTIFICATION_CHANNEL_ID=your_notification_channel_id

# USPS API (optional — only needed for tracking features)
USPS_CONSUMER_KEY=your_usps_key
USPS_CONSUMER_SECRET=your_usps_secret

# Deal Hunter (required — path to weekendmaxxing project)
DEAL_HUNTER_PATH=/home/youruser/bots/weekendmaxxing
```

### Where to Get These Values

| Variable | Where to Find It |
|----------|-----------------|
| `DISCORD_TOKEN` | [Discord Developer Portal](https://discord.com/developers/applications) → your app → Bot → Token |
| `OWNER_ID` | Your Discord user ID (enable Developer Mode in Discord settings, right-click yourself → Copy User ID) |
| `CLIENT_ID` | Developer Portal → your app → General Information → Application ID |
| `GUILD_ID` | Right-click your Discord server → Copy Server ID |
| `DEAL_HUNTER_PATH` | Absolute path to where you cloned weekendmaxxing (e.g., `/home/user/bots/weekendmaxxing` or `C:\Users\user\bots\weekendmaxxing`) |

---

## Discord Commands

Once the bot is running:

| Command | Description |
|---------|-------------|
| `/deals` | Run a full deal scan (15-30 min), DMs you top 10 results with embeds |
| `/deals destinations:Washington DC,Boston` | Scan specific cities only (faster) |
| `/dealstatus` | Show deal database stats and last run time |

---

## Deal Hunter Configuration

Edit these files in `weekendmaxxing/config/` to customize:

### `destinations.json`
Add or remove cities. Each entry needs:
```json
{"city": "City Name", "iata": "XXX", "avg_flight_min": 120}
```
For Amtrak-reachable cities, also add:
```json
{"city": "City Name", "iata": "XXX", "avg_flight_min": 120, "amtrak_station": "CODE", "amtrak_hrs": 2.0}
```

### `constraints.json`
Adjust budgets, timing windows, and preferences:
- `max_flight_roundtrip`: Max flight price (default $300)
- `max_train_roundtrip`: Max train price (default $200)
- `max_hotel_per_night_usd`: Max hotel cost per night (default $150)
- `hotel_min_rating`: Minimum hotel rating on 5-point scale (default 3.5)
- Timing windows for Friday evening, Saturday morning, Sunday return

### Score Threshold
Set the environment variable to change minimum deal score (default 55):
```bash
export DEAL_SCORE_THRESHOLD=65
```

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `/deals` not showing in Discord | Restart the bot and wait 1 minute for command sync |
| "Not authorized" on `/deals` | Your Discord user ID must match `OWNER_ID` in `.env` |
| Scan runs but finds 0 deals | Check Ollama is running: `curl http://localhost:11434/api/tags` |
| Bot crashes mid-scan | Check logs — the pipeline catches errors and DMs you the traceback |
| Ollama out of memory | You need 8GB+ RAM for llama3.1:8b |
| Playwright fails to launch | Run `playwright install chromium` and `playwright install-deps` |
| Import errors from weekendmaxxing | Check `DEAL_HUNTER_PATH` points to the correct directory |
| Bot connects but no commands | Make sure `GUILD_ID` is set in `.env` for guild-specific sync |

### Checking Logs

```bash
# Linux (systemd)
sudo journalctl -u zrbot -f

# Windows
# Logs print directly to the terminal running python bot.py
```

---

## Updating

Pull the latest code and restart:

```bash
cd ~/bots/weekendmaxxing && git pull
cd ~/bots/zrbot && git pull
# Linux:
sudo systemctl restart zrbot
# Windows: Ctrl+C the bot and re-run python bot.py
```
