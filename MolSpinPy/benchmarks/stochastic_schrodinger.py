"""Shared configuration for stochastic Schrodinger benchmarks."""

from dataclasses import dataclass
from typing import Iterable, Tuple, Optional, Sequence

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
    run : int = 1

@dataclass(frozen=True)
class SSBconfig():
    task_name: str = "TE"
    total_time: float = 1000.0
    time_step: float = 1.0
    stochasticstandarddeviation: bool = True
    samples: int = 12

class StochasticSchrodingerBenchmark(
    BenchmarkBase[StochasticSchrodingerParameters]
):
    """A benchmark system calculated with stochastic Schrodinger."""

    def __init__(
        self,
        name: str,
        variants: Iterable[SystemVariant],
        config: SSBconfig = SSBconfig(),
        runs: int = 1,
    ):
        super().__init__(name, variants)
        self._validate_config(config)
        if isinstance(runs, bool) or not isinstance(runs, int) or runs < 1:
            raise ValueError("runs must be a positive integer.")
        for variant in self.variants:
            if variant.config is not None:
                self._validate_config(variant.config)
        self.config = config
        self.runs = runs

    @staticmethod
    def _validate_config(config: SSBconfig) -> None:
        if not isinstance(config, SSBconfig):
            raise TypeError("config must be an instance of SSBconfig.")
        if not isinstance(config.task_name, str) or not config.task_name.strip():
            raise ValueError("config.task_name must be a non-empty string.")
        if not isinstance(config.total_time, (int, float)) or config.total_time <= 0:
            raise ValueError("config.total_time must be a positive number.")
        if not isinstance(config.time_step, (int, float)) or config.time_step <= 0:
            raise ValueError("config.time_step must be a positive number.")
        if not isinstance(config.stochasticstandarddeviation, bool):
            raise TypeError("config.stochasticstandarddeviation must be a boolean.")
        if (
            isinstance(config.samples, bool)
            or not isinstance(config.samples, int)
            or config.samples < 1
        ):
            raise ValueError("config.samples must be a positive integer.")
    
    def resolve_config(self, variant: Optional[SystemVariant[SSBconfig]] = None) -> SSBconfig:
        if variant is not None and variant.config is not None:
            return variant.config
        return self.config

    def build_task(self, config: SSBconfig) -> Task:
        """Return a stochastic Schrodinger task for the given configuration."""
        return Task(
            config.task_name,
            "HSGeneral",
            calculation="timeevolution",
            sampling="stochastic",
            montecarlosamples=config.samples,
            stochasticstandarddeviation=config.stochasticstandarddeviation,
            totaltime=config.total_time,
            timestep=config.time_step,
            dynamics="static",
            autoseed=True,
            propogationmethod="krylov",
            reactionoperators="haberkorn",
            samplingmethod="suz"
        )
    

    def prepare_model(self, variant: SystemVariant) -> dict:
        """Add the stochastic calculation task to an independent variant model."""
        model = variant.copy_model()
        tasks = model.setdefault("tasks", {})
        if not isinstance(tasks, dict):
            raise TypeError(f"Variant '{variant.name}' tasks must be a dictionary.")
        cfg = self.resolve_config(variant)
        task_name, task = self.build_task(cfg).ConvertToDictionary()
        tasks[task_name] = task
        settings = model.setdefault("settings", {})
        if not isinstance(settings, dict):
            raise TypeError(f"Variant '{variant.name}' settings must be a dictionary.")
        settings.setdefault("general", {}).setdefault("steps", 1)
        return model
