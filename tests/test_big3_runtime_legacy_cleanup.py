import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
PYTHON_DIR = ROOT / "python"
SRC_DIR = ROOT / "src"
if ROOT.parent.name == ".worktrees":
    WORKSPACE_ROOT = ROOT.parents[2]
else:
    WORKSPACE_ROOT = ROOT.parent

BIG3_LOOT_ACTIONS = PYTHON_DIR / "plumantics_big3_runtime" / "loot_actions.py"
BIG3_INTERACTIONS = PYTHON_DIR / "plumantics_big3_runtime" / "integration" / "interactions.py"
BIG3_CONFIG_IO = PYTHON_DIR / "plumantics_big3_runtime" / "config_io.py"
BOOTSTRAP = PYTHON_DIR / "cosmic_engine" / "bootstrap.py"
RUNTIME_HOOKS = PYTHON_DIR / "cosmic_engine" / "runtime_hooks.py"
CHILDHOOD_CHILD_AUTO_ASSIGN_XML = (
    WORKSPACE_ROOT
    / "PlumAntics Simstrology Childhood"
    / "src"
    / "Action"
    / "PlumAntics_Big3ModCore_ChildAutoAssignPythonLoot.xml"
)

REMOVED_RUNTIME_MARKERS = (
    (BIG3_INTERACTIONS, "class Big3UniverseDispatcherImmediate"),
    (BIG3_INTERACTIONS, "class Big3UniverseAssignBig3Immediate"),
    (BIG3_CONFIG_IO, "def load_json(path):"),
    (BIG3_CONFIG_IO, "def resolve_testbed_root(start_path):"),
)

RETAINED_RUNTIME_MARKERS = (
    (BIG3_LOOT_ACTIONS, "class Big3ChildAutoAssignPythonLoot"),
    (BIG3_LOOT_ACTIONS, "class Big3CaptureChartPythonLoot"),
    (BIG3_LOOT_ACTIONS, "class Big3EnsureLaneOverlaysPythonLoot"),
    (BIG3_LOOT_ACTIONS, "class Big3SetModeLockPythonLoot"),
    (BIG3_INTERACTIONS, "class Big3UniverseAssignSunImmediate"),
    (BIG3_INTERACTIONS, "class Big3UniverseAssignMoonImmediate"),
    (BIG3_INTERACTIONS, "class Big3UniverseAssignRisingImmediate"),
)

LIVE_XML_MARKERS = (
    "PlumAntics_Big3ModCore_CaptureChartPythonLoot",
    "PlumAntics_Big3ModCore_EnsureBig3OverlaysPythonLoot",
    "PlumAntics_Big3ModCore_SetModeBig3PythonLoot",
)


class Big3RuntimeLegacyCleanupTests(unittest.TestCase):
    def test_dead_big3_runtime_helpers_are_removed(self):
        for path, marker in REMOVED_RUNTIME_MARKERS:
            text = path.read_text(encoding="utf-8")
            self.assertNotIn(
                marker,
                text,
                msg="Expected dead legacy Big3 runtime surface to be removed: {0}".format(marker),
            )

    def test_live_big3_runtime_entrypoints_remain_present(self):
        for path, marker in RETAINED_RUNTIME_MARKERS:
            text = path.read_text(encoding="utf-8")
            self.assertIn(
                marker,
                text,
                msg="Expected still-wired Big3 runtime entrypoint to remain present: {0}".format(marker),
            )

    def test_childhood_addon_still_has_a_live_python_bridge_for_child_auto_assign(self):
        self.assertTrue(
            CHILDHOOD_CHILD_AUTO_ASSIGN_XML.exists(),
            msg="Expected the Childhood add-on child auto-assign tuning to exist in the sibling workspace.",
        )
        text = CHILDHOOD_CHILD_AUTO_ASSIGN_XML.read_text(encoding="utf-8")
        self.assertIn("Big3ChildAutoAssignPythonLoot", text)
        runtime_text = BIG3_LOOT_ACTIONS.read_text(encoding="utf-8")
        self.assertIn(
            "class Big3ChildAutoAssignPythonLoot",
            runtime_text,
            msg=(
                "The sibling Childhood add-on still references Big3ChildAutoAssignPythonLoot, "
                "so the runtime bridge class must remain present."
            ),
        )

    def test_live_src_tuning_still_points_at_retained_big3_runtime_loot_surfaces(self):
        hits = set()
        for path in SRC_DIR.rglob("*.xml"):
            text = path.read_text(encoding="utf-8")
            for marker in LIVE_XML_MARKERS:
                if marker in text:
                    hits.add(marker)

        self.assertEqual(
            set(LIVE_XML_MARKERS),
            hits,
            msg="Expected src XML to keep the retained Big3 runtime loot surfaces wired after cleanup.",
        )

    def test_bootstrap_household_onboarding_routes_through_runtime_bridge(self):
        runtime_text = RUNTIME_HOOKS.read_text(encoding="utf-8")
        bootstrap_text = BOOTSTRAP.read_text(encoding="utf-8")

        self.assertIn("def dispatch_household_onboard(", runtime_text)
        self.assertIn("dispatch_household_onboard(", bootstrap_text)


if __name__ == "__main__":
    unittest.main()
