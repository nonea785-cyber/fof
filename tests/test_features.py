from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from foxhole_buddy.core.store import (
    StockpileStore, make_squad, make_line, warning_due, mark_warning_sent, utc_now,
    LOGI_OPEN, LOGI_CLAIMED, LOGI_DELIVERED,
)
from foxhole_buddy.core.models import LogisticsRequest, derive_logi_status
from foxhole_buddy.catalog import Catalog
from foxhole_buddy.utils.formatting import relay_display_name
from foxhole_buddy.ui.embeds import operation_card_embed


def _line(item: str, qty: int = 1, category: str = "Resource", subcategory: str = "Material") -> dict:
    return make_line(category, subcategory, item, qty)


def _store() -> StockpileStore:
    return StockpileStore(Path(tempfile.mkdtemp()) / "f.db")


class GraduatedWarningTest(unittest.TestCase):
    def test_all_intervals_fire_and_persist(self) -> None:
        store = _store()
        now = datetime(2026, 6, 5, tzinfo=timezone.utc)
        sp = store.create(guild_id=1, channel_id=9, name="A", location="L",
                          stockpile_type="seaport", user_id=1, now=now)
        fired = []
        # Walk time down; at each tick fire whatever is due (catch-up included).
        for hrs in (13, 11, 5, 0.4, 0.1, -1):
            t = sp.expires_datetime - timedelta(hours=hrs)
            while (w := warning_due(sp, t)) is not None:
                mark_warning_sent(sp, w)
                fired.append(w)
        self.assertEqual(set(fired), {"12h", "6h", "1h", "30m", "expired"})

    def test_refresh_clears_reminders(self) -> None:
        store = _store()
        now = datetime(2026, 6, 5, tzinfo=timezone.utc)
        sp = store.create(guild_id=1, channel_id=9, name="A", location="L",
                          stockpile_type="seaport", user_id=1, now=now)
        sp.reminders_sent = ["12h", "6h"]
        store.update(sp)
        sp = store.refresh(sp.id, user_id=1, now=now)
        self.assertEqual(sp.reminders_sent, [])


class LogisticsLifecycleTest(unittest.TestCase):
    def test_claim_all_validate_all_and_op_link(self) -> None:
        store = _store()
        r = store.create_logistics_request(
            guild_id=1, channel_id=2, user_id=5,
            items=[_line("Basic Materials", 100)],
        )
        self.assertEqual(r.status, LOGI_OPEN)
        r = store.claim_all_logistics(r.id, user_id=6)
        self.assertEqual((r.status, r.claimed_by_user_id), (LOGI_CLAIMED, 6))
        r = store.validate_all_logistics(r.id, user_id=6)
        self.assertEqual(r.status, LOGI_DELIVERED)
        # op linking still works on a (now multi-line) request
        op = store.create_operation(guild_id=1, channel_id=2, name="Op",
                                    scheduled_at=datetime(2026, 7, 1, tzinfo=timezone.utc), leader_user_id=5)
        store.set_logistics_op(r.id, op.id)
        self.assertEqual([x.id for x in store.get_logistics_requests_for_op(op.id)], [r.id])
        store.set_logistics_op(r.id, None)
        self.assertEqual(store.get_logistics_requests_for_op(op.id), [])

    def test_multi_item_per_line_claim_and_validate(self) -> None:
        store = _store()
        r = store.create_logistics_request(
            guild_id=1, channel_id=2, user_id=5,
            items=[_line("Basic Materials", 50), _line("7.62mm", 20), _line("Bandages", 10)],
        )
        self.assertEqual(r.item_count(), 3)
        self.assertEqual(r.status, LOGI_OPEN)
        lids = [ln["lid"] for ln in r.line_items()]
        # Two different drivers claim two different lines → partial (CLAIMED).
        r = store.claim_logistics_line(r.id, lids[0], user_id=6)
        r = store.claim_logistics_line(r.id, lids[1], user_id=7)
        self.assertEqual(r.status, LOGI_CLAIMED)
        self.assertIsNone(r.claimed_by_user_id)  # mixed drivers
        # Validate one line; request stays in progress (line 2 claimed, line 3 open).
        r = store.validate_logistics_line(r.id, lids[0])
        statuses = {ln["lid"]: ln["status"] for ln in r.line_items()}
        self.assertEqual(statuses[lids[0]], LOGI_DELIVERED)
        self.assertEqual(r.status, LOGI_CLAIMED)
        # Manager claims the last open line, then validates everything.
        r = store.claim_logistics_line(r.id, lids[2], user_id=8)
        r = store.validate_all_logistics(r.id, user_id=999, is_manager=True)
        self.assertEqual(r.status, LOGI_DELIVERED)

    def test_revoke_returns_lines_to_open(self) -> None:
        store = _store()
        r = store.create_logistics_request(
            guild_id=1, channel_id=2, user_id=5, items=[_line("Bandages", 10)],
        )
        r = store.claim_all_logistics(r.id, user_id=6)
        self.assertEqual(r.status, LOGI_CLAIMED)
        r = store.revoke_logistics(r.id, user_id=6)
        self.assertEqual(r.status, LOGI_OPEN)

    def test_legacy_single_item_row_synthesizes_line(self) -> None:
        # A request that predates the items list still exposes one line.
        legacy = LogisticsRequest(
            id="old", guild_id=1, channel_id=2, message_id=None,
            category="Resource", subcategory="Material", item="Basic Materials",
            quantity=100, requested_by_user_id=5, status=LOGI_OPEN,
            claimed_by_user_id=None, op_id=None, notes="", created_at="x", updated_at="x",
            items=[],
        )
        lines = legacy.line_items()
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0]["item"], "Basic Materials")
        self.assertEqual(derive_logi_status(lines), LOGI_OPEN)


class OperationSquadTest(unittest.TestCase):
    def test_capacity_waitlist_promotion_and_lead(self) -> None:
        store = _store()
        op = store.create_operation(
            guild_id=1, channel_id=2, name="Push",
            scheduled_at=datetime(2026, 7, 1, tzinfo=timezone.utc), leader_user_id=1,
            squads=[make_squad("Armor", 2)],
        )
        key = op.squads[0]["key"]
        store.signup_squad(op.id, user_id=11, squad_key=key)
        store.signup_squad(op.id, user_id=12, squad_key=key)
        op, outcome = store.signup_squad(op.id, user_id=13, squad_key=key)
        self.assertEqual(outcome, "waitlist")
        # 11 withdraws → 13 promoted from waitlist
        op = store.withdraw(op.id, user_id=11)
        squad = op.find_squad(key)
        self.assertIn(13, squad["members"])
        self.assertEqual(squad["waitlist"], [])
        # lead assignment + clear on withdraw
        op = store.set_squad_lead(op.id, squad_key=key, user_id=12)
        self.assertEqual(op.find_squad(key)["lead_user_id"], 12)
        op = store.withdraw(op.id, user_id=12)
        self.assertIsNone(op.find_squad(key)["lead_user_id"])

    def test_set_squads_preserves_surviving_members(self) -> None:
        store = _store()
        op = store.create_operation(guild_id=1, channel_id=2, name="P",
                                    scheduled_at=datetime(2026, 7, 1, tzinfo=timezone.utc), leader_user_id=1,
                                    squads=[make_squad("Armor", 0)])
        key = op.squads[0]["key"]
        store.signup_squad(op.id, user_id=11, squad_key=key)
        op = store.set_squads(op.id, squad_defs=[("Armor", 4), ("Air Wing", 2)])
        self.assertEqual(op.find_squad(key)["members"], [11])
        self.assertEqual(op.find_squad(key)["capacity"], 4)
        self.assertEqual(len(op.squads), 2)


class GuildConfigTest(unittest.TestCase):
    def test_faction_and_alert_routing(self) -> None:
        store = _store()
        store.update_guild_config(1, channel_id=100, faction="warden",
                                  stockpile_channel_id=200, ops_channel_id=300)
        self.assertEqual(store.get_guild_faction(1), "warden")
        self.assertEqual(store.get_alert_channel(1, "stockpile"), 200)
        self.assertEqual(store.get_alert_channel(1, "ops"), 300)
        self.assertEqual(store.get_alert_channel(1, "anything-else"), 100)
        store.update_guild_config(2, channel_id=500)
        self.assertEqual(store.get_alert_channel(2, "stockpile"), 500)  # falls back

    def test_relay_channel_round_trips_and_clears(self) -> None:
        store = _store()
        store.update_guild_config(1, channel_id=100, relay_channel_id=777)
        self.assertEqual(store.get_relay_channel(1), 777)
        self.assertEqual(store.get_guild_config(1)["relay_channel_id"], 777)
        # Leaving the lobby clears membership.
        store.update_guild_config(1, relay_channel_id=None)
        self.assertIsNone(store.get_relay_channel(1))


class RelayTest(unittest.TestCase):
    def test_relay_channels_lists_only_joined_guilds(self) -> None:
        store = _store()
        store.update_guild_config(1, channel_id=10, relay_channel_id=111)
        store.update_guild_config(2, channel_id=20, relay_channel_id=222)
        store.update_guild_config(3, channel_id=30)  # configured but not joined
        self.assertEqual(set(store.relay_channels()), {(1, 111), (2, 222)})


class AllyChatTest(unittest.TestCase):
    def test_create_and_lookup(self) -> None:
        store = _store()
        code = store.create_ally_room(guild_id=1, channel_id=100)
        self.assertTrue(code.startswith("ALLY-"))
        self.assertEqual(store.ally_room_by_channel(1, 100), code)
        self.assertEqual(store.ally_members(code), [(1, 100)])

    def test_second_guild_joins(self) -> None:
        store = _store()
        code = store.create_ally_room(guild_id=1, channel_id=100)
        self.assertEqual(store.join_ally_room(2, 200, code), "ok")
        self.assertEqual(set(store.ally_members(code)), {(1, 100), (2, 200)})
        # Case-insensitive code entry works.
        self.assertEqual(store.join_ally_room(3, 300, code.lower()), "ok")
        self.assertEqual(len(store.ally_members(code)), 3)

    def test_multiple_rooms_per_guild(self) -> None:
        store = _store()
        a = store.create_ally_room(guild_id=1, channel_id=100)
        b = store.create_ally_room(guild_id=1, channel_id=101)
        self.assertNotEqual(a, b)
        self.assertEqual({r["room_code"] for r in store.ally_rooms_for_guild(1)}, {a, b})
        self.assertEqual(store.ally_room_by_channel(1, 101), b)

    def test_join_rejections(self) -> None:
        store = _store()
        code = store.create_ally_room(guild_id=1, channel_id=100)
        self.assertEqual(store.join_ally_room(2, 200, "ALLY-NOPE12"), "not_found")
        self.assertEqual(store.join_ally_room(1, 100, code), "already_member")
        # A channel already bound to one room can't join another.
        other = store.create_ally_room(guild_id=2, channel_id=200)
        self.assertEqual(store.join_ally_room(2, 200, code), "channel_in_use")
        self.assertNotEqual(other, code)

    def test_leave_and_purge(self) -> None:
        store = _store()
        code = store.create_ally_room(guild_id=1, channel_id=100)
        store.join_ally_room(2, 200, code)
        store.leave_ally_room(1, code)
        self.assertEqual(store.ally_members(code), [(2, 200)])
        store.create_ally_room(guild_id=2, channel_id=201)
        store.purge_guild(2)
        self.assertEqual(store.ally_rooms_for_guild(2), [])


class AlliedOpTest(unittest.TestCase):
    """Allied ops: one canonical op shared across an ally room, mirrored per server."""

    def _allied_op(self, store):
        # Host (guild 1) + ally (guild 2) share a room; host schedules an allied op.
        code = store.create_ally_room(guild_id=1, channel_id=100)
        store.join_ally_room(2, 200, code)
        op = store.create_operation(
            guild_id=1, channel_id=100, name="Coalition Push",
            scheduled_at=datetime(2026, 7, 1, tzinfo=timezone.utc), leader_user_id=1,
            squads=[make_squad("Armor", 2)], ally_room=code,
        )
        return code, op

    def test_create_persists_room_and_mirrors(self) -> None:
        store = _store()
        code, op = self._allied_op(store)
        self.assertEqual(op.ally_room, code)
        self.assertTrue(op.is_allied)
        store.add_operation_mirror(op.id, 1, 100, 9001)
        store.add_operation_mirror(op.id, 2, 200, 9002)
        mirrors = store.operation_mirrors(op.id)
        self.assertEqual({m["guild_id"] for m in mirrors}, {1, 2})
        self.assertEqual({m["message_id"] for m in mirrors}, {9001, 9002})
        # The ally guild sees it via its mirror; the host does not list it as a member op.
        member_ops = store.operations_for_member_guild(2, open_only=True)
        self.assertEqual([o.id for o in member_ops], [op.id])
        self.assertEqual(store.operations_for_member_guild(1, open_only=True), [])

    def test_rsvp_from_non_host_guild_updates_shared_op(self) -> None:
        store = _store()
        code, op = self._allied_op(store)
        # A user from the ally guild RSVPs — no guild filter, so it lands on the op.
        store.set_rsvp(op.id, user_id=42, state="going")
        store.set_participant_meta(
            op.id, 42, name="Ally Pilot", faction="colonial", guild_id=2, server="Server B"
        )
        op = store.get_operation(op.id)
        self.assertIn(42, op.going)
        self.assertEqual(op.participant_meta["42"]["server"], "Server B")
        # Withdrawing prunes both the bucket and the identity meta.
        op = store.withdraw(op.id, user_id=42)
        self.assertNotIn(42, op.going)
        self.assertNotIn("42", op.participant_meta)

    def test_squad_signup_and_lead_across_guilds(self) -> None:
        store = _store()
        code, op = self._allied_op(store)
        key = op.squads[0]["key"]
        # Signup + lead with no guild filter (the cross-server path).
        store.signup_squad(op.id, user_id=51, squad_key=key)
        op = store.set_squad_lead(op.id, squad_key=key, user_id=51)
        squad = op.find_squad(key)
        self.assertIn(51, squad["members"])
        self.assertEqual(squad["lead_user_id"], 51)

    def test_purge_member_keeps_op_purge_host_removes_it(self) -> None:
        store = _store()
        code, op = self._allied_op(store)
        store.add_operation_mirror(op.id, 1, 100, 9001)
        store.add_operation_mirror(op.id, 2, 200, 9002)
        # Ally leaves: only its mirror row goes; the op (hosted by guild 1) survives.
        store.purge_guild(2)
        self.assertIsNotNone(store.get_operation(op.id))
        self.assertEqual({m["guild_id"] for m in store.operation_mirrors(op.id)}, {1})
        # Host leaves: the op is deleted and its orphaned mirrors are swept.
        store.purge_guild(1)
        self.assertIsNone(store.get_operation(op.id))
        self.assertEqual(store.operation_mirrors(op.id), [])


def _embed_text(embed) -> str:
    parts = [embed.title or "", embed.description or ""]
    for f in embed.fields:
        parts.append(f.name or "")
        parts.append(str(f.value) if f.value is not None else "")
    return "\n".join(parts)


class AlliedOpRenderTest(unittest.TestCase):
    """Cross-server cards must render participants by name, never as a raw <@id>
    that would show as a broken mention in the away servers' copies."""

    def _allied_op(self, store):
        code = store.create_ally_room(guild_id=1, channel_id=100)
        store.join_ally_room(2, 200, code)
        op = store.create_operation(
            guild_id=1, channel_id=100, name="Coalition Push",
            scheduled_at=datetime(2026, 7, 1, tzinfo=timezone.utc), leader_user_id=1,
            ally_room=code,
        )
        return code, op

    def test_creator_renders_by_name_not_mention(self) -> None:
        store = _store()
        _, op = self._allied_op(store)
        # _submit_allied records the creator's identity; mirror that here.
        op = store.set_participant_meta(
            op.id, 1, name="Host Lead", faction="warden", guild_id=1, server="Server A"
        )
        text = _embed_text(operation_card_embed(op))
        self.assertIn("Host Lead", text)
        self.assertNotIn("<@1>", text)

    def test_meta_less_id_falls_back_to_plain_label(self) -> None:
        store = _store()
        _, op = self._allied_op(store)
        # A participant with no recorded meta must not leak a broken mention.
        op = store.set_rsvp(op.id, user_id=77, state="going")
        text = _embed_text(operation_card_embed(op))
        self.assertNotIn("<@77>", text)
        self.assertIn("User 77", text)


class _FakeMessage:
    def __init__(self, mid: int) -> None:
        self.id = mid


class _FakeChannel:
    def __init__(self, *, fail: bool = False, mid: int = 1000) -> None:
        self.fail = fail
        self.mid = mid
        self.sends: list = []

    async def send(self, *args, **kwargs):
        if self.fail:
            raise RuntimeError("missing Send Messages")
        self.sends.append((args, kwargs))
        return _FakeMessage(self.mid)


class _FakeBot:
    """Minimal stand-in exposing only what the loop / fan-out helpers touch."""

    def __init__(self, store: StockpileStore, channels: dict) -> None:
        self.store = store
        self._channels = channels

    def get_channel(self, cid):
        return self._channels.get(cid)

    async def fetch_channel(self, cid):
        ch = self._channels.get(cid)
        if ch is None:
            raise RuntimeError("unknown channel")
        return ch

    def add_view(self, *args, **kwargs) -> None:
        pass

    async def update_stockpile_message(self, stockpile) -> None:
        pass

    async def delete_card_message(self, channel_id, message_id) -> None:
        self.deleted = getattr(self, "deleted", [])
        self.deleted.append((channel_id, message_id))


class ReminderLoopResilienceTest(unittest.IsolatedAsyncioTestCase):
    async def test_one_failing_channel_does_not_abort_the_tick(self) -> None:
        from foxhole_buddy.tasks import reminder_loop

        store = _store()
        store.update_guild_config(1, channel_id=10)  # this guild's send will fail
        store.update_guild_config(2, channel_id=20)  # this one succeeds
        # ~20min of headroom → the "30m" warning (not expiry, so it persists a
        # reminder rather than deleting the row — that's what this test checks).
        past = utc_now() - timedelta(hours=47, minutes=40)
        store.create(guild_id=1, channel_id=10, name="A", location="L",
                     stockpile_type="seaport", user_id=1, now=past)
        sp2 = store.create(guild_id=2, channel_id=20, name="B", location="L",
                           stockpile_type="seaport", user_id=1, now=past)
        bad, good = _FakeChannel(fail=True), _FakeChannel()
        bot = _FakeBot(store, {10: bad, 20: good})

        # Must not raise even though guild 1's channel.send blows up.
        await reminder_loop.coro(bot)

        # Guild 2 was still processed: it got a send and its warning persisted.
        self.assertTrue(good.sends)
        self.assertTrue(store.get(sp2.id).reminders_sent)


class PostAlliedOpResilienceTest(unittest.IsolatedAsyncioTestCase):
    async def test_failed_send_records_no_mirror(self) -> None:
        from foxhole_buddy.core.bot import StockpileBot

        store = _store()
        code = store.create_ally_room(guild_id=1, channel_id=100)
        store.join_ally_room(2, 200, code)
        op = store.create_operation(
            guild_id=1, channel_id=100, name="Push",
            scheduled_at=datetime(2026, 7, 1, tzinfo=timezone.utc), leader_user_id=1,
            ally_room=code,
        )
        host = _FakeChannel(mid=9001)          # host post succeeds
        ally = _FakeChannel(fail=True)         # ally post fails
        bot = _FakeBot(store, {100: host, 200: ally})

        posted = await StockpileBot.post_allied_op(bot, op)

        self.assertEqual(posted, 1)
        mirrors = store.operation_mirrors(op.id)
        # Only the server we actually posted to has a mirror row; the failed one
        # is absent rather than left permanently stale with a NULL message_id.
        self.assertEqual([(m["guild_id"], m["message_id"]) for m in mirrors], [(1, 9001)])
        self.assertEqual(store.get_operation(op.id).message_id, 9001)


class DataAutoDeleteTest(unittest.TestCase):
    """'Done → gone': closed ops / delivered requests are fully removable, and
    deleting an op takes its mirrors with it and unlinks its supply requests."""

    def test_delete_operation_clears_mirrors_and_unlinks_logistics(self) -> None:
        store = _store()
        code = store.create_ally_room(guild_id=1, channel_id=100)
        store.join_ally_room(2, 200, code)
        op = store.create_operation(
            guild_id=1, channel_id=100, name="X",
            scheduled_at=datetime(2026, 7, 1, tzinfo=timezone.utc), leader_user_id=1,
            ally_room=code,
        )
        store.add_operation_mirror(op.id, 1, 100, 9001)
        store.add_operation_mirror(op.id, 2, 200, 9002)
        req = store.create_logistics_request(
            guild_id=1, channel_id=2, user_id=5, items=[_line("Bandages", 10)],
        )
        store.set_logistics_op(req.id, op.id)

        self.assertTrue(store.delete_operation(op.id))
        self.assertIsNone(store.get_operation(op.id))
        self.assertEqual(store.operation_mirrors(op.id), [])  # mirrors went too
        self.assertIsNone(store.get_logistics_request(req.id).op_id)  # request unlinked, not deleted

    def test_delivered_request_is_deletable(self) -> None:
        store = _store()
        r = store.create_logistics_request(
            guild_id=1, channel_id=2, user_id=5,
            items=[_line("Basic Materials", 50), _line("Bandages", 10)],
        )
        for lid in [ln["lid"] for ln in r.line_items()]:
            store.claim_logistics_line(r.id, lid, user_id=6)
        r = store.validate_all_logistics(r.id, user_id=6)
        self.assertEqual(r.status, LOGI_DELIVERED)  # the trigger condition
        self.assertTrue(store.delete_logistics_request(r.id))
        self.assertIsNone(store.get_logistics_request(r.id))


class StockpileExpiryDeleteTest(unittest.IsolatedAsyncioTestCase):
    async def test_expired_stockpile_is_alerted_then_deleted(self) -> None:
        from foxhole_buddy.tasks import reminder_loop

        store = _store()
        store.update_guild_config(1, channel_id=10)
        past = utc_now() - timedelta(hours=49)  # 48h window → already expired
        sp = store.create(guild_id=1, channel_id=10, name="A", location="L",
                          stockpile_type="seaport", user_id=1, now=past)
        ch = _FakeChannel()
        bot = _FakeBot(store, {10: ch})

        await reminder_loop.coro(bot)

        self.assertTrue(ch.sends)            # the Public-Risk alert still went out
        self.assertIsNone(store.get(sp.id))  # ...then the stockpile was cleared


class RelayDisplayNameTest(unittest.TestCase):
    def test_basic_format_with_faction(self) -> None:
        self.assertEqual(relay_display_name("Bob", "Wardens", "warden"), "Bob • Wardens · 🔵 Warden")
        self.assertEqual(relay_display_name("Sue", "Legion", "colonial"), "Sue • Legion · 🟢 Colonial")

    def test_unknown_faction_omits_badge(self) -> None:
        self.assertEqual(relay_display_name("Bob", "Wardens"), "Bob • Wardens")

    def test_truncates_to_webhook_limit_keeping_badge(self) -> None:
        name = relay_display_name("Bob", "X" * 200, "warden")
        self.assertLessEqual(len(name), 80)
        self.assertTrue(name.startswith("Bob • "))
        self.assertTrue(name.endswith("🔵 Warden"))

    def test_long_author_still_within_limit(self) -> None:
        name = relay_display_name("A" * 200, "Wardens", "warden")
        self.assertLessEqual(len(name), 80)


class CatalogFactionFilterTest(unittest.TestCase):
    def test_faction_filter_narrows_items(self) -> None:
        cat = Catalog.load("foxhole_buddy/catalog/seed_catalog.json")
        if cat.is_empty():
            self.skipTest("seed catalog missing")
        total = sum(len(cat.items(c, s)) for c, _ in cat.categories() for s, _ in cat.subcategories(c))
        warden = sum(len(cat.items(c, s, "warden")) for c, _ in cat.categories("warden")
                     for s, _ in cat.subcategories(c, "warden"))
        self.assertLess(warden, total)
        self.assertGreater(warden, 0)


class CatalogSearchTest(unittest.TestCase):
    def setUp(self) -> None:
        self.cat = Catalog.load("foxhole_buddy/catalog/seed_catalog.json")
        if self.cat.is_empty():
            self.skipTest("seed catalog missing")

    def test_search_ranks_and_shapes(self) -> None:
        results = self.cat.search("grenade")
        self.assertTrue(results)
        # Each result carries enough to build a request line.
        for key in ("name", "category_label", "subcategory_label", "crate_amount"):
            self.assertIn(key, results[0])

    def test_prefix_beats_substring(self) -> None:
        # "bandages" starts with "band" → must rank above any mid-word match.
        results = self.cat.search("band")
        self.assertTrue(results)
        self.assertTrue(results[0]["name"].lower().startswith("band"))

    def test_faction_filter_applies(self) -> None:
        everyone = len(self.cat.search("", limit=10000) or [])
        # Empty query returns nothing by contract.
        self.assertEqual(everyone, 0)
        warden = self.cat.search("materials", "warden")
        allf = self.cat.search("materials", None)
        self.assertLessEqual(len(warden), len(allf))

    def test_slang_alias_resolves(self) -> None:
        names = [m["name"] for m in self.cat.search("bmats")]
        self.assertIn("Basic Materials", names)

    def test_suggest_handles_typos(self) -> None:
        self.assertIn("Bandages", [m["name"] for m in self.cat.suggest("bandags")])
        self.assertEqual(self.cat.suggest("zzqqxx"), [])


class PurgeTest(unittest.TestCase):
    def test_purge_removes_all_guild_data(self) -> None:
        store = _store()
        store.update_guild_config(1, channel_id=1)
        store.create(guild_id=1, channel_id=2, name="A", location="L", stockpile_type="seaport", user_id=1)
        store.create_logistics_request(guild_id=1, channel_id=2, user_id=1, items=[_line("i", 1, "c", "s")])
        store.create_operation(guild_id=1, channel_id=2, name="op",
                               scheduled_at=datetime(2026, 7, 1, tzinfo=timezone.utc), leader_user_id=1)
        store.create(guild_id=2, channel_id=2, name="B", location="L", stockpile_type="seaport", user_id=1)
        store.purge_guild(1)
        self.assertEqual(store.known_guild_ids(), {2})


if __name__ == "__main__":
    unittest.main()
