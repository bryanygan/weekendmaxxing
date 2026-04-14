#!/bin/bash
# Weekend Deal Hunter + ZR Bot — Full server setup script
# Run this on a fresh Ubuntu/Debian machine (or WSL)
#
# Usage: bash setup_server.sh

set -e

echo "============================================"
echo " Weekend Deal Hunter — Server Setup"
echo "============================================"
echo ""

# ── 1. System dependencies ──
echo "[1/7] Installing system dependencies..."
sudo apt-get update -qq
sudo apt-get install -y -qq python3 python3-pip python3-venv git curl

# ── 2. Clone both repos ──
echo "[2/7] Cloning repositories..."
mkdir -p ~/bots
cd ~/bots

if [ ! -d "weekendmaxxing" ]; then
    git clone https://github.com/bryanygan/weekendmaxxing.git
else
    echo "  weekendmaxxing already exists, pulling latest..."
    cd weekendmaxxing && git pull && cd ..
fi

if [ ! -d "zrbot" ]; then
    git clone https://github.com/bryanygan/zrbot.git
else
    echo "  zrbot already exists, pulling latest..."
    cd zrbot && git pull && cd ..
fi

# ── 3. Python virtual environment ──
echo "[3/7] Setting up Python environment..."
python3 -m venv ~/bots/venv
source ~/bots/venv/bin/activate

pip install --upgrade pip -q
pip install -r ~/bots/weekendmaxxing/requirements.txt -q
pip install -r ~/bots/zrbot/requirements.txt -q

# ── 4. Playwright browser ──
echo "[4/7] Installing Playwright Chromium..."
playwright install chromium
playwright install-deps chromium 2>/dev/null || true

# ── 5. Ollama ──
echo "[5/7] Installing Ollama..."
if ! command -v ollama &> /dev/null; then
    curl -fsSL https://ollama.com/install.sh | sh
else
    echo "  Ollama already installed"
fi

echo "  Pulling llama3.1:8b (this may take a few minutes)..."
ollama pull llama3.1:8b

# ── 6. Configuration ──
echo "[6/7] Setting up configuration..."

# weekendmaxxing data directory
mkdir -p ~/bots/weekendmaxxing/data

# zrbot .env file
if [ ! -f ~/bots/zrbot/.env ]; then
    echo ""
    echo "  !! You need to create ~/bots/zrbot/.env with your Discord token !!"
    echo "  Copy from .env.example and fill in your values:"
    echo "  cp ~/bots/zrbot/.env.example ~/bots/zrbot/.env"
    echo "  nano ~/bots/zrbot/.env"
    echo ""
    cp ~/bots/zrbot/.env.example ~/bots/zrbot/.env
else
    echo "  .env already exists"
fi

# Add DEAL_HUNTER_PATH to .env if not present
if ! grep -q "DEAL_HUNTER_PATH" ~/bots/zrbot/.env; then
    echo "" >> ~/bots/zrbot/.env
    echo "# Weekend Deal Hunter path" >> ~/bots/zrbot/.env
    echo "DEAL_HUNTER_PATH=$HOME/bots/weekendmaxxing" >> ~/bots/zrbot/.env
    echo "  Added DEAL_HUNTER_PATH to .env"
fi

# ── 7. Systemd services ──
echo "[7/7] Creating systemd services..."

# Ollama service (usually auto-created by installer, but just in case)
sudo tee /etc/systemd/system/ollama.service > /dev/null << 'UNIT'
[Unit]
Description=Ollama LLM Server
After=network.target

[Service]
ExecStart=/usr/local/bin/ollama serve
Restart=always
RestartSec=5
User=$USER
Environment=HOME=$HOME

[Install]
WantedBy=multi-user.target
UNIT

# Replace $USER and $HOME in the unit file
sudo sed -i "s|\$USER|$(whoami)|g" /etc/systemd/system/ollama.service
sudo sed -i "s|\$HOME|$HOME|g" /etc/systemd/system/ollama.service

# ZR Bot service (runs the Discord bot which includes deal scanning)
sudo tee /etc/systemd/system/zrbot.service > /dev/null << UNIT
[Unit]
Description=ZR Discord Bot + Deal Hunter
After=network.target ollama.service
Wants=ollama.service

[Service]
Type=simple
WorkingDirectory=$HOME/bots/zrbot
ExecStart=$HOME/bots/venv/bin/python bot.py
Restart=always
RestartSec=10
User=$(whoami)
Environment=HOME=$HOME
Environment=DEAL_HUNTER_PATH=$HOME/bots/weekendmaxxing
Environment=PYTHONPATH=$HOME/bots/weekendmaxxing

[Install]
WantedBy=multi-user.target
UNIT

sudo systemctl daemon-reload
sudo systemctl enable ollama
sudo systemctl enable zrbot

echo ""
echo "============================================"
echo " Setup complete!"
echo "============================================"
echo ""
echo " Before starting, edit your Discord bot token:"
echo "   nano ~/bots/zrbot/.env"
echo ""
echo " Then start everything:"
echo "   sudo systemctl start ollama"
echo "   sudo systemctl start zrbot"
echo ""
echo " Check status:"
echo "   sudo systemctl status zrbot"
echo "   sudo journalctl -u zrbot -f"
echo ""
echo " Test Ollama:"
echo "   curl http://localhost:11434/api/tags"
echo ""
echo " In Discord, type:"
echo "   /deals                          (full scan)"
echo "   /deals destinations:Washington DC   (quick test)"
echo "   /dealstatus                     (check last run)"
echo ""
