import os
import discord
from discord import app_commands
from foxhole_buddy.core.store import StockpileStore, Stockpile, ResourceNeed
from foxhole_buddy.utils.env import optional_int_env
from foxhole_buddy.ui.embeds import stockpile_embed, resource_need_embed
from foxhole_buddy.ui.views import StockpileView
from foxhole_buddy.commands import register_commands
from foxhole_buddy.tasks import reminder_loop

class StockpileBot(discord.Client):
    def __init__(self, store: StockpileStore):
        intents = discord.Intents.default()
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.store = store
        self.guild_id = optional_int_env("DISCORD_GUILD_ID")

    async def setup_hook(self) -> None:
        register_commands(self)

        # Re-attach persistent views for all stockpiles across all guilds
        for stockpile in self.store.all():
            self.add_view(StockpileView(self, stockpile.id), message_id=stockpile.message_id)

        # Re-attach persistent views for factory alarms
        from foxhole_buddy.ui.views import FactoryAlarmCardView
        for alarm in self.store.get_factory_alarms():
            if alarm.message_id:
                self.add_view(FactoryAlarmCardView(self, alarm.id), message_id=alarm.message_id)

        if self.guild_id:
            guild = discord.Object(id=self.guild_id)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
        else:
            await self.tree.sync()

        reminder_loop.change_interval(seconds=int(os.getenv("REMINDER_INTERVAL_SECONDS", "60")))
        if not reminder_loop.is_running():
            reminder_loop.start(self)

    async def _check_channel(self, interaction: discord.Interaction) -> bool:
        """Verify the interaction is in this guild's configured reminder channel.

        Sends an ephemeral error and returns False if the check fails.
        """
        if interaction.guild_id is None:
            await interaction.response.send_message(
                "Foxhole Buddy only works inside a server.", ephemeral=True
            )
            return False

        configured = self.store.get_guild_channel(interaction.guild_id)
        if configured is None:
            await interaction.response.send_message(
                "⚙️ **Setup required.** An admin needs to run `/foxhole_buddy setup` "
                "in the desired reminder channel first.",
                ephemeral=True,
            )
            return False

        if interaction.channel_id != configured:
            await interaction.response.send_message(
                f"Please use Foxhole Buddy commands in <#{configured}>.",
                ephemeral=True,
            )
            return False

        return True

    async def update_stockpile_message(self, stockpile: Stockpile) -> None:
        if stockpile.message_id is None:
            return
        channel = self.get_channel(stockpile.channel_id) or await self.fetch_channel(stockpile.channel_id)
        message = await channel.fetch_message(stockpile.message_id)
        await message.edit(embed=stockpile_embed(stockpile), view=StockpileView(self, stockpile.id))

    async def update_resource_need_message(self, need: ResourceNeed) -> None:
        if need.message_id is None:
            return
        channel = self.get_channel(need.channel_id) or await self.fetch_channel(need.channel_id)
        message = await channel.fetch_message(need.message_id)
        await message.edit(embed=resource_need_embed(need))
