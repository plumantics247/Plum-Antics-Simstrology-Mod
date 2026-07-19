import pathlib
import sys
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[1]
PYTHON_DIR = ROOT / "python"
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))


from cosmic_engine import mode_lock
from cosmic_engine import planet_house_markers
from cosmic_engine import ts4_runtime_install


class OuterPlanetsLegacyHouseholdRefreshFlagTests(unittest.TestCase):
    def setUp(self):
        self.payload = {}
        self.original_read = mode_lock._read_payload
        self.original_write = mode_lock._write_payload

        def _fake_read():
            return dict(self.payload)

        def _fake_write(next_payload):
            self.payload = dict(next_payload)
            return True

        mode_lock._read_payload = _fake_read
        mode_lock._write_payload = _fake_write

    def tearDown(self):
        mode_lock._read_payload = self.original_read
        mode_lock._write_payload = self.original_write

    def test_outer_planets_refresh_flag_defaults_false(self):
        self.assertFalse(mode_lock.has_household_outer_planets_refresh_run(12345))

    def test_mark_outer_planets_refresh_persists_household_entry(self):
        ok = mode_lock.mark_household_outer_planets_refresh_run(
            12345,
            source="runtime_init",
            refresh_summary={"sims_refreshed": 3, "traits_added": 12},
        )
        self.assertTrue(ok)
        self.assertTrue(mode_lock.has_household_outer_planets_refresh_run(12345))
        entries = mode_lock.get_outer_planets_refreshed_households()
        self.assertEqual("completed", entries["12345"]["status"])
        self.assertEqual(3, entries["12345"]["sims_refreshed"])


class OuterPlanetsLegacyHouseholdSyncTests(unittest.TestCase):
    def test_outer_planets_only_refresh_targets_only_requested_sim_infos(self):
        sim_a = object()
        sim_b = object()

        with mock.patch(
            "cosmic_engine.planet_house_markers.is_outer_planets_addon_active",
            return_value=True,
            create=True,
        ), mock.patch(
            "cosmic_engine.planet_house_markers.sync_zone_planet_house_markers",
            return_value={"sims_seen": 2, "sims_changed": 1},
        ) as sync_mock:
            summary = planet_house_markers.sync_active_household_outer_planets_only(
                sim_infos=(sim_a, sim_b),
                refresh_marker_cache=False,
                transit_service=object(),
            )

        self.assertEqual(2, summary["sims_seen"])
        self.assertEqual(1, summary["outer_planets_only"])
        self.assertEqual((sim_a, sim_b), sync_mock.call_args[1]["sim_infos"])

    def test_outer_planets_only_refresh_reports_noop_when_addon_inactive(self):
        with mock.patch(
            "cosmic_engine.planet_house_markers.is_outer_planets_addon_active",
            return_value=False,
            create=True,
        ):
            summary = planet_house_markers.sync_active_household_outer_planets_only(
                sim_infos=(object(),),
                refresh_marker_cache=False,
                transit_service=object(),
            )
        self.assertEqual("addon_inactive", summary["reason"])
        self.assertEqual(0, summary["sims_seen"])


class OuterPlanetsLegacyRuntimeHookTests(unittest.TestCase):
    def test_runtime_hook_skips_when_household_already_marked(self):
        with mock.patch(
            "cosmic_engine.ts4_runtime_install.is_outer_planets_addon_active",
            return_value=True,
            create=True,
        ), mock.patch(
            "cosmic_engine.ts4_runtime_install._get_active_household_id",
            return_value=12345,
        ), mock.patch(
            "cosmic_engine.ts4_runtime_install.has_household_outer_planets_refresh_run",
            return_value=True,
            create=True,
        ), mock.patch(
            "cosmic_engine.ts4_runtime_install.sync_active_household_outer_planets_only",
            create=True,
        ) as sync_mock:
            summary = ts4_runtime_install._maybe_run_outer_planets_household_refresh(
                reason="runtime_init"
            )
        self.assertEqual("already_refreshed", summary["reason"])
        sync_mock.assert_not_called()

    def test_runtime_hook_marks_household_only_after_success(self):
        with mock.patch(
            "cosmic_engine.ts4_runtime_install.is_outer_planets_addon_active",
            return_value=True,
            create=True,
        ), mock.patch(
            "cosmic_engine.ts4_runtime_install._iter_active_household_sim_infos",
            return_value=(object(), object()),
        ), mock.patch(
            "cosmic_engine.ts4_runtime_install._get_active_household_id",
            return_value=12345,
        ), mock.patch(
            "cosmic_engine.ts4_runtime_install.has_household_outer_planets_refresh_run",
            return_value=False,
            create=True,
        ), mock.patch(
            "cosmic_engine.ts4_runtime_install.sync_active_household_outer_planets_only",
            return_value={"ok": True, "reason": "refreshed", "sims_refreshed": 2},
            create=True,
        ), mock.patch(
            "cosmic_engine.ts4_runtime_install.mark_household_outer_planets_refresh_run",
            return_value=True,
            create=True,
        ) as mark_mock:
            summary = ts4_runtime_install._maybe_run_outer_planets_household_refresh(
                reason="runtime_init"
            )
        self.assertTrue(summary["ok"])
        self.assertEqual("refreshed", summary["reason"])
        mark_mock.assert_called_once()

    def test_runtime_hook_does_not_mark_household_after_failed_sync(self):
        with mock.patch(
            "cosmic_engine.ts4_runtime_install.is_outer_planets_addon_active",
            return_value=True,
            create=True,
        ), mock.patch(
            "cosmic_engine.ts4_runtime_install._iter_active_household_sim_infos",
            return_value=(object(),),
        ), mock.patch(
            "cosmic_engine.ts4_runtime_install._get_active_household_id",
            return_value=12345,
        ), mock.patch(
            "cosmic_engine.ts4_runtime_install.has_household_outer_planets_refresh_run",
            return_value=False,
            create=True,
        ), mock.patch(
            "cosmic_engine.ts4_runtime_install.sync_active_household_outer_planets_only",
            side_effect=RuntimeError("boom"),
            create=True,
        ), mock.patch(
            "cosmic_engine.ts4_runtime_install.mark_household_outer_planets_refresh_run",
            create=True,
        ) as mark_mock:
            summary = ts4_runtime_install._maybe_run_outer_planets_household_refresh(
                reason="runtime_init"
            )
        self.assertEqual("refresh_failed", summary["reason"])
        mark_mock.assert_not_called()


class OuterPlanetsLegacyScopeTests(unittest.TestCase):
    def test_runtime_hook_does_not_call_broad_legacy_v2_migration(self):
        sim_a = object()
        sim_b = object()
        with mock.patch(
            "cosmic_engine.ts4_runtime_install.is_outer_planets_addon_active",
            return_value=True,
            create=True,
        ), mock.patch(
            "cosmic_engine.ts4_runtime_install._get_active_household_id",
            return_value=12345,
        ), mock.patch(
            "cosmic_engine.ts4_runtime_install.has_household_outer_planets_refresh_run",
            return_value=False,
            create=True,
        ), mock.patch(
            "cosmic_engine.ts4_runtime_install._iter_active_household_sim_infos",
            return_value=(sim_a, sim_b),
        ), mock.patch(
            "cosmic_engine.ts4_runtime_install.sync_active_household_outer_planets_only",
            return_value={"ok": True, "reason": "refreshed", "sims_refreshed": 2},
            create=True,
        ), mock.patch(
            "cosmic_engine.ts4_runtime_install.mark_household_outer_planets_refresh_run",
            return_value=True,
            create=True,
        ), mock.patch(
            "cosmic_engine.ts4_runtime_install.migrate_legacy_v2_household_for_sim_info",
            side_effect=AssertionError("broad migration should not run"),
            create=True,
        ):
            summary = ts4_runtime_install._maybe_run_outer_planets_household_refresh(
                reason="runtime_init"
            )
        self.assertTrue(summary["ok"])
        self.assertEqual("refreshed", summary["reason"])

    def test_runtime_hook_passes_only_active_household_sim_infos(self):
        sim_a = object()
        sim_b = object()
        with mock.patch(
            "cosmic_engine.ts4_runtime_install.is_outer_planets_addon_active",
            return_value=True,
            create=True,
        ), mock.patch(
            "cosmic_engine.ts4_runtime_install._get_active_household_id",
            return_value=12345,
        ), mock.patch(
            "cosmic_engine.ts4_runtime_install.has_household_outer_planets_refresh_run",
            return_value=False,
            create=True,
        ), mock.patch(
            "cosmic_engine.ts4_runtime_install._iter_active_household_sim_infos",
            return_value=(sim_a, sim_b),
        ), mock.patch(
            "cosmic_engine.ts4_runtime_install.sync_active_household_outer_planets_only",
            return_value={"ok": True, "reason": "refreshed", "sims_refreshed": 2},
            create=True,
        ) as sync_mock, mock.patch(
            "cosmic_engine.ts4_runtime_install.mark_household_outer_planets_refresh_run",
            return_value=True,
            create=True,
        ):
            summary = ts4_runtime_install._maybe_run_outer_planets_household_refresh(
                reason="runtime_init"
            )
        self.assertTrue(summary["ok"])
        self.assertEqual((sim_a, sim_b), sync_mock.call_args[1]["sim_infos"])


if __name__ == "__main__":
    unittest.main()
