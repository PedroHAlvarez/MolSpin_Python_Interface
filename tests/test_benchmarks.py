import unittest
from unittest.mock import Mock, patch

from MolSpinPy.benchmarks import (
    Cryptochrome4Benchmark,
    SystemVariant,
)


class BenchmarkTests(unittest.TestCase):
    def test_grid_for_each_variant(self):
        variants = [
            SystemVariant("small", {"spinsystems": {}}, 4),
            SystemVariant("large", {"spinsystems": {}}, 24),
        ]
        benchmark = Cryptochrome4Benchmark(variants, name="example")
        cases = list(benchmark.iter_cases())

        self.assertEqual(len(cases), 2 * 1352)
        self.assertEqual(benchmark.variants, tuple(variants))
        self.assertEqual(len(benchmark.parameter_sweep), 1352)
        for variant in benchmark.variants:
            points = [case.parameters for case in cases if case.variant is variant]
            self.assertEqual(len(points), 1352)
            self.assertEqual(len({
                (point.k_s_exponent, point.k_i_exponent, point.r_std, point.field)
                for point in points
            }), 1352)
            self.assertEqual({point.r_std for point in points}, {0, 0.01, 0.1, 1})
            self.assertEqual({point.field for point in points}, {
                (0, 0, 0), (0, 0, 0.1),
            })
            self.assertTrue(all(point.initial_state == "S" and point.samples == 12
                                for point in points))
        self.assertEqual(cases[0].parameters.k_s, 0.001)
        self.assertEqual(cases[0].parameters.k_i, 0.001)
        self.assertEqual(cases[1351].parameters.k_s, 1)
        self.assertEqual(cases[1351].parameters.k_i, 1)
        self.assertEqual(cases, list(benchmark.iter_cases()))

    def test_models_are_copied(self):
        original = {"spinsystems": {"example": {"value": 1}}}
        variant = SystemVariant("small", original)
        original["spinsystems"]["example"]["value"] = 2
        model = variant.copy_model()
        model["spinsystems"]["example"]["value"] = 3
        self.assertEqual(variant.copy_model()["spinsystems"]["example"]["value"], 1)

    def test_system_owns_configured_sweep_and_models(self):
        variant = SystemVariant("small", {"spinsystems": {"small": {}}}, 4)
        benchmark = Cryptochrome4Benchmark(
            [variant],
            samples=32,
            exponents=[6, 9],
            dephasing_rates=[0.1],
            fields=[(0, 0, 1)],
            initial_state="T",
        )

        self.assertIs(benchmark.variants[0], variant)
        self.assertEqual(len(benchmark.parameter_sweep), 4)
        self.assertEqual(
            benchmark.parameter_sweep,
            tuple(benchmark.iter_parameters()),
        )
        self.assertTrue(all(
            point.samples == 32
            and point.initial_state == "T"
            and point.field == (0, 0, 1)
            for point in benchmark.parameter_sweep
        ))

    def test_stochastic_task_setup_and_parameter_bindings_are_owned_by_system(self):
        variant = SystemVariant(
            "small",
            {
                "spinsystems": {
                    "MagLOV": {
                        "transitions": {},
                        "operators": {},
                        "interactions": {},
                        "properties": {},
                    }
                }
            },
            4,
        )
        benchmark = Cryptochrome4Benchmark(
            [variant],
            samples=16,
            exponents=[6],
            dephasing_rates=[0.1],
            fields=[(0, 0, 0.1)],
        )

        model = benchmark.prepare_model(variant)
        self.assertNotIn("tasks", variant.model)
        self.assertEqual(model["tasks"]["TE"]["type"], "HSGeneral")
        self.assertEqual(model["tasks"]["TE"]["sampling"], "stochastic")
        self.assertEqual(model["tasks"]["TE"]["montecarlosamples"], 16)
        bindings = benchmark.parameter_bindings(variant)
        self.assertEqual(
            bindings["spinsystems.MagLOV.transitions.s_sdd.rate"], (0.001,)
        )
        self.assertEqual(
            bindings["spinsystems.MagLOV.interactions.zeeman.field"],
            ([0.0, 0.0, 0.1],),
        )

    def test_deploy_local_dispatches_one_project_per_variant(self):
        variant = SystemVariant("small", {})
        benchmark = Cryptochrome4Benchmark(
            [variant], exponents=[6], dephasing_rates=[0], fields=[(0, 0, 0)]
        )
        project = Mock()
        project.Deploy.return_value = ["output"]

        with patch.object(benchmark, "create_projects", return_value=iter([project])):
            deployments = benchmark.deploy_local(NPZ=True)

        project.Deploy.assert_called_once_with(steps=1, NPZ=True)
        self.assertEqual(deployments[0].variant, variant)
        self.assertEqual(deployments[0].result, ["output"])

    def test_deploy_hpc_uses_connection_and_submission_configuration(self):
        variant = SystemVariant("small", {})
        benchmark = Cryptochrome4Benchmark(
            [variant], exponents=[6], dephasing_rates=[0], fields=[(0, 0, 0)]
        )
        project = Mock()
        project.SubmitToHPC.return_value = ["1234"]
        connection = {
            "hpc_username": "user",
            "hpc_host": "cluster",
            "hpc_key_path": "~/.ssh/key",
            "remote_binary_path": "/opt/molspin",
            "remote_working_dir": "/work/user",
        }

        with patch.object(benchmark, "create_projects", return_value=iter([project])):
            deployments = benchmark.deploy("hpc", **connection)

        project.LoadHPC.assert_called_once_with(
            hpc_username="user",
            hpc_host="cluster",
            hpc_key_path="~/.ssh/key",
            remote_working_dir="/work/user",
            cluster_profile="gwdg",
            proxy_host=None,
        )
        project.SubmitToHPC.assert_called_once_with(
            hpc_username="user",
            hpc_host="cluster",
            hpc_key_path="~/.ssh/key",
            remote_working_dir="/work/user",
            remote_binary_path="/opt/molspin",
            steps=1,
        )
        self.assertEqual(deployments[0].result, ["1234"])

    def test_invalid_inputs_are_rejected(self):
        variant = SystemVariant("small", {})
        with self.assertRaises(ValueError):
            SystemVariant("small", {}, 0)
        with self.assertRaises(ValueError):
            Cryptochrome4Benchmark([])
        with self.assertRaises(ValueError):
            Cryptochrome4Benchmark([variant, variant])
        with self.assertRaises(ValueError):
            Cryptochrome4Benchmark([variant], 0)
        with self.assertRaises(ValueError):
            Cryptochrome4Benchmark([variant], fields=[])
        with self.assertRaises(ValueError):
            Cryptochrome4Benchmark([variant], exponents=[])
        with self.assertRaises(ValueError):
            Cryptochrome4Benchmark([variant], fields=[(0, 1)])
        with self.assertRaises(ValueError):
            Cryptochrome4Benchmark([variant]).deploy("unknown")
        with self.assertRaises(ValueError):
            Cryptochrome4Benchmark([variant]).deploy("hpc")
