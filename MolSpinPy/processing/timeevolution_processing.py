import os
from typing import Dict, List, Optional, Tuple, Union

import matplotlib.cm as cm
import matplotlib.colors as mcolors
import matplotlib.pyplot as plt
import numpy as np
import re
import tempfile

from ..runtime import Project, RemoteDeploy
import shutil
import atexit

_SESSION_TEMP_DIR: Optional[str] = None

def _get_session_temp_dir() -> str:
    global _SESSION_TEMP_DIR
    if _SESSION_TEMP_DIR is None or not os.path.exists(_SESSION_TEMP_DIR):
        _SESSION_TEMP_DIR = tempfile.mkdtemp(prefix="hpc_fetch_session_")
        atexit.register(shutil.rmtree, _SESSION_TEMP_DIR, ignore_errors=True)
    return _SESSION_TEMP_DIR

class TimeEvolutionTool:
    def __init__(
        self,
        data: Union[str, Dict[str, np.ndarray]],
        project: Optional[Project] = None,
        time_key: Optional[str] = None,
        states_key: Optional[str] = None,
        cmap: Union[str, mcolors.Colormap] = "tab10",
        state_labels: Optional[List[str]] = None,
        local_cache_dir: Optional[str] = None,
        step_index: Optional[int] = None,
        task_key: Optional[str] = None,
    ):
        self.cmap_input = cmap
        self.raw_data: Dict[str, np.ndarray] = {}
        self.project = project
        self.local_path: Optional[str] = None

        if self.project is not None and isinstance(data, str) and not os.path.exists(data):
            data = self._resolve_project_file(
                target = data,
                local_cache_dir = local_cache_dir,
                step_index = step_index,
                task_key=task_key,
            )

        if isinstance(data, str):
            if not os.path.exists(data):
                raise FileNotFoundError(f"The file {data} does not exist.")
            self.local_path = os.path.abspath(data)
            loaded = np.load(self.local_path)
            self.raw_data = {k: loaded[k] for k in loaded.files}
        elif isinstance(data, dict):
            self.raw_data = data
        else:
            raise TypeError("Data must be a file path string to a .npz file or a dict of arrays.")

        self.time_key = time_key or self._find_time_key()
        if self.time_key is None or self.time_key not in self.raw_data:
            available_keys = list(self.raw_data.keys())
            raise KeyError(
                f"Could not find a valid time key. Available keys in .npz: {available_keys}"
            )
        self.time_arr: np.ndarray = np.asarray(self.raw_data[self.time_key]).squeeze()

        self.state_keys: List[str] = []
        self.states_arr: np.ndarray = self._parse_state_data(states_key)
        self.num_times, self.num_states = self.states_arr.shape

        if state_labels and len(state_labels) == self.num_states:
            self.state_labels = state_labels
        elif self.state_keys:
            self.state_labels = [
                k.split(".")[-1] if "." in k else k for k in self.state_keys
            ]
        else:
            self.state_labels = [f"State {i}" for i in range(self.num_states)]

        self.color_map: Dict[str, Tuple[float, float, float, float]] = {}
        self._setup_colors()

    def _construct_filename(self, target: str, step_index: Optional[int], task_key: Optional[str]) -> str:
        if target and target != "auto" and target.endswith(".npz"):
            return os.path.basename(target)
        project_name = getattr(self.project, "name", getattr(self.project, "_name", "sim"))
        task = task_key if task_key else "TE"
        step = step_index if step_index is not None else 0
        return f"{project_name}-{task}-{step}.dat.npz"

    def _resolve_project_file(self, target:str, local_cache_dir: Optional[str], step_index: Optional[int], task_key: Optional[str]) -> str:
        filename = self._construct_filename(target=target, step_index=step_index, task_key=task_key)

        local_dir = getattr(self.project, "_working_dir_local", None) or getattr(self.project, "working_dir", None) or "."
        project_name = getattr(self.project, "name", getattr(self.project, "_name", ""))
        session_dir = _SESSION_TEMP_DIR

        local_candidate_path = [
            os.path.join(local_cache_dir, filename) if local_cache_dir else None,
            os.path.join(session_dir, filename) if session_dir else None,
            os.path.join(local_dir, "molspin_npz", filename),
            os.path.join(local_dir, f"molspin_workspace_{project_name}", filename),
            os.path.join(local_dir, filename),
            os.path.abspath(filename),
        ]
        for path in local_candidate_path:
            if path == None:
                continue
            if os.path.exists(path):
                print("[StateTimeEvolutionTool]: Found local npz results file")
                return path

        if getattr(self.project, "_hpc", None) is not None:
            return self._fetch_from_hpc(filename.lower(), local_cache_dir)

        raise FileNotFoundError(
            f"Could not locate file '{filename}' in local workspace or HPC environment."
        )

    def _fetch_from_hpc(self,filename:str,local_cache_dir:Optional[str]) -> str:
        orchestrator = self.project._hpc
        remote_working_dir = orchestrator.remote_working_dir
        project_name = getattr(self.project, "name", getattr(self.project, "_name", ""))

        remote_file_path = f"{remote_working_dir.rstrip('/')}/molspin_workspace_{project_name}/{filename}"

        if local_cache_dir:
            target_dir = local_cache_dir
        else:
            target_dir = _get_session_temp_dir()

        os.makedirs(target_dir, exist_ok=True)
        local_path = os.path.join(target_dir, filename)

        print(f"[StateTimeEvolutionTool] Fetching HPC output: {remote_file_path} -> {local_path}")
        hpc_ssh = orchestrator._connect()
        sftp = hpc_ssh.open_sftp()
        try:
            sftp.get(remote_file_path, local_path)
        except IOError as e:
            raise FileNotFoundError(
                f"Could not find remote HPC file: {remote_file_path}"
            ) from e
        finally:
            sftp.close()
            hpc_ssh.close()

        return local_path


    def _find_time_key(self) -> Optional[str]:
        candidates = ["time(ns)", "time (ns)", "time", "times", "t_ns", "t"]
        for key in self.raw_data.keys():
            if key.lower() in candidates or "time" in key.lower():
                return key
        return None

    def _parse_state_data(
        self, user_states_key: Optional[Union[str, List[str]]]
    ) -> np.ndarray:
        if isinstance(user_states_key, list):
            self.state_keys = user_states_key
            stacked = [self.raw_data[k].squeeze() for k in user_states_key]
            return np.column_stack(stacked)

        if isinstance(user_states_key, str) and user_states_key in self.raw_data:
            self.state_keys = [user_states_key]
            arr = np.asarray(self.raw_data[user_states_key])
            return self._ensure_time_first(arr)

        matched_keys = [
            k for k in self.raw_data.keys() if re.search(r"^[a-zA-Z0-9_]+\.[a-zA-Z0-9_]+", k)
        ]

        if matched_keys:
            # Sort to keep predictable state ordering
            self.state_keys = sorted(matched_keys)
            stacked = [np.asarray(self.raw_data[k]).squeeze() for k in self.state_keys]
            return np.column_stack(stacked)

        # Case D: Fallback for generic 2D arrays named 'states', 'populations', 'probs', etc.
        fallback_candidates = ["states", "populations", "probs", "probabilities", "y", "P"]
        for key in fallback_candidates:
            if key in self.raw_data:
                self.state_keys = [key]
                return self._ensure_time_first(np.asarray(self.raw_data[key]))

        raise KeyError(
            f"No keys matching 'spinsystem.state' pattern or standard state names were found. "
            f"Available keys: {list(self.raw_data.keys())}"
        )

    def _ensure_time_first(self, arr: np.ndarray) -> np.ndarray:
        if arr.ndim == 1:
            return arr[:, np.newaxis]
        if (
            arr.ndim == 2
            and arr.shape[0] != len(self.time_arr)
            and arr.shape[1] == len(self.time_arr)
        ):
            return arr.T
        return arr

    def _setup_colors(self) -> None:
        if isinstance(self.cmap_input, str):
            colormap = cm.get_cmap(self.cmap_input, max(self.num_states, 1))
        else:
            colormap = self.cmap_input

        self.color_map = {
            label: colormap(i / max(1, self.num_states - 1)) if self.num_states > 1 else colormap(0)
            for i, label in enumerate(self.state_labels)
        }

    def plot_evolution(
        self,
        selected_states: Optional[List[Union[int, str]]] = None,
        figsize: Tuple[int, int] = (10, 6),
        title: Optional[str] = "State Time Evolution",
        x_label: str = "Time",
        y_label: str = "Population / Probability",
        grid: bool = True,
    ) -> Tuple[plt.Figure, plt.Axes]:
        fig, ax = plt.subplots(figsize=figsize)
        indices_to_plot = self._resolve_state_indices(selected_states)

        for idx in indices_to_plot:
            label = self.state_labels[idx]
            color = self.color_map[label]
            ax.plot(
                self.time_arr,
                self.states_arr[:, idx],
                label=f"$\\vert {label} \\rangle$" if not label.startswith("State") else label,
                color=color,
                lw=2.0,
                alpha=0.85,
            )

        ax.set_xlabel(x_label, fontweight="bold")
        ax.set_ylabel(y_label, fontweight="bold")
        ax.set_title(title, fontweight="bold")
        ax.grid(grid, linestyle="--", alpha=0.5)
        ax.legend(bbox_to_anchor=(1.02, 1), loc="upper left")

        plt.tight_layout()
        return fig, ax

    def plot_stacked_evolution(
        self,
        figsize: Tuple[int, int] = (10, 6),
        title: Optional[str] = "Stacked State Populations Evolution",
        x_label: str = "Time",
        y_label: str = "Cumulative Population",
    ) -> Tuple[plt.Figure, plt.Axes]:
        fig, ax = plt.subplots(figsize=figsize)
        colors = [self.color_map[label] for label in self.state_labels]

        ax.stackplot(
            self.time_arr,
            self.states_arr.T,
            labels=[f"$\\vert {lbl} \\rangle$" for lbl in self.state_labels],
            colors=colors,
            alpha=0.8,
        )

        ax.set_xlabel(x_label, fontweight="bold")
        ax.set_ylabel(y_label, fontweight="bold")
        ax.set_title(title, fontweight="bold")
        ax.set_ylim(0, 1.02)
        ax.grid(True, linestyle="--", alpha=0.3)
        ax.legend(bbox_to_anchor=(1.02, 1), loc="upper left")

        plt.tight_layout()
        return fig, ax

    def _resolve_state_indices(
        self, selected_states: Optional[List[Union[int, str]]]
    ) -> List[int]:
        if selected_states is None:
            return list(range(self.num_states))

        indices = []
        for state in selected_states:
            if isinstance(state, int) and 0 <= state < self.num_states:
                indices.append(state)
            elif isinstance(state, str) and state in self.state_labels:
                indices.append(self.state_labels.index(state))
            else:
                print(f"[StateTimeEvolutionTool] Warning: State '{state}' not found. Skipping.")
        return indices