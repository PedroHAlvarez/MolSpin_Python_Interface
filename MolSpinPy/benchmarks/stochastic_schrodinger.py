"""Shared configuration for stochastic Schrodinger benchmarks."""

from dataclasses import dataclass
from typing import Iterable, Tuple

from .benchmark import BenchmarkBase, SystemVariant
from ..objects import ActionScript, Task


@ActionScript
def select_benchmark_value(step, var, state, values):
    return values[step % len(values)]


@dataclass(frozen=True)
class StochasticSchrodingerParameters:
    """Parameters for one stochastic Schrodinger calculation."""

    k_s_exponent: float
    k_i_exponent: float
    k_s: float
    k_i: float
    r_std: float
    field: Tuple[float, float, float]
    samples: int
    initial_state: str = "S"


class StochasticSchrodingerBenchmark(
    BenchmarkBase[StochasticSchrodingerParameters]
):
    """A benchmark system calculated with stochastic Schrodinger."""

    def __init__(
        self,
        name: str,
        variants: Iterable[SystemVariant],
        samples: int = 12,
        task_name: str = "TE",
        total_time: float = 1000.0,
        time_step: float = 1.0,
    ):
        super().__init__(name, variants)
        if isinstance(samples, bool) or not isinstance(samples, int) or samples < 1:
            raise ValueError("samples must be a positive integer.")
        self.samples = samples
        self.task = Task(
            task_name,
            "HSGeneral",
            calculation="timeevolution",
            sampling="stochastic",
            montecarlosamples=samples,
            stochasticstandarddeviation=True,
            totaltime=total_time,
            timestep=time_step,
        )

    def prepare_model(self, variant: SystemVariant) -> dict:
        """Add the stochastic calculation task to an independent variant model."""
        model = variant.copy_model()
        tasks = model.setdefault("tasks", {})
        if not isinstance(tasks, dict):
            raise TypeError(f"Variant '{variant.name}' tasks must be a dictionary.")
        task_name, task = self.task.ConvertToDictionary()
        tasks[task_name] = task
        settings = model.setdefault("settings", {})
        if not isinstance(settings, dict):
            raise TypeError(f"Variant '{variant.name}' settings must be a dictionary.")
        settings.setdefault("general", {}).setdefault("steps", 1)
        return model
