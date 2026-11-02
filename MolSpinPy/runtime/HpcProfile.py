"""Cluster-specific settings for remote (Slurm) MolSpin deployment.

Everything that differs between HPC clusters lives in an ``HpcProfile``; the
deployment code in ``RemoteDeploy.py`` and ``Project.py`` contains no cluster
names or per-cluster branches. To support a new cluster, build a profile and
either register it (``HpcProfile.register(profile)``, then use
``cluster_profile="name"``) or pass the instance directly as ``cluster_profile``
to ``Project.LoadHPC`` / ``Project.SubmitToHPC``.
"""

from dataclasses import dataclass, field, replace
from typing import Dict, Tuple, Union


@dataclass(frozen=True)
class HpcProfile:
    """Describes how MolSpin is built and run on one cluster.

    Attributes:
        name: Registry key, matched case-insensitively. Also what
            ``cluster_profile="..."`` refers to.
        default_partition: Slurm partition used for job submission when the
            caller does not pass ``partition`` to ``SubmitToHPC``.
        runtime_modules: Environment modules loaded (after ``module purge``)
            at the top of every job script, in order. These must provide
            everything the compiled MolSpin binary and ``hpc_worker.py``
            need at run time (compiler runtime libraries, Armadillo/BLAS/
            LAPACK, Python and numpy).
        build_modules: Environment modules loaded when compiling in
            ``UpdateBinary``. Usually the same as ``runtime_modules``, but is
            kept separate because a build may need extra tools that jobs don't.
        build_partition: Partition used for the compile job in
            ``UpdateBinary``. Empty means use ``default_partition``. Useful
            where a short/test partition gives quick turnaround for builds.
        build_make_args: Extra arguments appended to ``make`` when building
            (e.g. to override architecture flags that don't suit the nodes).
        activate_venv: If True, job scripts ``source`` a Python virtualenv
            after loading the modules. Needed where the cluster's Python
            module does not provide numpy and friends.
        venv_subpath: Location of that virtualenv relative to the remote
            binary directory; only used when ``activate_venv`` is True.
        venv_packages: Packages ``InstallBinary`` pip-installs into that
            virtualenv (``hpc_worker.py`` needs numpy).
        use_external_armadillo_path: True when Armadillo is a manual install
            rather than a module. Then ``UpdateBinary`` patches the makefile
            to point at ``armadillo_path`` and job scripts add
            ``<armadillo>/lib64`` to ``LD_LIBRARY_PATH``. The path is supplied
            by the user (``armadillo_path`` / ``armadillo=`` kwarg).
        metadata_extra: Extra key/values written into the project metadata
            for runs on this cluster.

    Why the built-in profiles differ:
        * ``gwdg``: Armadillo is a manual install (``use_external_armadillo_path``),
          Python packages come from a virtualenv (``activate_venv``), builds
          run on the ``standard96:test`` partition and make needs no overrides.
        * ``rosa``: Armadillo and SciPy come as modules so no external path or
          virtualenv is needed, jobs go to ``rosa.p``, and make needs
          ``ARCHFLAGS=`` / ``LOOPFLAGS=`` cleared to build for the nodes there.
    """

    name: str
    default_partition: str
    runtime_modules: Tuple[str, ...] = ()
    build_modules: Tuple[str, ...] = ()
    build_partition: str = ""
    build_make_args: Tuple[str, ...] = ()
    activate_venv: bool = False
    venv_subpath: str = "molspinpyi_env"
    venv_packages: Tuple[str, ...] = ("numpy",)
    use_external_armadillo_path: bool = False
    metadata_extra: Dict[str, str] = field(default_factory=dict)

    _registry = {}

    def with_overrides(self, **overrides):
        return replace(self, **overrides)

    def runtime_environment(self, remote_binary_path, armadillo_path=""):
        sections = ["\n".join(("module purge", *(f"module load {m}" for m in self.runtime_modules)))]
        if self.use_external_armadillo_path:
            sections.append(f'export LD_LIBRARY_PATH="{armadillo_path}/lib64:$LD_LIBRARY_PATH"')
        if self.activate_venv:
            sections.append(f"source {remote_binary_path}/{self.venv_subpath}/bin/activate")
        return "\n\n".join(sections)

    @classmethod
    def register(cls, profile):
        cls._registry[profile.name.lower()] = profile
        return profile

    @classmethod
    def available(cls):
        return sorted(cls._registry)

    @classmethod
    def get(cls, profile: Union[str, "HpcProfile", None]):
        if isinstance(profile, HpcProfile):
            return profile
        key = (profile or "gwdg").lower()
        if key not in cls._registry:
            raise ValueError(
                f"Unknown HPC cluster profile '{profile}'. Available profiles: {', '.join(cls.available())}"
            )
        return cls._registry[key]


_GWDG_MODULES = ("gcc/11.5.0", "openblas", "netlib-lapack", "python/3.11.9")
_ROSA_MODULES = (
    "hpc-env/13.1",
    "Armadillo/15.0.1-foss-2023a",
    "SciPy-bundle/2023.05-foss-2023a",
)

HpcProfile.register(HpcProfile(
    name="gwdg",
    default_partition="standard96",
    runtime_modules=_GWDG_MODULES,
    build_modules=_GWDG_MODULES,
    build_partition="standard96:test",
    activate_venv=True,
    use_external_armadillo_path=True,
))

HpcProfile.register(HpcProfile(
    name="rosa",
    default_partition="rosa.p",
    runtime_modules=_ROSA_MODULES,
    build_modules=_ROSA_MODULES,
    build_make_args=("ARCHFLAGS=", "LOOPFLAGS="),
    metadata_extra={"cluster_profile": "rosa"},
))
