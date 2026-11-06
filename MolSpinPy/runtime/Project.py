#defines the project class which is the main overarching object that the users need

from asyncio import threads

from . import ActionManager
from ..msd import FileTemplate , MsdHandling, MSDWriter, ProcessSingleFile
from .RemoteDeploy import RemoteHpcOrchestrator
from .Metadata import ProjectMetadata
from ..utility import AssertFlags
from ..objects import object_spec

import enum
import copy
import queue
import os
import shutil
import concurrent.futures
import subprocess
import time
import threading
import sys

class dictMode(enum.Enum):
    REPLACE = 0
    CONCATINATE = 1

class Project():
    def __init__(self, name, template_structure = "BasicTemplate.msd"):
        self._name = name
        
        self._base_dict = {}
        self._compiled_dict = {}
        self._resolved_dict = {} #this is a combination of the base_dict and the compiled_dict
        
        self._manager = None
        self._hpc = None
        self._settings = {} #general settings as a plain dict
        self._spin_systems = {}
        self._settings_obj = None
        self._tasks = {}
        self._template = FileTemplate.get_template(template_structure)
        self._dict_template = FileTemplate._init_input_data()
        self._executable_path = None
        self._working_dir_local = None

    def check_dict_structure(self,new_dict,current_template=None, path=""):
        if current_template is None:
            current_template = self._dict_template

        #MANDATORY = [['spinsystems','actions','settings','outputs','tasks'],['spins','interactions','states','transitions','properties','pulses','operators'],['electrons','nuclei']]
        errors = 0
        for key,value in new_dict.items():
            template_keys = list(current_template.keys())

            if isinstance(current_template, dict) and not current_template:
                continue

            if key in current_template:
                target_template = current_template[key]
            elif len(template_keys) == 1 and isinstance(current_template[template_keys[0]],dict):
                target_template = current_template[template_keys[0]]
            elif len(template_keys) == 1:
                target_template = list(current_template.values())[0]
            else:
                if(key == "__case_map"):
                    continue
                print(f"Key '{key}' is not permitted at {path}")
                errors += 1
                continue
            if isinstance(target_template, dict):
                if not isinstance(value, dict):
                    print(f"'{key}' must be a dictionary structure at {path}")
                    errors += 1
                else:
                    if not self.check_dict_structure(value, target_template, f"{path}{key}/"):
                        errors += 1
            else:
                if value is None:
                    print(f"Mandatory leaf '{key}' is null at {path}")
                    errors += 1
            #if key not in self._dict_template:
            #    print(f"Unexpected key found: {key}")
            #    errors += 1
            #    continue
            #elif isinstance(value, dict):
            #    if not isinstance(self._dict_template[key],dict):
            #        print(f"Type mismatch at {key}: Expected value, found dict")
            #        errors += 1
            #    else:
            #        is_valid = self.check_dict_structure(value)
            #        if not is_valid:
            #            errors += 1
        if errors > 0:
            return False
        else:
            return True
            
    def attach_MSD_file(self, filename):
        self._base_dict = MsdHandling.ConvertMSDtoDictionary(filename)
    def attach_dict(self, dict, mode = dictMode.REPLACE):
        if(self.check_dict_structure(dict)):
            if(self._base_dict != {} and mode == dictMode.REPLACE ):
                print(f"Warning: Overiding project dictionary")
                self._base_dict = dict
            elif (self._base_dict == {}):
                self._base_dict = dict
            elif(mode == dictMode.CONCATINATE):
                self._base_dict = self.ConcatinateDictionarys(self._base_dict, dict)
        else:
            raise ValueError(f"{dict.__name__()} is not in the required format")
    
    def ConcatinateDictionarys(self, base, incoming):
        for key,value in incoming.items():
            if key in base:
                if isinstance(base[key], dict) and isinstance(value, dict):
                    self.ConcatinateDictionarys(base[key], value)
                elif isinstance(base[key],list) and isinstance(value,list):
                    base[key].extend(value)
                else:
                    base[key] = value
            else:
                base[key] = value
        return base
            
    def add_spin_system(self, spin_system):
        self._spin_systems[spin_system.name] = spin_system
        self._sync_dict()
        return spin_system

    def set_settings(self, settings):
        self._settings_obj = settings
        self._sync_dict()
        return settings

    def add_task(self, task):
        self._tasks[task.name] = task
        self._sync_dict()
        return task

    def _sync_dict(self):
        """Write the object-built spin systems, settings and tasks into the project dictionary."""
        if not self._base_dict:
            self._base_dict = FileTemplate._init_input_data()
        for section in ('spinsystems', 'settings', 'tasks'):
            self._base_dict.setdefault(section, {})
        for name, system in self._spin_systems.items():
            ss_name, ss_dict = system.ConvertToDictionary()
            self._base_dict['spinsystems'][ss_name] = ss_dict
        if self._settings_obj is not None:
            s_name, s_dict = self._settings_obj.ConvertToDictionary()
            self._base_dict['settings'] = {s_name: s_dict}
            self._settings = s_dict
        for task in self._tasks.values():
            t_name, t_dict = task.ConvertToDictionary()
            self._base_dict['tasks'][t_name] = t_dict

    def _sync_object_systems(self):
        """Regenerate the dictionary of every spin system driven by object-bound actions.

        Object-bound actions change the objects, not the dictionary, so the dictionary has to be
        rebuilt after each step. Dictionary-bound actions on these systems would be overwritten.
        """
        if self._manager is None or not self._spin_systems:
            return
        driven = set()
        for action in self._manager._actions:
            instance = getattr(action.ptr, "instance", None)
            location = object_spec.locate_object(self._spin_systems, instance) if instance is not None else None
            if location:
                driven.add(location[0])
        for system_name in driven:
            ss_name, ss_dict = self._spin_systems[system_name].ConvertToDictionary()
            target = self._resolved_dict if self._resolved_dict else self._base_dict
            target['spinsystems'][ss_name] = ss_dict

    def attach_ActionManager(self, manager : ActionManager):
        self._manager = manager
    def _extract_settings(self):
        keys = []
        for val, key in enumerate(self.MSDdict['settings']):
            keys.append(key)
        self._settings = self.MSDdict['settings'][keys[0]]
    @property
    def manager(self):
        return self._manager
    @property 
    def MSDdict(self):
        return self._base_dict
    @property
    def name(self):
        return self._name
    
    @staticmethod
    def _VerifySingleFile(file_path, instance):
        if not os.path.exists(file_path):
            return f"MISSING: {os.path.basename(file_path)} does not exist."
        if os.path.getsize(file_path) == 0:
            return f"CORRUPTED: {os.path.basename(file_path)} is empty (0 bytes)."
        
        try:
            trial_dict = MsdHandling.ConvertMSDtoDictionary(file_path)
            if not instance.check_dict_structure(trial_dict):
                return f"SCHEMA FAULT: {os.path.basename(file_path)} failed template rules."
        except Exception as e:
            return f"PARSING CRASH: {os.path.basename(file_path)} failed to read. Error: {e}"
        
        return None
    
    _BINARY_SUBDIRS = ("", "bin", "build", "Release", "release")

    @staticmethod
    def _binary_filenames():
        return ("molspin.exe", "MolSpin.exe") if os.name == "nt" else ("molspin", "MolSpin")

    @staticmethod
    def _is_executable_file(path):
        return os.path.isfile(path) and os.access(path, os.X_OK)

    @classmethod
    def _binary_in_location(cls, location):
        """Resolve a file or a MolSpin directory (checking common build subfolders) to an executable."""
        if not location:
            return None
        location = os.path.abspath(os.path.expanduser(os.path.expandvars(str(location))))
        if os.path.isfile(location):
            return location if cls._is_executable_file(location) else None
        if not os.path.isdir(location):
            return None
        for subdir in cls._BINARY_SUBDIRS:
            for name in cls._binary_filenames():
                candidate = os.path.join(location, subdir, name)
                if cls._is_executable_file(candidate):
                    return candidate
        return None

    def _find_molspin_binary(self, custom_path=None):
        """Locate the local MolSpin executable.

        Search order (first hit wins):
          1. ``custom_path`` (the ``molspin=`` kwarg of Deploy): a binary or a MolSpin directory
          2. ``MOLSPIN_PATH`` / ``MOLSPIN_HOME`` environment variables (same forms)
          3. ``molspin`` on the system PATH
          4. Common checkout locations: ./MolSpin, ../MolSpin and their parents' siblings
        Directories are checked directly and in bin/, build/ and Release/.
        Returns the absolute path, or None (after printing where it looked).
        """
        searched = []

        def try_location(label, location):
            if not location:
                return None
            found = self._binary_in_location(location)
            searched.append(f"{label}: {location}" + ("" if found else " (not found)"))
            return found

        found = try_location("molspin= argument", custom_path)
        if found:
            return found

        for var in ("MOLSPIN_PATH", "MOLSPIN_HOME"):
            found = try_location(f"${var}", os.environ.get(var))
            if found:
                return found

        for name in self._binary_filenames():
            on_path = shutil.which(name)
            if on_path:
                return os.path.abspath(on_path)
        searched.append("system PATH (not found)")

        cwd = os.path.abspath(os.getcwd())
        search_roots = [cwd, os.path.dirname(cwd), os.path.dirname(os.path.dirname(cwd))]
        for root in dict.fromkeys(search_roots):
            for folder in ("MolSpin", "molspin"):
                found = try_location("checkout", os.path.join(root, folder))
                if found:
                    return found

        print("Could not find a MolSpin executable. Searched:\n  " + "\n  ".join(searched))
        print("Pass Deploy(molspin='/path/to/MolSpin'), set MOLSPIN_PATH, or add molspin to PATH.")
        return None

    def VerifyIntegrity(self, output_dir, expected_steps, file_prefix):
        print(f"\n--- Verifying file creation for '{output_dir}' ---")
        files_to_check = []
        sample_rate = 100
        max_workers = 20
        start_id = 0
        for i in range(expected_steps):
            if i % sample_rate == 0 or i == (expected_steps - 1):
                current_id = start_id + i
                filename = f"{file_prefix}_{current_id}.msd"
                files_to_check.append(os.path.join(output_dir, filename))
        failed_reports = []

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_file = {
                executor.submit(self._VerifySingleFile, path, self): path 
                for path in files_to_check
            }
        
        for future in concurrent.futures.as_completed(future_to_file):
            error_msg = future.result()
            if error_msg:
                failed_reports.append(error_msg)


        print("-------------------------------------------------")
        print(f"Verification Summary: Sampled {len(files_to_check)} files")
        if not failed_reports:
            print("SUCCESS: All checked MSD files passed validation")
            return True
        else:
            print(f"FAILURE: Detected {len(failed_reports)} issues during file audit:")
            for issue in failed_reports:
                print(f" - {issue}")
            return False

    @staticmethod   
    def _execute_single_file_local(executable_path, file_path, log_dir, NPZ = False, npz_dir = None, silent = True):
        base_name = os.path.basename(file_path)
        log_file_path = os.path.join(log_dir, f"{base_name}.log")
        command = [executable_path,"-p","2", file_path]
        components = file_path.split(os.sep)
        #print(components)
        #file_directory = os.path.dirname(os.path.abspath(file_path))

        #custom_env = os.environ.copy()
        #custom_env["OMP_NUM_THREADS"] = 2
        #custom_env["OPENBLAS_NUM_THREADS"] = 2

        try:
            with open(log_file_path, 'w') as log_f:
                process = subprocess.run(
                    command, 
                    stdout=log_f, 
                    stderr=subprocess.PIPE, 
                    text=True, 
                    check=True,
                    #env=custom_env
                    #cwd=file_directory
                )
            #return None 
        except subprocess.CalledProcessError as e:
            return f"CRASH: {base_name} failed. Exit Code {e.returncode}. Stderr: {e.stderr.strip()}"
        except Exception as e:
            return f"SYSTEM ERROR: Failed to spawn process for {base_name}. Details: {e}"

        if(NPZ):
            result_paths = []
            folder = os.path.join(*components[:-1], "molspin_results")
            #print(folder)
            split_msd = components[-1].split(".")[0].split("_")
            index = split_msd[-1]
            #print([split_msd, index])
            for f in os.listdir(folder):
                #f will look like components[-1] but with some extra text in the last bit
                #e.g. components[-1] = "StrainT1times_2.msd" but f will be "StrainT1times-TE_2.dat"
                if not ".dat" in f:
                    continue
                index_string = "-{index}.".format(index=index)
                #if index_string in f:
                    #print(f)
                if split_msd[0] in f and index_string in f:
                    result_paths.append(os.path.join(folder, f))
            #print(result_paths)
            for results_path in result_paths:
                ProcessSingleFile(results_path, npz_dir, silent=silent)
                #delete the msd file
                os.remove(results_path)
            os.remove(file_path)
        return None



    def RunMolSpinDeploymentLocal(self, output_dir, parallel = True, max_workers = 20, NPZ = False):
        print(f"\n-----Starting MolSpin Execution-----")
        if not self._executable_path or not os.path.exists(self._executable_path):
            raise FileNotFoundError(
                f"Cannot launch deployment: '{self._executable_path}' is not a valid executable. "
                "Verify your custom subdirectory path initialization."
            )
        
        log_dir = os.path.join(output_dir, "molspin_logs")
        result_dir = os.path.join(output_dir, "molspin_results")
        npz_dir = os.path.join(output_dir, "molspin_npz")
        os.makedirs(log_dir, exist_ok=True)
        os.makedirs(result_dir, exist_ok=True)
        os.makedirs(npz_dir, exist_ok=True)
        msd_files = [
            os.path.join(output_dir, f) for f in os.listdir(output_dir) 
            if f.endswith(".msd") and "_INITIAL" not in f
        ]
        msd_files.sort()

        if not msd_files:
            print(f"Aborting execution: No runnable .msd files found in '{output_dir}'.")
            return False
        
        print(f"Found {len(msd_files)} states. Mode: {'Parallel Pool' if parallel else 'Sequential Pipeline'}")
        failed_runs = []

        start_time = time.time()
        completed_counter = 0
        progress_lock = threading.Lock()
        total_files = len(msd_files)
        bar_length = 50

        def update_progress():
            nonlocal completed_counter
            with progress_lock:
                completed_counter += 1

                elapsed = time.time() - start_time
                pace = completed_counter / elapsed if elapsed > 0 else 0

                if pace > 0:
                    remaining_files = total_files - completed_counter
                    ete_seconds = remaining_files / pace
                    ete_str = time.strftime("%H:%M:%S", time.gmtime(ete_seconds))
                else:
                    ete_str = "--:--:--"

                elapsed_str = time.strftime("%H:%M:%S", time.gmtime(elapsed))

                #bar_length = 50
                filled_length = int(round(bar_length * completed_counter / float(total_files)))
                percent = (completed_counter / float(total_files)) * 100
                bar = '█' * filled_length + '-' * (bar_length - filled_length)

                sys.stdout.write(
                    f"\rDeploying Experiment: [{bar}] {completed_counter}/{total_files} "
                    f"({percent:.1f}%) | Time: {elapsed_str} < Remaining: {ete_str} | {pace:.1f} sim/s"
                )
                sys.stdout.flush()

        sys.stdout.write(f"Deploying Experiment: [{' ' * bar_length}] 0/{total_files} (0.0%) | Time: 00:00:00 < Remaining: --:--:--\r")
        sys.stdout.flush()
        
        if parallel:
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_file = {
                    executor.submit(self._execute_single_file_local, self._executable_path, path, log_dir, NPZ, npz_dir, silent=True): path 
                    for path in msd_files
                }
                
                for future in concurrent.futures.as_completed(future_to_file):
                    error_report = future.result()
                    if error_report:
                        failed_runs.append(error_report)
                    update_progress()
        else:
            for file_path in msd_files:
                error_report = self._execute_single_msd_file(self._executable_path, file_path, log_dir)
                if error_report:
                    failed_runs.append(error_report)
                update_progress()

        print("\n")
        end_time = time.time()
        total_elapsed_seconds = end_time - start_time
        hours, rem = divmod(total_elapsed_seconds, 3600)
        minutes, seconds = divmod(rem, 60)

        print("==================================================")
        print(rf" EXPERIMENT {self._name.upper()} ANALYTICS SUMMARY")
        print("==================================================")
        print(f" * Execution Runtime : {int(hours)}h {int(minutes)}m {seconds:.2f}s")
        print(f" * Total Files Run   : {total_files}")
        print(f" * Successful % : {total_files - len(failed_runs)}/{total_files}")
        print(f" * Average Pace : {total_elapsed_seconds / total_files:.3f} seconds per simulation frame")
        print("--------------------------------------------------")
        
        if not failed_runs:
            print("SUCCESS: Every file batch cleared processing smoothly!")
            return True
        else:
            print(f"WARNING: Anomaly thresholds triggered across {len(failed_runs)} runs:")
            for fault in failed_runs[:5]:
                print(f"  - {fault}")
            if len(failed_runs) > 5:
                print(f"  ... [Truncated]. Check the output log folders for full details: {log_dir}")
            return False

    def _dryRun(self):
        steps = int(self._settings['steps'])
        for i in range(steps):
            self.manager.run(i,True)

    def Deploy(self, **kwargs):
        """Deploy a local MolSpin simulation project.
        
        Args:
            steps (int): Number of MSD files (jobs) to create. Default from settings or 1.
            steps_per_simulation (int): Number of simulation steps within each MSD file. 
                                        Default from settings.steps_per_simulation or 1.
            NPZ (bool): Convert results to NPZ format. Default False.
            max_processes (int): Maximum parallel workers. Default 10.
            molspin (str): Custom path to MolSpin binary.
        """
        npz = kwargs.get('NPZ', False)
        max_processes = kwargs.get('max_processes', 10)
        if not self._executable_path and AssertFlags.get("ASSERT_BINARY", True):
            self._executable_path = self._find_molspin_binary(custom_path=kwargs.get("molspin", None))
            if not self._executable_path:
                raise RuntimeError("MolSpin installation not found")

        current_dicts = []
        if self._resolved_dict == {}:
            self._resolved_dict = self._base_dict

        if self._manager is None:
            raise ValueError("Deployment failed: No ActionManager attached to the project.")
        if not self._settings or 'steps' not in self._settings:
            try:
                self._extract_settings()
            except:
                print("Warning: Could not automatically extract settings. Defaulting to 1 job with 1 step per simulation.")
                self._settings['steps'] = 1
        
        # steps: how many MSD files to create
        steps = int(kwargs.get('steps', self._settings['steps']))
        
        # steps_per_simulation: how many steps within each MSD file
        steps_per_simulation = int(kwargs.get('steps_per_simulation', self._settings.get('steps_per_simulation', 1)))

        io_queue = None

        target = f"outputs/{self._name}/"
        output_dir = os.path.dirname(target)

        if os.path.exists(output_dir):
            print(f"Warning: Overwriting existing directory structure at '{output_dir}'")
            shutil.rmtree(output_dir)

        if output_dir:
            print(f"Creating project directory: {target}")
            os.makedirs(output_dir, exist_ok=True)

        self._working_dir_local = output_dir

        io_queue = queue.Queue()
        workers = []
        num_workers = 20
        print(f"Spawning {num_workers} parallel MSD file writing threads...")
        for _ in range(num_workers):
            t = MSDWriter(self._template,io_queue,self._name,target)
            t.start()
            workers.append(t)

        print(f"Deploying Project {self._name} : Creating {steps} MSD files with {steps_per_simulation} steps per simulation")
        initial_input = copy.deepcopy(self._resolved_dict)  # before actions mutate it
        metadata = ProjectMetadata(self.name, self._template, initial_input, self._manager, self._settings,
                                   spin_systems=self._spin_systems)
        for i in range(steps):
            self.manager.run(i)
            self._sync_object_systems()

            #very temp code 
            for val,key in enumerate(self._resolved_dict['tasks']):
                file = f'"{output_dir}/molspin_results/{self._name}-{key}-{i}.'
                logfile = file + 'log"'
                resultfile = file + 'dat"'

                self._resolved_dict['tasks'][key]['logfile'] = logfile
                self._resolved_dict['tasks'][key]['datafile'] = resultfile

            snapshot = copy.deepcopy(self._resolved_dict)
            
            # Set steps_per_simulation in the MSD file settings
            if 'settings' in snapshot and 'general' in snapshot['settings']:
                snapshot['settings']['general']['steps'] = steps_per_simulation

            if not self.check_dict_structure(snapshot):
                if io_queue:
                    io_queue.put(None)
                raise ValueError(f"Structural fault at Job {i}: An action corrupted the mandatory schema.")
            
            current_dicts.append(snapshot)

            if io_queue:
                io_queue.put((i, snapshot))
        if io_queue:
            print("Simulation steps complete. Finalizing background disk writes...")
            for i in range(num_workers):
                io_queue.put(None)
            for t in workers:
                t.join()
            print("File streaming threads cleanly closed.")
        is_healthy = self.VerifyIntegrity(output_dir, expected_steps=steps, file_prefix=self._name)
        if not is_healthy:
            raise IOError("Deployment verification failed! Data on disk is incomplete or corrupted.")

        if AssertFlags.get("ASSERT_METADATA"):
            metadata.write(output_dir, steps=steps, steps_per_simulation=steps_per_simulation, execution_mode="local")
        else:
            print("Skipping metadata generation due to ASSERT_METADATA=False")

        
        if AssertFlags.get("ASSERT_DEPLOY", True):
            execution_clear = self.RunMolSpinDeploymentLocal(
                output_dir=output_dir,
                parallel=True,
                max_workers=max_processes,
                NPZ = npz
        )
        else:
            execution_clear = True
        if not execution_clear:
            raise RuntimeError("Deployment pipeline halted: Anomalies caught during MolSpin processing execution.")
        
        if not npz:
            return [f"outputs/{output_dir}",f"outputs/{output_dir}/molspin_results"]
        else:
            return [f"outputs/{output_dir}",f"outputs/{output_dir}/molspin_npz"]

    def LoadHPC(self, hpc_username, hpc_host, hpc_key_path, remote_working_dir, **kwargs):
        if self._hpc == None:
            cluster_profile = kwargs.pop('cluster_profile', 'gwdg')
            self._hpc = RemoteHpcOrchestrator(
                hpc_username,
                hpc_host,
                hpc_key_path,
                kwargs.pop('proxy_host', None),
                cluster_profile=cluster_profile,
            )
            self._hpc.remote_working_dir = remote_working_dir
        
    def SubmitToHPC(self, hpc_username, hpc_host, hpc_key_path, remote_binary_path, remote_working_dir, **kwargs):
        """Submit a project to HPC cluster for execution.
        
        Args:
            hpc_username: HPC cluster username
            hpc_host: HPC cluster hostname
            hpc_key_path: Path to SSH private key
            remote_binary_path: Path to MolSpin binary on HPC
            remote_working_dir: Working directory on HPC
            steps (int): Number of MSD files (jobs) to create. Default from settings or 1.
            steps_per_simulation (int): Number of simulation steps within each MSD file.
                                        Default from settings.steps_per_simulation or 1.
            partition: SLURM partition. Default from cluster profile.
            walltime: SLURM walltime limit. Default '01:00:00'.
            max_concurrent: Max concurrent processes per node. Default 20.
            max_nodes: Max nodes to use. Default 10.
            **kwargs: Additional HPC parameters
        """
        if self._hpc == None:
            cluster_profile = kwargs.pop('cluster_profile', 'gwdg')
            self._hpc = RemoteHpcOrchestrator(
                hpc_username,
                hpc_host,
                hpc_key_path,
                kwargs.pop('proxy_host', None),
                cluster_profile=cluster_profile,
            )
            self._hpc.remote_working_dir = remote_working_dir
        else:
            kwargs.pop('cluster_profile', None)
            kwargs.pop('proxy_host', None)

        if self._resolved_dict == {}:
            self._resolved_dict = self._base_dict
        
        # steps: how many MSD files to create
        steps = int(kwargs.pop('steps', self._settings.get('steps', 1)))
        
        # steps_per_simulation: how many steps within each MSD file
        steps_per_simulation = int(kwargs.pop('steps_per_simulation', self._settings.get('steps_per_simulation', 1)))
        
        job_id = self._hpc.execute_remote_deployment(
            project_name=self.name,
            steps=steps,
            steps_per_simulation=steps_per_simulation,
            resolved_dict=self._resolved_dict,
            manager=self._manager,
            remote_binary_path=remote_binary_path,
            remote_working_dir=remote_working_dir,
            partition=kwargs.pop('partition', self._hpc.default_partition),
            walltime=kwargs.pop('walltime', '01:00:00'),
            calcs_per_node=kwargs.pop('max_concurrent', 20),
            max_nodes=kwargs.pop('max_nodes', 10),
            template=self._template,
            post_step=self._sync_object_systems,
            spin_systems=self._spin_systems,
            estimated_memory = kwargs.pop('estimated_memory', 1024), #at some point introduce a memory estimator function
            **kwargs
        )
        return job_id
    
    def WatchHPC(self, job_id):
        """Watch HPC job progress.
        
        Args:
            job_id: The SLURM job ID(s) to watch
        """
        if self._hpc == None:
            return RuntimeError("No HPC project found")
        self._hpc.watch_hpc_job(job_id=job_id, total_tasks=self._settings.get('steps', 1), project_name=self.name, poll_interval=5)
    
    def DownloadFromHPC(self, job_id, remote_working_dir, local_npz_output_path):
        #orchestrator = RemoteHpcOrchestrator(hpc_username, hpc_host, hpc_key_path, proxy_host)
        if self._hpc == None:
            return RuntimeError("No HPC project found")
        return self._hpc.download_remote_deployment(
            project_name=self.name,
            remote_working_dir=remote_working_dir,
            local_npz_path=local_npz_output_path,
            job_ids=job_id
        )

    def UpdateBinary(self, remote_binary_path, armadillo_path="", partition=None, hpc_module_list=None):
        """Sync the remote MolSpin checkout and rebuild it as described by the active HpcProfile."""
        if self._hpc == None:
            return RuntimeError("No HPC connection found - use LoadHPC() first to establish a connection.")
        profile = self._hpc.profile
        partition = partition or profile.build_partition or profile.default_partition
        modules = hpc_module_list or profile.build_modules
        hpcssh = self._hpc._connect()
        run_remote = self._make_remote_runner(hpcssh)

        try:
            check_cmd = f"[ -d '{remote_binary_path}/.git' ] && echo 'VALID' || echo 'INVALID'"
            exit_status, stdout_output, stderr_output = run_remote(check_cmd)
            if exit_status != 0 or stdout_output.strip() != "VALID":
                print(f"Error: {remote_binary_path} is not a valid Git repository.")
                if stderr_output.strip():
                    print(stderr_output.strip())
                return False

            branch_cmd = f"cd {remote_binary_path} && git branch --show-current"
            exit_status, stdout_output, stderr_output = run_remote(branch_cmd)
            if exit_status != 0:
                print(f"Failed to determine active branch:\n{stderr_output.strip()}")
                return False
            active_branch = stdout_output.strip() or "main"
            print(f"Detected active branch: '{active_branch}' for folder '{remote_binary_path.split('/')[-1]}'")

            fetch_cmd = f"cd {remote_binary_path} && git fetch --all"
            exit_status, _, stderr_output = run_remote(fetch_cmd)
            if exit_status != 0:
                print(f"Git fetch failed:\n{stderr_output.strip()}")
                return False

            hash_cmd = (
                f"cd {remote_binary_path} && "
                f"git rev-parse HEAD && "
                f"git rev-parse origin/{active_branch}"
            )
            exit_status, stdout_output, stderr_output = run_remote(hash_cmd)
            if exit_status != 0:
                print(f"Failed to compare local and remote Git revisions:\n{stderr_output.strip()}")
                return False

            revisions = stdout_output.strip().split()
            if len(revisions) != 2:
                print(f"Unexpected Git revision output: {stdout_output!r}")
                return False
            local_hash, remote_hash = revisions

            status_cmd = f"cd {remote_binary_path} && git status --porcelain"
            exit_status, status_output, stderr_output = run_remote(status_cmd)
            if exit_status != 0:
                print(f"Failed to inspect Git working tree:\n{stderr_output.strip()}")
                return False

            if AssertFlags.get("ASSERT_GIT", True):
                if local_hash != remote_hash or status_output.strip():
                    upgrade_cmd = (
                        f"cd {remote_binary_path} && "
                        f"git reset --hard origin/{active_branch} && "
                        f"git clean -fd"
                    )
                    exit_status, stdout_output, stderr_output = run_remote(upgrade_cmd)
                    if exit_status != 0:
                        print(f"Error during Git synchronization:\n{stderr_output.strip()}")
                        return False
                    print(f"Git synchronization successful. Output:\n{stdout_output.strip()}")
                else:
                    print(f"MolSpin is already up-to-date and clean on branch '{active_branch}'.")
            else:
                print("Skipping Git synchronization due to ASSERT_GIT=False. Ensure the repository is in the desired state manually.")

            if not self._build_remote_binary(run_remote, remote_binary_path, armadillo_path, partition, modules):
                return False

            print("MolSpin successfully updated and compiled.")
            return True
        finally:
            hpcssh.close()

    def InstallBinary(self, remote_binary_path, repo_url, armadillo_path="", branch=None,
                      partition=None, hpc_module_list=None):
        """Clone MolSpin onto the cluster, build it, and (if the profile needs one) create the Python venv.

        remote_binary_path must not already contain a checkout; use UpdateBinary for that.
        """
        if self._hpc == None:
            return RuntimeError("No HPC connection found - use LoadHPC() first to establish a connection.")
        profile = self._hpc.profile
        partition = partition or profile.build_partition or profile.default_partition
        modules = hpc_module_list or profile.build_modules
        remote_binary_path = remote_binary_path.rstrip("/")
        hpcssh = self._hpc._connect()
        run_remote = self._make_remote_runner(hpcssh)

        try:
            exit_status, stdout_output, _ = run_remote(
                f"[ -e '{remote_binary_path}' ] && echo 'EXISTS' || echo 'FREE'"
            )
            if exit_status != 0:
                print("Could not inspect the remote install location.")
                return False
            if stdout_output.strip() == "EXISTS":
                exit_status, stdout_output, _ = run_remote(f"ls -A '{remote_binary_path}' | head -n 1")
                if stdout_output.strip():
                    print(f"Error: {remote_binary_path} already exists and is not empty. Use UpdateBinary() instead.")
                    return False

            if profile.use_external_armadillo_path and not armadillo_path:
                print("This cluster profile requires armadillo_path to patch the makefile.")
                return False

            parent_dir = os.path.dirname(remote_binary_path) or "."
            branch_arg = f"--branch {branch} " if branch else ""
            clone_cmd = f"mkdir -p '{parent_dir}' && git clone {branch_arg}'{repo_url}' '{remote_binary_path}'"
            print(f"Cloning {repo_url} into {remote_binary_path}...")
            exit_status, _, stderr_output = run_remote(clone_cmd)
            if exit_status != 0:
                print(f"Git clone failed:\n{stderr_output.strip()}")
                return False

            if profile.activate_venv:
                if not self._create_remote_venv(run_remote, remote_binary_path, profile):
                    return False

            if not self._build_remote_binary(run_remote, remote_binary_path, armadillo_path, partition, modules):
                return False

            print(f"MolSpin successfully installed at {remote_binary_path}.")
            return True
        finally:
            hpcssh.close()

    @staticmethod
    def _make_remote_runner(hpcssh):
        """Return run_remote(command) -> (exit_status, stdout, stderr) over an open SSH client."""
        def run_remote(command):
            _, stdout, stderr = hpcssh.exec_command(command)
            channel = stdout.channel
            stdout_chunks = []
            stderr_chunks = []

            while True:
                while channel.recv_ready():
                    stdout_chunks.append(channel.recv(65536))
                while channel.recv_stderr_ready():
                    stderr_chunks.append(channel.recv_stderr(65536))

                if channel.exit_status_ready():
                    while channel.recv_ready():
                        stdout_chunks.append(channel.recv(65536))
                    while channel.recv_stderr_ready():
                        stderr_chunks.append(channel.recv_stderr(65536))
                    break

                time.sleep(0.01)

            exit_status = channel.recv_exit_status()
            stdout_text = b"".join(stdout_chunks).decode("utf-8", errors="replace")
            stderr_text = b"".join(stderr_chunks).decode("utf-8", errors="replace")
            return exit_status, stdout_text, stderr_text
        return run_remote

    def _create_remote_venv(self, run_remote, remote_binary_path, profile):
        module_load_string = " && ".join(f"module load {mod}" for mod in profile.runtime_modules)
        venv_path = f"{remote_binary_path}/{profile.venv_subpath}"
        packages = " ".join(profile.venv_packages)
        venv_cmd = (
            f"bash -l -c 'module purge && {module_load_string} && "
            f"python -m venv {venv_path} && "
            f"{venv_path}/bin/python -m pip install --upgrade pip {packages}'"
        )
        print(f"Creating Python virtualenv at {venv_path}...")
        exit_status, _, stderr_output = run_remote(venv_cmd)
        if exit_status != 0:
            print(f"Virtualenv creation failed:\n{stderr_output.strip()}")
            return False
        return True

    def _build_remote_binary(self, run_remote, remote_binary_path, armadillo_path, partition, modules):
        """Patch the makefile if the profile needs it, then clean and compile on a compute node."""
        profile = self._hpc.profile
        if profile.use_external_armadillo_path:
            if not armadillo_path:
                print("This cluster profile requires armadillo_path to patch the makefile.")
                return False
            makefile_cmd = (
                f"cd {remote_binary_path} && "
                f"sed -i 's|^ARMADILLO_CFLAGS ?=.*|ARMADILLO_CFLAGS = -I{armadillo_path}/include|g' makefile && "
                f"sed -i 's|^ARMADILLO_LIBS ?=.*|ARMADILLO_LIBS = -L{armadillo_path}/lib64 -larmadillo|g' makefile"
            )
            exit_status, _, stderr_output = run_remote(makefile_cmd)
            if exit_status != 0:
                print(f"Failed to modify Makefile:\n{stderr_output.strip()}")
                return False

        clean_cmd = f"cd {remote_binary_path} && make clean"
        exit_status, _, stderr_output = run_remote(clean_cmd)
        if exit_status != 0:
            print(f"make clean failed:\n{stderr_output.strip()}")
            return False

        module_load_string = " && ".join(f"module load {mod}" for mod in modules)
        make_args = " ".join(profile.build_make_args)
        compile_cmd = (
            f"cd {remote_binary_path} && "
            f"srun -p {partition} -N 1 -c 16 --time=00:30:00 --job-name='MolSpinCompile' "
            f"bash -l -c 'module purge && {module_load_string} && "
            f"make -j16 {make_args}'"
        )

        print(f"Submitting MolSpin compilation through Slurm partition '{partition}'...")
        exit_status, stdout_output, stderr_output = run_remote(compile_cmd)
        if exit_status != 0:
            print("C++ compilation failed on the compute node.")
            if stdout_output.strip():
                stdout_tail = "\n".join(stdout_output.strip().splitlines()[-40:])
                print(f"HPC Diagnostics (stdout tail):\n{stdout_tail}")
            if stderr_output.strip():
                print(f"HPC Diagnostics (stderr):\n{stderr_output.strip()}")
            return False
        return True

    def GenerateParamMap(self,steps):
        base_state = copy.deepcopy(self._resolved_dict)
        param_map = {}
        for i in range (0,steps):
            params = self.manager.run(i,True)
            param_map[i] = params
        self._resolved_dict = base_state
        return param_map

