from __future__ import annotations

import os
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import tasks

from stockpile_store import (
    EXPIRY_HOURS,
    Stockpile,
    StockpileStore,
    format_remaining,
    mark_warning_sent,
    remaining_time,
    utc_now,
    warning_due,
)


def load_env_file(path: str = ".env") -> None:
    env_path = Path(path)
    if not env_path.exists():
        return

    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def required_env(name: str) -> str:
    value = os.getenv(name)
    if not value or value.startswith("put_your_"):
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def required_int_env(name: str) -> int:
    value = required_env(name)
    try:
        return int(value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be a numeric Discord ID.") from exc


def optional_int_env(name: str) -> int | None:
    value = os.getenv(name)
    return int(value) if value else None


def unix_ts(value) -> int:
    return int(value.timestamp())


def stockpile_type_label(stockpile: Stockpile) -> str:
    return "Storage Depot" if stockpile.type == "storage_depot" else "Seaport"


def stockpile_status(stockpile: Stockpile) -> tuple[str, int]:
    remaining = remaining_time(stockpile)
    seconds_left = remaining.total_seconds()
    if seconds_left <= 0:
        return "PUBLIC RISK", 0xD83A3A
    if seconds_left <= 2 * 3600:
        return "CRITICAL", 0xF04747
    if seconds_left <= 6 * 3600:
        return "URGENT", 0xF59E0B
    if seconds_left <= 24 * 3600:
        return "WATCH", 0xEAB308
    return "SECURE", 0x2D7D46


def progress_bar(stockpile: Stockpile) -> str:
    total_seconds = EXPIRY_HOURS * 3600
    seconds_left = max(0, int(remaining_time(stockpile).total_seconds()))
    filled = round((seconds_left / total_seconds) * 10)
    filled = max(0, min(10, filled))
    return f"{'█' * filled}{'░' * (10 - filled)}"


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


class StockpileView(discord.ui.View):
    def __init__(self, bot: "StockpileBot", stockpile_id: str):
        super().__init__(timeout=None)
        self.bot = bot
        self.stockpile_id = stockpile_id
        self.add_item(RefreshStockpileButton(stockpile_id))


class RefreshStockpileButton(discord.ui.Button):
    def __init__(self, stockpile_id: str):
        super().__init__(
            label="Mark Refreshed",
            style=discord.ButtonStyle.success,
            custom_id=f"stockpile_refresh:{stockpile_id}",
        )
        self.stockpile_id = stockpile_id

    async def callback(self, interaction: discord.Interaction) -> None:
        view = self.view
        if not isinstance(view, StockpileView):
            await interaction.response.send_message("This stockpile button is not active.", ephemeral=True)
            return

        try:
            stockpile = view.bot.store.refresh(self.stockpile_id, user_id=interaction.user.id)
        except KeyError:
            await interaction.response.send_message("That stockpile no longer exists.", ephemeral=True)
            return

        await interaction.response.edit_message(embed=stockpile_embed(stockpile), view=StockpileView(view.bot, stockpile.id))
        await interaction.followup.send(
            f"Updated `{stockpile.name}`. Next public-risk check: <t:{unix_ts(stockpile.expires_datetime)}:R>.",
            ephemeral=True,
        )


class StockpileBot(discord.Client):
    def __init__(self, store: StockpileStore, bot_channel_id: int, urgent_role_id: int | None):
        intents = discord.Intents.default()
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.store = store
        self.bot_channel_id = bot_channel_id
        self.urgent_role_id = urgent_role_id
        self.guild_id = optional_int_env("DISCORD_GUILD_ID")

    async def setup_hook(self) -> None:
        self.register_commands()
        for stockpile in self.store.all():
            self.add_view(StockpileView(self, stockpile.id), message_id=stockpile.message_id)

        if self.guild_id:
            guild = discord.Object(id=self.guild_id)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
        else:
            await self.tree.sync()

        reminder_loop.change_interval(seconds=int(os.getenv("REMINDER_INTERVAL_SECONDS", "300")))
        if not reminder_loop.is_running():
            reminder_loop.start(self)

    def register_commands(self) -> None:
        stockpile_group = app_commands.Group(name="foxhole_buddy", description="Foxhole stockpile reminders.")

        @stockpile_group.command(name="help", description="Show how to use the stockpile reminder bot.")
        async def stockpile_help(interaction: discord.Interaction) -> None:
            embed = discord.Embed(
                title="Foxhole Buddy Help",
                description="A lightweight logistics timer for reserve stockpiles.",
                color=0x2D7D46,
            )
            embed.add_field(
                name="Command Deck",
                value=(
                    "`/foxhole_buddy add` - create a tracked stockpile\n"
                    "`/foxhole_buddy list` - scan active timers\n"
                    "`/foxhole_buddy refresh` - reset a timer by ID\n"
                    "`/foxhole_buddy delete` - remove a timer\n"
                    "`/foxhole_buddy help` - open this panel"
                ),
                inline=False,
            )
            embed.add_field(
                name="Refresh Protocol",
                value=(
                    "Use **Mark Refreshed** only after you refresh the stockpile in Foxhole. "
                    "Foxhole Buddy tracks your timer; it cannot touch the game state."
                ),
                inline=False,
            )
            embed.add_field(
                name="Timer Rules",
                value=(
                    f"Each refresh arms a **{EXPIRY_HOURS}h** window. "
                    "Alerts fire at **24h**, **6h**, **2h**, and once after expiry."
                ),
                inline=False,
            )
            embed.add_field(
                name="Example Drop",
                value="`/foxhole_buddy add name:Bmats location:Callahan's Passage type:Storage Depot`",
                inline=False,
            )
            embed.set_footer(text="Foxhole Buddy | Keep the depot private")
            await interaction.response.send_message(embed=embed, ephemeral=True)

        @stockpile_group.command(name="add", description="Create a Foxhole reserve stockpile reminder.")
        @app_commands.choices(
            type=[
                app_commands.Choice(name="Seaport", value="seaport"),
                app_commands.Choice(name="Storage Depot", value="storage_depot"),
            ]
        )
        async def stockpile_add(
            interaction: discord.Interaction,
            name: str,
            location: str,
            type: app_commands.Choice[str],
        ) -> None:
            if interaction.channel_id != self.bot_channel_id:
                await interaction.response.send_message(
                    "Wrong channel. Use the dedicated Foxhole Buddy reminder channel.",
                    ephemeral=True,
                )
                return

            stockpile = self.store.create(
                guild_id=interaction.guild_id or 0,
                channel_id=interaction.channel_id,
                name=name,
                location=location,
                stockpile_type=type.value,
                user_id=interaction.user.id,
            )
            await interaction.response.send_message(
                embed=stockpile_embed(stockpile),
                view=StockpileView(self, stockpile.id),
            )
            message = await interaction.original_response()
            self.store.set_message_id(stockpile.id, message.id)

        @stockpile_group.command(name="list", description="List active Foxhole stockpile reminders.")
        async def stockpile_list(interaction: discord.Interaction) -> None:
            if interaction.channel_id != self.bot_channel_id:
                await interaction.response.send_message(
                    "Wrong channel. Use the dedicated Foxhole Buddy reminder channel.",
                    ephemeral=True,
                )
                return

            stockpiles = self.store.all()
            if not stockpiles:
                embed = discord.Embed(
                    title="Foxhole Buddy Stockpiles",
                    description="No active stockpile timers yet.",
                    color=0x6B7280,
                )
                embed.set_footer(text="Create one with /foxhole_buddy add")
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return

            summary = discord.Embed(
                title="Foxhole Buddy Stockpile Board",
                description=(
                    f"Rebuilt **{len(stockpiles)}** stockpile card(s) below.\n"
                    "Each card has its own **Mark Refreshed** button."
                ),
                color=0x2D7D46,
            )
            summary.set_footer(text="Use the button only after refreshing the stockpile in Foxhole")
            await interaction.response.send_message(embed=summary)

            channel = interaction.channel
            if channel is None:
                channel = self.get_channel(self.bot_channel_id) or await self.fetch_channel(self.bot_channel_id)

            for stockpile in stockpiles:
                message = await channel.send(
                    embed=stockpile_embed(stockpile),
                    view=StockpileView(self, stockpile.id),
                )
                self.store.set_message_id(stockpile.id, message.id)

        @stockpile_group.command(name="refresh", description="Reset a stockpile timer after refreshing it in Foxhole.")
        async def stockpile_refresh(interaction: discord.Interaction, stockpile_id: str) -> None:
            try:
                stockpile = self.store.refresh(stockpile_id, user_id=interaction.user.id)
            except KeyError:
                await interaction.response.send_message("Unknown stockpile ID. Run `/foxhole_buddy list` to check IDs.", ephemeral=True)
                return

            await self.update_stockpile_message(stockpile)
            await interaction.response.send_message(
                f"Updated `{stockpile.name}`. Next public-risk check: <t:{unix_ts(stockpile.expires_datetime)}:R>.",
                ephemeral=True,
            )

        @stockpile_group.command(name="delete", description="Delete a Foxhole stockpile reminder.")
        async def stockpile_delete(interaction: discord.Interaction, stockpile_id: str) -> None:
            deleted = self.store.delete(stockpile_id)
            message = (
                f"Removed stockpile timer `{stockpile_id}`."
                if deleted
                else "Unknown stockpile ID. Run `/foxhole_buddy list` to check IDs."
            )
            await interaction.response.send_message(message, ephemeral=True)

        self.tree.add_command(stockpile_group)

    async def update_stockpile_message(self, stockpile: Stockpile) -> None:
        if stockpile.message_id is None:
            return
        channel = self.get_channel(stockpile.channel_id) or await self.fetch_channel(stockpile.channel_id)
        message = await channel.fetch_message(stockpile.message_id)
        await message.edit(embed=stockpile_embed(stockpile), view=StockpileView(self, stockpile.id))


@tasks.loop(seconds=300)
async def reminder_loop(bot: StockpileBot) -> None:
    now = utc_now()
    channel = bot.get_channel(bot.bot_channel_id) or await bot.fetch_channel(bot.bot_channel_id)

    for stockpile in bot.store.all():
        warning = warning_due(stockpile, now)
        if warning is None:
            continue

        prefix = ""
        if warning == "2h" and bot.urgent_role_id:
            prefix = f"<@&{bot.urgent_role_id}> "

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


def main() -> None:
    load_env_file()
    token = required_env("DISCORD_TOKEN")
    bot_channel_id = required_int_env("BOT_CHANNEL_ID")
    urgent_role_id = optional_int_env("URGENT_ROLE_ID")
    data_file = os.getenv("DATA_FILE", "data/stockpiles.json")

    bot = StockpileBot(
        store=StockpileStore(data_file),
        bot_channel_id=bot_channel_id,
        urgent_role_id=urgent_role_id,
    )
    bot.run(token)


if __name__ == "__main__":
    main()
