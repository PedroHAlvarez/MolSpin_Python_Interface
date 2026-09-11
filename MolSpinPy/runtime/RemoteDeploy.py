import os
import time
import copy
import paramiko
import numpy as np
import math

import sys
import time
import io
import re

from . import ActionManager
from ..msd import FileTemplate , MsdHandling, MSDWriter
from .Metadata import ProjectMetadata
from ..utility import AssertFlags

class RemoteHpcOrchestrator:
    def __init__(self, username, hpc_host, key_path, proxy_host=None):
        self.username = username
        self.hpc_host = hpc_host
        self.key_path = os.path.expanduser(key_path)
        self.proxy_host = proxy_host
        self.remote_working_dir = None

    @staticmethod
    def calculate_hpc_schedule(total_tasks, max_nodes=5, max_concurrent=20, 
                           est_single_job_hours=20.0, max_walltime_hours=48.0, 
                           safety_buffer=1.2):
        
        total_concurrent_capacity = max_nodes * max_concurrent
        total_waves_needed = math.ceil(total_tasks / max_concurrent / max_nodes)
        buffered_job_time = est_single_job_hours * safety_buffer
        max_safe_waves_per_allocation = math.floor(max_walltime_hours / buffered_job_time)
        if max_safe_waves_per_allocation < 1:
            raise ValueError( f"A single simulation with buffer ({buffered_job_time}h) "
            f"exceeds the partition limit ({max_walltime_hours}h)")

        print(f"--- HPC Scheduling Evaluation ---")
        print(f"Total tasks to run: {total_tasks}")
        print(f"Estimated single job duration (with buffer): {buffered_job_time:.2f} hours")
        print(f"Max safe consecutive waves per SLURM job: {max_safe_waves_per_allocation}")

        batches = []
        tasks_remaining = total_tasks

        while tasks_remaining > 0:
            max_tasks_for_this_batch = total_concurrent_capacity * max_safe_waves_per_allocation
            batch_tasks = min(tasks_remaining, max_tasks_for_this_batch)

            if batch_tasks <= total_concurrent_capacity:
                batch_nodes = math.ceil(batch_tasks / max_concurrent)
                batch_calcs_per_node = max_concurrent
                batch_waves = 1
            else:
                batch_nodes = max_nodes
                batch_calcs_per_node = math.ceil(batch_tasks / max_nodes)
                batch_waves = math.ceil(batch_calcs_per_node / max_concurrent)

            batch_walltime_hours = math.ceil(batch_waves * buffered_job_time)
            walltime_str = f"{batch_walltime_hours:02d}:00:00"

            batches.append({
                "tasks_in_batch": batch_tasks,
                "nodes": batch_nodes,
                "calcs_per_node": batch_calcs_per_node,
                "walltime": walltime_str
            })

            tasks_remaining -= batch_tasks

        return batches

    def _generate_slurm_script(self, remote_results_dir, remote_logs_dir, remote_binary_path, 
                           partition, walltime, total_tasks, project_name, max_concurrent, 
                           calcs_per_node, total_array_nodes,max_nodes, armadillo_path,email_address = ""):
        print(f"--- Generating Slurm Script Blueprint ---")
        print(f" - Project: {project_name}")
        print(f" - Active Walltime Limit: {walltime}")
        print(f" - Array Width (Nodes Requested): 1-{total_array_nodes}")
        print(f" - Max Concurrent Processes per Node: {max_concurrent}")
        print(f" - Max Concurrent Nodes: {max_nodes}")
        print(f" - Total Calculations Assigned to each Node: {calcs_per_node}\n")

        cal_per_node = calcs_per_node
        manifest_name = f"{project_name}_hpc.jsonl.gz"
        worker_path = f"hpc_worker.py"
        email_script = ""
        if email_address != "":
            email_script = f"#SBATCH --mail-type=BEGIN,END,FAIL\n#SBATCH --mail-user={email_address}"

        job_script = f"""#!/bin/bash
#SBATCH --job-name=molspin_python_{project_name}
#SBATCH --partition={partition}
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task={max_concurrent}
#SBATCH --time={walltime}
#SBATCH --array=1-{total_array_nodes}%{max_nodes}
#SBATCH --output={remote_logs_dir}/array_%A_%a.out
#SBATCH --error={remote_logs_dir}/array_%A_%a.err
{email_script}


module purge
module load gcc/11.5.0
module load openblas
module load netlib-lapack
module load python/3.11.9

export LD_LIBRARY_PATH="{armadillo_path}/lib64:$LD_LIBRARY_PATH"

source {remote_binary_path}/molspinpyi_env/bin/activate

cd {remote_results_dir}
CALCS_PER_NODE={cal_per_node}
MAX_CONCURRENT={max_concurrent}
START_LINE=$(((SLURM_ARRAY_TASK_ID - 1) * CALCS_PER_NODE + 1))
END_LINE=$((SLURM_ARRAY_TASK_ID * CALCS_PER_NODE))

MANIFEST_PATH={manifest_name}
WORKER_PATH={worker_path}

for (( line_idx=$START_LINE; line_idx<=$END_LINE; line_idx++ )); do
    if [ $line_idx -gt {total_tasks} ]; then
        echo "Reached end of job map"
        break
    fi

    while [ $(jobs -rp | wc -l) -ge $MAX_CONCURRENT ]; do
        sleep 1
    done

    python "$WORKER_PATH" \
        "$MANIFEST_PATH"  \
        "$line_idx"        \
        "{remote_results_dir}" \
        "{remote_logs_dir}" \
        "{remote_binary_path}" &
done
wait 

echo "Array node $SLURM_ARRAY_TASK_ID computations done"
"""
        
        epilogue_script = rf"""#!/bin/bash
#SBATCH --job-name=molspin_python_{project_name}_tarball
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --partition={partition}
#SBATCH --time={walltime}
#SBATCH --output={remote_logs_dir}/epi_%j.out
#SBATCH --error={remote_logs_dir}/epi_%j.err

REMOTE_RESULTS_DIR="{remote_results_dir}"
PARENT_DIR="${{REMOTE_RESULTS_DIR%/*}}"
BASE_DIR="${{REMOTE_RESULTS_DIR##*/}}"
cd "$REMOTE_RESULTS_DIR" || {{ echo "Directory not found! Exiting." >&2; exit 1; }}
ARCHIVE_OUT="${{PARENT_DIR}}/workspace_${{SLURM_ARRAY_JOB_ID}}.tar"
if ls *.npz *.log >/dev/null 2>&1; then
    tar -cf "$ARCHIVE_OUT" *.npz *.log
    echo "Tarball created successfully at: $ARCHIVE_OUT"
else
    echo "Error: No .npz or .log files found in $REMOTE_RESULTS_DIR" >&2
    exit 1
fi
"""
        return job_script,epilogue_script

    def execute_remote_deployment(self, steps, resolved_dict, project_name, manager, template : FileTemplate.FileTemplate, 
                                  remote_binary_path, remote_working_dir,partition, walltime,calcs_per_node,max_nodes, **kwargs):
        base_template = template
        hpc_ssh = self._connect()
        sftp = hpc_ssh.open_sftp()
        self.remote_working_dir = remote_working_dir
        remote_results_dir = f"{remote_working_dir.rstrip('/')}/molspin_workspace_{project_name}"
        remote_logs_dir = f"{remote_results_dir}/cluster_logs"
        _, stdout, _ = hpc_ssh.exec_command(f"rm -rf {remote_results_dir} && mkdir -p {remote_logs_dir}")

        exit_status = stdout.channel.recv_exit_status()

        if AssertFlags.get("ASSERT_DEPLOY") == False:
            print("Skipping remote deployment due to ASSERT_DEPLOY=False.")
            return None



        #sftp.put(metadata_json, f"{remote_results_dir}/project_metadata.json")
        #sftp.put(metadata_markdown, f"{remote_results_dir}/project_metadata.md")
        #os.remove(metadata_json)
        #os.remove(metadata_markdown)

        start_id = 0
        msd_filenames = []
        compressor = MsdHandling.SequentialSweepCompressor()
        for i in range(steps):
            manager.run(i)

            snapshot = copy.deepcopy(resolved_dict)
            snapshot['settings']['general']['steps'] = 1

            for val, key in enumerate(resolved_dict['tasks']):
                base_output_name = f"./{project_name}-{key}-{i}"
                snapshot['tasks'][key]['logfile'] = f"{base_output_name}.log"
                snapshot['tasks'][key]['datafile'] = f"{base_output_name}.dat"

            filename = f"{project_name}_{start_id + i}.msd"
            msd_filenames.append(filename)
            rendered_str = template.render(snapshot)
            compressor.process_rendered_string(rendered_str)

            #remote_file_path = f"{remote_results_dir}/{filename}"
            #template.render_to_file_ssh(snapshot,remote_file_path,sftp)

        template, sweep_data = compressor.build_payloads()
        MsdHandling.writeLocal(template, sweep_data, f"{project_name}_hpc.jsonl")
        MsdHandling.writeLocalCompressed(template, sweep_data, f"{project_name}_hpc.jsonl.gz")
        sftp.put(f"{project_name}_hpc.jsonl.gz",f"{remote_results_dir}/{project_name}_hpc.jsonl.gz")
        os.remove(f"{project_name}_hpc.jsonl.gz")
        package_root = os.path.join(os.path.dirname(os.path.abspath(__file__)),"hpc_worker.py")
        sftp.put(package_root, f"{remote_results_dir}/hpc_worker.py")

        msd_filenames.sort()
        with sftp.file(f"{remote_results_dir}/hpc_job_map.txt", 'w') as f:
            f.write("\n".join(msd_filenames) + "\n")

        if AssertFlags.get("ASSERT_METADATA"):
            metadata = ProjectMetadata(
                project_name,
                base_template,
                resolved_dict,
                manager,
                resolved_dict.get('settings', {}),
            )
            metadata_json, metadata_markdown = metadata.write(
                ".",
                steps=steps,
                execution_mode="hpc",
                extra={
                    "remote_working_dir": remote_working_dir,
                    "partition": partition,
                    "walltime": walltime,
                    "max_concurrent": calcs_per_node,
                    "max_nodes": max_nodes,
                },
            )
        else:
            print("Skipping metadata generation due to ASSERT_METADATA=False")
        
        pipeline_filename = "submit_pipeline.sh"
        pipeline_root = os.path.join(os.path.dirname(os.path.abspath(__file__)),pipeline_filename)
        sftp.put(pipeline_root, f"{remote_results_dir}/{pipeline_filename}")

        total_tasks = len(msd_filenames)
        
        #batches = self.calculate_hpc_schedule(total_tasks=total_tasks, max_nodes=max_nodes, max_concurrent=calcs_per_node, 
        #                                             est_single_job_hours=kwargs.get('est_sim_time', 20),
        #                                             max_walltime_hours=kwargs.get('max_walltime_hours', 48),
        #                                                safety_buffer=kwargs.get('safety_buffer', 1.2))
        
        total_tasks = len(msd_filenames)
        total_array_nodes = math.ceil(total_tasks / calcs_per_node)
        est_single_job_hours=kwargs.get('est_sim_time', 20)
        safety_buffer=kwargs.get('safety_buffer', 1.2)
        allocated_hours = math.ceil(est_single_job_hours * safety_buffer)
        walltime_str = f"{allocated_hours:02d}:00:00"
        if walltime is not None:
            walltime_str = walltime

        slurm_template,epilogue = self._generate_slurm_script(
            remote_results_dir=remote_results_dir,
            remote_logs_dir=remote_logs_dir,
            remote_binary_path=remote_binary_path,
            partition=partition,
            walltime=walltime_str,
            total_tasks=total_tasks,
            project_name=project_name,
            calcs_per_node=calcs_per_node,
            max_concurrent=calcs_per_node,
            total_array_nodes=total_array_nodes,
            max_nodes=max_nodes,
            armadillo_path=kwargs.get("armadillo",""),
            email_address=kwargs.get('email', "")
        )
        submitted_job_ids = []
        #script_filename = "submit_pipeline.sh"
        script_filename = "job_script.sh"
        epilogue_filename = "epilogue_script.sh"
        remote_script_path = f"{remote_results_dir}/{script_filename}"
        remote_epi_path = f"{remote_results_dir}/{epilogue_filename}"
        with sftp.file(remote_script_path, 'w') as f:
            f.write(slurm_template)
        with sftp.file(remote_epi_path, 'w') as f:
            f.write(epilogue)
        submit_cmd = f"bash {remote_results_dir}/{pipeline_filename} {remote_results_dir}"
        _, stdout, stderr = hpc_ssh.exec_command(submit_cmd)
        output_str = stdout.read().decode('utf-8')
        error_str = stderr.read().decode('utf-8')

        match = re.search(r"submitted:(\d+),(\d+)", output_str.lower())
        if match:
            main_job = match.group(1)
            tarball_job = match.group(2)
            submitted_job_ids.append(main_job)
            submitted_job_ids.append(tarball_job)
            #last_job_id = current_job_id
            print(f"Successfully queued job | Slurm ID: {main_job}")
        else:
            print(f"Error executing batch script {script_filename} on HPC.")
            print(f"HPC Diagnostics: {error_str}")
            return None
        
        sftp.close()
        hpc_ssh.close()

        #with sftp.file(f"{remote_results_dir}/submit_pipeline.slurm", 'w') as f:
        #    f.write(slurm_template)
        #sftp.close()
#
        #_, stdout, stderr = hpc_ssh.exec_command(f"sbatch {remote_results_dir}/submit_pipeline.slurm")
        #submission_output = stdout.read().decode().strip()
        #job_id = "".join(filter(str.isdigit, submission_output))
        #
        #if not job_id:
        #    raise RuntimeError(f"Slurm rejected: {stderr.read().decode().strip()}")
        #
        #hpc_ssh.close()
        #print(f"\n Payload safely deployed to cluster grid! Slurm Job ID: {job_id}")
        print("You can now safely disconnect your internet, close your laptop, or turn off your PC.")
        print(f"\nJob IDs: {submitted_job_ids}")
        return submitted_job_ids
    
    def download_remote_deployment(self, project_name, remote_working_dir, local_npz_path, job_ids):
        hpc_ssh = self._connect()
        if isinstance(job_ids, str):
            job_ids = [job_ids]
        jobs_comma_separated = ",".join(job_ids)
        _, sq_out, _ = hpc_ssh.exec_command(f"squeue -j {jobs_comma_separated} -h")
        active_jobs = sq_out.read().decode().strip()

        if active_jobs:
            remaining_lines = active_jobs.split("\n")
            hpc_ssh.close()
            print(f"\n[Cluster Update]: Active Jobs found in queue ({len(remaining_lines)} rows matching).")
            print("Run download method later.")
            return False        
        
        print(f"\n[Success]: All tracked jobs ({jobs_comma_separated}) have finished computing!")
        
        #print(f"Job {job_id} is complete! Starting download")
        #remote_tar_path = f"{remote_working_dir.rstrip('/')}/workspace_{job_id}.tar"
        #remote_tar_path = f"{remote_working_dir.rstrip('/')}/workspace_$SLURM_ARRAY_JOB_ID.tar"
        remote_results_dir = f"{remote_working_dir.rstrip('/')}/molspin_workspace_{project_name}"
        parent_dir = os.path.dirname(remote_results_dir)
        #local_temp_tar = rf"./{project_name}.tar.gz"
        transport = hpc_ssh.get_transport()
        if transport is not None:
            transport.set_keepalive(10)
            
        sftp = hpc_ssh.open_sftp()
        sftp.get_channel().settimeout(15.0)
        try:
            sftp.stat(remote_results_dir)
        except IOError:
            print(f"Error: Staging workspace directory {remote_results_dir} not found.")
            sftp.close()
            hpc_ssh.close()
            return False
        
        job_ids.pop()
        target_tar_files = [f"workspace_{jid}.tar" for jid in job_ids]
        verified_tar_files = []
        for tar_file in target_tar_files:
            remote_tar_path = f"{parent_dir.rstrip('/')}/{tar_file}"
            try:
                sftp.stat(remote_tar_path)
                verified_tar_files.append(tar_file)
            except IOError:
                print(f"Warning: Expected result archive '{tar_file}' was not found on the host filesystem.")
        
        if not verified_tar_files:
            print("No output .tar result files")
            sftp.close()
            hpc_ssh.close()
            return False
        
        print(f"Found {len(verified_tar_files)} .tar files")
        #print("Archiving and compressing remote .dat files on HPC")
        #tar_cmd = f"tar -czf {remote_tar_path} -C {os.path.dirname(remote_results_dir)} molspin_run_workspace"
        #stdin, stdout, stderr = hpc_ssh.exec_command(tar_cmd)
        #if stdout.channel.recv_exit_status() != 0:
        #    print(f"Compression failed on HPC: {stderr.read().decode()}")
        #    hpc_ssh.close()
        #    return False
        
        start_download_time = time.time()

        stats = {
            'last bytes': 0,
            'last time': time.time(),
            'current speed': 0.0
        }

        def ProgressStats(transferred, total):
            current_time = time.time()
            time_diff = current_time - stats['last time']
            if time_diff >= 1.0:
                bytes_diff = transferred - stats['last bytes']
                stats['current speed'] = (bytes_diff / (1024**2)) / time_diff
                stats['last bytes'] = transferred
                stats['last time'] = current_time
            
            done_mb = transferred / (1024**2)
            total_mb = total / (1024**2)
            msg = f"\rStreaming zip | Speed: {stats['current speed']:6.2f} MB/s | {done_mb:6.1f}/{total_mb:.1f} MB"
            sys.stdout.write(msg)
            sys.stdout.flush()

        for tar_file in verified_tar_files:
            try:
                print(f"\nPulling down: {tar_file}")
                specific_remote_tar = f"{parent_dir.rstrip('/')}/{tar_file}"
                specific_local_tar = rf"./{os.path.splitext(tar_file)[0]}_{project_name}.tar"
                sftp.get(remotepath=specific_remote_tar, localpath=specific_local_tar, callback=ProgressStats)
                print()
            except Exception as e:
                print(f"\n[Critical Failure] Download stream broken for {tar_file}: {e}")
                sftp.close()
                hpc_ssh.close()
                return False
    
        print("Cleaning up remote HPC workspace and tarball archive files")
        paths_to_clean = " ".join([f"{parent_dir.rstrip('/')}/{tf}" for tf in verified_tar_files])
        cleanup_cmd = f"rm -rf {remote_results_dir} {paths_to_clean}"
        _, stdout, _ = hpc_ssh.exec_command(cleanup_cmd)
        stdout.channel.recv_exit_status()
        print("Remote workspace scrub complete")

        sftp.close()
        hpc_ssh.close()
        
        total_time = time.time() - start_download_time
        mins, secs = divmod(int(total_time), 60)
        print(f"Data successfully downloaded! Total time: {mins}m:{secs}s")
        return True
    
    def watch_hpc_job(self, job_id, total_tasks, project_name, poll_interval=5):

        if isinstance(job_id, str):
            job_id = [job_id]

        print(f"Initializing live monitor for Slurm Jobs: {', '.join(job_id)}")

        remote_working_dir = f"/{self.remote_working_dir.strip('/')}"
        remote_results_dir = f"{remote_working_dir}/molspin_workspace_{project_name}"
        
        remote_results_dir = f"{self.remote_working_dir.rstrip('/')}/molspin_workspace_{project_name}"
        
        hpc_ssh = None
        sftp = None
        completed_tasks = 0
        bar_length = 50
        start_time = None
        retry = 0
        total_tasks = int(total_tasks) + 1

        try:
            while True:
                try:
                    if hpc_ssh is None or not hpc_ssh.get_transport() or not hpc_ssh.get_transport().is_active():
                        if hpc_ssh is not None:
                            sys.stdout.write("\nConnection lost! Attempting to reconnect to login node\n")
                            sys.stdout.flush()
                        
                        if retry >= 10:
                            print("Maximum reconnection attempts reached. Exiting monitor loop.")
                            break
                        retry = 0
                        hpc_ssh = self._connect() 
                        sftp = hpc_ssh.open_sftp()
                        if start_time is not None:
                            sys.stdout.write("Reconnected successfully. Resuming progress bar\n")
                        else:
                            start_time = time.time()
                        sys.stdout.flush()

                    jobs_comma_separated = ",".join(job_id)
                    _, stdout, _ = hpc_ssh.exec_command(f"squeue -j {jobs_comma_separated} -h")
                    squeue_output = stdout.read().decode().strip()

                    try:
                        remote_files = sftp.listdir(remote_results_dir)
                        completed_tasks = sum(1 for f in remote_files if f.endswith('.log'))
                    except IOError:
                        pass

                    percent = (completed_tasks / total_tasks) * 100 if total_tasks > 0 else 0
                    filled_blocks = int(round(bar_length * completed_tasks / float(total_tasks)))
                    bar = '█' * filled_blocks + '-' * (bar_length - filled_blocks)

                    elapsed = time.time() - start_time
                    pace = completed_tasks / elapsed if elapsed > 0 else 0

                    if pace > 0:
                        remaining_files = total_tasks - completed_tasks
                        ete_seconds = remaining_files / pace
                        ete_str = time.strftime("%H:%M:%S", time.gmtime(ete_seconds))
                    else:
                        ete_str = "--:--:--"

                    elapsed_str = time.strftime("%H:%M:%S", time.gmtime(elapsed))

                    sys.stdout.write(
                        f"\rDeploying Experiment: [{bar}] {completed_tasks}/{total_tasks} "
                        f"({percent:.1f}%) | Time: {elapsed_str} < Remaining: {ete_str} | {pace:.1f} sim/s"
                    )
                    sys.stdout.flush()

                    if not squeue_output:
                        break

                    time.sleep(poll_interval)
                except (paramiko.SSHException, IOError, ConnectionResetError, OSError) as net_error:
                    retry += 1
                    if sftp: 
                        try: sftp.close() 
                        except: pass
                    if hpc_ssh: 
                        try: hpc_ssh.close() 
                        except: pass
                    hpc_ssh = None
                    sftp = None
                    
                    time.sleep(10)
        
        finally:
            if sftp: sftp.close()
            if hpc_ssh: hpc_ssh.close()
            print() 
            
        if completed_tasks == total_tasks:
            print("Execution complete! All calculations are ready to download")
        else:
            print(f"Job stream finished. Processed {completed_tasks}/{total_tasks} calculations. Check cluster_logs for errors.")

    def _connect(self):
        hpc_ssh = paramiko.SSHClient()
        hpc_ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        connect_kwargs = {
            "username": self.username,
            "key_filename": self.key_path
        }
        if self.proxy_host:
            print(f"[Network] Constructing Proxy Tunnel via: {self.proxy_host}...")
            proxy_ssh = paramiko.SSHClient()
            proxy_ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            proxy_ssh.connect(self.proxy_host, **connect_kwargs)
            
            proxy_transport = proxy_ssh.get_transport()
            proxy_channel = proxy_transport.open_channel(
                "direct-tcpip", (self.hpc_host, 22), ('127.0.0.1', 0)
            )
            
            print(f"[Network] Passing through tunnel to cluster host: {self.hpc_host}...")
            hpc_ssh.connect(self.hpc_host, sock=proxy_channel, **connect_kwargs)
        else:
            print(f"[Network] Connecting directly to: {self.hpc_host}...")
            hpc_ssh.connect(self.hpc_host, **connect_kwargs)
            
        return hpc_ssh

