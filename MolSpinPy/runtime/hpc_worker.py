import sys
import os
import json
import subprocess

def reconstruct(manifest_path, task_idx, output_dir):
    if not os.path.exists(manifest_path):
        print(f"Error: Manifest file not found at {manifest_path}", file=sys.stderr)
        sys.exit(1)

    master_template = None
    target_params = None

    with open(manifest_path, "r", encoding="utf-8") as f:
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

#def run(molspin, file, path):


if __name__ == "__main__":
    if len(sys.argv) < 5:
        print("Usage: python hpc_worker.py <manifest_jsonl> <task_idx> <output_dir> <molspin_runtime>", file=sys.stderr)
        sys.exit(1)
    
    manifest_file = sys.argv[1]
    task_index = int(sys.argv[2])
    results_directory = sys.argv[3]
    molspin_runtime = sys.argv[4]

    path,file = reconstruct(manifest_file, task_index, results_directory)