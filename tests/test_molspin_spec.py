import tempfile
import unittest
from pathlib import Path
from unittest import mock

from MolSpinPy.utility import molspin_spec
from MolSpinPy.utility.molspin_spec import MolSpinSpecBuilder, SpecSheet, find_source_root, BUNDLED_SPEC

SOURCE = find_source_root()


class BundledSpecTests(unittest.TestCase):
    def test_fallback_is_unverified_when_no_source(self):
        with mock.patch.object(molspin_spec, "find_source_root", return_value=None):
            sheet = MolSpinSpecBuilder.build()
        self.assertFalse(sheet.verified)
        self.assertEqual(set(sheet.tasks), {"HSGeneral", "SSGeneral", "MultiSSGeneral"})
        self.assertIn("totaltime", sheet.get("ss-general").properties)

    def test_json_round_trip(self):
        sheet = SpecSheet.from_json(BUNDLED_SPEC)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "spec.json"
            sheet.to_json(path)
            again = SpecSheet.from_json(path)
        self.assertEqual(sheet.to_dict(), again.to_dict())

    def test_typed_dicts_are_importable(self):
        sheet = SpecSheet.from_json(BUNDLED_SPEC)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "props.py"
            sheet.write_typed_dicts(path)
            namespace = {}
            exec(compile(path.read_text(encoding="utf-8"), str(path), "exec"), namespace)
        self.assertIn("totaltime", namespace["HSGeneralProperties"].__annotations__)


@unittest.skipIf(SOURCE is None, "MolSpin source tree not available")
class SourceScanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sheet = MolSpinSpecBuilder(SOURCE).build_sheet()

    def test_verified_and_tasks_found(self):
        self.assertTrue(self.sheet.verified)
        self.assertIs(self.sheet.get("hs-general"), self.sheet.tasks["HSGeneral"])
        self.assertIs(self.sheet.get("MultiSS-General"), self.sheet.tasks["MultiSSGeneral"])

    def test_properties_types_defaults_aliases(self):
        hs = self.sheet.tasks["HSGeneral"]
        self.assertEqual(hs.properties["totaltime"].value_type, "float")
        self.assertEqual(hs.properties["totaltime"].default, 10000.0)
        self.assertEqual(hs.properties["krylovsize"].value_type, "int")
        self.assertEqual(hs.properties["spinlist"].value_type, "list")
        self.assertEqual(hs.resolve_alias("time_dependence"), "dynamics")
        self.assertEqual(hs.properties["dynamics"].default, "static")
        self.assertEqual(hs.properties["sampling"].choices, ["direct", "stochastic"])

    def test_task_folders_do_not_leak_other_objects(self):
        self.assertNotIn("tau_c", self.sheet.tasks["SSGeneral"].properties)

    def test_constraints(self):
        hs = self.sheet.tasks["HSGeneral"]
        self.assertIn("powderfullsphere", hs.conflicts_of("powderdomain"))
        self.assertIn("powdersamplingpoints", hs.requires_of("powdergrid"))
        self.assertIn("calculation", hs.requires_of("observables"))


class TaskIntegrationTests(unittest.TestCase):
    def test_task_exposes_spec(self):
        from MolSpinPy.objects import Task
        task = Task("t", "HSGeneral", totaltime=5, time_dependence="static", bogus=1)
        self.assertEqual(task.spec.type, "HSGeneral")
        self.assertEqual(task.unknown_properties(), ["bogus"])
        self.assertEqual(task.property_spec("powder").name, "powderaveraging")
        self.assertIn("totaltime", task.allowed_properties())
        self.assertEqual(task.ConvertToDictionary()[1]["totaltime"], 5)

    def test_unknown_type_has_no_spec(self):
        from MolSpinPy.objects import Task
        task = Task("TE", type="x")
        self.assertIsNone(task.spec)
        self.assertEqual(task.allowed_properties(), [])
        self.assertEqual(task.unknown_properties(), [])


if __name__ == "__main__":
    unittest.main()
