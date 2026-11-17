# About this manual

MolSpinPy provides Python objects and utilities for preparing MolSpin
input, generating parameter sweeps, running calculations, deploying work
to supported Slurm clusters, and exploring result data. This manual
describes the implementation identified as version 0.1.0 in the project
package metadata. It is based on the code currently in the repository;
the release should be treated as an early, evolving interface.

MolSpinPy prepares input and coordinates execution; it does not replace
the MolSpin simulation program. A usable MolSpin executable or a
configured remote installation is needed to perform simulations.

# Installation and compatibility

The package metadata declares Python 3.8 or newer and the following
runtime dependencies: NumPy, Matplotlib, SciPy, and Paramiko. From the
repository root, install the package with:

    python -m pip install .

For development tools, install the optional development dependencies
with:

    python -m pip install ".[dev]"

## Packaging notes for 0.1.0

There are differences between the declared installation requirements and
imports in the current source:

- `MolSpinPy.processing.EigenValueSpectrumTool` imports pandas, but
  pandas is not listed in the package dependencies.

- The package initialization imports `typing_extensions`, which is also
  not listed as a direct dependency.

- The setuptools configuration explicitly lists only the top-level
  `MolSpinPy` package, not its subpackages. Check the installed
  distribution contains `objects`, `runtime`, and the other subpackages;
  an editable install or running from the repository root may be needed
  with this packaging configuration.

- The source contains a Python 3.10-style union annotation in the
  rotation actions. Although the package metadata says Python 3.8+,
  Python 3.10 or newer is the practical choice for this version.

If importing the package fails because of a missing module, install the
corresponding dependency in the active environment. For example:

    python -m pip install pandas typing_extensions

# Core concepts

<div class="description">

A MolSpin data file. The parser converts it into nested Python
dictionaries that can be inspected or modified.

Owns the base input, the selected MSD template, optional object-built
spin systems, settings, tasks, an action manager, and local or remote
execution state.

Couples a target variable to an action function and optional timing,
sequence, and parent-child settings.

Registers, orders, tests, and applies actions at each sweep step.

Turns a dictionary snapshot into a MolSpin `.msd` input file. The
default is `BasicTemplate.msd`.

JSON and Markdown records of the input, template, action setup,
environment, and execution information.

</div>

A typical parameter-sweep workflow is:

1.  Read an MSD input or assemble a project with Python objects.

2.  Create an `ActionManager` and add actions for variables to change.

3.  Render a new MSD input for each sweep step.

4.  Run the generated input with MolSpin locally or submit the sweep to
    a configured HPC cluster.

5.  Process result files and plot selected quantities.

# Reading and rendering MSD input

## Load an existing input file

`ConvertMSDtoDictionary` parses MolSpin blocks into a dictionary with
top-level sections for `spinsystems`, `settings`, `actions`, `outputs`,
and `tasks`. The parser accepts line comments beginning with `//`,
braces for blocks, and semicolon terminated assignments. It tracks
original case while normalizing lookup keys for parsing.

    import MolSpinPy as msp

    input_data = msp.msd.MsdHandling.ConvertMSDtoDictionary(
        "base_inputfile.msd"
    )
    if input_data is None:
        raise FileNotFoundError("Could not read the MSD input file")

    project = msp.runtime.Project("example")
    project.attach_dict(input_data)

An MSD file can also be attached directly with
`project.attach_MSD_file(filename)`. To add a dictionary to an already
populated project, `attach_dict` accepts `dictMode.CONCATINATE` from
`MolSpinPy.runtime.Project`; otherwise the default mode replaces the
base dictionary. The project validates input structure against its
template before attaching it.

## The default input shape

The built-in template expects the following principal sections:

    {
        "spinsystems": {
            "system_name": {
                "spins": {},
                "interactions": {},
                "states": {},
                "transitions": {},
                "properties": {},
                "pulses": {},
                "operators": {}
            }
        },
        "settings": {},
        "actions": {},
        "outputs": {},
        "tasks": {}
    }

The template renders spin systems, spins, interactions, states,
transitions, properties, pulses, operators, settings, outputs, and run
tasks when those sections are present. The alternative
`BasicTemplate_withActions.msd` also renders actions and pulse
sequences. MolSpin-specific block names, property names, units, and
valid task types must follow the MolSpin program’s input requirements.

## Render a single input file

The template can be used independently of the project deployment
pipeline. This is useful for inspecting generated input or validating
the rendered configuration before a large run.

    from pathlib import Path

    template = msp.msd.FileTemplate.get_template("BasicTemplate.msd")
    rendered = template.render(input_data)
    Path("preview.msd").write_text(rendered, encoding="utf-8")

Custom templates can be loaded with
`msp.msd.FileTemplate.get_template(filename, folder=...)`. Template
syntax supports variable substitutions, `if`/`elif`/ `else` conditions,
and loops over dictionary entries. Template resources are packaged under
`MolSpinPy/resources/templates`.

# Building models with Python objects

The object API is available under `msp.objects`. A spin system can
contain electron and nuclear spins, interactions, states, transitions,
and properties. The supported interaction classes include Zeeman,
zero-field splitting, hyperfine, dipolar, and exchange interactions.

    from MolSpinPy.maths.vector import Vector

    system = msp.objects.spin_system.SpinSystem("GS")
    electron = system.add_electron(
        msp.objects.spin_object.Electron("e1")
    )
    nucleus = system.add_nucleus(
        msp.objects.spin_object.Nucleus("n1")
    )

    system.add_interaction(
        msp.objects.interactions.Zeeman_Interaction(
            "field", electron, Vector("0 0 1")
        )
    )
    system.add_interaction(
        msp.objects.interactions.Hyperfine_Interaction(
            "hf", electron, nucleus,
            msp.maths.tensor.Isotropic("1.0")
        )
    )
    system.add_state(msp.objects.State("initial", {electron: 1, nucleus: 1}))
    system.set_property("initialstate", "initial")

    project = msp.runtime.Project("object_model")
    project.add_spin_system(system)
    project.set_settings(msp.objects.Settings("general", steps=20))

The spin indices passed to `State` are resolved using each spin’s index
mapping. A state may also be supplied as raw MolSpin text using
`State.from_text`. Nuclei can cause state definitions to be expanded
into nuclear permutations when states are added to a spin system.

`Settings(name, steps=1, **properties)` creates a general settings
block. For project deployment, the settings block’s `steps` value is the
default number of MSD files (jobs) to generate. The value written as
`steps` in each generated MSD file is configured separately with
`steps_per_simulation`; it defaults to 1. Thus, `steps` passed to
`Deploy` or `SubmitToHPC` counts files, while `steps_per_simulation`
controls the MolSpin steps inside each file.
`Task(name, type, **properties)` creates a run task; the type and
properties must be valid for the MolSpin executable. Use
`project.add_task(task)` to include it in the project.

# Actions and parameter sweeps

## Binding an action

An action can target a dictionary variable with a dotted key path, or a
property on a Python object. Dictionary-bound action keys are resolved
case-insensitively. The following example is based on the checked-in
nitrogen-vacancy strain-relaxation example and expects the corresponding
MSD file to contain the named interaction properties.

    import math
    import MolSpinPy as msp

    input_data = msp.msd.MsdHandling.ConvertMSDtoDictionary(
        "NV_centre_N14_strain_relaxation.msd"
    )
    if input_data is None:
        raise FileNotFoundError("Could not read the NV MSD input")

    manager = msp.runtime.ActionManager()
    project = msp.runtime.Project("NV_sweep")
    project.attach_dict(input_data)
    project.attach_ActionManager(manager)

    shear = 1 / math.sqrt(2)
    direction = msp.maths.list.List(
        f"1 1 1 {shear:.6f} {shear:.6f} {shear:.6f}"
    )

    function = msp.objects.Actions.LogSpaceList(
        start=1e-5,
        stop=1e-3,
        num=100,
        direction=direction,
        Normalize=False,
        Exponent=False,
        length=6,
    )
    action = msp.objects.Action(
        input_data,
        function,
        duration=100,
        loop=True,
        key="spinsystems.GS.interactions.strain.E",
    )
    manager.add_action(action)

The `Action` constructor accepts timing options including `duration`,
`start`, `interval`, `loop`, and `active`; an optional `parent` creates
a dependent action. Actions are tested when first run and then applied
in priority order. Action functions update the bound value on each
applicable step.

## Built-in action functions

The built-in action package currently exports:

- `LineSpaceScalar` and `LineSpaceVector`;

- `LogSpaceScalar`, `LogSpaceVector`, and `LogSpaceList`;

- `FibonacciSphere` and `RotateVector`.

The line- and log-space functions generate numeric sequences. Vector and
list variants multiply the sequence by a direction; their normalization
options default to true where supported. The log-space functions accept
`Exponent=False` when `start` and `stop` are values rather than base
exponents. `RotateVector` rotates a three-dimensional bound value using
a rotation axis and angle.

## Custom action scripts

Decorate a Python function with `msp.objects.ActionScript`. It receives
the current local step, bound variable, and action state when those
arguments are present in its signature. It must return a replacement
value or modify `var.value`.

    @msp.objects.ActionScript
    def scale_value(step, var, state, factor=2.0):
        return var.value * factor

    scale_action = msp.objects.Action(
        input_data,
        scale_value,
        key="spinsystems.GS.interactions.strain.E",
        factor=2.0,
    )
    manager.add_action(scale_action)

The decorated function’s extra arguments become action parameters. An
`ActionManager` can also attach actions to object-bound variables, for
example `electron.spin` or a supported interaction property.
Object-bound actions are recorded only when the target object belongs to
a spin system attached to the project.

# Local generation and execution

`Project.Deploy()` is the intended combined workflow for generating MSD
files, writing metadata, and optionally running a local MolSpin binary.
The `steps` argument is the number of MSD files (independent MolSpin
jobs) to create. It defaults to the value in the project’s general
settings, or to 1 if not specified there. `steps_per_simulation` sets
the MolSpin `steps` value written in each MSD file’s general settings;
it defaults to 1. Each generated file is then run as one MolSpin job.
For example, `steps=20` and `steps_per_simulation=5` create 20 MSD
files, each configured to run for 5 MolSpin steps.

The binary can be found through the `molspin` argument, `MOLSPIN_PATH`
or `MOLSPIN_HOME`, the system path, or common checkout folders. Other
options include `max_processes` and `NPZ`.

    project.Deploy(
        steps=20,
        steps_per_simulation=5,
        molspin=r"C:\path\to\molspin.exe",
    )

## Output handling

The local deployment creates `outputs/<project-name>/`. If that
project-specific directory already exists, it is removed and recreated;
directories for other project names are not removed. Preserve any
previous results for the same project name before deploying again. The
`AssertFlags` options can disable binary lookup or MolSpin execution
while retaining input generation and integrity verification. For
inspecting one rendered input independently, use `FileTemplate.render`
as shown earlier.

On a successful local run, logs are placed in `molspin_logs/`, task data
in `molspin_results/`, and, when `NPZ=True`, converted archives in
`molspin_npz/`.

# HPC deployment

Remote deployment uses SSH/SFTP through Paramiko and submits Slurm jobs.
Its `steps` and `steps_per_simulation` arguments have the same meaning
and defaults as for local deployment: `steps` is the number of MSD
files/jobs, and `steps_per_simulation` is the MolSpin `steps` value
inside each file (default 1). For example, 20 jobs with 5 simulation
steps each are submitted as 20 MSD files, each configured for 5 steps.
You need an SSH username, host, private-key path, remote working
directory, and a MolSpin checkout or executable on the cluster. A proxy
host may be supplied when required by the cluster’s SSH configuration.

    project.LoadHPC(
        hpc_username="user",
        hpc_host="cluster.example.org",
        hpc_key_path="~/.ssh/id_ed25519",
        remote_working_dir="/home/user/molspin-runs",
        cluster_profile="gwdg",
    )

    job_ids = project.SubmitToHPC(
        hpc_username="user",
        hpc_host="cluster.example.org",
        hpc_key_path="~/.ssh/id_ed25519",
        remote_binary_path="/home/user/MolSpin",
        remote_working_dir="/home/user/molspin-runs",
        partition="standard96",
        walltime="01:00:00",
        max_concurrent=20,
        max_nodes=10,
        steps=20,
        steps_per_simulation=5,
    )
    project.WatchHPC(job_ids)

`SubmitToHPC` also accepts the cluster profile and optional scheduling
settings. Built-in profiles are:

<div class="center">

| Profile | Default partition | Notes |
|:---|:---|:---|
| `gwdg` | `standard96` | Uses a manually installed Armadillo path and a Python virtual environment. |
| `rosa` | `rosa.p` | Loads cluster modules for Armadillo and SciPy; applies make flag overrides. |

</div>

Profiles can be registered or customized with `HpcProfile.register` and
`HpcProfile.with_overrides`. Calling
`HpcProfile.register(profile, remember=True)` also saves the profile to
`hpc_profiles.json` inside the installed MolSpinPy package (override the
location with the `MOLSPINPY_HPC_PROFILES` environment variable), so it
is loaded automatically in every later script on that machine.
`HpcProfile.saved()` lists remembered profiles and
`HpcProfile.forget(name)` removes one. Built-in profiles cannot be
remembered or removed, and reinstalling or upgrading the package may
wipe the file. Use `InstallBinary` to clone and build MolSpin at a new
remote location, or `UpdateBinary` to synchronize and rebuild an
existing checkout. With the default Git assertion enabled, updating may
reset the remote checkout to its upstream branch and remove untracked
files. Review the remote checkout before using this operation.

Remote submissions recreate the project’s remote workspace directory.
Consequently, a subsequent submission for the same project name and
working directory may replace the earlier workspace. Preserve needed
results before resubmitting. Use `DownloadFromHPC` to retrieve a
completed job’s results; optional email and cluster-specific module
settings are also supported by the deployment implementation.
Downloading results also removes the remote project workspace and its
archive after a successful transfer, so do not rely on that workspace as
a long-term backup.

# Metadata and project restoration

Metadata generation is enabled by default. Local deployment writes a
JSON record and a readable Markdown record alongside the generated
files. The record includes the base input, template source, settings,
action tree, function configuration, and execution details. The JSON
execution record stores `steps` (the number of generated MSD files)
separately from `steps_per_simulation` (the MolSpin steps configured
inside each file).

`ProjectLoader` reconstructs a project from a metadata JSON file or a
dictionary. Built-in action functions can be restored without executing
custom code. Custom `ActionScript` source is executable content and is
disabled by default:

    loader = msp.runtime.ProjectLoader(
        "outputs/project/project_metadata.json",
        allow_code=True,
    )
    restored_project = loader.build()

Only load metadata from a trusted source when enabling `allow_code`.
Modules outside the built-in allow-list are refused unless explicitly
permitted with `allow_modules`. The loader verifies recorded hashes for
custom source and dependencies; hash verification is not a substitute
for reviewing code before executing it.

# Processing results

## Converting MolSpin data files

`ProcessSingleFile(filename, output_dir)` reads a whitespace-delimited
data file whose first row contains column names, then saves an NPZ
archive with parsed columns. This is used by local or downloaded-result
workflows when NPZ conversion is enabled.

## Time evolution plots

`TimeEvolutionTool` accepts an NPZ file path or a dictionary of NumPy
arrays. It locates a time column and state/population arrays, then
provides line and stacked-area plots.

    tool = msp.processing.TimeEvolutionTool(
        "results.npz",
        time_key="time(ns)",
    )
    figure, axes = tool.plot_evolution()
    figure.savefig("time-evolution.png", dpi=160)

When data are in a project workspace, a project can be passed to the
tool to resolve local or HPC result paths. The optional time key, state
key(s), labels, and cache directory can be specified when the file’s
column names require explicit selection.

## Eigenvalue spectra

`EigenValueSpectrumTool` accepts a whitespace-delimited file path or a
pandas DataFrame. It recognizes eigenvalue columns named with
`.lambdaN`, reference-state fractions named with `.refN(state)`, and
pairwise mixing columns named `RefMix(a,b)` or `EigenMix(a,b)`. Its
public analysis methods include `plot_spectrum`,
`plot_mixing_fractions`, and `find_anticrossings`. Values and thresholds
use the units and scales in the input data.

# Troubleshooting

<div class="description">

Check the current working directory or pass an absolute path. The parser
returns `None` for a missing file.

Confirm the dot-separated path exists in the parsed dictionary. Use
dictionary keys from the input file; key matching is case-insensitive.

Check the value type and dimensions of the action result against its
target. Actions are tested by the manager before the first normal step.

Pass the executable or installation directory through
`Deploy(molspin=...)`, set `MOLSPIN_PATH`, or add MolSpin to `PATH`.

Set `allow_code=True` only after reviewing the metadata source, and
explicitly permit any required external modules.

This is a known 0.1.0 output path mismatch described in the local
deployment section.

</div>

# Public module map

<div class="center">

| Module | Main purpose |
|:---|:---|
| `msp.msd` | MSD parsing, templates, rendering, and data conversion. |
| `msp.objects` | Spin models, actions, states, transitions, settings, and tasks. |
| `msp.maths` | Vector, list, and tensor representations. |
| `msp.runtime` | Projects, action management, HPC profiles, and metadata loading. |
| `msp.processing` | Time-evolution and eigenvalue-spectrum processing. |
| `msp.utility` | Runtime flags and supporting utilities. |

</div>
