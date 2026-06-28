"""Inventory management views."""

from typing import TYPE_CHECKING

import discord

from foxhole_buddy.theme import Color
from foxhole_buddy.ui.embeds import (
    base_inventory_actions_embed,
    base_inventory_list_embed,
    inventory_type_embed,
    main_menu_embed,
)
from foxhole_buddy.ui.modals import AddInventoryModal, RemoveInventoryModal

if TYPE_CHECKING:
    from foxhole_buddy.core.bot import StockpileBot


class InventoryTypeView(discord.ui.View):
    """Shown after clicking Inventory — picks Base Inv vs Off Site Inv."""

    def __init__(self, bot: "StockpileBot"):
        super().__init__(timeout=120)
        self.bot = bot

    @discord.ui.button(label="Base Inv", style=discord.ButtonStyle.primary, emoji="🏭")
    async def base_inv_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.edit_message(
            embed=base_inventory_actions_embed(),
            view=BaseInventoryActionsView(self.bot),
        )

    @discord.ui.button(label="Off Site Inv", style=discord.ButtonStyle.secondary, emoji="📦")
    async def offsite_inv_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        embed = discord.Embed(
            title="📦 Off-Site Inventory",
            description="*(Coming Soon)* Off-site inventory tracking is not yet available.",
            color=Color.GRAY,
        )
        await interaction.response.edit_message(embed=embed, view=InventoryTypeView(self.bot))

    @discord.ui.button(label="Back", style=discord.ButtonStyle.secondary, emoji="◀️")
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        from foxhole_buddy.ui.views.menu import MainMenuView

        await interaction.response.edit_message(
            embed=main_menu_embed(),
            view=MainMenuView(self.bot),
        )


class BaseInventoryActionsView(discord.ui.View):
    """Base Inventory sub-menu: Add / Remove / List / Back."""

    def __init__(self, bot: "StockpileBot"):
        super().__init__(timeout=120)
        self.bot = bot

    @discord.ui.button(label="Add", style=discord.ButtonStyle.success, emoji="➕", row=0)
    async def add_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not await self.bot._check_channel(interaction):
            return
        await interaction.response.send_modal(AddInventoryModal(self.bot))

    @discord.ui.button(label="Remove", style=discord.ButtonStyle.danger, emoji="➖", row=0)
    async def remove_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not await self.bot._check_channel(interaction):
            return
        await interaction.response.send_modal(RemoveInventoryModal(self.bot))

    @discord.ui.button(label="List", style=discord.ButtonStyle.primary, emoji="📋", row=0)
    async def list_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not await self.bot._check_channel(interaction):
            return

        guild_id = interaction.guild_id or 0
        inventory = self.bot.store.get_base_inventory(guild_id)

        await interaction.response.send_message(
            embed=base_inventory_list_embed(inventory),
            ephemeral=True
        )

    @discord.ui.button(label="Back", style=discord.ButtonStyle.secondary, emoji="◀️", row=1)
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.edit_message(
            embed=inventory_type_embed(),
            view=InventoryTypeView(self.bot),
        )
