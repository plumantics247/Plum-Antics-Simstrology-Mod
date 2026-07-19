import pathlib
import unittest
import xml.etree.ElementTree as ET


ROOT = pathlib.Path(__file__).resolve().parents[1]
SUBSCRIBER_PATH = (
    ROOT
    / "src"
    / "core"
    / "Action"
    / "PlumAntics_Big3ModCore_AstrologyRefreshContext_GeneralMoodsSubscriber.xml"
)


class GeneralMoodsRefreshSubscriberTests(unittest.TestCase):
    def test_refresh_subscriber_keeps_only_moon_migration_and_python_sync(self):
        root = ET.parse(SUBSCRIBER_PATH).getroot()
        action_ids = [
            action.findtext("T[@n='actions']")
            for action in root.findall("./L[@n='loot_actions']/V[@t='actions']")
        ]
        self.assertEqual(
            [
                "1833257501",
                "830000000000009103",
            ],
            action_ids,
            msg="GeneralMoods refresh subscriber should only keep the moon migration and Python sync actions.",
        )


if __name__ == "__main__":
    unittest.main()
