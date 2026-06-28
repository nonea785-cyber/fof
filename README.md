# Foxhole Buddy

A Discord logistics bot for Foxhole regiments. Track stockpile timers, request supplies from a structured item catalog, schedule operations, manage base inventory, and set personal factory queue alarms — all from an interactive menu.

## Features

- **📦 Stockpile Timers** — Track reserve stockpiles with a 48-hour expiry window. Graduated alerts fire at 12h, 6h, 1h, 30m, and after expiry (the 30m ping can mention an urgent role). Each card has a persistent **Mark Refreshed** button.
- **🚚 Logistics Requests** — Build a supply request holding **multiple items**: add each by **typing its name** (fuzzy search) or by **browsing** the catalog (Category → Subcategory → Item), all driven by a catalog synced from the Foxhole wiki. Drivers can **Claim** the whole list *or* individual line items, deliver, then **Validate** to close them — claiming per item lets several drivers split one request. Filtered to your faction when set. The catalog refreshes automatically every ~2 days (`CATALOG_SYNC_HOURS`).
- **⚔️ Operations** — Schedule ops with **Going / Tentative / Can't** RSVP, or add named **squads** (capacity + auto-waitlist + assignable leads). Times show in each viewer's local zone; auto-stamped with the live war number; reminders ping attendees 30m before and at start. Link logistics requests to an op so drivers know what to bring.
- **🤝 Allied Ops** — Schedule **one operation shared live across an ally room**: the interactive card is mirrored into every member server's channel, and players RSVP / pick squads / get assigned as leads **from their own server** into one combined roster (shown by name · faction · server, since cross-server mentions don't resolve). Reminders fire in each server's channel, pinging that server's own attendees. Only the host can edit / start / cancel. Reuses your existing **🛡️ Ally Chat** rooms — open **War Room → ⚔️ Operations → 🤝 Allied Op** and pick a room.
- **📋 Base Inventory** — Add, remove, and list materials stored at your main base. Quantities support decimals and are kept clean (auto-deletes at zero).
- **🏭 Factory Alarms** — Set personal reminders for facility production queues. Choose between a 3-ping alarm (10m before, at completion, 10m after) or a 1-ping alarm (at completion only). Timers round to the nearest 5-minute interval.
- **🌐 Live War Data** — The **War Room** (`/foxhole_buddy war_room`) shows the current war status and per-hex casualty reports alongside operations. War number is cached and refreshed ~daily (`WAR_SYNC_HOURS`).
- **📡 Regi Net** — Opt-in cross-server chat. Designate a channel, then `/global <message> [image]` (or the **✍️ Transmit** panel button) broadcasts to **every** linked server's channel — one global net across all factions. Messages relay via webhook (so they look like native chat) stamped with the sender's **name · regiment · faction**. No privileged intents needed; the bot only needs **Manage Webhooks** in that channel.
- **🛡️ Ally Chat** — Private cross-server rooms shared only with chosen allies (3+ servers supported). One admin **creates a room** and gets an invite code; allied admins **join with the code** + a channel. Then `/ally <message> [image]` (or the panel) relays only within that room. A server can be in several ally rooms, each bound to its own channel. Set up under `/foxhole_buddy setup → 💬 Setup Chats → 🛡️ Ally Chats`; bot needs **Manage Webhooks** in each ally channel. These same rooms power **🤝 Allied Ops** (above) — the bot must be present in each allied server, which it already is to relay chat.

### Server setup

`/foxhole_buddy setup` (admin) sets the main channel and optionally: an **urgent role** (30m stockpile ping), your **faction** (Warden/Colonial — filters the catalog *and* tags your Regi Net messages), separate **alert channels** for stockpile warnings and operation reminders, and a **Regi Net** channel (under 🌐 Regi Chat) to join the global cross-server net. From there you can also post a **Net Control** panel with a one-tap Transmit button.

> **Regi Net prerequisite:** grant the bot **Manage Webhooks** (plus View Channel / Send Messages) in the chosen channel — that's it. Because broadcasting is done with the `/global` slash command, **no privileged Message Content intent is required.**

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

### Locally

```bash
python main.py
```

### Or using Docker (Recommended)

You can run the pre-built Docker image directly from GitHub Container Registry. 
*Note: If the repository is private, you must first authenticate with GitHub using a Personal Access Token (PAT) with `read:packages` permission.*

```bash
# 1. (Private Repos Only) Authenticate Docker with GitHub
docker login ghcr.io -u YOUR_GITHUB_USERNAME
# When prompted for a password, paste your GitHub PAT

# 2. Create a directory for the bot data
mkdir data

# 3. Create your .env file
touch .env
# (Edit .env and add your DISCORD_TOKEN)

# 4. Run the container
docker run -d \
  --name foxhole-buddy \
  --env-file .env \
  -v $(pwd)/data:/app/data \
  --restart unless-stopped \
  ghcr.io/nonea785-cyber/fof:latest
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
3. From the menu, choose **Stockpile**, **Logistics**, **Inventory**, or **Factories**.
4. Everything is button & modal driven — no slash command arguments needed.

## Multi-Server

The bot is fully multi-server safe. Each Discord server's data (stockpiles, resources, inventory, alarms) is isolated by Guild ID. No server can see another server's information.

## Data

Runtime data is stored in a SQLite database at `data/foxhole.db` by default (configurable via `DB_FILE` in `.env`). Back this file up if the bot matters to your group.

On first boot the bot automatically imports any legacy flat-JSON store (`DATA_FILE`, default `data/stockpiles.json`) into the database, then renames it to `*.migrated` so it is never imported twice. Data is partitioned by Guild ID and indexed for fast per-server queries; when the bot is removed from a server, that server's data is purged automatically (both on the leave event and via a sweep at startup).

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
