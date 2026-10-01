import re
from typing import List, Optional, Tuple, Union

import matplotlib.cm as cm
from matplotlib.collections import LineCollection
import matplotlib.colors as mcolors
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.interpolate import PchipInterpolator

class EigenValueSpectrumTool:
    def __init__(
        self,
        data: Union[str, List[str], pd.DataFrame],
        mixing_threshold: float = 0.70,
        cmap: Union[str, mcolors.Colormap] = "tab10",
        time_step : Optional[Union[float,int]] = None,
        **read_data_kwargs
    ):
        self.mixing_threshold = mixing_threshold
        self.cmap_input = cmap
        self.requested_time_step = time_step

        data_types = ["str", "pandas Dataframe"]

        if isinstance(data, str):
            self.raw_df = pd.read_csv(data,sep=r"\s+", **read_data_kwargs)
        elif isinstance(data, pd.DataFrame):
            self.raw_df = data.copy()
        else:
            raise TypeError(
                rf"Data must be a {' or '.join(data_types)}"
            )

        self.x_var : str = ""
        self.time_col: Optional[str] = None
        self.eigen_indices: List[int] = []
        self.ref_states: List[str] = []
        self.pairwise_mix_cols: List[Tuple[str, str, str, str]] = []
        self.color_map: dict = {}
        self.has_ref_states: bool = False
        self.has_pairwise_mix: bool = False
        self.is_time_dependent: bool = False

        self._parse_headers()
        self.df = self._prepare_data_slice()

        if self.has_ref_states:
            self._setup_colors()
            self._classify_eigenstates()

    def _parse_headers(self) -> None:
        columns = list(self.raw_df.columns)
        eigen_matches = [
            re.search(r"\.lambda(\d+)", col) for col in columns if ".lambda" in col
        ]
        self.eigen_indices = sorted(
            list(set(int(m.group(1)) for m in eigen_matches if m))
        )
        ref_matches = [
            re.search(r"\.ref\d+\((.*?)\)", col) for col in columns if ".ref" in col
        ]
        self.ref_states = list(
            dict.fromkeys([m.group(1) for m in ref_matches if m])
        )
        self.has_ref_states = len(self.ref_states) > 0

        for col in columns:
            mix_match = re.search(r"(?:RefMix|EigenMix)\((.*?),(.*?)\)", col, re.IGNORECASE)
            if mix_match:
                state_a, state_b = mix_match.group(1).strip(), mix_match.group(2).strip()
                if state_a != state_b:
                    if state_a.isdigit() and state_b.isdigit():
                        label = (f"$\\lambda_{{{state_a}}} - \\lambda_{{{state_b}}}$")
                    else:
                        label = f"{state_a} - {state_b}"
                    self.pairwise_mix_cols.append((label, state_a, state_b,col))

        seen_cols = set()
        unique_pairwise = []
        for label, sa,sb,col in self.pairwise_mix_cols:
            if col not in seen_cols:
                seen_cols.add(col)
                unique_pairwise.append((label, sa, sb, col))

        self.pairwise_mix_cols = unique_pairwise
        self.has_pairwise_mix = len(self.pairwise_mix_cols) > 0

        time_candidates = ["time(ns)", "time", "t_ns", "t"]
        self.time_col = next(
            (c for c in columns if c.lower() in time_candidates), None
        )
        if self.time_col and self.raw_df[self.time_col].nunique() > 1:
            self.is_time_dependent = True

        exclude_pattern = r"(^step$|\.lambda|\.ref|\.refmix|\.eigenmix)"
        data_cols = [
            col
            for col in columns
            if not re.search(exclude_pattern, col, re.IGNORECASE)
        ]
        non_time_cols = [col for col in data_cols if col != self.time_col]
        if non_time_cols:
            self.x_var = non_time_cols[0]
        elif data_cols:
            self.x_var = data_cols[0]
        else:
            self.x_var = columns[0]

    def _prepare_data_slice(self) -> pd.DataFrame:
        if not self.is_time_dependent:
            return self.raw_df.copy()
        if self.requested_time_step is not None and self.time_col:
            available_times = self.raw_df[self.time_col].unique()
            closest_time = available_times[
                (np.abs(available_times - self.requested_time_step)).argmin()
            ]
            print(
                f"[EigenValueSpectrumTool] Filtering dataset for {self.time_col} ≈ {closest_time}"
            )
            return self.raw_df[
                self.raw_df[self.time_col] == closest_time
            ].copy()
        if self.x_var == self.time_col or "time" in self.x_var.lower():
            return self.raw_df.copy()
        if self.raw_df.duplicated(subset=[self.x_var]).any():
            first_time = self.raw_df[self.time_col].iloc[0]
            print(
                f"[EigenValueSpectrumTool] Time dependency detected. Defaulting slice to {self.time_col} = {first_time}"
            )
            return self.raw_df[self.raw_df[self.time_col] == first_time].copy()
        return self.raw_df.copy()
    
    def get_available_times(self) -> List[float]:
        if self.time_col and self.time_col in self.raw_df.columns:
            return sorted(self.raw_df[self.time_col].unique().tolist())
        return []
    
    def set_time_step(self, time_step: float) -> None:
        self.requested_time_step = time_step
        self.df = self._prepare_data_slice()
        if self.has_ref_states:
            self._classify_eigenstates()

    def find_anticrossings(
        self,
        *,
        min_gap: float = 0.0,
        max_gap: Optional[float] = None,
        min_prominence: float = 0.0,
        prominence_window: int = 5,
        min_mixing: Optional[float] = None,
        mixing_pair: Optional[Tuple[str, str]] = None,
        x_range: Optional[Tuple[float, float]] = None,
        energy_range: Optional[Tuple[float, float]] = None,
    ) -> pd.DataFrame:
        """Find anticrossings from pairwise mixing peaks when available.

        Mixing and energy values use the units and scales in the input data.
        ``min_gap`` and ``max_gap`` filter candidates but do not define them.
        ``min_prominence`` applies to the mixing curve when available, otherwise
        to the eigenvalue-gap curve.
        If pairwise mixing data is absent, local eigenvalue-gap minima are used.
        """
        if min_gap < 0 or min_prominence < 0:
            raise ValueError("min_gap and min_prominence must be non-negative")
        if max_gap is not None and max_gap < min_gap:
            raise ValueError("max_gap must be greater than or equal to min_gap")
        if prominence_window < 1:
            raise ValueError("prominence_window must be at least 1")
        if min_mixing is not None and not 0 <= min_mixing <= 1:
            raise ValueError("min_mixing must be between 0 and 1")
        if (
            min_mixing is not None
            and not self.has_pairwise_mix
            and not self.has_ref_states
        ):
            raise ValueError("min_mixing requires mixing-fraction or reference-state data")
        if mixing_pair is not None and (
            len(mixing_pair) != 2 or mixing_pair[0] == mixing_pair[1]
        ):
            raise ValueError("mixing_pair must contain two distinct reference states")
        for name, bounds in (("x_range", x_range), ("energy_range", energy_range)):
            if bounds is not None and bounds[0] > bounds[1]:
                raise ValueError(f"{name} lower bound must not exceed its upper bound")

        result_columns = [
            "x",
            "mixing_state_a",
            "mixing_state_b",
            "eigen_index_a",
            "eigen_index_b",
            "eigenvalue_a",
            "eigenvalue_b",
            "gap",
            "prominence",
            "mixing_score",
        ]

        pair_groups = {}
        if self.has_pairwise_mix:
            requested_pair = set(mixing_pair) if mixing_pair is not None else None
            for _, state_a, state_b, col in self.pairwise_mix_cols:
                pair_key = frozenset((state_a, state_b))
                if requested_pair is not None and pair_key != requested_pair:
                    continue
                if pair_key not in pair_groups:
                    pair_groups[pair_key] = {
                        "states": (state_a, state_b),
                        "columns": [],
                    }
                pair_groups[pair_key]["columns"].append(col)
            if mixing_pair is not None and not pair_groups:
                raise ValueError(f"No pairwise mixing data found for {mixing_pair!r}")
        elif mixing_pair is not None:
            raise ValueError("mixing_pair requires pairwise mixing data")

        x_values = self.df[self.x_var].to_numpy(dtype=float)
        finite_x = np.isfinite(x_values)
        x_values = x_values[finite_x]
        if x_values.size < 3:
            return pd.DataFrame(columns=result_columns)

        energies = []
        eigen_indices = []
        reference_weights = {}
        for eigen_index in self.eigen_indices:
            energy_col = next(
                (
                    col
                    for col in self.df.columns
                    if re.search(fr"\.lambda{eigen_index}(?!\d)", col)
                ),
                None,
            )
            if energy_col is not None:
                energies.append(self.df.loc[finite_x, energy_col].to_numpy(dtype=float))
                eigen_indices.append(eigen_index)

                reference_cols = {}
                for col in self.df.columns:
                    match = re.search(fr"\.ref{eigen_index}\((.*?)\)", col)
                    if match:
                        reference_cols[match.group(1)] = col
                if reference_cols:
                    reference_weights[eigen_index] = {
                        state: self.df.loc[finite_x, col].to_numpy(dtype=float)
                        for state, col in reference_cols.items()
                    }

        if len(energies) < 2:
            return pd.DataFrame(columns=result_columns)

        energies = np.column_stack(energies)
        order = np.argsort(x_values)
        x_values = x_values[order]
        energies = energies[order]
        for weights in reference_weights.values():
            for state in weights:
                weights[state] = weights[state][order]
        if np.any(np.diff(x_values) <= 0):
            raise ValueError("x values must be unique to find anticrossings")

        candidates = []

        def append_candidate(
            sample_index: int,
            energy_index_a: int,
            energy_index_b: int,
            prominence: float,
            mixing_score: float,
            mixing_states: Tuple[Optional[str], Optional[str]],
        ) -> None:
            energy_a = energies[sample_index, energy_index_a]
            energy_b = energies[sample_index, energy_index_b]
            gap = abs(energy_a - energy_b)
            midpoint = (energy_a + energy_b) / 2
            if gap < min_gap or (max_gap is not None and gap > max_gap):
                return
            if x_range is not None and not x_range[0] <= x_values[sample_index] <= x_range[1]:
                return
            if energy_range is not None and not energy_range[0] <= midpoint <= energy_range[1]:
                return
            if min_mixing is not None and (
                not np.isfinite(mixing_score) or mixing_score < min_mixing
            ):
                return

            candidates.append(
                {
                    "x": x_values[sample_index],
                    "mixing_state_a": mixing_states[0],
                    "mixing_state_b": mixing_states[1],
                    "eigen_index_a": eigen_indices[energy_index_a],
                    "eigen_index_b": eigen_indices[energy_index_b],
                    "eigenvalue_a": energy_a,
                    "eigenvalue_b": energy_b,
                    "gap": gap,
                    "prominence": prominence,
                    "mixing_score": mixing_score,
                }
            )

        if pair_groups:
            for pair in pair_groups.values():
                state_a, state_b = pair["states"]
                mix_values = self.df.loc[finite_x, pair["columns"]].to_numpy(dtype=float)
                mix_values = np.max(
                    np.where(np.isfinite(mix_values), mix_values, -np.inf), axis=1
                )
                mix_values[~np.isfinite(mix_values)] = np.nan
                mix_values = mix_values[order]

                for i in range(1, len(x_values) - 1):
                    if not (
                        np.isfinite(mix_values[i - 1 : i + 2]).all()
                        and mix_values[i] >= mix_values[i - 1]
                        and mix_values[i] > mix_values[i + 1]
                    ):
                        continue

                    mixing_score = mix_values[i]
                    left = mix_values[max(0, i - prominence_window) : i]
                    right = mix_values[i + 1 : i + 1 + prominence_window]
                    left = left[np.isfinite(left)]
                    right = right[np.isfinite(right)]
                    if left.size == 0 or right.size == 0:
                        continue
                    prominence = mixing_score - max(left.min(), right.min())
                    if prominence < min_prominence:
                        continue

                    best_assignment = None
                    for a in range(len(eigen_indices)):
                        weights_a = reference_weights.get(eigen_indices[a], {})
                        state_a_weight = weights_a.get(state_a)
                        state_b_weight = weights_a.get(state_b)
                        if state_a_weight is None or state_b_weight is None:
                            continue
                        for b in range(a + 1, len(eigen_indices)):
                            weights_b = reference_weights.get(eigen_indices[b], {})
                            other_a_weight = weights_b.get(state_a)
                            other_b_weight = weights_b.get(state_b)
                            if other_a_weight is None or other_b_weight is None:
                                continue
                            assignment_score = (
                                state_a_weight[i] * other_b_weight[i]
                                + state_b_weight[i] * other_a_weight[i]
                            )
                            if best_assignment is None or assignment_score > best_assignment[0]:
                                best_assignment = (assignment_score, a, b)

                    if best_assignment is None or best_assignment[0] <= 0:
                        gaps = np.abs(energies[i, :, None] - energies[i, None, :])
                        gaps[np.tril_indices_from(gaps)] = np.inf
                        a, b = np.unravel_index(np.argmin(gaps), gaps.shape)
                    else:
                        _, a, b = best_assignment

                    append_candidate(i, a, b, prominence, mixing_score, (state_a, state_b))
        else:
            for a in range(len(eigen_indices) - 1):
                for b in range(a + 1, len(eigen_indices)):
                    gaps = np.abs(energies[:, a] - energies[:, b])
                    weights_a = reference_weights.get(eigen_indices[a], {})
                    weights_b = reference_weights.get(eigen_indices[b], {})
                    if weights_a and weights_b:
                        mixing_scores = np.zeros(gaps.shape)
                        for state in self.ref_states:
                            if state in weights_a and state in weights_b:
                                mixing_scores += np.minimum(weights_a[state], weights_b[state])
                    else:
                        mixing_scores = np.full(gaps.shape, np.nan)

                    for i in range(1, len(x_values) - 1):
                        if not (
                            np.isfinite(gaps[i - 1 : i + 2]).all()
                            and gaps[i] <= gaps[i - 1]
                            and gaps[i] < gaps[i + 1]
                        ):
                            continue
                        left = gaps[max(0, i - prominence_window) : i]
                        right = gaps[i + 1 : i + 1 + prominence_window]
                        if left.size == 0 or right.size == 0:
                            continue
                        prominence = min(left.max(), right.max()) - gaps[i]
                        if prominence < min_prominence:
                            continue
                        append_candidate(
                            i,
                            a,
                            b,
                            prominence,
                            mixing_scores[i],
                            (None, None),
                        )

        return pd.DataFrame(candidates, columns=result_columns).sort_values(
            ["x", "gap"], ignore_index=True
        )

    def _setup_colors(self) -> None:
        num_ref = len(self.ref_states)
        if isinstance(self.cmap_input, str):
            colormap = cm.get_cmap(self.cmap_input, max(num_ref, 1))
        else:
            colormap = self.cmap_input
        self.color_map = {
            state: colormap(i / max(1, num_ref - 1)) if num_ref > 1 else colormap(0)
            for i, state in enumerate(self.ref_states)
        }
        self.color_map["Mixed"] = (0.5, 0.5, 0.5, 0.6)

    def _classify_eigenstates(self, data: Optional[pd.DataFrame] = None) -> None:
        data = self.df if data is None else data
        columns = list(data.columns)
        for N in self.eigen_indices:
            ref_cols_N = [
                col
                for col in columns
                if re.search(fr"\.ref{N}\((.*?)\)", col)
            ]
            if ref_cols_N:
                max_overlap = data[ref_cols_N].max(axis=1)
                max_state = (
                    data[ref_cols_N]
                    .idxmax(axis=1)
                    .str.extract(r"\((.*?)\)")[0]
                )
                data[f"eigen_{N}_label"] = np.where(
                    max_overlap >= self.mixing_threshold, max_state, "Mixed"
                )
            else:
                data[f"eigen_{N}_label"] = "Mixed"

    def _interpolate_plot_data(self, min_points: Optional[int]) -> pd.DataFrame:
        if min_points is not None and min_points < 2:
            raise ValueError("min_points must be at least 2")
        if min_points is None or len(self.df) >= min_points:
            return self.df

        x_values = self.df[self.x_var].to_numpy(dtype=float)
        if not np.isfinite(x_values).all():
            return self.df
        order = np.argsort(x_values)
        x_values = x_values[order]
        if x_values.size < 2 or np.any(np.diff(x_values) <= 0):
            return self.df

        additional_count = min_points - len(x_values)
        candidate_x = np.linspace(x_values[0], x_values[-1], min_points)
        candidate_x = candidate_x[~np.isin(candidate_x, x_values)]
        if candidate_x.size > additional_count:
            selected = np.linspace(
                0, candidate_x.size - 1, additional_count
            ).round().astype(int)
            candidate_x = candidate_x[selected]
        plot_x = np.sort(np.concatenate((x_values, candidate_x)))
        plot_columns = {self.x_var: plot_x}
        for column in self.df.columns:
            if column == self.x_var or not pd.api.types.is_numeric_dtype(self.df[column]):
                continue
            values = self.df[column].to_numpy(dtype=float)[order]
            finite_values = np.isfinite(values)
            if finite_values.sum() < 2:
                continue
            interpolator = PchipInterpolator(
                x_values[finite_values], values[finite_values], extrapolate=False
            )
            plot_columns[column] = interpolator(plot_x)

        plot_data = pd.DataFrame(plot_columns)
        if self.has_ref_states:
            self._classify_eigenstates(plot_data)
        return plot_data

    def plot_spectrum(
        self,
        figsize: Tuple[int, int] = (10, 6),
        title: Optional[str] = None,
        min_points: Optional[int] = None,
        show_markers: bool = False,
    ) -> Tuple[plt.Figure, plt.Axes]:
        """Plot the spectrum, optionally interpolating sparse data for display."""
        plot_data = self._interpolate_plot_data(min_points)
        fig, ax = plt.subplots(figsize=figsize)
        columns = list(plot_data.columns)
        for N in self.eigen_indices:
            energy_col = next(
                (col for col in columns if f".lambda{N}" in col), None
            )
            if not energy_col:
                continue
            label_col = f"eigen_{N}_label"
            if self.has_ref_states and label_col in plot_data.columns:
                x_values = plot_data[self.x_var].to_numpy()
                energy_values = plot_data[energy_col].to_numpy()
                state_values = plot_data[label_col].to_numpy()
                points = np.column_stack((x_values, energy_values))
                segments = np.stack((points[:-1], points[1:]), axis=1)
                segment_labels = state_values[:-1].copy()
                transitions = state_values[:-1] != state_values[1:]
                segment_labels[transitions] = "Mixed"

                ax.plot(
                    x_values,
                    energy_values,
                    color="black",
                    lw=0.45,
                    alpha=0.25,
                    zorder=1,
                )
                for label, color in self.color_map.items():
                    segment_mask = segment_labels == label
                    if segment_mask.any():
                        ax.add_collection(
                            LineCollection(
                                segments[segment_mask],
                                colors=[color],
                                linewidths=1.5,
                                alpha=0.95,
                                label=label,
                                zorder=2,
                            )
                        )
                    if show_markers:
                        mask = state_values == label
                        if not mask.any():
                            continue
                        ax.scatter(
                            x_values[mask],
                            energy_values[mask],
                            color=color,
                            s=4,
                            label=label,
                            alpha=0.85,
                            zorder=3,
                        )
            else:
                ax.plot(
                    plot_data[self.x_var],
                    plot_data[energy_col],
                    lw=1.5,
                    label=f"$\\lambda_{{{N}}}$",
                )
        if self.has_ref_states:
            handles, labels = ax.get_legend_handles_labels()
            by_label = dict(zip(labels, handles))
            ax.legend(
                by_label.values(),
                by_label.keys(),
                title="Reference state",
                bbox_to_anchor=(1.02, 1),
                loc="upper left",
            )
        else:
            ax.legend(title="Eigenstate", bbox_to_anchor=(1.02, 1), loc="upper left")
        ax.set_xlabel(self.x_var)
        ax.set_ylabel("Energy Eigenvalue ($rad/ns$)")
        if title is None:
            title = "Energy Spectrum"
            if self.is_time_dependent and self.time_col:
                current_time = plot_data[self.time_col].iloc[0]
                title += f" ({self.time_col} = {current_time})"
        ax.set_title(title, fontweight="bold")
        ax.grid(True, linestyle="--", alpha=0.5)
        plt.tight_layout()
        return fig, ax

    def plot_mixing_fractions(
        self,
        cols: int = 2,
        figsize_per_row: Tuple[float, float] = (12, 3.2),
        title: Optional[str] = None,
    ) -> Optional[Tuple[plt.Figure, np.ndarray]]:
        if not self.has_pairwise_mix:
            print("[EigenValueSpectrumTool] No reference states detected. Skipping mixing plot.")
            return None

        primary_states = sorted(
            list(
                set(
                    [item[1] for item in self.pairwise_mix_cols]
                    + [item[2] for item in self.pairwise_mix_cols]
                )
            ),
            key=lambda x: int(x) if x.isdigit() else x,
        )
        
        num_panels = len(primary_states)
        if num_panels == 0:
            return None
        actual_cols = min(cols, num_panels)
        rows = (num_panels + actual_cols - 1) // actual_cols

        fig, axes = plt.subplots(
            rows,
            actual_cols,
            figsize=(figsize_per_row[0], figsize_per_row[1] * rows),
            sharex=True,
            sharey=True,
            squeeze=False,
        )
        axes_flat = axes.flatten()

        for idx, base_state in enumerate(primary_states):
            ax = axes_flat[idx]

            for _, state_a, state_b, col_name in self.pairwise_mix_cols:
                if col_name not in self.df.columns:
                    continue

                partner_state = None
                if state_a == base_state:
                    partner_state = state_b
                elif state_b == base_state:
                    partner_state = state_a

                if partner_state is not None:
                    label = (
                        f"$\\lambda_{{{partner_state}}}$"
                        if partner_state.isdigit()
                        else partner_state
                    )

                    line_color = self.color_map.get(partner_state, None)

                    ax.plot(
                        self.df[self.x_var],
                        self.df[col_name],
                        label=label,
                        lw=1.8,
                        alpha=0.85,
                        color = line_color
                    )

            panel_title = (
                f"State $\\lambda_{{{base_state}}}$"
                if base_state.isdigit()
                else f"State: {base_state}"
            )
            ax.set_title(f"Mixing with {panel_title}", fontweight="bold")
            ax.set_ylim(-0.02, 0.52)
            ax.grid(True, linestyle="--", alpha=0.5)

            if idx % actual_cols == 0:
                ax.set_ylabel("Mixing Fraction ($\eta_{jk}$)")
            if idx >= (rows - 1) * actual_cols:
                ax.set_xlabel(self.x_var)

            handles, labels = ax.get_legend_handles_labels()
            by_label = dict(zip(labels,handles))
            ax.legend(
                by_label.values(),
                by_label.keys(),
                title="Partner State", loc="upper left", fontsize=8)

        for idx in range(num_panels, len(axes_flat)):
            fig.delaxes(axes_flat[idx])

        if title is None:
            title = "pairwise state mixing fractions across reference states"
            if self.is_time_dependent and self.time_col:
                current_time = self.df[self.time_col].iloc[0]
                title += f" ({self.time_col} = {current_time})"

        fig.suptitle(title, fontsize=14, fontweight="bold", y=0.99)
        plt.tight_layout()
        plt.subplots_adjust(top=0.92)

        return fig, axes