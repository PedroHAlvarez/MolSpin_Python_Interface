import sys
import os
import json
import subprocess
import gzip
import shutil
import numpy as np
import mmap


def ProcessSingleFile(filename, output_dir):
    lines = _ReadFile(filename)
    base_name = os.path.basename(filename)
    output_path = os.path.join(output_dir, f"{base_name}.npz")
    _SaveToNPZ(lines, output_path)

def _ReadFile(filename):
    if isinstance(filename,str):
        with open(filename, "rb") as f:
            with mmap.mmap(f.fileno(), length=0, access=mmap.ACCESS_READ) as mm:
                lines = []
                for line in iter(mm.readline, b""):
                    lines.append(line.decode('utf-8').split())
                return lines

def _SaveToNPZ(lines, filename):
    header_names = lines[0]
    data_rows = np.array(lines[1:])
    save_dict = {}
    save_dict['_group_map'] = data_rows[:,0]
    for i,name in enumerate(header_names):
        if i == 0: continue
        col_data = data_rows[:,i]
        try:
            save_dict[name] = col_data.astype(float)
        except ValueError:
            save_dict[name] = col_data
    np.savez(filename, **save_dict)

def reconstruct(manifest_path, task_idx, output_dir, gzip_file = True):
    if not os.path.exists(manifest_path):
        print(f"Error: Manifest file not found at {manifest_path}", file=sys.stderr)
        sys.exit(1)

    master_template = None
    target_params = None

    if(gzip_file):
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
    else:
        with open(manifest_path, "rt", encoding="utf-8") as f:
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
    escaped_template = master_template.replace("{", "{{").replace("}","}}")
    for key in target_params.keys():
        place_holder = f"{{{key}}}"
        escaped_placeholder = f"{{{{{key}}}}}"
        escaped_template = escaped_template.replace(escaped_placeholder,place_holder)
    reconstituted_msd_text = escaped_template.format(**target_params)
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

    print(f"DEBUG: binary_exec value is: {repr(binary_exec)}")
    print(f"DEBUG: Does os.path.exists say true? {os.path.exists(binary_exec)}")
    print(f"DEBUG: Is it a file? {os.path.isfile(binary_exec)}")

    with open(local_log_path, 'w') as log_f:
        result = subprocess.run(
            [binary_exec, file],
            cwd=scratch_dir,
            env=env_context,
            stdout=log_f,
            stderr=subprocess.STDOUT
        )

    cluster_logs = os.path.join(results_dir,"cluster_logs")
    for item in os.listdir(scratch_dir):
        if item.endswith(".dat") or item.endswith(".log"):
            source_path = os.path.join(scratch_dir, item)
            destination_path = os.path.join(results_dir, item)
            shutil.copy2(source_path, destination_path)
            ProcessSingleFile(destination_path,results_dir)
            os.remove(destination_path)
        if item.endswith(".log"):
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


def main():
    if len(sys.argv) < 6:# and len(sys.argv) != 1:
        print("Usage: python hpc_worker.py <manifest_jsonl> <task_idx> <output_dir> <logfile_dir> <molspin_runtime>", file=sys.stderr)
        sys.exit(1)

    #if len(sys.argv) == 1:
    #    manifest_file = "StrainT1times-3_hpc.jsonl"
    #    task_index = 6
    #    results_directory = "results"
    #    reconstruct(manifest_file, task_index, results_directory, False)
    #    return
    
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
    shutil.copy2(file,os.path.join(scratch_space,os.path.basename(file)))

    try:
        run(molspin_runtime, file, results_directory, task_index, scratch_space)
    finally:
        if os.path.exists(scratch_space):
            print(f"Purging node-local scratch space: {scratch_space}")
            shutil.rmtree(scratch_space)
        if os.path.exists(file):
            print("Removing msd input file from workspace")
            os.remove(file)
    



if __name__ == "__main__":
    main()
