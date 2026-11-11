"""Lazy, multi-file access to MolSpin ``.npz`` result files.

``DataCollection`` presents one or many ``.npz`` files (see ``reader``) as a single
table whose rows are split into *groups* by the ``_group_map`` column (one group per
simulation step for time evolutions). Only the metadata needed is loaded: files are
grouped on demand and columns are read on demand into a size-bounded cache.

Rows are addressed by *global row index*: the position of a row in the
concatenation of all files, in the order the files were given.
"""

import re
import threading
import zipfile
from collections import OrderedDict
from multiprocessing import shared_memory

import numpy as np

from .reader import GROUP_MAP_KEY, resolve_path

DEFAULT_MAX_OPEN_FILES = 64
DEFAULT_MAX_CACHE_BYTES = 2 * 1024**3

_GROUP_KEY = re.compile(r"^f(\d+)_g(-?\d+)$")


def group_key(file_index, group_id):
    return f"f{file_index}_g{group_id}"


def _group_sort_key(key):
    file_index, group_id = _GROUP_KEY.match(key).groups()
    return int(file_index), int(group_id)


def _file_index_of(key):
    return _group_sort_key(key)[0]


def _count_rows(filename):
    """Row count of an ``.npz`` read from the ``_group_map`` array header only."""
    try:
        with zipfile.ZipFile(filename) as archive:
            with archive.open(GROUP_MAP_KEY + ".npy") as member:
                version = np.lib.format.read_magic(member)
                reader = (
                    np.lib.format.read_array_header_1_0
                    if version == (1, 0)
                    else np.lib.format.read_array_header_2_0
                )
                shape = reader(member)[0]
                return int(shape[0]) if shape else 1
    except (KeyError, ValueError, OSError, zipfile.BadZipFile):
        with np.load(filename, allow_pickle=True) as archive:
            return int(archive[GROUP_MAP_KEY].shape[0])


class _FileStore:
    """Shared file handles and column cache behind a collection and its slices."""

    def __init__(self, filenames, max_open_files, max_cache_bytes):
        self.filenames = [resolve_path(name) for name in filenames]
        self.max_open_files = max_open_files
        self.max_cache_bytes = max_cache_bytes
        self._lock = threading.RLock()
        self._handles = OrderedDict()
        self._columns = OrderedDict()
        self._cached_bytes = 0
        self.row_counts = [_count_rows(name) for name in self.filenames]
        self.offsets = np.concatenate([[0], np.cumsum(self.row_counts)]).astype(np.int64)
        self.keys = []
        if self.filenames:
            with np.load(self.filenames[0], allow_pickle=True) as first:
                self.keys = [k for k in first.files if k != GROUP_MAP_KEY]

    @property
    def total_rows(self):
        return int(self.offsets[-1])

    def _handle(self, file_index):
        handle = self._handles.get(file_index)
        if handle is not None:
            self._handles.move_to_end(file_index)
            return handle
        handle = np.load(self.filenames[file_index], allow_pickle=True)
        self._handles[file_index] = handle
        while len(self._handles) > self.max_open_files:
            _, old = self._handles.popitem(last=False)
            old.close()
        return handle

    def file_column(self, file_index, key):
        with self._lock:
            cache_key = (file_index, key)
            column = self._columns.get(cache_key)
            if column is not None:
                self._columns.move_to_end(cache_key)
                return column
            try:
                column = np.asarray(self._handle(file_index)[key])
            except KeyError:
                raise KeyError(f"Column '{key}' not found in {self.filenames[file_index]}") from None
            self._columns[cache_key] = column
            self._cached_bytes += column.nbytes
            while self._cached_bytes > self.max_cache_bytes and len(self._columns) > 1:
                _, old = self._columns.popitem(last=False)
                self._cached_bytes -= old.nbytes
            return column

    def read(self, key, indices):
        """Values of column ``key`` at global row ``indices`` (int or integer array)."""
        if isinstance(indices, (int, np.integer)):
            index = int(indices)
            if not 0 <= index < self.total_rows:
                raise IndexError(f"Row {index} out of range (0..{self.total_rows - 1}).")
            file_index = int(np.searchsorted(self.offsets, index, side="right")) - 1
            return self.file_column(file_index, key)[index - self.offsets[file_index]]

        indices = np.asarray(indices, dtype=np.int64)
        if indices.size == 0:
            return np.empty(0, dtype=self.file_column(0, key).dtype)
        if indices.min() < 0 or indices.max() >= self.total_rows:
            raise IndexError(f"Row index out of range (0..{self.total_rows - 1}).")
        files = np.searchsorted(self.offsets, indices, side="right") - 1
        first = files.min()
        if first == files.max():
            return self.file_column(int(first), key)[indices - self.offsets[first]]
        parts = []
        for file_index in np.unique(files):
            mask = files == file_index
            parts.append(
                (mask, self.file_column(int(file_index), key)[indices[mask] - self.offsets[file_index]])
            )
        result = np.empty(indices.shape, dtype=np.result_type(*[part.dtype for _, part in parts]))
        for mask, part in parts:
            result[mask] = part
        return result

    def file_groups(self, file_index):
        """``{group id: global row indices}`` for one file."""
        labels = self.file_column(file_index, GROUP_MAP_KEY)
        if labels.size == 0:
            return {}
        try:
            ids = labels.astype(np.int64)
        except (ValueError, TypeError):
            _, ids = np.unique(labels, return_inverse=True)
            ids = ids.reshape(-1)
        order = np.argsort(ids, kind="stable")
        sorted_ids = ids[order]
        bounds = np.flatnonzero(sorted_ids[1:] != sorted_ids[:-1]) + 1
        pieces = np.split(order + self.offsets[file_index], bounds)
        firsts = np.concatenate([[0], bounds])
        return {int(sorted_ids[start]): piece for start, piece in zip(firsts, pieces)}

    def drop_file(self, file_index):
        with self._lock:
            handle = self._handles.pop(file_index, None)
            if handle is not None:
                handle.close()
            for cache_key in [k for k in self._columns if k[0] == file_index]:
                self._cached_bytes -= self._columns.pop(cache_key).nbytes

    def close(self):
        with self._lock:
            for handle in self._handles.values():
                handle.close()
            self._handles.clear()
            self._columns.clear()
            self._cached_bytes = 0


class Row:
    """One row of a collection; columns are available by key or attribute."""

    __slots__ = ("_store", "index", "_keys")

    def __init__(self, store, index, keys=None):
        self._store = store
        self.index = int(index)
        self._keys = keys or []

    def __getitem__(self, key):
        return self._store.read(key, self.index)

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        try:
            return self._store.read(name, self.index)
        except KeyError:
            raise AttributeError(f"'Row' object has no data column or attribute '{name}'") from None

    def __repr__(self):
        try:
            values = {key: self._store.read(key, self.index) for key in self._keys}
            return f"Row(index={self.index}, data={values})"
        except Exception:
            return f"<Row {self.index}>"


class GroupView:
    """The rows of one group. ``view[key]`` is that column's values for the group."""

    __slots__ = ("_store", "keys", "indices")

    def __init__(self, store, keys, indices):
        self._store = store
        self.keys = keys
        self.indices = indices

    def __getitem__(self, key):
        if isinstance(key, str):
            if key not in self.keys:
                raise KeyError(f"Key '{key}' not found in group.")
            return self._store.read(key, self.indices)
        if isinstance(key, (int, np.integer)):
            try:
                return Row(self._store, self.indices[key], self.keys)
            except IndexError:
                raise IndexError(f"Index {key} out of range for group view.") from None
        if isinstance(key, slice):
            return [Row(self._store, index, self.keys) for index in self.indices[key]]
        raise KeyError(f"Key '{key}' not found in group.")

    def __len__(self):
        return len(self.indices)

    def __iter__(self):
        for index in self.indices:
            yield Row(self._store, index, self.keys)


class ColumnProxy:
    __slots__ = ("_collection", "key")

    def __init__(self, collection, key):
        self._collection = collection
        self.key = key

    def __getitem__(self, indices):
        if isinstance(indices, slice):
            indices = np.arange(*indices.indices(self._collection._store.total_rows))
        return self._collection.column(self.key, indices)

    def __len__(self):
        return self._collection.n_rows if self.key in self._collection.keys else 0


class DataProxy:
    """``collection.data[key][indices]`` access by global row index."""

    __slots__ = ("_collection",)

    def __init__(self, collection):
        self._collection = collection

    def __getitem__(self, key):
        return ColumnProxy(self._collection, key)

    def _get_data_from_global_idx(self, name, indices):
        return self._collection.column(name, indices)


class SharedColumn:
    """A column copied into shared memory so worker processes can read it without pickling."""

    __slots__ = ("name", "shape", "dtype")

    def __init__(self, name, shape, dtype):
        self.name = name
        self.shape = tuple(shape)
        self.dtype = dtype

    def read(self, indices=None):
        shm = shared_memory.SharedMemory(name=self.name)
        try:
            array = np.ndarray(self.shape, dtype=self.dtype, buffer=shm.buf)
            return array.copy() if indices is None else array[indices]
        finally:
            shm.close()

    def __getitem__(self, indices):
        return self.read(indices)

    def unlink(self):
        shm = shared_memory.SharedMemory(name=self.name)
        shm.close()
        shm.unlink()


class DataCollection:
    """Lazy view over one or more ``.npz`` result files, split into groups.

    ``collection[i]`` is a ``GroupView``; ``collection[a:b]`` and
    ``collection[group_selection, row_selection]`` return new collections sharing
    the same files. A collection holding a single group behaves as a flat table:
    ``len`` and slicing then refer to rows.
    """

    def __init__(
        self,
        filenames=None,
        max_open_files=DEFAULT_MAX_OPEN_FILES,
        max_cache_bytes=DEFAULT_MAX_CACHE_BYTES,
        _store=None,
        _groups=None,
    ):
        self._lock = threading.RLock()
        self._max_open_files = max_open_files
        self._max_cache_bytes = max_cache_bytes
        if _store is not None:
            self._store = _store
            self._derived = True
            self._groups = dict(_groups)
            self._order = sorted(self._groups, key=_group_sort_key)
            self._loaded = [True] * len(_store.filenames)
        else:
            if filenames is None:
                filenames = []
            elif isinstance(filenames, (str, bytes)) or hasattr(filenames, "__fspath__"):
                filenames = [filenames]
            self._store = _FileStore(list(filenames), max_open_files, max_cache_bytes)
            self._derived = False
            self._groups = {}
            self._order = []
            self._loaded = [False] * len(self._store.filenames)

    def _derive(self, groups):
        return DataCollection(
            _store=self._store,
            _groups=groups,
            max_open_files=self._max_open_files,
            max_cache_bytes=self._max_cache_bytes,
        )

    # --- structure -------------------------------------------------------

    @property
    def filenames(self):
        return list(self._store.filenames)

    @property
    def keys(self):
        return list(self._store.keys)

    @property
    def n_files(self):
        return len(self._store.filenames)

    @property
    def n_rows(self):
        if self._derived:
            return int(sum(len(idx) for idx in self._groups.values()))
        return self._store.total_rows

    @property
    def n_groups(self):
        self.load_all()
        return len(self._order)

    @property
    def groups(self):
        """All group ids in order (loads every file)."""
        self.load_all()
        return list(self._order)

    @property
    def loaded_groups(self):
        """Group ids discovered so far, without loading further files."""
        return list(self._order)

    @property
    def active_indices(self):
        """Global row indices of every row in this collection."""
        if not self._derived:
            return np.arange(self._store.total_rows, dtype=np.int64)
        self.load_all()
        if not self._order:
            return np.empty(0, dtype=np.int64)
        return np.concatenate([self._groups[key] for key in self._order])

    def group_indices(self, group):
        """Global row indices of a group, given its id or its position."""
        if isinstance(group, (int, np.integer)):
            group = self._order_at(int(group))
        return self._groups[group]

    # --- loading ---------------------------------------------------------

    def load_file(self, file_index):
        with self._lock:
            if self._loaded[file_index]:
                return
            found = self._store.file_groups(file_index)
            for group_id, indices in found.items():
                self._groups[group_key(file_index, group_id)] = indices
            self._order = sorted(self._groups, key=_group_sort_key)
            self._loaded[file_index] = True

    def load_next_file(self):
        """Load the next unloaded file's groups; ``False`` when nothing is left."""
        with self._lock:
            for file_index, done in enumerate(self._loaded):
                if not done:
                    self.load_file(file_index)
                    return True
            return False

    def load_all(self):
        for file_index in range(len(self._loaded)):
            self.load_file(file_index)

    def load_until(self, min_groups):
        """Load files in order until at least ``min_groups`` groups are known.

        Returns the number of files loaded so far.
        """
        with self._lock:
            while len(self._order) < min_groups and self.load_next_file():
                pass
            return sum(self._loaded)

    def unload_file(self, file_index):
        """Forget one file's groups and release its cached data (root collections only)."""
        if self._derived or not self._loaded[file_index]:
            return
        with self._lock:
            prefix = f"f{file_index}_"
            for key in [k for k in self._groups if k.startswith(prefix)]:
                del self._groups[key]
            self._order = sorted(self._groups, key=_group_sort_key)
            self._loaded[file_index] = False
            self._store.drop_file(file_index)

    def close(self):
        """Close file handles and drop cached columns; data is reopened on next access."""
        self._store.close()

    # --- data access -----------------------------------------------------

    def column(self, key, indices=None):
        """Column values at global row ``indices`` (all rows of this collection by default)."""
        if indices is None:
            indices = self.active_indices
        return self._store.read(key, indices)

    @property
    def data(self):
        return DataProxy(self)

    def unique(self, key):
        return np.unique(self.column(key))

    def _order_at(self, position):
        if position >= len(self._order) or position < 0:
            if position < 0:
                self.load_all()
            else:
                self.load_until(position + 1)
        try:
            return self._order[position]
        except IndexError:
            raise IndexError("Group index out of range.") from None

    def __len__(self):
        self.load_all()
        if len(self._order) == 1:
            return len(self._groups[self._order[0]])
        return len(self._order)

    def __iter__(self):
        position = 0
        while True:
            while position >= len(self._order):
                if not self.load_next_file():
                    return
            yield GroupView(self._store, self._store.keys, self._groups[self._order[position]])
            position += 1

    def __getitem__(self, selection):
        if isinstance(selection, (int, np.integer)):
            key = self._order_at(int(selection))
            return GroupView(self._store, self._store.keys, self._groups[key])
        if isinstance(selection, slice):
            self.load_all()
            if len(self._order) == 1:
                return self._derive({self._order[0]: self._groups[self._order[0]][selection]})
            return self._derive({key: self._groups[key] for key in self._order[selection]})
        if isinstance(selection, tuple):
            if len(selection) != 2:
                raise ValueError("Tuple key must have exactly two elements: (group_slice, data_slice).")
            group_selection, row_selection = selection
            self.load_all()
            if isinstance(group_selection, (int, np.integer)):
                if not -len(self._order) <= group_selection < len(self._order):
                    raise IndexError("Group index out of range.")
                chosen = [self._order[group_selection]]
            elif isinstance(group_selection, slice):
                chosen = self._order[group_selection]
            else:
                raise TypeError("Group index must be int or slice")
            groups = {key: self._groups[key][row_selection] for key in chosen}
            return self._derive({key: idx for key, idx in groups.items() if len(idx)})
        raise TypeError("Index must be int, slice or (group, rows) tuple.")

    # --- sharing between processes ---------------------------------------

    def to_shared_memory(self, key, file_index=0):
        """Copy one file's column into shared memory; call ``unlink()`` on the result when done."""
        column = np.ascontiguousarray(self._store.file_column(file_index, key))
        shm = shared_memory.SharedMemory(create=True, size=max(column.nbytes, 1))
        try:
            np.ndarray(column.shape, dtype=column.dtype, buffer=shm.buf)[...] = column
            return SharedColumn(shm.name, column.shape, column.dtype.str)
        finally:
            shm.close()

    def __getstate__(self):
        with self._lock:
            return {
                "filenames": self._store.filenames,
                "max_open_files": self._max_open_files,
                "max_cache_bytes": self._max_cache_bytes,
                "derived": self._derived,
                "groups": self._groups,
                "loaded": self._loaded,
            }

    def __setstate__(self, state):
        self._lock = threading.RLock()
        self._max_open_files = state["max_open_files"]
        self._max_cache_bytes = state["max_cache_bytes"]
        self._store = _FileStore(state["filenames"], self._max_open_files, self._max_cache_bytes)
        self._derived = state["derived"]
        self._groups = state["groups"]
        self._order = sorted(self._groups, key=_group_sort_key)
        self._loaded = state["loaded"]

    # --- names used by the original DataManagment module -----------------

    def GetKeys(self):
        return self.keys

    def UniqueHeaders(self):
        count = len(np.unique(self.column("Header")))
        return [count for _ in range(len(self))]

    @property
    def cached_keys(self):
        return self.keys

    @property
    def file_row_offsets(self):
        return self._store.offsets.tolist()

    @property
    def unique_groups(self):
        if not self._order:
            self.load_until(1)
        return self._order

    @property
    def _unique_groups(self):
        return self._order

    @property
    def _index_map(self):
        return self._groups

    def _get_data_from_global_idx(self, key, indices):
        return self.column(key, indices)

    def load_next_file_routing(self):
        return self.load_next_file()

    def prewarm_initial_routing(self, max_workers):
        return self.load_until(max_workers)

    def move_to_shared_memory(self, file_index, key):
        shared = self.to_shared_memory(key, file_index)
        return {"shm_name": shared.name, "shape": shared.shape, "dtype": shared.dtype}


DataPointCollection = DataCollection
DataPoint = Row
DataView = Row
