#defines the project class which is the main overarching object that the users need

from asyncio import threads

from . import ActionManager
from ..msd import FileTemplate , MsdHandling, MSDWriter, ProcessSingleFile
from .RemoteDeploy import RemoteHpcOrchestrator
from .Metadata import ProjectMetadata
from ..utility import AssertFlags

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
        self._settings = {} #will be upgraded to a class in future versions 
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
    
    @staticmethod
    def _find_all_paths(binary = "molspin"):
        if os.name == "nt" and not binary.endswith(".exe"):
            binary += ".exe"

        path_env = os.environ.get("PATH", "")
        path_sep = ";" if os.name == "nt" else ":"
        directories = path_env.split(path_sep)

        found_matches = []
        for directory in directories:
            clean_dir = directory.strip('"').strip()
            full_path=os.path.join(clean_dir,binary)
            if os.path.exists(full_path) and os.path.isfile(full_path):
                if os.access(full_path, os.X_OK):
                    found_matches.append(os.path.abspath(full_path))
        return list(set(found_matches))
    
    @staticmethod
    def _is_valid_molspin_dir(full_path):
        if not full_path or not os.path.exists(full_path) or not os.path.isfile(full_path):
            return False
            
        normalized_path = os.path.abspath(full_path).lower()
        path_parts = normalized_path.split(os.sep)
        
        return any("molspin" in part.lower() for part in path_parts)
    
    def _find_molspin_binary(self, custom_path = "../MolSpin"):
        binary_name = "molspin"

        if custom_path:
            if os.path.isdir(custom_path):
                full_path = os.path.join(custom_path, binary_name)
            else:
                full_path = custom_path

            if os.path.exists(full_path) and os.path.isfile(full_path):
                return os.path.abspath(full_path)

        # Check Dedicated Environment Variable
        # Users can set this in their terminal via: export MOLSPIN_PATH=/path/to/custom/molspin/
        env_path = os.environ.get("MOLSPIN_PATH") or os.environ.get("MOLSPIN_HOME")
        if env_path:
            if os.path.isdir(env_path):
                full_path = os.path.join(env_path, binary_name)
            else:
                full_path = env_path

            if os.path.exists(full_path) and os.path.isfile(full_path):
                return os.path.abspath(full_path)

        #current_search_dir = os.path.abspath(os.getcwd())
#
        #for _ in range(4):
        #    potential_subdirs = [
        #        os.path.join(current_search_dir, "molspin"),
        #        os.path.join(current_search_dir, "MolSpin"),
        #        current_search_dir
        #    ]
#
        #    for subdir in potential_subdirs:
        #        if os.path.exists(subdir) and os.path.isdir(subdir):
#
        #            for sub_target in [subdir, os.path.join(subdir, "bin"), os.path.join(subdir, "build")]:
        #                full_path = os.path.join(sub_target, binary_name)
        #                if os.path.exists(full_path) and os.path.isfile(full_path):
        #                    return os.path.abspath(full_path)
#
#
        #    parent_dir = os.path.dirname(current_search_dir)
        #    if parent_dir == current_search_dir:
        #        break
        #    current_search_dir = parent_dir
#
        #return None
    
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
                print("Warning: Could not automatically extract settings. Defaulting to 1 step.")
                self._settings['steps'] = 1
        steps = int(kwargs.get('steps', self._settings['steps']))

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

        print(f"Deploying Project {self._name} : Creating {steps} MSD files")
        for i in range(steps):
            self.manager.run(i)

            #very temp code 
            for val,key in enumerate(self._resolved_dict['tasks']):
                file = f'"{output_dir}/molspin_results/{self._name}-{key}-{i}.'
                logfile = file + 'log"'
                resultfile = file + 'dat"'

                self._resolved_dict['tasks'][key]['logfile'] = logfile
                self._resolved_dict['tasks'][key]['datafile'] = resultfile
            #self._resolved_dict['settings']['general']['steps'] = 1

            snapshot = copy.deepcopy(self._resolved_dict)

            if not self.check_dict_structure(snapshot):
                if io_queue:
                    io_queue.put(None)
                raise ValueError(f"Structural fault at Step {i}: An action corrupted the mandatory schema.")
            
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
            ProjectMetadata(
                self.name,
                self._template,
                self._base_dict,
                self._manager,
                self._settings,
            ).write(output_dir, steps=steps, execution_mode="local")
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
        
        job_id = self._hpc.execute_remote_deployment(
            project_name=self.name,
            steps=int(self._settings.get('steps', 1)),
            resolved_dict=self._resolved_dict,
            manager=self._manager,
            remote_binary_path=remote_binary_path,
            remote_working_dir=remote_working_dir,
            partition=kwargs.pop('partition', self._hpc.default_partition),
            walltime=kwargs.pop('walltime', '01:00:00'),
            calcs_per_node=kwargs.pop('max_concurrent', 20),
            max_nodes=kwargs.pop('max_nodes', 10),
            template=self._template,
            **kwargs
        )
        return job_id
    
    def WatchHPC(self, job_id):
        if self._hpc == None:
            return RuntimeError("No HPC project found")
        self._hpc.watch_hpc_job(job_id=job_id, total_tasks=self._settings.get('steps',1), project_name=self.name, poll_interval=5)
    
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

    def UpdateBinary(self, remote_binary_path, armadillo_path=None, partition=None, hpc_module_list=None):
        if self._hpc == None:
            return RuntimeError("No HPC connection found - use LoadHPC() first to establish a connection.")
        if partition is None:
            partition = self._hpc.default_partition
        check_cmd = f"[ -d '{remote_binary_path}/.git' ] && echo 'VALID' || echo 'INVALID'"
        hpcssh = self._hpc._connect()
        _,stdout,_ = hpcssh.exec_command(check_cmd)
        if stdout.read().decode('utf-8').strip() != "VALID":
            print(f"Error: {remote_binary_path} is not a valid Git repository.")
            return False
        branch_cmd = f"cd {remote_binary_path} && git branch --show-current"
        _, stdout, stderr = hpcssh.exec_command(branch_cmd)
        active_branch = stdout.read().decode('utf-8').strip() or "main"

        print(f"Detected active branch: '{active_branch}' for folder '{remote_binary_path.split('/')[-1]}'")
        fetch_cmd = (
            f"cd {remote_binary_path} && "
            f"git fetch --all"
            #f"git pull origin {active_branch} && "
        )

        exit_status = stderr.channel.recv_exit_status()

        _, stdout, stderr = hpcssh.exec_command(fetch_cmd)
        hash_cmd = (
            f"cd {remote_binary_path} && "
            f"git rev-parse HEAD && "
            f"git rev-parse origin/{active_branch}"
        )
        _, stdout, _ = hpcssh.exec_command(hash_cmd)
        local_hash, remote_hash = stdout.read().decode('utf-8').strip().split()
        if local_hash == remote_hash:
            print(f"MolSpin is already up-to-date on branch '{active_branch}'. No action required.")
            #return True
        if AssertFlags.get("ASSERT_GIT", True):
            upgrade_cmd = (
                f"cd {remote_binary_path} && "
                f"git reset --hard origin/{active_branch} && "
                f"git clean -fd"
            )
            _, stdout, stderr = hpcssh.exec_command(upgrade_cmd)
            stdout_output = stdout.read().decode('utf-8').strip()
            stderr_output = stderr.read().decode('utf-8').strip()
            if stderr.channel.recv_exit_status() != 0:
                print(f"Error during Git pull: {stderr_output}")
                return False
            print(f"Git pull successful. Output:\n{stdout_output}")
        else:
            print("Skipping Git pull due to flag ASSERT_GIT=False. Ensure your repository is up-to-date manually.")
        modules = f"-lopenblas -llapack -fopenmp -DARMA_NO_DEBUG"
        armadillo_string = f"ARMADILLO = -larmadillo {modules}"
        old_path = f"path/to/armadillo/installdir"
        #modify_makefile_cmd = (
        #    f"cd {remote_binary_path} && " 
        #    f"sed -i 's|^{armadillo_string}|# {armadillo_string}|g' makefile && "
        #    f"sed -i 's|^# ARMADILLO = -I/{old_path}/include/ -DARMA_DONT_USE_WRAPPER -fopenmp|ARMADILLO = -I{armadillo_path}/include/ {modules} -DARMA_DONT_USE_WRAPPER|g' makefile"
        #)

        if self._hpc.profile["use_external_armadillo_path"]:
            if not armadillo_path:
                raise ValueError("armadillo_path is required for the 'gwdg' HPC profile.")

            armadillo_cflags = f"ARMADILLO_CFLAGS = -I{armadillo_path}/include"
            armadillo_libs = f"ARMADILLO_LIBS = -L{armadillo_path}/lib64 -larmadillo"

            modify_makefile_cmd = (
                f"cd {remote_binary_path} && "
                f"sed -i 's|^ARMADILLO_CFLAGS ?=.*|{armadillo_cflags}|g' makefile && "
                f"sed -i 's|^ARMADILLO_LIBS ?=.*|{armadillo_libs}|g' makefile"
            )

            _, _, stderr = hpcssh.exec_command(modify_makefile_cmd)
            if stderr.channel.recv_exit_status() != 0:
                print(f"Failed to modify Makefile:\n{stderr.read().decode('utf-8')}")
                return None

        clean_cmd = f"cd {remote_binary_path} && make clean"
        _, _, stderr = hpcssh.exec_command(clean_cmd)
        wait = stderr.channel.recv_exit_status()

        modules = hpc_module_list
        if modules is None:
            modules = self._hpc.profile["build_modules"]
        module_load_string = " && ".join([f"module load {mod}" for mod in modules])
        if module_load_string:
            module_load_string += " && "

        make_args = " ".join(self._hpc.profile["build_make_args"])
        if make_args:
            make_args = f" {make_args}"

        compile_cmd = (
            f"cd {remote_binary_path} && "
            f"srun -p {partition} -N 1 -c 16 --time=00:30:00 --job-name='MolSpinCompile' "
            f"bash -l -c 'module purge && {module_load_string}make -j16{make_args}'"
        )

        _, stdout, stderr = hpcssh.exec_command(compile_cmd)
        if stderr.channel.recv_exit_status() != 0:
            print("C++ Compilation failed on the compute node!")
            print(f"HPC Diagnostics (stderr):\n{stderr.read().decode('utf-8')}")
            return None
        print("MolSpin successfully updated.")

