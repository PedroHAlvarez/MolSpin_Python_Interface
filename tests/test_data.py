import os
import tempfile
import unittest

import numpy as np

from MolSpinPy import data


def write_dat(path, steps, rows_per_step, offset=0.0):
    with open(path, "w") as handle:
        handle.write("Step Time(ns) Value Name\n")
        for step in range(1, steps + 1):
            for row in range(rows_per_step):
                handle.write(f"{step} {row} {step * 10 + row + offset} n{step}\n")
            handle.write("\n")


class DataModuleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.paths = []
        for i in range(3):
            dat = os.path.join(self.tmp.name, f"run-{i}.dat")
            write_dat(dat, steps=11, rows_per_step=4, offset=i * 1000)
            self.paths.append(data.convert_dat_to_npz(dat, silent=True))

    def collection(self):
        return data.DataCollection(self.paths)

    def test_convert_keeps_all_rows(self):
        with np.load(self.paths[0], allow_pickle=True) as npz:
            self.assertEqual(len(npz["_group_map"]), 44)
            self.assertEqual(npz["Time(ns)"].dtype.kind, "f")
            self.assertEqual(npz["Name"].dtype.kind, "U")

    def test_structure(self):
        c = self.collection()
        self.assertEqual(c.n_files, 3)
        self.assertEqual(c.n_rows, 132)
        self.assertEqual(c.keys, ["Time(ns)", "Value", "Name"])
        self.assertEqual(c.n_groups, 33)
        self.assertEqual(c.groups[:3], ["f0_g1", "f0_g2", "f0_g3"])
        self.assertEqual(len(c.group_indices("f1_g1")), 4)

    def test_group_and_column_access(self):
        c = self.collection()
        self.assertEqual(list(c[1]["Value"]), [20, 21, 22, 23])
        self.assertEqual(c[0][2].Value, 12)
        self.assertEqual(c[11]["Value"][0], 1010)
        self.assertEqual(c.column("Value", [0, 44])[1], 1010)
        with self.assertRaises(KeyError):
            c[0]["nope"]
        with self.assertRaises(IndexError):
            c.column("Value", [10**6])

    def test_slicing(self):
        c = self.collection()
        sub = c[2:5]
        self.assertEqual(len(sub), 3)
        self.assertEqual(sub.groups, ["f0_g3", "f0_g4", "f0_g5"])
        rows = c[1:3, 1:3]
        self.assertEqual(len(rows), 2)
        self.assertEqual(list(rows[0]["Time(ns)"]), [1, 2])
        single = c[0:1][0:1]
        self.assertEqual(len(single), 1)

    def test_streaming_matches_legacy_names(self):
        c = self.collection()
        seen = list(c._unique_groups)
        while c.load_next_file_routing():
            seen = list(c._unique_groups)
        self.assertEqual(len(seen), 33)
        idx = c._index_map[seen[-1]]
        self.assertEqual(c._get_data_from_global_idx("Value", idx)[0], 2110)
        self.assertEqual(len(c.active_indices), 132)
        self.assertEqual(c.data["Value"][idx][0], 2110)

    def test_unload_and_pickle(self):
        import pickle

        c = self.collection()
        c.load_all()
        c.unload_file(1)
        self.assertEqual(len(c.loaded_groups), 22)
        c2 = pickle.loads(pickle.dumps(c[0:5]))
        self.assertEqual(list(c2[0]["Value"]), [10, 11, 12, 13])

    def test_cache_eviction(self):
        c = data.DataCollection(self.paths, max_open_files=1, max_cache_bytes=1)
        self.assertEqual(c.column("Value", [0, 44, 88])[2], 2010)

    def test_combine_and_tail(self):
        dat = [p[:-4] for p in self.paths]
        out = data.combine_files(dat, os.path.join(self.tmp.name, "all"), silent=True)
        c = data.DataCollection(out)
        self.assertEqual(c.n_rows, 132)
        self.assertEqual(c.n_groups, 33)
        self.assertTrue(data.tail_line(dat[0]).startswith("11 3"))

    def test_ewma(self):
        e = data.ExponentiallyWeightedMovingAverage(1.0)
        self.assertEqual(e.update(5.0, 1.0)[1], 5.0)
        std, mean, _, _ = e.update(7.0, 1.0)
        self.assertGreater(std, 0)
        self.assertGreater(mean, 5.0)


if __name__ == "__main__":
    unittest.main()
