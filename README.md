# Foxhole Buddy

Lightweight Python Discord bot for Foxhole reserve stockpile reminders.

The bot stores stockpiles in a local JSON text file and tracks expiry as 50 hours after the last in-game refresh.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` and set:

- `DISCORD_TOKEN`
- `BOT_CHANNEL_ID`

## Run

```bash
python3 bot.py
```

## Commands

- `/foxhole_buddy add name location type`
- `/foxhole_buddy list`
- `/foxhole_buddy refresh stockpile_id`
- `/foxhole_buddy delete stockpile_id`

Each stockpile card has a **Mark Refreshed** button. Press it only after refreshing the stockpile in Foxhole.

`/foxhole_buddy list` rebuilds the public stockpile board by posting one fresh card per stockpile, each with its own refresh button.

## Testing Core Logic

```bash
python3 -m unittest
```

## Data

Runtime data is stored at `data/stockpiles.json` by default. Back this file up if the bot matters to your group.
