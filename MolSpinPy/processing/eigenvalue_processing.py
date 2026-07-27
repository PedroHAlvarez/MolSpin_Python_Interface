import re
from typing import List, Optional, Tuple, Union

import matplotlib.cm as cm
import matplotlib.colors as mcolors
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

class EigenValueSpectrumTool:
    def __init__(
        self,
        data: Union[str, pd.DataFrame],
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

    def _classify_eigenstates(self) -> None:
        columns = list(self.df.columns)
        for N in self.eigen_indices:
            ref_cols_N = [
                col
                for col in columns
                if re.search(fr"\.ref{N}\((.*?)\)", col)
            ]
            if ref_cols_N:
                max_overlap = self.df[ref_cols_N].max(axis=1)
                max_state = (
                    self.df[ref_cols_N]
                    .idxmax(axis=1)
                    .str.extract(r"\((.*?)\)")[0]
                )
                self.df[f"eigen_{N}_label"] = np.where(
                    max_overlap >= self.mixing_threshold, max_state, "Mixed"
                )
            else:
                self.df[f"eigen_{N}_label"] = "Mixed"

    def plot_spectrum(
        self,
        figsize: Tuple[int, int] = (10, 6),
        title: Optional[str] = None,
    ) -> Tuple[plt.Figure, plt.Axes]:
        fig, ax = plt.subplots(figsize=figsize)
        columns = list(self.df.columns)
        for N in self.eigen_indices:
            energy_col = next(
                (col for col in columns if f".lambda{N}" in col), None
            )
            if not energy_col:
                continue
            label_col = f"eigen_{N}_label"
            if self.has_ref_states and label_col in self.df.columns:
                for label, color in self.color_map.items():
                    mask = self.df[label_col] == label
                    if mask.any():
                        ax.scatter(
                            self.df.loc[mask, self.x_var],
                            self.df.loc[mask, energy_col],
                            color=color,
                            s=14,
                            label=label,
                            alpha=0.85,
                        )
                ax.plot(
                    self.df[self.x_var],
                    self.df[energy_col],
                    color="black",
                    lw=0.5,
                    alpha=0.3,
                )
            else:
                ax.plot(
                    self.df[self.x_var],
                    self.df[energy_col],
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
        ax.set_ylabel("Energy Eigenvalue ($meV$)")
        if title is None:
            title = "Energy Spectrum"
            if self.is_time_dependent and self.time_col:
                current_time = self.df[self.time_col].iloc[0]
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
                title="Partner State", loc="upper right", fontsize=8)

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