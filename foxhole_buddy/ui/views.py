import discord
from typing import TYPE_CHECKING
from foxhole_buddy.utils.formatting import unix_ts
from foxhole_buddy.ui.embeds import (
    stockpile_actions_embed,
    resources_actions_embed,
    main_menu_embed,
    resource_need_embed,
    stockpile_embed,
    inventory_type_embed,
    base_inventory_actions_embed,
    base_inventory_list_embed,
    factory_menu_embed,
    factory_alarm_embed
)
from foxhole_buddy.ui.modals import (
    AddStockpileModal,
    PostNeedModal,
    ClaimResourceModal,
    LogFarmedModal,
    RefreshStockpileModal,
    DeleteStockpileModal,
    AddInventoryModal,
    RemoveInventoryModal,
    AddFactoryAlarmModal
)

if TYPE_CHECKING:
    from foxhole_buddy.core.bot import StockpileBot

class MainMenuView(discord.ui.View):
    """Top-level regiment management menu."""

    def __init__(self, bot: "StockpileBot"):
        super().__init__(timeout=120)
        self.bot = bot

    @discord.ui.button(label="Stockpile", style=discord.ButtonStyle.primary, emoji="📦")
    async def stockpile_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.edit_message(
            embed=stockpile_actions_embed(),
            view=StockpileActionsView(self.bot),
        )

    @discord.ui.button(label="Resources", style=discord.ButtonStyle.secondary, emoji="⛏️")
    async def resources_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.edit_message(
            embed=resources_actions_embed(),
            view=ResourcesActionsView(self.bot),
        )

    @discord.ui.button(label="Inventory", style=discord.ButtonStyle.success, emoji="📋")
    async def inventory_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.edit_message(
            embed=inventory_type_embed(),
            view=InventoryTypeView(self.bot),
        )

    @discord.ui.button(label="Factories", style=discord.ButtonStyle.danger, emoji="🏭")
    async def factories_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.edit_message(
            embed=factory_menu_embed(),
            view=FactoryMenuView(self.bot),
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
        await interaction.response.edit_message(
            embed=stockpile_actions_embed(),
            view=StockpileActionsView(self.bot),
        )


class ResourcesActionsView(discord.ui.View):
    """Resources sub-menu: Post Need / I Can Farm / I Farmed / Needs Board / Back."""

    def __init__(self, bot: "StockpileBot"):
        super().__init__(timeout=120)
        self.bot = bot

    @discord.ui.button(label="Post Need", style=discord.ButtonStyle.danger, emoji="📋", row=0)
    async def post_need_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not await self.bot._check_channel(interaction):
            return
        await interaction.response.send_modal(PostNeedModal(self.bot))

    @discord.ui.button(label="I Can Farm", style=discord.ButtonStyle.success, emoji="⚒️", row=0)
    async def claim_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not await self.bot._check_channel(interaction):
            return
        await interaction.response.send_modal(ClaimResourceModal(self.bot))

    @discord.ui.button(label="I Farmed", style=discord.ButtonStyle.primary, emoji="✅", row=0)
    async def farmed_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not await self.bot._check_channel(interaction):
            return
        await interaction.response.send_modal(LogFarmedModal(self.bot))

    @discord.ui.button(label="Needs Board", style=discord.ButtonStyle.secondary, emoji="📊", row=1)
    async def board_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not await self.bot._check_channel(interaction):
            return
        needs = [n for n in self.bot.store.get_resource_needs(guild_id=interaction.guild_id) if not n.fulfilled]
        if not needs:
            await interaction.response.send_message(
                embed=discord.Embed(title="No Open Needs", description="No materials needed right now.", color=0x6B7280),
                ephemeral=True,
            )
            return
        await interaction.response.defer(ephemeral=True)
        for need in needs:
            await interaction.followup.send(embed=resource_need_embed(need), ephemeral=True)

    @discord.ui.button(label="Back", style=discord.ButtonStyle.secondary, emoji="◀️", row=1)
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.edit_message(embed=main_menu_embed(), view=MainMenuView(self.bot))


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
                color=0x2D7D46,
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
                    color=0x6B7280,
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

    @discord.ui.button(label="Back", style=discord.ButtonStyle.secondary, emoji="◀️", row=1)
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.edit_message(
            embed=main_menu_embed(),
            view=MainMenuView(self.bot),
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
            color=0x6B7280,
        )
        await interaction.response.edit_message(embed=embed, view=InventoryTypeView(self.bot))

    @discord.ui.button(label="Back", style=discord.ButtonStyle.secondary, emoji="◀️")
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
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


class FactoryMenuView(discord.ui.View):
    """Menu for managing factory alarms."""

    def __init__(self, bot: "StockpileBot"):
        super().__init__(timeout=120)
        self.bot = bot

    @discord.ui.button(label="Add 3-Ping Alarm", style=discord.ButtonStyle.success, emoji="🔔", row=0)
    async def add_3ping_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not await self.bot._check_channel(interaction):
            return
        await interaction.response.send_modal(AddFactoryAlarmModal(self.bot, single_ping=False))

    @discord.ui.button(label="Add 1-Ping Alarm", style=discord.ButtonStyle.primary, emoji="⏱️", row=0)
    async def add_1ping_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not await self.bot._check_channel(interaction):
            return
        await interaction.response.send_modal(AddFactoryAlarmModal(self.bot, single_ping=True))

    @discord.ui.button(label="List Active", style=discord.ButtonStyle.secondary, emoji="📋", row=1)
    async def list_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not await self.bot._check_channel(interaction):
            return
        
        alarms = self.bot.store.get_factory_alarms(guild_id=interaction.guild_id)
        if not alarms:
            await interaction.response.send_message("No active factory alarms.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        for alarm in alarms:
            await interaction.followup.send(
                embed=factory_alarm_embed(alarm),
                view=FactoryAlarmCardView(self.bot, alarm.id),
                ephemeral=True
            )

    @discord.ui.button(label="Back", style=discord.ButtonStyle.secondary, emoji="◀️", row=1)
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.edit_message(
            embed=main_menu_embed(),
            view=MainMenuView(self.bot),
        )


class FactoryAlarmCardView(discord.ui.View):
    def __init__(self, bot: "StockpileBot", alarm_id: str):
        super().__init__(timeout=None)
        self.bot = bot
        self.alarm_id = alarm_id
        
        button = discord.ui.Button(
            label="Turn Off Queue",
            style=discord.ButtonStyle.danger,
            emoji="⏹️",
            custom_id=f"factory_alarm_off:{alarm_id}"
        )
        button.callback = self.turn_off_callback
        self.add_item(button)

    async def turn_off_callback(self, interaction: discord.Interaction) -> None:
        deleted = self.bot.store.delete_factory_alarm(self.alarm_id, interaction.guild_id)
        if deleted:
            try:
                if interaction.message and interaction.message.flags.ephemeral:
                    await interaction.response.edit_message(content="*Alarm turned off.*", embed=None, view=None)
                else:
                    await interaction.response.defer()
                    if interaction.message:
                        await interaction.message.delete()
            except (discord.NotFound, discord.HTTPException):
                # The interaction response might already be done or message deleted
                pass
        else:
            await interaction.response.send_message("This alarm is already completed or deleted.", ephemeral=True)
