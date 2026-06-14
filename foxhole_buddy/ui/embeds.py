import discord
from foxhole_buddy.core.store import Stockpile, ResourceNeed, remaining_time, format_remaining, EXPIRY_HOURS
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
        color=0x2D7D46,
    )
    embed.add_field(name="📦 Stockpile", value="Track reserve stockpile timers", inline=True)
    embed.add_field(name="⛏️ Resources", value="Manage farming needs & contributions", inline=True)
    embed.add_field(name="📋 Inventory", value="Manage base inventory", inline=True)
    embed.add_field(name="🏭 Factories", value="Set personal facility queue alarms", inline=True)
    embed.set_footer(text="Foxhole Buddy | Keep the depot private")
    return embed

def stockpile_actions_embed() -> discord.Embed:
    embed = discord.Embed(
        title="📦 Stockpile Actions",
        description="Manage your regiment's reserve stockpile timers.",
        color=0x2D7D46,
    )
    embed.add_field(name="➕ Add", value="Track a new stockpile", inline=True)
    embed.add_field(name="📋 List", value="View active timers", inline=True)
    embed.add_field(name="🔄 Refresh", value="Reset a timer by ID", inline=True)
    embed.add_field(name="🗑️ Delete", value="Remove a timer by ID", inline=True)
    embed.set_footer(text="Foxhole Buddy | Use buttons below")
    return embed

def resources_actions_embed() -> discord.Embed:
    embed = discord.Embed(
        title="⛏️ Resource Management",
        description="Track what your regiment needs to farm and who's contributing.",
        color=0xF59E0B,
    )
    embed.add_field(name="📋 Post Need", value="Post a material the regiment needs", inline=True)
    embed.add_field(name="⚒️ I Can Farm", value="Pledge to farm a needed resource", inline=True)
    embed.add_field(name="✅ I Farmed", value="Log resources you've farmed", inline=True)
    embed.add_field(name="📊 Needs Board", value="View all open farming needs", inline=True)
    embed.set_footer(text="Foxhole Buddy | Every crate counts")
    return embed

def resource_need_embed(need: ResourceNeed) -> discord.Embed:
    total_pledged = sum(c["pledged"] for c in need.claims)
    total_farmed = sum(c["farmed"] for c in need.claims)
    pct = min(100, int((total_farmed / need.amount_needed) * 100)) if need.amount_needed > 0 else 0
    filled = round(pct / 10)
    bar = f"{'█' * filled}{'░' * (10 - filled)}"
    if need.fulfilled:
        status, color = "✅ FULFILLED", 0x2D7D46
    elif need.claims:
        status, color = "⚒️ IN PROGRESS", 0xF59E0B
    else:
        status, color = "🔴 NEEDS FARMERS", 0xD83A3A
    embed = discord.Embed(
        title=f"⛏️ {need.material}",
        description=f"**{status}**",
        color=color,
    )
    embed.add_field(name="Needed", value=f"`{need.amount_needed:,}`", inline=True)
    embed.add_field(name="Pledged", value=f"`{total_pledged:,}`", inline=True)
    embed.add_field(name="Farmed", value=f"`{total_farmed:,}`", inline=True)
    embed.add_field(name="Progress", value=f"`{bar}` {pct}%", inline=False)
    if need.claims:
        contributors = "\n".join(
            f"<@{c['user_id']}> — pledged `{c['pledged']:,}`, farmed `{c['farmed']:,}`"
            for c in need.claims
        )
        embed.add_field(name="Contributors", value=contributors, inline=False)
    embed.add_field(name="Need ID", value=f"`{need.id}`", inline=True)
    embed.add_field(name="Posted by", value=f"<@{need.created_by_user_id}>", inline=True)
    embed.set_footer(text="Foxhole Buddy | Use I Can Farm to pledge · I Farmed to report")
    return embed


def inventory_type_embed() -> discord.Embed:
    embed = discord.Embed(
        title="🏭 Inventory Management",
        description="Select which inventory you want to manage.",
        color=0x4B5563,
    )
    embed.add_field(name="Base Inv", value="Manage the main facility stockpile", inline=True)
    embed.add_field(name="Off Site Inv", value="(Coming Soon) Manage remote storage", inline=True)
    return embed


def base_inventory_actions_embed() -> discord.Embed:
    embed = discord.Embed(
        title="🏭 Base Inventory",
        description="Add, remove, or list materials stored at your main base.",
        color=0x4B5563,
    )
    embed.add_field(name="➕ Add", value="Add materials to inventory", inline=True)
    embed.add_field(name="➖ Remove", value="Remove materials from inventory", inline=True)
    embed.add_field(name="📋 List", value="View current inventory", inline=True)
    embed.set_footer(text="Foxhole Buddy | Track every crate")
    return embed


def base_inventory_list_embed(inventory: dict[str, float]) -> discord.Embed:
    embed = discord.Embed(
        title="🏭 Base Inventory List",
        color=0x4B5563,
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
        color=0x4B5563,
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
        color=0x3B82F6,
    )
    embed.add_field(name="Finishes At", value=f"<t:{unix_ts(alarm.end_datetime)}:f>", inline=True)
    embed.add_field(name="Time Left", value=f"<t:{unix_ts(alarm.end_datetime)}:R>", inline=True)
    embed.add_field(name="Ping Type", value=f"`{ping_type}`", inline=False)
    embed.set_footer(text="Foxhole Buddy | Use the button below to turn off this alarm")
    return embed

