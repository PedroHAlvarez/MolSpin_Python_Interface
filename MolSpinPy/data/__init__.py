"""Reading, converting and lazily accessing MolSpin result data."""

from .collection import (
    DataCollection,
    DataPoint,
    DataPointCollection,
    DataView,
    GroupView,
    Row,
)
from .reader import (
    combine_files,
    convert_dat_to_npz,
    convert_files,
    convert_series,
    read_dat,
    tail_line,
    write_npz,
)
from .remote import enroll_ssh_key, fetch_dat_as_npz
from .stats import ExponentiallyWeightedMovingAverage

__all__ = [
    "DataCollection",
    "DataPoint",
    "DataPointCollection",
    "DataView",
    "GroupView",
    "Row",
    "combine_files",
    "convert_dat_to_npz",
    "convert_files",
    "convert_series",
    "read_dat",
    "tail_line",
    "write_npz",
    "enroll_ssh_key",
    "fetch_dat_as_npz",
    "ExponentiallyWeightedMovingAverage",
]
