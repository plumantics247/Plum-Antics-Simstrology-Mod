import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
PYTHON_DIR = ROOT / "python"
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))


from cosmic_engine import house_ingress_notifications, loot_actions, planet_house_markers


class _FakeTrait(object):
    def __init__(self, name):
        self.name = str(name)


class _FakeTransitService(object):
    def __init__(self, chart, body_names):
        self._chart = dict(chart)
        self._body_names = tuple(body_names)

    def chart_for_house_sign_map(self, house_sign_map):
        return dict(self._chart)

    def active_body_names(self):
        return tuple(self._body_names)


class OuterPlanetsHouseRuntimeTests(unittest.TestCase):
    def test_hidden_marker_name_parser_accepts_outer_body(self):
        parsed = planet_house_markers._parse_planet_house_marker_name(
            "PlumAntics_CosmicEngineHouses_EighthHouse_PlutoHidden"
        )
        self.assertEqual(("Pluto", 7), parsed)

    def test_visible_marker_name_parser_accepts_outer_body(self):
        parsed = planet_house_markers._parse_planet_house_reward_marker_name(
            "PlumAntics_CosmicEngineHouses_TenthHouse_ChironTransitMarker"
        )
        self.assertEqual(("Chiron", 9), parsed)

    def test_extract_transit_marker_rows_includes_outer_bodies(self):
        traits = (
            _FakeTrait("PlumAntics_CosmicEngineHouses_FirstHouse_UranusTransitMarker"),
            _FakeTrait("PlumAntics_CosmicEngineHouses_FourthHouse_PlutoTransitMarker"),
            _FakeTrait("PlumAntics_CosmicEngineHouses_TenthHouse_ChironTransitMarker"),
        )
        self.assertEqual(
            [
                "Uranus (1st House)",
                "Pluto (4th House)",
                "Chiron (10th House)",
            ],
            loot_actions._extract_transit_marker_rows(traits),
        )

    def test_desired_marker_traits_for_sim_uses_activation_aware_body_roster(self):
        available = {
            ("Sun", 0): "sun-marker",
            ("Pluto", 3): "pluto-marker",
            ("Chiron", 9): "chiron-marker",
        }
        chart = {
            "Sun": {"house_index": 0},
            "Pluto": {"house_index": 3},
            "Chiron": {"house_index": 9},
        }
        service = _FakeTransitService(chart, ("Sun", "Pluto", "Chiron"))

        resolved = planet_house_markers._desired_marker_traits_for_sim(
            service,
            house_sign_map={index: index for index in range(12)},
            available_by_body_house=available,
        )

        self.assertEqual(
            {
                "Sun": "sun-marker",
                "Pluto": "pluto-marker",
                "Chiron": "chiron-marker",
            },
            resolved,
        )

    def test_ingress_notification_body_names_use_service_active_roster(self):
        service = _FakeTransitService({}, ("Moon", "Pluto", "Chiron"))
        self.assertEqual(
            ("Moon", "Pluto", "Chiron"),
            house_ingress_notifications._ingress_body_names(service),
        )

    def test_notice_icon_mapping_covers_outer_bodies_with_shared_pluto_chiron(self):
        mapping = planet_house_markers._PLANET_NOTICE_ICON_INSTANCE_BY_BODY

        self.assertEqual(0xA8F7344C2D7B91E1, mapping["Uranus"])
        self.assertEqual(0xB61C9D4F7AE20358, mapping["Neptune"])
        self.assertEqual(0xC4E8A91B5FD07236, mapping["Pluto"])
        self.assertEqual(0xC4E8A91B5FD07236, mapping["Chiron"])


if __name__ == "__main__":
    unittest.main()
