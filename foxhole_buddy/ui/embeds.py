import discord
from foxhole_buddy.theme import Color
from foxhole_buddy.core.store import (
    Stockpile,
    LogisticsRequest,
    Operation,
    LOGI_OPEN,
    LOGI_CLAIMED,
    LOGI_DELIVERED,
    logi_counts,
    OP_SCHEDULED,
    OP_IN_PROGRESS,
    OP_COMPLETED,
    OP_CANCELLED,
    remaining_time,
    format_remaining,
    EXPIRY_HOURS,
)
from foxhole_buddy.utils.formatting import stockpile_type_label, stockpile_status, progress_bar, unix_ts

def stockpile_embed(stockpile: Stockpile) -> discord.Embed:
    remaining = format_remaining(remaining_time(stockpile))
    status, color = stockpile_status(stockpile)
    embed = discord.Embed(
        title=f"{stockpile.name}",
        description=(
            f"**{status}** | `{stockpile_type_label(stockpile)}`\n"
            f"**{stockpile.location}**"
        ),
        color=color,
    )
    embed.add_field(name="Timer", value=f"`{progress_bar(stockpile)}`\n**{remaining}** left", inline=False)
    embed.add_field(name="Stockpile ID", value=f"`{stockpile.id}`", inline=True)
    embed.add_field(name="Expires", value=f"<t:{unix_ts(stockpile.expires_datetime)}:R>", inline=True)
    embed.add_field(name="Last Refresh", value=f"<t:{unix_ts(stockpile.last_refreshed_datetime)}:R>", inline=True)
    embed.add_field(name="Updated By", value=f"<@{stockpile.last_refreshed_by_user_id}>", inline=True)
    embed.add_field(name="Refresh Window", value=f"{EXPIRY_HOURS}h", inline=True)
    embed.set_footer(text="Foxhole Buddy | Refresh in-game first, then press Mark Refreshed")
    return embed

def main_menu_embed() -> discord.Embed:
    embed = discord.Embed(
        title="🦊 Foxhole Buddy — Regiment Management",
        description="Your regiment's logistics assistant. Choose a category below.",
        color=Color.BRAND,
    )
    embed.add_field(name="📦 Stockpile", value="Reserve timers (12h/6h/1h/30m alerts)", inline=True)
    embed.add_field(name="🚚 Logistics", value="Request supplies from the catalog", inline=True)
    embed.add_field(name="📋 Inventory", value="Manage base inventory", inline=True)
    embed.add_field(name="🏭 Factories", value="Personal facility queue alarms", inline=True)
    embed.set_footer(text="Foxhole Buddy | War room: /foxhole_buddy war_room")
    return embed


def war_room_embed() -> discord.Embed:
    embed = discord.Embed(
        title="⚔️ War Room",
        description="Plan operations and check the live war.",
        color=Color.PURPLE,
    )
    embed.add_field(name="⚔️ Operations", value="Schedule ops, RSVP & squads", inline=True)
    embed.add_field(name="🌐 War Status", value="Current war number & state", inline=True)
    embed.add_field(name="💀 War Report", value="Casualties for a map/hex", inline=True)
    embed.set_footer(text="Foxhole Buddy | For the regiment")
    return embed


def war_status_embed(data: dict) -> discord.Embed:
    winner = data.get("winner", "NONE")
    winner_text = {
        "NONE": "⚔️ In progress",
        "WARDENS": "🔵 Wardens won",
        "COLONIALS": "🟢 Colonials won",
    }.get(winner, winner)
    embed = discord.Embed(title=f"🌐 Foxhole — War #{data.get('warNumber', '?')}", color=Color.BRAND)
    embed.add_field(name="Status", value=winner_text, inline=True)
    if data.get("requiredVictoryTowns") is not None:
        embed.add_field(name="Towns to win", value=str(data["requiredVictoryTowns"]), inline=True)
    start = data.get("conquestStartTime")
    if start:
        embed.add_field(name="Conquest start", value=f"<t:{int(start / 1000)}:R>", inline=True)
    embed.set_footer(text="Foxhole Buddy | Live war data")
    return embed


def war_report_embed(pretty_name: str, data: dict) -> discord.Embed:
    embed = discord.Embed(title=f"💀 War Report — {pretty_name}", color=Color.RED)
    embed.add_field(name="🔵 Warden casualties", value=f"{data.get('wardenCasualties', 0):,}", inline=True)
    embed.add_field(name="🟢 Colonial casualties", value=f"{data.get('colonialCasualties', 0):,}", inline=True)
    embed.add_field(name="Total enlistments", value=f"{data.get('totalEnlistments', 0):,}", inline=True)
    if data.get("dayOfWar") is not None:
        embed.add_field(name="Day of war", value=str(data["dayOfWar"]), inline=True)
    embed.set_footer(text="Foxhole Buddy | Live war data")
    return embed

def stockpile_actions_embed(urgent_role_id: int | None = None) -> discord.Embed:
    embed = discord.Embed(
        title="📦 Stockpile Actions",
        description="Manage your regiment's reserve stockpile timers.",
        color=Color.BRAND,
    )
    embed.add_field(name="➕ Add", value="Track a new stockpile", inline=True)
    embed.add_field(name="📋 List", value="View active timers", inline=True)
    embed.add_field(name="🔄 Refresh", value="Reset a timer by ID", inline=True)
    embed.add_field(name="🗑️ Delete", value="Remove a timer by ID", inline=True)
    embed.add_field(
        name="🔔 Urgent role (30m ping)",
        value=f"<@&{urgent_role_id}>" if urgent_role_id else "*none — pick below*",
        inline=False,
    )
    embed.set_footer(text="Foxhole Buddy | Use buttons below")
    return embed

def logistics_menu_embed() -> discord.Embed:
    embed = discord.Embed(
        title="🚚 Logistics Requests",
        description=(
            "Build a supply request with one or more items — add them by typing a "
            "name or browsing the catalog. Drivers can claim the whole list or "
            "individual items, deliver, then validate to close them out."
        ),
        color=Color.AMBER,
    )
    embed.add_field(name="➕ New Request", value="Search or browse → build a cart → submit", inline=True)
    embed.add_field(name="📊 Open Requests", value="View requests still needing delivery", inline=True)
    embed.set_footer(text="Foxhole Buddy | Keep the frontline supplied")
    return embed


_LOGI_STATUS = {
    LOGI_OPEN: ("🟥 OPEN — needs a driver", Color.RED),
    LOGI_CLAIMED: ("🚚 IN PROGRESS — claimed", Color.AMBER),
    LOGI_DELIVERED: ("✅ DELIVERED", Color.BRAND),
}
_LOGI_LINE_EMOJI = {LOGI_OPEN: "🟥", LOGI_CLAIMED: "🚚", LOGI_DELIVERED: "✅"}


def _format_lines(lines: list[dict], show_driver: bool = True) -> str:
    """Render line items as one bullet each, with status + optional driver."""
    out = []
    for line in lines:
        emoji = _LOGI_LINE_EMOJI.get(line.get("status", LOGI_OPEN), "🟥")
        driver = ""
        if show_driver and line.get("claimed_by_user_id"):
            driver = f" → <@{line['claimed_by_user_id']}>"
        out.append(f"{emoji} **{line['item']}** ×{line['quantity']:,}{driver}")
    return "\n".join(out)


def logistics_request_embed(request: LogisticsRequest) -> discord.Embed:
    lines = request.line_items()
    status_text, color = _LOGI_STATUS.get(request.status, ("OPEN", Color.RED))
    n = len(lines)
    title = f"🚚 {lines[0]['item']} ×{lines[0]['quantity']:,}" if n == 1 else f"🚚 Supply Request — {n} items"

    embed = discord.Embed(title=title, description=f"**{status_text}**", color=color)
    body = _format_lines(lines)
    embed.add_field(name="Items", value=body if len(body) <= 1024 else body[:1000] + "\n…", inline=False)

    counts = logi_counts(lines)
    progress = f"🟥 {counts[LOGI_OPEN]} open · 🚚 {counts[LOGI_CLAIMED]} claimed · ✅ {counts[LOGI_DELIVERED]} delivered"
    embed.add_field(name="Progress", value=progress, inline=False)

    embed.add_field(name="Requested by", value=f"<@{request.requested_by_user_id}>", inline=True)
    if request.op_id:
        embed.add_field(name="Operation", value="🔗 Linked to an op", inline=True)
    embed.add_field(name="Request ID", value=f"`{request.id}`", inline=True)
    if request.notes:
        embed.add_field(name="Notes", value=request.notes, inline=False)
    embed.set_footer(text="Foxhole Buddy | Claim a line or the whole list → deliver → Validate")
    return embed


def cart_embed(draft, hint: str | None = None) -> discord.Embed:
    """The running shopping cart shown while building a new request."""
    lines = draft.lines
    color = Color.AMBER if lines else Color.GRAY
    embed = discord.Embed(
        title="🛒 New Logistics Request",
        description=hint or "Add items by name or by browsing the catalog, then submit.",
        color=color,
    )
    if lines:
        total = sum(line["quantity"] for line in lines)
        body = "\n".join(
            f"`{i:>2}` **{line['item']}** ×{line['quantity']:,}  ·  *{line['category']} › {line['subcategory']}*"
            for i, line in enumerate(lines, start=1)
        )
        embed.add_field(
            name=f"Cart — {len(lines)} item(s), {total:,} total",
            value=body if len(body) <= 1024 else body[:1000] + "\n…",
            inline=False,
        )
    else:
        embed.add_field(
            name="Cart is empty",
            value="Use **Add by Name** 🔎 or **Browse** 📂 to add your first item.",
            inline=False,
        )
    if draft.notes:
        embed.add_field(name="Notes", value=draft.notes, inline=False)
    embed.set_footer(text="Foxhole Buddy | Catalog synced from the Foxhole wiki")
    return embed


def setup_embed(config: dict) -> discord.Embed:
    main_id = config.get("channel_id")
    faction = config.get("faction")
    ready = main_id is not None and faction is not None
    missing = []
    if main_id is None:
        missing.append("a **main channel**")
    if faction is None:
        missing.append("a **faction**")
    embed = discord.Embed(
        title="⚙️ Foxhole Buddy — Server Setup",
        description=(
            "All set! Alert channels are optional — leave them to use the main channel."
            if ready else
            "⚠️ **Setup incomplete.** Pick " + " and ".join(missing) + " below to finish."
        ),
        color=Color.BRAND if ready else Color.AMBER,
    )

    def channel(cid):
        return f"<#{cid}>" if cid else None

    embed.add_field(
        name="📍 Main channel",
        value=channel(main_id) or "⚠️ *not set*",
        inline=False,
    )
    faction_text = {"warden": "🔵 Warden", "colonial": "🟢 Colonial"}.get(faction, "⚠️ *required — pick below*")
    embed.add_field(name="⚔️ Faction", value=faction_text, inline=False)

    embed.add_field(
        name="⚔️ Operations channel",
        value=(
            f"{channel(config.get('ops_channel_id'))} — ops happen here (main channel works too)"
            if config.get("ops_channel_id") else "↳ *uses main channel*"
        ),
        inline=False,
    )
    embed.add_field(
        name="💬 Chats",
        value="Global & ally cross-server chat → press **💬 Setup Chats**",
        inline=False,
    )
    embed.set_footer(text="Foxhole Buddy | Changes save instantly · press Done when finished")
    return embed


def regi_net_panel_embed(faction: str | None, linked: int) -> discord.Embed:
    """Persistent 'Net Control' panel posted in a server's Regi Net channel."""
    fac = {"warden": "🔵 Warden", "colonial": "🟢 Colonial"}.get(faction or "", "⚪ Unaligned")
    embed = discord.Embed(
        title="📡 REGI NET — LIVE",
        description=(
            "Open comms across **all** linked regiments — every faction, one net.\n"
            "Send with **`/global <message> [image]`** or tap **✍️ Transmit** below.\n"
            "Your name, regiment, and faction ride along with every message."
        ),
        color=Color.BRAND,
    )
    embed.add_field(name="Your faction", value=fac, inline=True)
    embed.add_field(name="Regiments linked", value=f"**{linked}**", inline=True)
    embed.set_footer(text="Foxhole Buddy | Regi Net · cross-server comms")
    return embed


def ally_net_panel_embed(room_code: str, members: int) -> discord.Embed:
    """Persistent panel posted in an ally-room channel."""
    embed = discord.Embed(
        title="🛡️ ALLY NET — LIVE",
        description=(
            "Private comms with your allied servers in this room.\n"
            "Send with **`/ally <message> [image]`** or tap **✍️ Transmit** below."
        ),
        color=Color.PURPLE,
    )
    embed.add_field(name="Room code", value=f"`{room_code}`", inline=True)
    embed.add_field(name="Servers linked", value=f"**{members}**", inline=True)
    embed.set_footer(text="Foxhole Buddy | Ally Net · private comms")
    return embed


def chats_setup_embed(relay_channel_id: int | None, ally_room_count: int) -> discord.Embed:
    """Hub page for configuring cross-server chats (global + ally)."""
    embed = discord.Embed(
        title="💬 Setup Chats",
        description="Configure cross-server communications for this server.",
        color=Color.BRAND,
    )
    embed.add_field(
        name="🌐 Global chat (Regi Net)",
        value=(
            f"<#{relay_channel_id}> — `/global` reaches every linked regiment "
            "(bot needs **Manage Webhooks** here)"
            if relay_channel_id else "↳ *not joined — pick a channel below*"
        ),
        inline=False,
    )
    embed.add_field(
        name="🛡️ Ally chats (private rooms)",
        value=(
            f"**{ally_room_count}** room(s) joined — open **🛡️ Ally Chats** to manage"
            if ally_room_count else "↳ *none — open 🛡️ Ally Chats to create or join one*"
        ),
        inline=False,
    )
    embed.set_footer(text="Foxhole Buddy | Changes save instantly")
    return embed


def ally_setup_embed(rooms: list[dict]) -> discord.Embed:
    """Ally-room management page: lists the guild's rooms + how to add more."""
    embed = discord.Embed(
        title="🛡️ Ally Chats",
        description=(
            "Private cross-server rooms shared only with allies who have the code.\n"
            "**Create** a room to get a code to share, or **Join** with a code an ally gave "
            "you. Pick the channel first, then Create/Join."
        ),
        color=Color.PURPLE,
    )
    if rooms:
        lines = [
            f"`{r['room_code']}` → <#{r['channel_id']}> · **{r['members']}** server(s)"
            for r in rooms
        ]
        embed.add_field(name="Your ally rooms", value="\n".join(lines), inline=False)
    else:
        embed.add_field(name="Your ally rooms", value="*none yet*", inline=False)
    embed.set_footer(text="Foxhole Buddy | Share codes only with trusted allies")
    return embed


def operations_menu_embed() -> discord.Embed:
    embed = discord.Embed(
        title="⚔️ Operations",
        description=(
            "Schedule operations and let players RSVP. Keep it simple with "
            "**Going / Tentative / Can't**, or add named **squads** with capacity "
            "and leads for full coordination."
        ),
        color=Color.PURPLE,
    )
    embed.add_field(name="➕ Schedule Op", value="Plan a new operation", inline=True)
    embed.add_field(name="📋 View Ops", value="See upcoming operations", inline=True)
    embed.set_footer(text="Foxhole Buddy | For the regiment")
    return embed


_OP_STATUS = {
    OP_SCHEDULED: ("🟢 Scheduled", Color.BRAND),
    OP_IN_PROGRESS: ("🔵 In Progress", Color.BLUE),
    OP_COMPLETED: ("⚫ Completed", Color.GRAY),
    OP_CANCELLED: ("🔴 Cancelled", Color.RED),
}


_LOGI_STATUS_EMOJI = {LOGI_OPEN: "🟥", LOGI_CLAIMED: "🚚", LOGI_DELIVERED: "✅"}


_FACTION_DOT = {"warden": "🔵", "colonial": "🟢"}


def operation_card_embed(op: Operation, linked_requests: list | None = None) -> discord.Embed:
    status_text, color = _OP_STATUS.get(op.status, ("Scheduled", Color.BRAND))
    ts = unix_ts(op.scheduled_datetime)

    # Allied ops are mirrored into other servers where a raw <@id> won't resolve
    # or ping, so render their rosters by name + faction + home server instead.
    meta = op.participant_meta or {}

    def who(uid: int) -> str:
        if not op.ally_room:
            return f"<@{uid}>"
        info = meta.get(str(uid))
        if not info:
            # No recorded identity for this id on a shared op — fall back to a
            # plain label rather than a <@id> that would render as a broken
            # mention in the away servers' copies.
            return f"User {uid}"
        label = info.get("name") or f"User {uid}"
        badge = _FACTION_DOT.get((info.get("faction") or "").lower(), "")
        extra = " · ".join(x for x in (badge, info.get("server")) if x)
        return f"{label} ({extra})" if extra else label

    def roster(user_ids: list[int], empty: str = "—") -> str:
        if not user_ids:
            return empty
        text = ", ".join(who(uid) for uid in user_ids)
        return text if len(text) <= 1024 else text[:1000] + " …"

    embed = discord.Embed(
        title=f"⚔️ Op #{op.op_number} — {op.name}",
        description=op.description or "*No briefing provided.*",
        color=color,
    )
    if op.ally_room:
        embed.add_field(
            name="🤝 Allied Op",
            value=f"Shared live across ally room `{op.ally_room}`.",
            inline=False,
        )
    embed.add_field(name="When", value=f"<t:{ts}:F>\n<t:{ts}:R>", inline=True)
    embed.add_field(name="Leader", value=who(op.leader_user_id), inline=True)
    if op.location:
        embed.add_field(name="Location", value=op.location, inline=True)
    if op.war_number is not None:
        embed.add_field(name="War", value=f"#{op.war_number}", inline=True)

    embed.add_field(
        name="RSVP",
        value=(
            f"✅ Going **{op.going_count()}** · "
            f"❓ Tentative **{len(op.tentative)}** · "
            f"🚫 Can't **{len(op.not_available)}**"
        ),
        inline=False,
    )

    for squad in op.squads:
        cap = squad["capacity"]
        used = len(squad["members"])
        count = f"{used}/{cap}" if cap else f"{used}"
        lead = f" · 👑 {who(squad['lead_user_id'])}" if squad.get("lead_user_id") else ""
        name = f"🪖 {squad['name']} ({count}){lead}"
        value = roster(squad["members"])
        if squad["waitlist"]:
            value += f"\n*Waitlist:* {roster(squad['waitlist'])}"
        embed.add_field(name=name, value=value, inline=False)

    if op.going and op.squads:
        # Committed players who haven't picked a squad yet.
        embed.add_field(name="✅ Going (no squad)", value=roster(op.going), inline=False)
    elif op.going and not op.squads:
        embed.add_field(name="✅ Going", value=roster(op.going), inline=False)

    if op.tentative:
        embed.add_field(name="❓ Tentative", value=roster(op.tentative), inline=False)
    if op.not_available:
        embed.add_field(name="🚫 Can't Make It", value=roster(op.not_available), inline=False)

    if linked_requests:
        all_lines = [line for req in linked_requests for line in req.line_items()]
        rendered = []
        for req in linked_requests:
            for line in req.line_items():
                emoji = _LOGI_STATUS_EMOJI.get(line.get("status", LOGI_OPEN), "🟥")
                driver = f" → <@{line['claimed_by_user_id']}>" if line.get("claimed_by_user_id") else ""
                entry = f"{emoji} {line['item']} ×{line['quantity']:,}{driver}"
                rendered.append(entry)
        value = "\n".join(rendered)
        if len(value) > 1024:
            shown, kept = [], 0
            for entry in rendered:
                if sum(len(s) + 1 for s in shown) + len(entry) > 980:
                    break
                shown.append(entry)
                kept += 1
            value = "\n".join(shown) + f"\n… +{len(rendered) - kept} more"
        embed.add_field(
            name=f"📦 Logistics ({len(all_lines)} items, {len(linked_requests)} request(s))",
            value=value,
            inline=False,
        )

    embed.set_footer(text=f"Foxhole Buddy | Op ID: {op.id} · {status_text}")
    return embed


def inventory_type_embed() -> discord.Embed:
    embed = discord.Embed(
        title="🏭 Inventory Management",
        description="Select which inventory you want to manage.",
        color=Color.SLATE,
    )
    embed.add_field(name="Base Inv", value="Manage the main facility stockpile", inline=True)
    embed.add_field(name="Off Site Inv", value="(Coming Soon) Manage remote storage", inline=True)
    return embed


def base_inventory_actions_embed() -> discord.Embed:
    embed = discord.Embed(
        title="🏭 Base Inventory",
        description="Add, remove, or list materials stored at your main base.",
        color=Color.SLATE,
    )
    embed.add_field(name="➕ Add", value="Add materials to inventory", inline=True)
    embed.add_field(name="➖ Remove", value="Remove materials from inventory", inline=True)
    embed.add_field(name="📋 List", value="View current inventory", inline=True)
    embed.set_footer(text="Foxhole Buddy | Track every crate")
    return embed


def base_inventory_list_embed(inventory: dict[str, float]) -> discord.Embed:
    embed = discord.Embed(
        title="🏭 Base Inventory List",
        color=Color.SLATE,
    )
    if not inventory:
        embed.description = "The base inventory is currently empty."
        return embed

    # Format as a clean markdown table
    lines = ["```", f"{'Material':<25} | {'Quantity':>10}", "-" * 38]
    # Sort alphabetically by material
    for mat, qty in sorted(inventory.items()):
        # Format qty: if it's a whole number, don't show .0
        qty_str = f"{int(qty)}" if qty.is_integer() else f"{qty:.2f}"
        lines.append(f"{mat:<25} | {qty_str:>10}")
    lines.append("```")
    
    embed.description = "\n".join(lines)
    embed.set_footer(text="Foxhole Buddy | Base Inventory")
    return embed


def factory_menu_embed() -> discord.Embed:
    embed = discord.Embed(
        title="🏭 Factory Alarms",
        description="Set personal reminders for facility production queues.\n*Note: Timers are strictly rounded to the nearest 5-minute interval.*",
        color=Color.SLATE,
    )
    embed.add_field(name="🔔 3-Ping Alarm", value="Pings you 10m before, at completion, and 10m after", inline=True)
    embed.add_field(name="⏱️ 1-Ping Alarm", value="Pings you exactly when the queue finishes", inline=True)
    embed.add_field(name="📋 List Active", value="View your currently active alarms", inline=False)
    embed.set_footer(text="Foxhole Buddy | Clear your queues for the regiment")
    return embed


def factory_alarm_embed(alarm) -> discord.Embed:
    ping_type = "1-Ping (Exact Time Only)" if alarm.single_ping else "3-Ping (Before, Exact, After)"
    embed = discord.Embed(
        title=f"🏭 Factory Alarm: {alarm.facility_name}",
        description=f"**Started by:** <@{alarm.created_by_user_id}>",
        color=Color.BLUE,
    )
    embed.add_field(name="Finishes At", value=f"<t:{unix_ts(alarm.end_datetime)}:f>", inline=True)
    embed.add_field(name="Time Left", value=f"<t:{unix_ts(alarm.end_datetime)}:R>", inline=True)
    embed.add_field(name="Ping Type", value=f"`{ping_type}`", inline=False)
    embed.set_footer(text="Foxhole Buddy | Use the button below to turn off this alarm")
    return embed

