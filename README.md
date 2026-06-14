# Foxhole Buddy

A Discord logistics bot for Foxhole regiments. Track stockpile timers, coordinate resource farming, manage base inventory, and set personal factory queue alarms — all from an interactive menu.

## Features

- **📦 Stockpile Timers** — Track reserve stockpiles with a 50-hour expiry window. Alerts fire at 24h, 6h, 2h, and after expiry. Each card has a persistent **Mark Refreshed** button.
- **⛏️ Resource Management** — Post farming needs, pledge contributions, log farmed amounts, and track progress on a live Needs Board.
- **📋 Base Inventory** — Add, remove, and list materials stored at your main base. Quantities support decimals and are kept clean (auto-deletes at zero).
- **🏭 Factory Alarms** — Set personal reminders for facility production queues. Choose between a 3-ping alarm (10m before, at completion, 10m after) or a 1-ping alarm (at completion only). Timers round to the nearest 5-minute interval.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` and set:

- `DISCORD_TOKEN` — your bot token from the [Discord Developer Portal](https://discord.com/developers/applications)
- `DISCORD_GUILD_ID` — *(optional)* for instant slash-command sync during development
- `REMINDER_INTERVAL_SECONDS` — *(optional)* background loop interval, defaults to `60`

## Run

```bash
python main.py
```

## Commands

| Command | Description |
|---------|-------------|
| `/foxhole_buddy setup` | **(Admin)** Register the current channel as the bot's operating channel for this server. Optionally set an urgent role for 2h stockpile pings. |
| `/foxhole_buddy manage` | Open the interactive regiment management menu. All features are accessed from here. |
| `/foxhole_buddy help` | Show a quick-start info panel. |

## How It Works

1. An admin runs `/foxhole_buddy setup` in the channel where the bot should operate.
2. Any member runs `/foxhole_buddy manage` to open the menu.
3. From the menu, choose **Stockpile**, **Resources**, **Inventory**, or **Factories**.
4. Everything is button & modal driven — no slash command arguments needed.

## Multi-Server

The bot is fully multi-server safe. Each Discord server's data (stockpiles, resources, inventory, alarms) is isolated by Guild ID. No server can see another server's information.

## Data

Runtime data is stored at `data/stockpiles.json` by default (configurable via `DATA_FILE` in `.env`). Back this file up if the bot matters to your group.

## Project Structure

```
main.py                         # Entry point
foxhole_buddy/
├── core/
│   ├── bot.py                  # Discord client, setup_hook, persistent views
│   └── store.py                # JSON data layer, all CRUD operations
├── ui/
│   ├── embeds.py               # All Discord embed builders
│   ├── modals.py               # Text input modals (add, refresh, delete, etc.)
│   └── views.py                # Button views and navigation
├── utils/
│   ├── env.py                  # .env file loader
│   └── formatting.py           # Status labels, progress bars, timestamps
├── commands.py                 # Slash command registration
└── tasks.py                    # Background reminder loop (stockpiles + factory alarms)
```
