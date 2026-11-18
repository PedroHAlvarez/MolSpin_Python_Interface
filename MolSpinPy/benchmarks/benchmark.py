"""Common types for planning benchmark systems."""

from abc import ABC, abstractmethod
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Dict, Generic, Iterable, Iterator, Mapping, Optional, Tuple, TypeVar

ConfigT = TypeVar("ConfigT")

@dataclass
class SystemVariant(Generic[ConfigT]):
    """A named MolSpin input for one size or configuration of a system."""

    name: str
    model: dict
    hilbert_dimension: Optional[int] = None
    config: Optional[ConfigT] = None

    def __post_init__(self):
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("A system variant must have a non-empty name.")
        if not isinstance(self.model, dict):
            raise TypeError("A system variant model must be a MolSpin input dictionary.")
        if self.hilbert_dimension is not None and (
            isinstance(self.hilbert_dimension, bool)
            or not isinstance(self.hilbert_dimension, int)
            or self.hilbert_dimension < 1
        ):
            raise ValueError("hilbert_dimension must be a positive integer.")
        self.model = deepcopy(self.model)

    def copy_model(self) -> dict:
        """Return an independent input dictionary for a future benchmark job."""
        return deepcopy(self.model)


class BenchmarkSystem:
    """A named system with one or more distinct variants."""

    def __init__(self, name: str, variants: Iterable[SystemVariant]):
        if not isinstance(name, str) or not name.strip():
            raise ValueError("A benchmark system must have a non-empty name.")
        self.name = name
        self.variants: Tuple[SystemVariant, ...] = tuple(variants)
        if not self.variants:
            raise ValueError("A benchmark system must have at least one variant.")
        if not all(isinstance(variant, SystemVariant) for variant in self.variants):
            raise TypeError("Each system variant must be a SystemVariant.")
        names = [variant.name for variant in self.variants]
        if len(set(names)) != len(names):
            raise ValueError("System variant names must be unique.")


Parameters = TypeVar("Parameters")


@dataclass(frozen=True)
class BenchmarkCase(Generic[Parameters]):
    """One planned calculation; generating a case does not run MolSpin."""

    system_name: str
    variant: SystemVariant
    parameters: Parameters


@dataclass(frozen=True)
class BenchmarkDeployment:
    """The result and project created for one deployed system variant."""

    variant: SystemVariant
    project: Any
    result: Any


class BenchmarkBase(ABC, Generic[Parameters]):
    """Base class for a concrete system and its parameter sweep."""

    def __init__(self, name: str, variants: Iterable[SystemVariant]):
        if not isinstance(name, str) or not name.strip():
            raise ValueError("A benchmark system must have a non-empty name.")
        self.name = name
        self.variants: Tuple[SystemVariant, ...] = tuple(variants)
        if not self.variants:
            raise ValueError("A benchmark system must have at least one variant.")
        if not all(isinstance(variant, SystemVariant) for variant in self.variants):
            raise TypeError("Each system variant must be a SystemVariant.")
        names = [variant.name for variant in self.variants]
        if len(set(names)) != len(names):
            raise ValueError("System variant names must be unique.")

    @abstractmethod
    def iter_parameters(self) -> Iterator[Parameters]:
        """Generate the parameter sweep owned by this benchmark system."""
        raise NotImplementedError

    def iter_cases(self) -> Iterator[BenchmarkCase[Parameters]]:
        """Generate cases for every system variant and sweep point."""
        for variant in self.variants:
            for parameters in self.iter_parameters():
                yield BenchmarkCase(self.name, variant, parameters)

    @abstractmethod
    def prepare_model(self, variant: SystemVariant) -> dict:
        """Return a complete MolSpin input for a variant."""
        raise NotImplementedError

    @abstractmethod
    def parameter_bindings(
        self, variant: SystemVariant
    ) -> Mapping[str, Iterable[Any]]:
        """Map MolSpin dictionary paths to one value per sweep point."""
        raise NotImplementedError

    def create_projects(self) -> Iterator[Any]:
        """Create configured, undeployed projects for all system variants."""
        from ..objects import Action
        from ..runtime import ActionManager, Project
        from .stochastic_schrodinger import select_benchmark_value

        parameter_count = sum(1 for _ in self.iter_parameters())
        for variant in self.variants:
            model = self.prepare_model(variant)
            manager = ActionManager()
            bindings = self.parameter_bindings(variant)
            for path, values in bindings.items():
                sequence = tuple(values)
                if len(sequence) != parameter_count:
                    raise ValueError(
                        f"Parameter binding '{path}' contains {len(sequence)} values; "
                        f"expected {parameter_count}."
                    )
                manager.add_action(
                    Action(
                        model,
                        deepcopy(select_benchmark_value),
                        key=path,
                        values=sequence,
                    )
                )
            project = Project(f"{self.name}-{variant.name}")
            project.attach_dict(model)
            project.attach_ActionManager(manager)
            project._extract_settings()
            yield project

    def deploy_local(self, **kwargs) -> Tuple[BenchmarkDeployment, ...]:
        """Deploy every system variant to the local MolSpin runtime."""
        steps = sum(1 for _ in self.iter_parameters())
        deployments = []
        for project, variant in zip(self.create_projects(), self.variants):
            result = project.Deploy(steps=steps, **kwargs)
            deployments.append(BenchmarkDeployment(variant, project, result))
        return tuple(deployments)

    def deploy_hpc(
        self,
        hpc_username: str,
        hpc_host: str,
        hpc_key_path: str,
        remote_binary_path: str,
        remote_working_dir: str,
        **kwargs,
    ) -> Tuple[BenchmarkDeployment, ...]:
        """Submit every system variant to an HPC MolSpin runtime."""
        connection: Dict[str, str] = {
            "hpc_username": hpc_username,
            "hpc_host": hpc_host,
            "hpc_key_path": hpc_key_path,
            "remote_working_dir": remote_working_dir,
        }
        steps = sum(1 for _ in self.iter_parameters())
        deployments = []
        for project, variant in zip(self.create_projects(), self.variants):
            project.LoadHPC(
                **connection,
                cluster_profile=kwargs.get("cluster_profile", "gwdg"),
                proxy_host=kwargs.get("proxy_host"),
            )
            submit_options = dict(kwargs)
            submit_options["steps"] = steps
            submit_options["remote_binary_path"] = remote_binary_path
            submit_options.pop("cluster_profile", None)
            submit_options.pop("proxy_host", None)
            result = project.SubmitToHPC(**connection, **submit_options)
            deployments.append(BenchmarkDeployment(variant, project, result))
        return tuple(deployments)

    def deploy(self, target: str = "local", **kwargs) -> Tuple[BenchmarkDeployment, ...]:
        """Deploy the benchmark locally or on HPC."""
        if target == "local":
            return self.deploy_local(**kwargs)
        if target == "hpc":
            required = (
                "hpc_username",
                "hpc_host",
                "hpc_key_path",
                "remote_binary_path",
                "remote_working_dir",
            )
            missing = [name for name in required if not kwargs.get(name)]
            if missing:
                raise ValueError(
                    "Missing required HPC configuration: " + ", ".join(missing)
                )
            return self.deploy_hpc(**kwargs)
        raise ValueError("target must be either 'local' or 'hpc'.")


Benchmark = BenchmarkBase