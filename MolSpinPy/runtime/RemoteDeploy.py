import os
import time
import copy
import paramiko
import numpy as np
import math

import sys
import time
import io

from . import ActionManager
from ..msd import FileTemplate , MsdHandling, MSDWriter

class RemoteHpcOrchestrator:
    def __init__(self, username, hpc_host, key_path, proxy_host=None):
        self.username = username
        self.hpc_host = hpc_host
        self.key_path = os.path.expanduser(key_path)
        self.proxy_host = proxy_host
        self.remote_working_dir = None

    def _generate_slurm_script(self, remote_results_dir, remote_logs_dir, remote_binary_path, 
                            partition, walltime, total_tasks, project_name, cal_per_node):
        total_array_nodes = math.ceil(total_tasks / cal_per_node)
        script = f"""#!/bin/bash
#SBATCH --job-name=molspin_python_{project_name}
#SBATCH --partition={partition}
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task={cal_per_node}
#SBATCH --time={walltime}
#SBATCH --array=1-{total_array_nodes}
#SBATCH --output={remote_logs_dir}/array_%A_%a.out
#SBATCH --error={remote_logs_dir}/array_%A_%a.err

module purge
module load gcc/11.5.0
module load openblas
module load netlib-lapack

cd {remote_results_dir}
CALCS_PER_NODE={cal_per_node}
START_LINE=$(((SLURM_ARRAY_TASK_ID - 1) * CALCS_PER_NODE + 1))
END_LINE=$((SLURM_ARRAY_TASK_ID * CALCS_PER_NODE))

for (( line_idx=$START_LINE; line_idx<=$END_LINE; line_idx++ )); do
    TARGET_MSD_FILE=$(sed -n "${{line_idx}}p" hpc_job_map.txt)
    if [ -z "$TARGET_MSD_FILE" ]; then
        echo "Reached end of job map"
        break
    fi

    NODE_LOCAL_DIR="/tmp/molspin_${{SLURM_ARRAY_JOB_ID}}_${{SLURM_ARRAY_TASK_ID}}_core_${{line_idx}}"
    mkdir -p "$NODE_LOCAL_DIR"
    cp "./$TARGET_MSD_FILE" "$NODE_LOCAL_DIR/"
    (
        cd "$NODE_LOCAL_DIR"
        export OMP_NUM_THREADS=1
        export MKL_NUM_THREADS=1
        export OPENBLAS_NUM_THREADS=1

        {remote_binary_path}/molspin "$TARGET_MSD_FILE"

        BASE_NAME=$(basename "$TARGET_MSD_FILE" .msd)
        cp ./*.log "{remote_results_dir}/" 2>/dev/null
        cp ./*.dat "{remote_results_dir}/" 2>/dev/null

        rm -rf "$NODE_LOCAL_DIR"
    ) &
done
wait
echo "Array node $SLURM_ARRAY_TASK_ID computations done"
if [ "$SLURM_ARRAY_TASK_ID" -eq "$((SLURM_ARRAY_TASK_COUNT - 1))" ]; then
    echo "Last array task finished computing. Monitoring workspace for final file writes"
    
    EXPECTED_FILES={total_tasks}
    CURRENT_FILES=0
    
    while [ "$CURRENT_FILES" -lt "$EXPECTED_FILES" ]; do
        # Count only files ending in .dat inside the directory
        CURRENT_FILES=$(ls -1 "{remote_results_dir}"/*.dat 2>/dev/null | wc -l)
        echo "Workspace progress: $CURRENT_FILES / $EXPECTED_FILES files written. Checking again in 5s..."
        if [ "$CURRENT_FILES" -lt "$EXPECTED_FILES" ]; then
            sleep 5
        fi
    done

    PARENT_DIR=$(dirname "{remote_results_dir}")
    BASE_DIR=$(basename "{remote_results_dir}")

    cd "{remote_results_dir}"
    
    echo "All files verified on disk! Launching compute-node compression"
    tar -cf "$PARENT_DIR/workspace_$SLURM_ARRAY_JOB_ID.tar" *.dat *.log"
    echo "Tarball created successfully at: $PARENT_DIR/workspace_$SLURM_ARRAY_JOB_ID.tar"
fi
"""
        return script

    def execute_remote_deployment(self, steps, resolved_dict, project_name, manager, template : FileTemplate.FileTemplate, 
                                  remote_binary_path, remote_working_dir,partition, walltime,calcs_per_node):
        
        hpc_ssh = self._connect()
        sftp = hpc_ssh.open_sftp()
        self.remote_working_dir = remote_working_dir
        remote_results_dir = f"{remote_working_dir.rstrip('/')}/molspin_run_workspace"
        remote_logs_dir = f"{remote_results_dir}/cluster_logs"
        _, stdout, _ = hpc_ssh.exec_command(f"rm -rf {remote_results_dir} && mkdir -p {remote_logs_dir}")

        exit_status = stdout.channel.recv_exit_status()

        start_id = 0
        msd_filenames = []
        
        for i in range(steps):
            manager.run(i)

            resolved_dict['settings']['general']['steps'] = 1

            for val, key in enumerate(resolved_dict['tasks']):
                base_output_name = f"./{project_name}-{key}-{i}"
                resolved_dict['tasks'][key]['logfile'] = f"{base_output_name}.log"
                resolved_dict['tasks'][key]['datafile'] = f"{base_output_name}.dat"

            snapshot = copy.deepcopy(resolved_dict)
            filename = f"{project_name}_{start_id + i}.msd"
            msd_filenames.append(filename)

            remote_file_path = f"{remote_results_dir}/{filename}"
            template.render_to_file_ssh(snapshot,remote_file_path,sftp)
        msd_filenames.sort()
        with sftp.file(f"{remote_results_dir}/hpc_job_map.txt", 'w') as f:
            f.write("\n".join(msd_filenames) + "\n")

        total_tasks = len(msd_filenames)
        slurm_template = self._generate_slurm_script(
            remote_results_dir=remote_results_dir,
            remote_logs_dir=remote_logs_dir,
            remote_binary_path=remote_binary_path,
            partition=partition,
            walltime=walltime,
            total_tasks=total_tasks,
            cal_per_node=calcs_per_node,
            project_name=project_name
        )

        with sftp.file(f"{remote_results_dir}/submit_pipeline.slurm", 'w') as f:
            f.write(slurm_template)
        sftp.close()

        _, stdout, stderr = hpc_ssh.exec_command(f"sbatch {remote_results_dir}/submit_pipeline.slurm")
        submission_output = stdout.read().decode().strip()
        job_id = "".join(filter(str.isdigit, submission_output))
        
        if not job_id:
            raise RuntimeError(f"Slurm rejected: {stderr.read().decode().strip()}")
        
        hpc_ssh.close()
        print(f"\n Payload safely deployed to cluster grid! Slurm Job ID: {job_id}")
        print("You can now safely disconnect your internet, close your laptop, or turn off your PC.")
        return job_id
    
    def download_remote_deployment(self, project_name, remote_working_dir, local_npz_path, job_id):
        hpc_ssh = self._connect()
        _, sq_out, _ = hpc_ssh.exec_command(f"squeue -j {job_id} -h")
        active_jobs = sq_out.read().decode().strip()

        if active_jobs:
            remaining_nodes = len(active_jobs.split("\n"))
            hpc_ssh.close()
            print(f"Cluster update: Job {job_id} is STILL RUNNING. {remaining_nodes} array node blocks active.")
            print("Run the download method again later.")
            return False
        
        print(f"Job {job_id} is complete! Starting download")
        #remote_tar_path = f"{remote_working_dir.rstrip('/')}/workspace_{job_id}.tar"
        remote_tar_path = f"{remote_working_dir.rstrip('/')}/workspace_$SLURM_ARRAY_JOB_ID.tar"
        remote_results_dir = f"{remote_working_dir.rstrip('/')}/molspin_run_workspace"
        local_temp_tar = rf"./{project_name}.tar.gz"
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
        
        try:
            all_files = sftp.listdir(remote_results_dir)
            target_files = sorted([f for f in all_files if f.endswith('.dat')])
        except IOError:
            print("Error: Unable to scan remote workspace directory files.")
            sftp.close()
            hpc_ssh.close()
            return False
        
        if not target_files:
            print("No output .dat result files")
            sftp.close()
            hpc_ssh.close()
            return False
        
        print(f"Found {len(target_files)} datasets")
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

        try:
            print(f"\nDownloading .tar file")
            sftp.get(remotepath=remote_tar_path, localpath=local_temp_tar, callback=ProgressStats)
            print()
        except Exception as e:
            print(f"\nDownload stream failed: {e}")
            sftp.close()
            hpc_ssh.close()
            return False
        print("Cleaning up remote HPC workspace and tarball archive files")
        cleanup_cmd = f"rm -rf {remote_results_dir} {remote_tar_path}"
        stdin, stdout, stderr = hpc_ssh.exec_command(cleanup_cmd)
        stdout.channel.recv_exit_status()
        print("Remote workspace scrub complete")

        sftp.close()
        hpc_ssh.close()
        
        total_time = time.time() - start_download_time
        mins, secs = divmod(int(total_time), 60)
        print(f"Data successfully downloaded! Total time: {mins}m:{secs}s")
        return True
    
    def watch_hpc_job(self, job_id, total_tasks, poll_interval=5):
        print(f"Initializing live monitor for Slurm Job: {job_id}")
        
        remote_results_dir = f"{self.remote_working_dir.rstrip('/')}/molspin_run_workspace"
        
        hpc_ssh = None
        sftp = None
        completed_tasks = 0
        bar_length = 50
        start_time = None
        retry = 0
        total_tasks = int(total_tasks)

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

                    _, stdout, _ = hpc_ssh.exec_command(f"squeue -j {job_id} -h")
                    squeue_output = stdout.read().decode().strip()

                    try:
                        remote_files = sftp.listdir(remote_results_dir)
                        completed_tasks = sum(1 for f in remote_files if f.endswith('.log'))
                    except IOError:
                        pass

                    percent = (completed_tasks / total_tasks) * 100
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

