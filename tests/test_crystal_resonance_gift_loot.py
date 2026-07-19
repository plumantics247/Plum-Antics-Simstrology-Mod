import importlib
import pathlib
import sys
import unittest
from types import SimpleNamespace


sys.dont_write_bytecode = True

ROOT = pathlib.Path(__file__).resolve().parents[1]
PYTHON_DIR = ROOT / "python"
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))


loot_actions = importlib.import_module("cosmic_engine.loot_actions")
crystal_resonance = importlib.import_module("cosmic_engine.crystal_resonance")
crystal_resonance_activation = importlib.import_module("cosmic_engine.crystal_resonance_activation")
chart_records = importlib.import_module("cosmic_engine.chart_records")


class _FakeResolver(object):
    def __init__(self, **attrs):
        for key, value in attrs.items():
            setattr(self, key, value)


class _FakeSimInfo(object):
    def __init__(self, sim_id):
        self.sim_id = int(sim_id)
        self.id = int(sim_id)


class _FakeSim(object):
    def __init__(self, sim_info):
        self.sim_info = sim_info


class _FakeGiftObject(object):
    def __init__(self, definition_name, object_id):
        self.id = int(object_id)
        self.guid64 = int(object_id)
        self.definition = SimpleNamespace(name=str(definition_name))


class CrystalResonanceGiftLootTests(unittest.TestCase):
    def tearDown(self):
        crystal_resonance_activation.clear_crystal_resonance_activation_override()
        crystal_resonance.expire_attunements(now_ticks=10 ** 9)

    def _payload(self, sun, moon, rising):
        return {
            "sun_sign_index": chart_records.SIGNS.index(sun),
            "moon_sign_index": chart_records.SIGNS.index(moon),
            "rising_sign_index": chart_records.SIGNS.index(rising),
        }

    def test_resolve_participant_object_returns_raw_object_candidate(self):
        gifted_object = _FakeGiftObject("collectible_Crystal_Diamond", 91)
        resolver = _FakeResolver(obj=gifted_object)

        resolved = loot_actions._resolve_participant_object(resolver, ("PickedObject", "Object"))

        self.assertIs(gifted_object, resolved)

    def test_gifted_crystal_loot_registers_matching_attunement_and_marks_receiver_dirty(self):
        crystal_resonance_activation.set_crystal_resonance_activation_override(True)
        actor = _FakeSimInfo(7001)
        receiver = _FakeSimInfo(7002)
        gifted_object = _FakeGiftObject("collectible_Crystal_Diamond", 99)
        resolver = _FakeResolver(actor=_FakeSim(actor), target=receiver, obj=gifted_object)

        dirty_calls = []
        original_chart_payload_for_sim = loot_actions.chart_payload_for_sim
        original_mark_sim_dirty = loot_actions.mark_sim_dirty
        original_now_ticks = getattr(loot_actions, "_current_sim_absolute_ticks", None)
        original_minutes_to_ticks = getattr(loot_actions, "_sim_minutes_to_ticks", None)
        try:
            loot_actions.chart_payload_for_sim = lambda sim_info: self._payload("Aries", "Cancer", "Leo")
            loot_actions.mark_sim_dirty = (
                lambda sim_info, scopes, *, reason="unspecified": dirty_calls.append(
                    (getattr(sim_info, "sim_id", None), tuple(scopes), reason)
                )
            )
            loot_actions._current_sim_absolute_ticks = lambda: 100
            loot_actions._sim_minutes_to_ticks = lambda minutes: 50

            loot = loot_actions.CosmicEngineRegisterGiftedCrystalResonanceLoot()
            loot.apply_to_resolver(resolver)

            self.assertEqual(("Diamond",), crystal_resonance.active_attunement_keys_for_sim(7002, now_ticks=120))
            self.assertEqual(
                [(7002, ("crystal_resonance",), "gifted_crystal_resonance")],
                dirty_calls,
            )
        finally:
            loot_actions.chart_payload_for_sim = original_chart_payload_for_sim
            loot_actions.mark_sim_dirty = original_mark_sim_dirty
            if original_now_ticks is not None:
                loot_actions._current_sim_absolute_ticks = original_now_ticks
            else:
                delattr(loot_actions, "_current_sim_absolute_ticks")
            if original_minutes_to_ticks is not None:
                loot_actions._sim_minutes_to_ticks = original_minutes_to_ticks
            else:
                delattr(loot_actions, "_sim_minutes_to_ticks")


if __name__ == "__main__":
    unittest.main()
