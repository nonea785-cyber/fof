import discord
from typing import TYPE_CHECKING
from foxhole_buddy.utils.formatting import unix_ts
from foxhole_buddy.ui.embeds import stockpile_embed, factory_alarm_embed

if TYPE_CHECKING:
    from foxhole_buddy.core.bot import StockpileBot
    from foxhole_buddy.ui.views import StockpileView

class AddStockpileModal(discord.ui.Modal, title="Add Stockpile"):
    name_input = discord.ui.TextInput(
        label="Stockpile Name",
        placeholder='e.g. "Bmats Reserve"',
        max_length=100,
    )
    location_input = discord.ui.TextInput(
        label="Location",
        placeholder='e.g. "Callahan\'s Passage"',
        max_length=100,
    )

    def __init__(self, bot: "StockpileBot", stockpile_type: str):
        super().__init__()
        self.bot = bot
        self.stockpile_type = stockpile_type

    async def on_submit(self, interaction: discord.Interaction) -> None:
        stockpile = self.bot.store.create(
            guild_id=interaction.guild_id or 0,
            channel_id=interaction.channel_id,
            name=self.name_input.value,
            location=self.location_input.value,
            stockpile_type=self.stockpile_type,
            user_id=interaction.user.id,
        )
        # Import inside to avoid circular imports if needed, though TYPE_CHECKING usually handles it.
        from foxhole_buddy.ui.views import StockpileView
        await interaction.response.send_message(
            embed=stockpile_embed(stockpile),
            view=StockpileView(self.bot, stockpile.id),
        )
        message = await interaction.original_response()
        self.bot.store.set_message_id(stockpile.id, message.id)


class RefreshStockpileModal(discord.ui.Modal, title="Refresh Stockpile"):
    stockpile_id_input = discord.ui.TextInput(
        label="Stockpile ID",
        placeholder="8-character ID shown on the stockpile card",
        min_length=8,
        max_length=8,
    )

    def __init__(self, bot: "StockpileBot"):
        super().__init__()
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            stockpile = self.bot.store.refresh(
                self.stockpile_id_input.value.strip(),
                user_id=interaction.user.id,
                guild_id=interaction.guild_id,
            )
        except KeyError:
            await interaction.response.send_message(
                "Unknown stockpile ID. Use the **List** button to find IDs.", ephemeral=True
            )
            return
        await self.bot.update_stockpile_message(stockpile)
        await interaction.response.send_message(
            f"✅ Refreshed `{stockpile.name}`. Expires <t:{unix_ts(stockpile.expires_datetime)}:R>.",
            ephemeral=True,
        )


class DeleteStockpileModal(discord.ui.Modal, title="Delete Stockpile"):
    stockpile_id_input = discord.ui.TextInput(
        label="Stockpile ID",
        placeholder="8-character ID shown on the stockpile card",
        min_length=8,
        max_length=8,
    )

    def __init__(self, bot: "StockpileBot"):
        super().__init__()
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction) -> None:
        deleted = self.bot.store.delete(
            self.stockpile_id_input.value.strip(),
            guild_id=interaction.guild_id,
        )
        if deleted:
            await interaction.response.send_message(
                f"🗑️ Removed stockpile `{self.stockpile_id_input.value.strip()}`.", ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "Unknown stockpile ID. Use the **List** button to find IDs.", ephemeral=True
            )


def _parse_quantity(raw: str) -> int | None:
    """Parse a positive whole-number quantity, tolerating commas/whitespace."""
    try:
        quantity = int((raw or "").replace(",", "").strip())
    except (ValueError, AttributeError):
        return None
    return quantity if quantity > 0 else None


async def _rerender_cart(interaction: discord.Interaction, bot, draft, hint=None) -> None:
    """Edit the originating ephemeral message back to the cart view."""
    from foxhole_buddy.ui.embeds import cart_embed
    from foxhole_buddy.ui.views.logistics import LogisticsCartView

    await interaction.response.edit_message(
        embed=cart_embed(draft, hint=hint), view=LogisticsCartView(bot, draft)
    )


class LineQuantityModal(discord.ui.Modal, title="Add Item"):
    """Capture a quantity for a browsed item and add it to the request cart."""

    quantity_input = discord.ui.TextInput(
        label="Quantity",
        placeholder="e.g. 5 (crates or units)",
        max_length=9,
    )

    def __init__(self, bot: "StockpileBot", draft, category: str, subcategory: str, item: str):
        super().__init__()
        self.bot = bot
        self.draft = draft
        self.category = category
        self.subcategory = subcategory
        self.item = item
        self.title = f"Add: {item}"[:45]  # modal titles cap at 45 chars

    async def on_submit(self, interaction: discord.Interaction) -> None:
        quantity = _parse_quantity(self.quantity_input.value)
        if quantity is None:
            await interaction.response.send_message(
                "Quantity must be a positive whole number.", ephemeral=True
            )
            return
        from foxhole_buddy.core.models import make_line
        self.draft.lines.append(make_line(self.category, self.subcategory, self.item, quantity))
        await _rerender_cart(interaction, self.bot, self.draft)


class SearchItemModal(discord.ui.Modal, title="Add by Name"):
    """Type an item name + quantity; fuzzy-match the catalog and add to the cart."""

    name_input = discord.ui.TextInput(
        label="Item name",
        placeholder="e.g. bandages, grenade, 7.62, materials",
        max_length=100,
    )
    quantity_input = discord.ui.TextInput(
        label="Quantity",
        placeholder="e.g. 5 (crates or units)",
        max_length=9,
    )

    def __init__(self, bot: "StockpileBot", draft):
        super().__init__()
        self.bot = bot
        self.draft = draft

    async def on_submit(self, interaction: discord.Interaction) -> None:
        quantity = _parse_quantity(self.quantity_input.value)
        if quantity is None:
            await interaction.response.send_message(
                "Quantity must be a positive whole number.", ephemeral=True
            )
            return
        faction = self.bot.store.get_guild_faction(interaction.guild_id)
        matches = self.bot.catalog.search(self.name_input.value, faction)
        query = self.name_input.value.strip()
        if not matches:
            # No catalog hit → offer "did you mean?" suggestions and the option
            # to add the typed text as a custom (off-catalog) item.
            from foxhole_buddy.ui.embeds import cart_embed
            from foxhole_buddy.ui.views.logistics import NoMatchView
            suggestions = self.bot.catalog.suggest(query, faction)
            hint = (
                f'No catalog match for "{query}". Did you mean one of these — '
                "or add it as a custom item?"
                if suggestions
                else f'No catalog match for "{query}". Add it as a custom item, or use Browse.'
            )
            await interaction.response.edit_message(
                embed=cart_embed(self.draft, hint=hint),
                view=NoMatchView(self.bot, self.draft, query, quantity, suggestions),
            )
            return
        if len(matches) == 1:
            from foxhole_buddy.core.models import make_line
            m = matches[0]
            self.draft.lines.append(
                make_line(m["category_label"], m["subcategory_label"], m["name"], quantity)
            )
            await _rerender_cart(interaction, self.bot, self.draft)
            return
        # Multiple hits → let them disambiguate, carrying the typed quantity.
        from foxhole_buddy.ui.embeds import cart_embed
        from foxhole_buddy.ui.views.logistics import SearchResultView
        await interaction.response.edit_message(
            embed=cart_embed(self.draft, hint=f'Multiple matches for "{query}" — pick one:'),
            view=SearchResultView(self.bot, self.draft, matches, quantity),
        )


class LogisticsNotesModal(discord.ui.Modal, title="Delivery Notes"):
    """Set/replace the delivery notes for the whole request."""

    def __init__(self, bot: "StockpileBot", draft):
        super().__init__()
        self.bot = bot
        self.draft = draft
        self.notes_input = discord.ui.TextInput(
            label="Notes (optional)",
            placeholder="e.g. drop at the frontline bunker base",
            style=discord.TextStyle.paragraph,
            required=False,
            max_length=300,
            default=draft.notes or None,
        )
        self.add_item(self.notes_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        self.draft.notes = self.notes_input.value or ""
        await _rerender_cart(interaction, self.bot, self.draft)


class AddInventoryModal(discord.ui.Modal, title="Add to Base Inventory"):
    material_input = discord.ui.TextInput(
        label="Material Name",
        placeholder='e.g. "Bmats" or "Diesel"',
        max_length=100,
    )
    amount_input = discord.ui.TextInput(
        label="Amount",
        placeholder="e.g. 10.5 or 500",
        max_length=20,
    )

    def __init__(self, bot: "StockpileBot"):
        super().__init__()
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            amount = float(self.amount_input.value.replace(",", "").strip())
            if amount <= 0:
                raise ValueError
        except ValueError:
            await interaction.response.send_message("Amount must be a number greater than 0.", ephemeral=True)
            return
            
        guild_id = interaction.guild_id or 0
        material = self.material_input.value
        
        self.bot.store.add_to_base_inventory(guild_id, material, amount)
        qty_str = f"{int(amount)}" if amount.is_integer() else f"{amount:.2f}"
        await interaction.response.send_message(f"✅ Added `{qty_str}` of **{material.title()}** to base inventory.", ephemeral=True)


class RemoveInventoryModal(discord.ui.Modal, title="Remove from Base Inventory"):
    material_input = discord.ui.TextInput(
        label="Material Name",
        placeholder='e.g. "Bmats" or "Diesel"',
        max_length=100,
    )
    amount_input = discord.ui.TextInput(
        label="Amount",
        placeholder="e.g. 10.5 or 500",
        max_length=20,
    )

    def __init__(self, bot: "StockpileBot"):
        super().__init__()
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            amount = float(self.amount_input.value.replace(",", "").strip())
            if amount <= 0:
                raise ValueError
        except ValueError:
            await interaction.response.send_message("Amount must be a number greater than 0.", ephemeral=True)
            return
            
        guild_id = interaction.guild_id or 0
        material = self.material_input.value
        
        try:
            self.bot.store.remove_from_base_inventory(guild_id, material, amount)
            qty_str = f"{int(amount)}" if amount.is_integer() else f"{amount:.2f}"
            await interaction.response.send_message(f"➖ Removed `{qty_str}` of **{material.title()}** from base inventory.", ephemeral=True)
        except KeyError:
            await interaction.response.send_message(f"❌ **{material.title()}** is not in the base inventory.", ephemeral=True)
        except ValueError as e:
            await interaction.response.send_message(f"❌ {str(e)}", ephemeral=True)


class AddFactoryAlarmModal(discord.ui.Modal, title="Set Factory Alarm"):
    facility_input = discord.ui.TextInput(
        label="Facility Name",
        placeholder='e.g. "Coke Refinery" or "Blast Furnace"',
        max_length=100,
    )
    duration_input = discord.ui.TextInput(
        label="Duration (in minutes)",
        placeholder="e.g. 60 for 1h (Rounded to nearest 5m)",
        max_length=40,
    )

    def __init__(self, bot: "StockpileBot", single_ping: bool):
        super().__init__()
        self.bot = bot
        self.single_ping = single_ping

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            duration = int(self.duration_input.value.strip())
            if duration < 5:
                raise ValueError("Duration must be at least 5 minutes.")
        except ValueError:
            await interaction.response.send_message("Please enter a valid number of minutes (minimum 5).", ephemeral=True)
            return

        # Round to nearest 5
        remainder = duration % 5
        if remainder > 0:
            if remainder >= 3:
                duration += (5 - remainder)
            else:
                duration -= remainder

        alarm = self.bot.store.create_factory_alarm(
            guild_id=interaction.guild_id or 0,
            channel_id=interaction.channel_id,
            facility_name=self.facility_input.value,
            duration_minutes=duration,
            single_ping=self.single_ping,
            user_id=interaction.user.id,
        )

        from foxhole_buddy.ui.views import FactoryAlarmCardView
        await interaction.response.send_message(
            embed=factory_alarm_embed(alarm),
            view=FactoryAlarmCardView(self.bot, alarm.id),
        )
        message = await interaction.original_response()
        self.bot.store.set_factory_alarm_message_id(alarm.id, message.id)


# ── Operations ───────────────────────────────────────────────────────────────────

import re
from datetime import datetime, timezone
from foxhole_buddy.core.store import make_squad
from foxhole_buddy.ui.embeds import operation_card_embed

_DATE_FORMATS = ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M")


def parse_schedule(raw: str) -> datetime | None:
    """Parse an operator-entered UTC date/time into an aware UTC datetime."""
    raw = raw.strip().replace("T", " ")
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def parse_squads(raw: str) -> list[dict]:
    """One squad per line; an optional trailing 'xN' / '×N' sets capacity."""
    squads: list[dict] = []
    seen: set[str] = set()
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        capacity = 0
        match = re.search(r"[x×]\s*(\d+)\s*$", line, re.IGNORECASE)
        if match:
            capacity = int(match.group(1))
            line = line[: match.start()].strip()
        if not line:
            continue
        squad = make_squad(line, capacity)
        if squad["key"] in seen:
            continue
        seen.add(squad["key"])
        squads.append(squad)
    return squads


def squads_to_text(squads: list[dict]) -> str:
    lines = []
    for squad in squads:
        if squad["capacity"]:
            lines.append(f"{squad['name']} x{squad['capacity']}")
        else:
            lines.append(squad["name"])
    return "\n".join(lines)


class CreateOperationModal(discord.ui.Modal, title="Schedule Operation"):
    name_input = discord.ui.TextInput(label="Operation Name", max_length=100)
    schedule_input = discord.ui.TextInput(
        label="Date & Time — UTC",
        placeholder="YYYY-MM-DD HH:MM   e.g. 2026-06-28 23:30",
        max_length=20,
    )
    location_input = discord.ui.TextInput(
        label="Location (optional)", required=False, max_length=100,
        placeholder="e.g. Kuoppa Seaport",
    )
    description_input = discord.ui.TextInput(
        label="Briefing (optional)", required=False, style=discord.TextStyle.paragraph,
        max_length=1000,
    )
    squads_input = discord.ui.TextInput(
        label="Squads (optional) — one per line",
        required=False, style=discord.TextStyle.paragraph, max_length=500,
        placeholder="Flame Tank Crew x6\nTremola Squad x3\nInfantry",
    )

    def __init__(self, bot: "StockpileBot", ally_room: str | None = None):
        super().__init__()
        self.bot = bot
        # When set, the op is shared across this ally room and mirrored into every
        # member server's channel instead of being posted in the current channel.
        self.ally_room = ally_room

    async def on_submit(self, interaction: discord.Interaction) -> None:
        when = parse_schedule(self.schedule_input.value)
        if when is None:
            await interaction.response.send_message(
                "Couldn't read that date/time. Use **UTC** like `2026-06-28 23:30`.",
                ephemeral=True,
            )
            return

        if self.ally_room:
            await self._submit_allied(interaction, when)
            return

        op = self.bot.store.create_operation(
            guild_id=interaction.guild_id or 0,
            channel_id=interaction.channel_id,
            name=self.name_input.value,
            scheduled_at=when,
            leader_user_id=interaction.user.id,
            description=self.description_input.value or "",
            location=self.location_input.value or "",
            war_number=getattr(self.bot, "war_number", None),
            squads=parse_squads(self.squads_input.value or ""),
        )

        from foxhole_buddy.ui.views import OperationCardView
        await interaction.response.send_message(
            embed=operation_card_embed(op),
            view=OperationCardView(self.bot, op.id),
        )
        message = await interaction.original_response()
        self.bot.store.set_operation_message_id(op.id, message.id)

    async def _submit_allied(self, interaction: discord.Interaction, when: datetime) -> None:
        # The host's copy lives in its own bound channel for the room.
        host_channel = next(
            (cid for gid, cid in self.bot.store.ally_members(self.ally_room)
             if gid == interaction.guild_id),
            interaction.channel_id,
        )
        op = self.bot.store.create_operation(
            guild_id=interaction.guild_id or 0,
            channel_id=host_channel,
            name=self.name_input.value,
            scheduled_at=when,
            leader_user_id=interaction.user.id,
            description=self.description_input.value or "",
            location=self.location_input.value or "",
            war_number=getattr(self.bot, "war_number", None),
            squads=parse_squads(self.squads_input.value or ""),
            ally_room=self.ally_room,
        )
        # Record the creator's identity so the leader renders by name in every
        # mirror — without this they'd show as a raw <@id> that won't resolve in
        # the other servers' copies (they haven't RSVP'd, so have no meta yet).
        op = self.bot.store.set_participant_meta(
            op.id, interaction.user.id,
            name=interaction.user.display_name,
            faction=self.bot.store.get_guild_faction(interaction.guild_id),
            guild_id=interaction.guild_id,
            server=interaction.guild.name if interaction.guild else None,
        )
        # Respond first (fan-out is slow network I/O past Discord's ~3s window).
        await interaction.response.defer(ephemeral=True)
        count = await self.bot.post_allied_op(op)
        await interaction.followup.send(
            f"🤝 Allied op **#{op.op_number} — {op.name}** posted to **{count}** "
            f"server(s) in room `{self.ally_room}`.",
            ephemeral=True,
        )


class EditOperationModal(discord.ui.Modal, title="Edit Operation"):
    def __init__(self, bot: "StockpileBot", op_id: str):
        super().__init__()
        self.bot = bot
        self.op_id = op_id
        op = bot.store.get_operation(op_id)
        self.title = f"Edit Op #{op.op_number}"[:45] if op else "Edit Operation"

        prefill = op.scheduled_datetime.strftime("%Y-%m-%d %H:%M") if op else ""
        self.name_input = discord.ui.TextInput(
            label="Operation Name", max_length=100, default=op.name if op else "",
        )
        self.schedule_input = discord.ui.TextInput(
            label="Date & Time — UTC", max_length=20, default=prefill,
        )
        self.location_input = discord.ui.TextInput(
            label="Location (optional)", required=False, max_length=100,
            default=op.location if op else "",
        )
        self.description_input = discord.ui.TextInput(
            label="Briefing (optional)", required=False, style=discord.TextStyle.paragraph,
            max_length=1000, default=op.description if op else "",
        )
        self.squads_input = discord.ui.TextInput(
            label="Squads (optional) — one per line",
            required=False, style=discord.TextStyle.paragraph, max_length=500,
            default=squads_to_text(op.squads) if op else "",
        )
        for item in (self.name_input, self.schedule_input, self.location_input,
                     self.description_input, self.squads_input):
            self.add_item(item)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        # Reached only via the card's leader-gated Edit button; allied ops are
        # editable by the host from any member server, so don't filter by guild.
        op = self.bot.store.get_operation(self.op_id)
        if op is None:
            await interaction.response.send_message("That operation no longer exists.", ephemeral=True)
            return
        when = parse_schedule(self.schedule_input.value)
        if when is None:
            await interaction.response.send_message(
                "Couldn't read that date/time. Use **UTC** like `2026-06-28 23:30`.",
                ephemeral=True,
            )
            return

        from foxhole_buddy.core.store import dt_to_str
        op.name = self.name_input.value.strip()
        op.scheduled_at = dt_to_str(when)
        op.location = (self.location_input.value or "").strip()
        op.description = (self.description_input.value or "").strip()
        self.bot.store.update_operation(op)
        # Replace squads while preserving sign-ups for surviving squad names.
        new_defs = [(s["name"], s["capacity"]) for s in parse_squads(self.squads_input.value or "")]
        op = self.bot.store.set_squads(self.op_id, squad_defs=new_defs)

        await self.bot.update_operation_message(op)
        await interaction.response.send_message("✅ Operation updated.", ephemeral=True)


class NotifyOperationModal(discord.ui.Modal, title="Notify Attendees"):
    message_input = discord.ui.TextInput(
        label="Message (optional)", required=False, style=discord.TextStyle.paragraph,
        max_length=500, placeholder="e.g. Form up at the staging base now!",
    )

    def __init__(self, bot: "StockpileBot", op_id: str):
        super().__init__()
        self.bot = bot
        self.op_id = op_id

    async def on_submit(self, interaction: discord.Interaction) -> None:
        op = self.bot.store.get_operation(self.op_id)
        if op is None:
            await interaction.response.send_message("That operation no longer exists.", ephemeral=True)
            return
        recipients = op.participant_ids() + op.tentative
        if not recipients:
            await interaction.response.send_message("Nobody has signed up to notify yet.", ephemeral=True)
            return
        note = self.message_input.value.strip() or "Heads up — check the operation details."
        if op.ally_room:
            # Fan the notice to every allied server, pinging each one's own people.
            await interaction.response.send_message(
                "📣 Notified every allied server.", ephemeral=True
            )
            await self.bot.announce_allied_op(
                op, f"📣 **Op #{op.op_number} — {op.name}**\n{note}", recipients=recipients
            )
            return
        mentions = " ".join(f"<@{uid}>" for uid in recipients)
        await interaction.response.send_message(
            f"📣 **Op #{op.op_number} — {op.name}**\n{mentions}\n{note}"
        )
