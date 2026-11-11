"""Reading MolSpin ``.dat`` output and converting it to ``.npz`` column files.

A MolSpin ``.dat`` file is whitespace separated text whose first line holds the
column names. The first column (``Step`` for time evolutions) labels the group a
row belongs to. It is stored as ``_group_map``; every other column is stored under
its own name, as ``float`` when it parses as numbers and as strings otherwise.
"""

import io
import mmap
import os
import sys
import time

import numpy as np

GROUP_MAP_KEY = "_group_map"


def resolve_path(path):
    return os.path.abspath(os.path.expanduser(os.fspath(path)))


def _dat_path(name):
    """Accept ``run-TE-0`` as well as ``run-TE-0.dat``."""
    path = resolve_path(name)
    if os.path.exists(path) or path.endswith(".dat"):
        return path
    return path + ".dat"


class _Progress:
    def __init__(self, label, total, silent):
        self.label = label
        self.total = max(total, 1)
        self.silent = silent
        self._last_bytes = 0
        self._last_time = time.time()
        self._speed = 0.0

    def update(self, current):
        if self.silent:
            return
        now = time.time()
        elapsed = now - self._last_time
        if elapsed < 0.5:
            return
        self._speed = ((current - self._last_bytes) / 1024**2) / elapsed
        self._last_bytes = current
        self._last_time = now
        percent = current / self.total * 100
        sys.stdout.write(f"\r{self.label}: {percent:5.1f}% | Speed: {self._speed:6.2f} MB/s")
        sys.stdout.flush()


def read_dat(source, silent=False):
    """Parse a ``.dat`` file or an in-memory ``io.BytesIO`` buffer.

    Returns ``(header, rows)``: the column names and a list of rows of strings.
    Blank lines are skipped.
    """
    if isinstance(source, io.BytesIO):
        lines = [raw.decode("utf-8").split() for raw in source]
    else:
        path = resolve_path(source)
        lines = []
        if os.path.getsize(path) == 0:
            return [], []
        with open(path, "rb") as handle:
            with mmap.mmap(handle.fileno(), length=0, access=mmap.ACCESS_READ) as mm:
                progress = _Progress("Parsing Data", mm.size(), silent)
                for raw in iter(mm.readline, b""):
                    lines.append(raw.decode("utf-8").split())
                    if len(lines) % 1000 == 0:
                        progress.update(mm.tell())
        if not silent:
            print()
    lines = [line for line in lines if line]
    if not lines:
        return [], []
    return lines[0], lines[1:]


def write_npz(header, rows, destination, silent=False):
    """Write parsed ``.dat`` content as ``.npz``; returns the path actually written."""
    if len(rows) == 0:
        raise ValueError("No data rows to write.")
    table = np.array(rows)
    columns = {GROUP_MAP_KEY: table[:, 0]}
    for i, name in enumerate(header):
        if not silent:
            filled = 20 * (i + 1) // len(header)
            bar = "█" * filled + "-" * (20 - filled)
            sys.stdout.write(f"\rSaving Data: |{bar}| {int((i + 1) / len(header) * 100)}% ({name[:15]})")
            sys.stdout.flush()
        if i == 0:
            continue
        column = table[:, i]
        try:
            columns[name] = column.astype(float)
        except ValueError:
            columns[name] = column
    destination = os.fspath(destination)
    np.savez(destination, **columns)
    written = destination if destination.endswith(".npz") else destination + ".npz"
    if not silent:
        print(f"\nSaved {written} to .npz file")
    return written


def convert_dat_to_npz(source, destination=None, silent=False):
    """Convert one ``.dat`` file to ``.npz``.

    ``destination`` may be a ``.npz`` path, a directory (the file name is kept and
    ``.npz`` appended, matching what ``Project`` produces) or ``None`` (written next
    to the source). Returns the written path, or ``None`` if the file is empty.
    """
    source = _dat_path(source)
    if destination is None:
        destination = source
    destination = resolve_path(destination)
    if os.path.isdir(destination):
        destination = os.path.join(destination, os.path.basename(source))
    if not silent:
        print(f"Processing file: {source}")
    header, rows = read_dat(source, silent=silent)
    if not rows:
        print(f"Warning: File {source} is empty or could not be read.")
        return None
    return write_npz(header, rows, destination, silent=silent)


def convert_files(filenames, new_filenames=None, silent=False):
    """Convert several ``.dat`` files; returns the list of written paths."""
    if isinstance(filenames, (str, os.PathLike)):
        filenames = [filenames]
    if new_filenames is None:
        new_filenames = [None] * len(filenames)
    elif isinstance(new_filenames, (str, os.PathLike)):
        new_filenames = [new_filenames]
    if len(new_filenames) != len(filenames):
        raise ValueError("filenames and new_filenames must have the same length.")
    written = []
    for name, new_name in zip(filenames, new_filenames):
        path = convert_dat_to_npz(name, new_name or None, silent=silent)
        if path:
            written.append(path)
    return written


def convert_series(base_file, start, stop, new_base_filename="", base_path="", silent=False):
    """Convert ``<base_file>-<i>.dat`` for ``i`` in ``start..stop`` (inclusive).

    Outputs go to ``<new_base>/<new_base>-<i>.npz`` (``new_base`` defaults to
    ``base_file``); the directory is created.
    """
    target = new_base_filename or base_file
    os.makedirs(target, exist_ok=True)
    source_base = os.path.join(base_path, base_file) if base_path else base_file
    filenames = [f"{source_base}-{i}" for i in range(start, stop + 1)]
    new_filenames = [f"{target}/{target}-{i}" for i in range(start, stop + 1)]
    return convert_files(filenames, new_filenames, silent=silent)


def combine_files(filenames, destination, silent=False):
    """Merge several ``.dat`` files into one ``.npz``.

    Group labels get an ``_f<file number>`` suffix so groups from different files
    stay distinct. The files must share the same columns as the first one.
    Returns the written path, or ``None`` if nothing could be read.
    """
    if isinstance(filenames, (str, os.PathLike)):
        filenames = [filenames]
    header = None
    blocks = []
    labels = []
    for i, name in enumerate(filenames):
        path = _dat_path(name)
        file_header, rows = read_dat(path, silent=silent)
        if not rows:
            print(f"Warning: File {path} is empty or could not be read.")
            continue
        if header is None:
            header = file_header
        elif len(file_header) != len(header):
            raise ValueError(f"{path} has {len(file_header)} columns, expected {len(header)}.")
        block = np.array(rows)
        labels.extend(f"{label}_f{i}" for label in block[:, 0])
        blocks.append(block)
    if header is None:
        print("Error: No valid data rows were found in the files.")
        return None
    combined = np.vstack([block.astype(object) for block in blocks])
    combined[:, 0] = labels
    return write_npz(header, combined.astype(str), destination, silent=silent)


def tail_line(path, block_size=4096):
    """Last non-empty line of a text file, or ``None`` if it cannot be read."""
    try:
        with open(resolve_path(path), "rb") as handle:
            handle.seek(0, os.SEEK_END)
            position = handle.tell()
            data = b""
            while position > 0:
                step = min(block_size, position)
                position -= step
                handle.seek(position)
                data = handle.read(step) + data
                stripped = data.rstrip()
                if b"\n" in stripped:
                    return stripped.rsplit(b"\n", 1)[1].decode("utf-8").strip()
            return data.decode("utf-8").strip()
    except OSError:
        return None
