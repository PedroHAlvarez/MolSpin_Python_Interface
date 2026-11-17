"""Cryptochrome-4 benchmark system using stochastic Schrodinger."""

from itertools import product
from typing import Dict, Iterable, Iterator, Sequence, Tuple

from .benchmark import SystemVariant
from .stochastic_schrodinger import (
    StochasticSchrodingerBenchmark,
    StochasticSchrodingerParameters,
)


class Cryptochrome4Benchmark(StochasticSchrodingerBenchmark):
    """Cryptochrome-4 models, variants, and their stochastic parameter sweep."""

    DEFAULT_EXPONENTS = tuple(6 + index * 0.25 for index in range(13))
    DEFAULT_DEPHASING_RATES = (0.0, 0.01, 0.1, 1.0)
    DEFAULT_FIELDS = ((0.0, 0.0, 0.0), (0.0, 0.0, 0.1))

    def __init__(
        self,
        variants: Iterable[SystemVariant],
        samples: int = 12,
        exponents: Iterable[float] = DEFAULT_EXPONENTS,
        dephasing_rates: Iterable[float] = DEFAULT_DEPHASING_RATES,
        fields: Iterable[Sequence[float]] = DEFAULT_FIELDS,
        initial_state: str = "S",
        name: str = "Cryptochrome4",
    ):
        if not isinstance(initial_state, str) or not initial_state:
            raise ValueError("initial_state must be a non-empty string.")
        self.exponents = self._validated_values("exponents", exponents)
        self.dephasing_rates = self._validated_values(
            "dephasing_rates", dephasing_rates
        )
        self.fields = self._validated_fields(fields)
        self.initial_state = initial_state
        super().__init__(name, variants, samples)
        self.parameter_sweep: Tuple[StochasticSchrodingerParameters, ...] = tuple(
            StochasticSchrodingerParameters(
                k_s_exponent=k_s_exponent,
                k_i_exponent=k_i_exponent,
                k_s=10 ** k_s_exponent / 10**9,
                k_i=10 ** k_i_exponent / 10**9,
                r_std=r_std,
                field=field,
                samples=self.samples,
                initial_state=self.initial_state,
            )
            for field, r_std, k_s_exponent, k_i_exponent in product(
                self.fields,
                self.dephasing_rates,
                self.exponents,
                self.exponents,
            )
        )

    @staticmethod
    def _validated_values(name: str, values: Iterable[float]) -> Tuple[float, ...]:
        try:
            result = tuple(values)
        except TypeError as error:
            raise TypeError(f"{name} must be an iterable of numbers.") from error
        if not result:
            raise ValueError(f"{name} must not be empty.")
        if any(
            isinstance(value, bool) or not isinstance(value, (int, float))
            for value in result
        ):
            raise TypeError(f"{name} must contain only numbers.")
        return tuple(float(value) for value in result)

    @staticmethod
    def _validated_fields(
        fields: Iterable[Sequence[float]],
    ) -> Tuple[Tuple[float, float, float], ...]:
        try:
            values = tuple(fields)
        except TypeError as error:
            raise TypeError("fields must be an iterable of three-component vectors.") from error
        if not values:
            raise ValueError("fields must not be empty.")
        result = []
        for field in values:
            if (
                isinstance(field, (str, bytes))
                or not hasattr(field, "__len__")
                or len(field) != 3
            ):
                raise ValueError("Each field must have exactly three components.")
            if any(
                isinstance(component, bool)
                or not isinstance(component, (int, float))
                for component in field
            ):
                raise TypeError("Field components must be numbers.")
            result.append(tuple(float(component) for component in field))
        return tuple(result)

    def iter_parameters(self) -> Iterator[StochasticSchrodingerParameters]:
        """Iterate over the sweep belonging to this system."""
        return iter(self.parameter_sweep)

    def parameter_bindings(self, variant: SystemVariant) -> Dict[str, Tuple]:
        """Bind every sweep value to the corresponding MolSpin model field."""
        spin_systems = variant.model.get("spinsystems", {})
        if not isinstance(spin_systems, dict) or not spin_systems:
            raise ValueError(
                f"Variant '{variant.name}' must contain at least one spin system."
            )
        if len(spin_systems) != 1:
            raise ValueError(
                f"Variant '{variant.name}' must identify one spin system for "
                "the Cryptochrome-4 benchmark."
            )
        system = next(iter(spin_systems))
        prefix = f"spinsystems.{system}"
        parameters = self.parameter_sweep
        bindings = {
            f"{prefix}.transitions.s_sdd.rate": tuple(
                point.k_s for point in parameters
            ),
            f"{prefix}.operators.st_dephasing.rates": tuple(
                point.r_std for point in parameters
            ),
            f"{prefix}.interactions.zeeman.field": tuple(
                list(point.field) for point in parameters
            ),
            f"{prefix}.properties.prop.initialstate": tuple(
                point.initial_state for point in parameters
            ),
        }
        for transition in ("s_sid", "t0_sid", "tp_sid", "td_sid"):
            bindings[f"{prefix}.transitions.{transition}.rate"] = tuple(
                point.k_i for point in parameters
            )
        return bindings
