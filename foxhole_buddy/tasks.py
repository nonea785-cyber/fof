import discord
from discord.ext import tasks
from collections import defaultdict
from typing import TYPE_CHECKING
from foxhole_buddy.core.store import utc_now, warning_due, remaining_time, mark_warning_sent, format_remaining
from foxhole_buddy.utils.formatting import stockpile_status, unix_ts, stockpile_type_label

if TYPE_CHECKING:
    from foxhole_buddy.core.bot import StockpileBot
    from foxhole_buddy.core.store import Stockpile

@tasks.loop(seconds=60)
async def reminder_loop(bot: "StockpileBot") -> None:
    now = utc_now()

    # Group stockpiles by channel_id to minimise Discord API calls
    by_channel: dict[int, list["Stockpile"]] = defaultdict(list)
    for stockpile in bot.store.all():
        by_channel[stockpile.channel_id].append(stockpile)

    for channel_id, stockpiles in by_channel.items():
        try:
            channel = bot.get_channel(channel_id) or await bot.fetch_channel(channel_id)
        except Exception:
            continue  # Channel deleted or bot lost access

        for stockpile in stockpiles:
            warning = warning_due(stockpile, now)
            if warning is None:
                continue

            # Per-guild urgent role (set via /foxhole_buddy setup)
            urgent_role_id = bot.store.get_guild_urgent_role(stockpile.guild_id)
            prefix = ""
            if warning == "2h" and urgent_role_id:
                prefix = f"<@&{urgent_role_id}> "

            status, color = stockpile_status(stockpile)
            if warning == "expired":
                title = "Public Risk"
                description = (
                    f"**{stockpile.name}** may now be public.\n"
                    f"Last tracked expiry was <t:{unix_ts(stockpile.expires_datetime)}:R>."
                )
            else:
                title = f"{warning.upper()} Stockpile Alert"
                description = (
                    f"**{stockpile.name}** at **{stockpile.location}** is entering the **{status}** window.\n"
                    f"Time left: **{format_remaining(remaining_time(stockpile, now))}**"
                )

            embed = discord.Embed(title=title, description=description, color=color)
            embed.add_field(name="Stockpile ID", value=f"`{stockpile.id}`", inline=True)
            embed.add_field(name="Type", value=stockpile_type_label(stockpile), inline=True)
            embed.add_field(name="Expires", value=f"<t:{unix_ts(stockpile.expires_datetime)}:R>", inline=True)
            embed.set_footer(text="Foxhole Buddy | Refresh in-game, then press Mark Refreshed")

            await channel.send(content=prefix or None, embed=embed)
            mark_warning_sent(stockpile, warning)
            bot.store.update(stockpile)
            await bot.update_stockpile_message(stockpile)

    # Process Factory Alarms
    from datetime import timedelta
    for alarm in bot.store.get_factory_alarms():
        try:
            channel = bot.get_channel(alarm.channel_id) or await bot.fetch_channel(alarm.channel_id)
        except Exception:
            continue

        remaining = alarm.end_datetime - now

        if not alarm.single_ping:
            # 3-Ping: T-10m, T=0, T+10m — use sequential `if` so missed pings
            # still fire if the bot was offline (e.g. bot restarts).
            if remaining <= timedelta(minutes=10) and remaining > timedelta(minutes=0) and not alarm.warned_before:
                await channel.send(f"⏰ <@{alarm.created_by_user_id}>, your queue at **{alarm.facility_name}** finishes in 10 minutes!")
                bot.store.mark_factory_alarm_warned(alarm.id, "before")

            if remaining <= timedelta(minutes=0) and not alarm.warned_exact:
                await channel.send(f"⏰ <@{alarm.created_by_user_id}>, your queue at **{alarm.facility_name}** is finished! Please clear it.")
                bot.store.mark_factory_alarm_warned(alarm.id, "exact")

            if remaining <= timedelta(minutes=-10) and not alarm.warned_after:
                await channel.send(f"🚨 <@{alarm.created_by_user_id}>, your queue at **{alarm.facility_name}** has been finished for 10 minutes! Clear it now so others can use it!")
                # Send first, THEN delete — so a failed send doesn't lose the alarm
                bot.store.delete_factory_alarm(alarm.id)
        else:
            # 1-Ping: exactly at T=0
            if remaining <= timedelta(minutes=0) and not alarm.warned_exact:
                await channel.send(f"⏰ <@{alarm.created_by_user_id}>, your queue at **{alarm.facility_name}** is finished! Please clear it.")
                bot.store.delete_factory_alarm(alarm.id)
