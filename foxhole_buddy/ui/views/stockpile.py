"""Stockpile management views."""

from typing import TYPE_CHECKING

import discord

from foxhole_buddy.theme import Color
from foxhole_buddy.ui.embeds import main_menu_embed, stockpile_actions_embed, stockpile_embed
from foxhole_buddy.ui.modals import AddStockpileModal, DeleteStockpileModal, RefreshStockpileModal
from foxhole_buddy.utils.formatting import unix_ts

if TYPE_CHECKING:
    from foxhole_buddy.core.bot import StockpileBot


class StockpileActionsView(discord.ui.View):
    """Stockpile sub-menu: Add / List / Refresh / Delete / Back."""

    def __init__(self, bot: "StockpileBot"):
        super().__init__(timeout=120)
        self.bot = bot

    @discord.ui.button(label="Add", style=discord.ButtonStyle.success, emoji="➕", row=0)
    async def add_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not await self.bot._check_channel(interaction):
            return
        await interaction.response.edit_message(
            embed=discord.Embed(
                title="📦 Add Stockpile — Choose Type",
                description="What kind of stockpile is this?",
                color=Color.BRAND,
            ),
            view=StockpileTypeView(self.bot),
        )

    @discord.ui.button(label="List", style=discord.ButtonStyle.primary, emoji="📋", row=0)
    async def list_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not await self.bot._check_channel(interaction):
            return
        stockpiles = self.bot.store.all(guild_id=interaction.guild_id)
        if not stockpiles:
            await interaction.response.send_message(
                embed=discord.Embed(
                    title="No Stockpiles",
                    description="No active timers yet. Use **Add** to create one.",
                    color=Color.GRAY,
                ),
                ephemeral=True,
            )
            return
        await interaction.response.defer(ephemeral=True)
        channel = (
            interaction.channel
            or self.bot.get_channel(interaction.channel_id)
            or await self.bot.fetch_channel(interaction.channel_id)
        )
        for stockpile in stockpiles:
            msg = await channel.send(
                embed=stockpile_embed(stockpile),
                view=StockpileView(self.bot, stockpile.id),
            )
            self.bot.store.set_message_id(stockpile.id, msg.id)
        await interaction.followup.send(f"Listed **{len(stockpiles)}** stockpile(s).", ephemeral=True)

    @discord.ui.button(label="Refresh", style=discord.ButtonStyle.secondary, emoji="🔄", row=0)
    async def refresh_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not await self.bot._check_channel(interaction):
            return
        await interaction.response.send_modal(RefreshStockpileModal(self.bot))

    @discord.ui.button(label="Delete", style=discord.ButtonStyle.danger, emoji="🗑️", row=0)
    async def delete_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not await self.bot._check_channel(interaction):
            return
        await interaction.response.send_modal(DeleteStockpileModal(self.bot))

    @discord.ui.select(
        cls=discord.ui.RoleSelect, placeholder="🔔 Urgent role for the 30m ping (optional)",
        min_values=0, max_values=1, row=1,
    )
    async def urgent_role(self, interaction: discord.Interaction, select: discord.ui.RoleSelect) -> None:
        if not await self.bot._check_channel(interaction):
            return
        role_id = select.values[0].id if select.values else None
        self.bot.store.update_guild_config(interaction.guild_id, urgent_role_id=role_id)
        await interaction.response.edit_message(
            embed=stockpile_actions_embed(role_id),
            view=StockpileActionsView(self.bot),
        )

    @discord.ui.button(label="Back", style=discord.ButtonStyle.secondary, emoji="◀️", row=2)
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        from foxhole_buddy.ui.views.menu import MainMenuView

        await interaction.response.edit_message(
            embed=main_menu_embed(),
            view=MainMenuView(self.bot),
        )


class StockpileTypeView(discord.ui.View):
    """Shown after clicking Add — picks Seaport vs Storage Depot before opening the modal."""

    def __init__(self, bot: "StockpileBot"):
        super().__init__(timeout=60)
        self.bot = bot

    @discord.ui.button(label="Seaport", style=discord.ButtonStyle.primary, emoji="⚓")
    async def seaport_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_modal(AddStockpileModal(self.bot, "seaport"))

    @discord.ui.button(label="Storage Depot", style=discord.ButtonStyle.primary, emoji="🏭")
    async def depot_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_modal(AddStockpileModal(self.bot, "storage_depot"))

    @discord.ui.button(label="Back", style=discord.ButtonStyle.secondary, emoji="◀️")
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        role_id = self.bot.store.get_guild_urgent_role(interaction.guild_id)
        await interaction.response.edit_message(
            embed=stockpile_actions_embed(role_id),
            view=StockpileActionsView(self.bot),
        )


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
            stockpile = view.bot.store.refresh(
                self.stockpile_id,
                user_id=interaction.user.id,
                guild_id=interaction.guild_id,
            )
        except KeyError:
            await interaction.response.send_message("That stockpile no longer exists.", ephemeral=True)
            return

        await interaction.response.edit_message(embed=stockpile_embed(stockpile), view=StockpileView(view.bot, stockpile.id))
        await interaction.followup.send(
            f"Updated `{stockpile.name}`. Next public-risk check: <t:{unix_ts(stockpile.expires_datetime)}:R>.",
            ephemeral=True,
        )
