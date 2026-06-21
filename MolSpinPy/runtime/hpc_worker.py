import sys
import os
import json
import subprocess
import gzip
import shutil

def reconstruct(manifest_path, task_idx, output_dir):
    if not os.path.exists(manifest_path):
        print(f"Error: Manifest file not found at {manifest_path}", file=sys.stderr)
        sys.exit(1)

    master_template = None
    target_params = None

    with gzip.open(manifest_path, "rt", encoding="utf-8") as f:
        first_line = f.readline()
        if not first_line:
            print("Error: Empty manifest file.", file=sys.stderr)
            sys.exit(1)
        
        master_template = json.loads(first_line)["content"]
        
        current_idx = 1
        for line in f:
            if current_idx == task_idx:
                target_params = json.loads(line)["params"]
                break
            current_idx += 1

    if target_params is None:
        print(f"Error: Task index {task_idx} out of bounds for manifest.", file=sys.stderr)
        sys.exit(1)

    reconstituted_msd_text = master_template.format(**target_params)
    config_filename = f"{task_idx}.msd"
    config_filepath = os.path.join(output_dir, config_filename)

    with open(config_filepath, "w", encoding="utf-8") as out_file:
        out_file.write(reconstituted_msd_text)
    return config_filepath,config_filename

def run(molspin, file, results_dir, task_idx,scratch_dir):
    binary_exec = os.path.join(molspin, "molspin")

    env_context = os.environ.copy()
    env_context["OMP_NUM_THREADS"] = "1"
    env_context["MKL_NUM_THREADS"] = "1"
    env_context["OPENBLAS_NUM_THREADS"] = "1"

    local_log_path = os.path.join(scratch_dir, f"{task_idx}.out")

    with open(local_log_path, 'w') as log_f:
        result = subprocess.run(
            [binary_exec, file],
            cwd=scratch_dir,
            env=env_context,
            stdout=log_f,
            stderr=subprocess.STDOUT
        )

    cluster_logs = os.join(results_dir,"cluster_logs")
    for item in os.listdir(scratch_dir):
        if item.endswith(".dat") or item.endswith(".log"):
            source_path = os.path.join(scratch_dir, item)
            destination_path = os.path.join(results_dir, item)
            shutil.copy2(source_path, destination_path)
        if item.endswith(".out"):
            source_path = os.path.join(scratch_dir, item)
            destination_path = os.path.join(cluster_logs, item)
            shutil.copy2(source_path, destination_path)
            
    if result.returncode != 0:
        print(f"Error: Simulation failed for task {task_idx}", file=sys.stderr)
        sys.exit(result.returncode)

if __name__ == "__main__":
    if len(sys.argv) < 6:
        print("Usage: python hpc_worker.py <manifest_jsonl> <task_idx> <output_dir> <logfile_dir> <molspin_runtime>", file=sys.stderr)
        sys.exit(1)
    
    manifest_file = sys.argv[1]
    task_index = int(sys.argv[2])
    results_directory = sys.argv[3]
    logfile_directory = sys.argv[4]
    molspin_runtime = sys.argv[5]

    slurm_job_id = os.environ.get("SLURM_ARRAY_JOB_ID", "local")
    slurm_task_id = os.environ.get("SLURM_ARRAY_TASK_ID", str(task_index))

    scratch_space = f"/tmp/molspin_{slurm_job_id}_{slurm_task_id}_idx_{task_index}"
    os.makedirs(scratch_space, exist_ok=True)

    _,file = reconstruct(manifest_file, task_index, results_directory)
    try:
        run(molspin_runtime, file, results_directory, task_index, scratch_space)
    finally:
        if os.path.exists(scratch_space):
            print(f"Purging node-local scratch space: {scratch_space}")
            shutil.rmtree(scratch_space)
