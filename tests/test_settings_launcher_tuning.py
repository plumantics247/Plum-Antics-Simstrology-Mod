import pathlib
import sys
from types import SimpleNamespace
import unittest
import xml.etree.ElementTree as ET


ROOT = pathlib.Path(__file__).resolve().parents[1]
PYTHON_DIR = ROOT / "python"
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))

CORE_INTERACTION_DIR = ROOT / "src" / "core" / "Interaction"
COMPAT_INTERACTION_DIR = ROOT / "src" / "SignCompatibility" / "Interaction"
LAUNCHER_PATHS = (
    CORE_INTERACTION_DIR / "PlumAntics_CosmicEngineCore_SettingsLauncher.xml",
    COMPAT_INTERACTION_DIR / "PlumAntics_CosmicEngineCore_SettingsLauncher_Compatibility.xml",
    CORE_INTERACTION_DIR / "PlumAntics_CosmicEngineCore_SettingsLauncher_Retrogrades.xml",
)


class SettingsLauncherTuningTests(unittest.TestCase):
    def test_launchers_use_custom_settings_picker_class_and_choices(self):
        failures = []
        for path in LAUNCHER_PATHS:
            root = ET.parse(path).getroot()
            picker_class = root.attrib.get("c")
            picker_module = root.attrib.get("m")
            has_choices = root.find("L[@n='choices']") is not None
            has_possible_actions = root.find("L[@n='possible_actions_']") is not None
            if (
                picker_class != "CosmicEngineSettingsPickerInteraction"
                or picker_module != "cosmic_engine.settings_picker"
                or not has_choices
                or has_possible_actions
            ):
                failures.append(
                    "{0}: c={1} m={2} choices={3} possible_actions_={4}".format(
                        path.name,
                        picker_class,
                        picker_module,
                        has_choices,
                        has_possible_actions,
                    )
                )
        self.assertFalse(
            failures,
            "Settings launchers must use the custom settings picker class and tune rows under choices. "
            + "; ".join(failures),
        )

    def test_launchers_match_self_interaction_object_target_shell(self):
        failures = []
        for path in LAUNCHER_PATHS:
            root = ET.parse(path).getroot()
            target_type = root.findtext("E[@n='target_type']")
            has_test_globals = root.find("L[@n='test_globals']") is not None
            has_tests = root.find("L[@n='tests']") is not None
            if target_type != "OBJECT" or not has_test_globals or has_tests:
                failures.append(
                    "{0}: target_type={1} test_globals={2} tests={3}".format(
                        path.name,
                        target_type,
                        has_test_globals,
                        has_tests,
                    )
                )
        self.assertFalse(
            failures,
            "Settings launcher pickers must use OBJECT + test_globals shell "
            "to match working self interactions. " + "; ".join(failures),
        )

    def test_settings_picker_module_imports_outside_game_runtime(self):
        from cosmic_engine import settings_picker

        self.assertTrue(
            hasattr(settings_picker, "CosmicEngineSettingsPickerInteraction")
        )

    def test_settings_picker_materializes_row_text_from_factories(self):
        from cosmic_engine.settings_picker import CosmicEngineSettingsPickerInteraction

        choice = SimpleNamespace(
            item_name=lambda: "Compatibility",
            item_description=lambda: "Compatibility options",
            item_tooltip=lambda: "Open compatibility settings",
            continuation=None,
        )

        original_choices = getattr(CosmicEngineSettingsPickerInteraction, "choices", None)
        CosmicEngineSettingsPickerInteraction.choices = (choice,)
        try:
            rows = list(
                CosmicEngineSettingsPickerInteraction.picker_rows_gen(
                    CosmicEngineSettingsPickerInteraction,
                    None,
                    None,
                    None,
                )
            )
        finally:
            CosmicEngineSettingsPickerInteraction.choices = original_choices

        self.assertEqual(1, len(rows))
        row = rows[0]
        self.assertEqual("Compatibility", row.name)
        self.assertEqual("Compatibility options", row.row_description)
        self.assertTrue(callable(row.row_tooltip))
        self.assertEqual("Open compatibility settings", row.row_tooltip())


if __name__ == "__main__":
    unittest.main()
