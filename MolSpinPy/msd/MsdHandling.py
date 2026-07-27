import os
from . import RecursiveRenderer
import numpy as np
import sys
import math
import random
import json
import gzip

def ConvertMSDtoDictionary(filename):
    if not os.path.isfile(filename):
        print(f"Error: The file '{filename}' does not exist.")
        return None
    with open(filename, "r") as f:
        text = f.read()
    lexer = RecursiveRenderer.Lexer(text)
    parser = RecursiveRenderer.RecursiveRenderer(lexer)
    return parser.parse()

class SequentialSweepCompressor:
    def __init__(self):
        self.baseline_lines = None
        self.variable_indices = set()
        self.sweep_deltas = [] 
        self.total_files = 0
    def process_rendered_string(self, rendered_str):
        current_lines = rendered_str.splitlines()
        
        if self.baseline_lines is None:
            self.baseline_lines = current_lines
            self.sweep_deltas.append({})
            self.total_files += 1
            return

        file_delta = {}
        max_lines = max(len(self.baseline_lines), len(current_lines))
        
        for line_num in range(max_lines):
            base_line = self.baseline_lines[line_num] if line_num < len(self.baseline_lines) else ""
            curr_line = current_lines[line_num] if line_num < len(current_lines) else ""
            
            if base_line != curr_line:
                self.variable_indices.add(line_num)
                file_delta[line_num] = curr_line
                
        self.sweep_deltas.append(file_delta)
        self.total_files += 1

    def build_payloads(self):
        if not self.baseline_lines:
            return "", []

        template_lines = []
        for line_num, line in enumerate(self.baseline_lines):
            if line_num in self.variable_indices:
                template_lines.append(f"{{line_{line_num}}}")
            else:
                template_lines.append(line)
        master_template = "\n".join(template_lines)

        final_sweep_rows = []
        for file_delta in self.sweep_deltas:
            row_params = {}
            for line_num in self.variable_indices:
                if line_num in file_delta:
                    row_params[f"line_{line_num}"] = file_delta[line_num]
                else:
                    row_params[f"line_{line_num}"] = (
                        self.baseline_lines[line_num] if line_num < len(self.baseline_lines) else ""
                    )
            final_sweep_rows.append(row_params)

        return master_template, final_sweep_rows

#depricate heavy memory function
def GenerateBoilerPlateTemplate(rendered_strings):
    total_files = len(rendered_strings)
    if total_files == 0:
        return "", []
    
    baseline_lines = rendered_strings[0].splitlines()
    num_lines = len(baseline_lines)
    variable_indices = set()

    target_sample_size = max(10, min(20000, int(math.sqrt(total_files))))
    if total_files <= target_sample_size:
        sampled_indices = list(range(total_files))
    else:
        sampled_indices = [0, total_files - 1]
        inner_slots = target_sample_size - 2
        bucket_width = (total_files - 2) / inner_slots

        for i in range(inner_slots):
            start_idx = int(1 + i * bucket_width)
            end_idx = int(1 + (i + 1) * bucket_width) - 1
            
            if start_idx <= end_idx:
                sampled_indices.append(random.randint(start_idx, end_idx))
            else:
                sampled_indices.append(start_idx)
        
        sampled_indices = sorted(list(set(sampled_indices)))

    for idx in sampled_indices:
        current_lines = rendered_strings[idx].splitlines()
        for line_num in range(min(num_lines, len(current_lines))):
            if baseline_lines[line_num] != current_lines[line_num]:
                variable_indices.add(line_num)
    template_lines = []
    for line_num, line in enumerate(baseline_lines):
        if line_num in variable_indices:
            template_lines.append(f"{{line_{line_num}}}")
        else:
            template_lines.append(line)

    master_template = "\n".join(template_lines)
    param_sweep_rows = []
    for s in rendered_strings:
        current_lines = s.splitlines()
        row_delta = {}
        for line_num in variable_indices:
            if line_num < len(current_lines):
                row_delta[f"line_{line_num}"] = current_lines[line_num]
        param_sweep_rows.append(row_delta)

    return master_template, param_sweep_rows

def ParseTokenizedStringsToJSONL(_fileHandle, master_template, param_sweep):
    _fileHandle.write(json.dumps({"content": master_template}) + "\n")
    for row in param_sweep:
        _fileHandle.write(json.dumps({"params": row}) + "\n")

def writeLocal(master_template, param_sweep_rows, local_filepath):
    with open(local_filepath, "w", encoding="utf-8") as f:
        ParseTokenizedStringsToJSONL(f, master_template, param_sweep_rows)

def writeLocalCompressed(master_template, param_sweep_rows, local_filepath):
    with gzip.open(local_filepath, "wt", encoding="utf-8") as f:
        ParseTokenizedStringsToJSONL(f,master_template,param_sweep_rows)

def writeSFTP(master_template, param_sweep_rows, remote_filepath, sftp_client):
    with sftp_client.open(remote_filepath, "w") as remote_file:
        ParseTokenizedStringsToJSONL(remote_file, master_template, param_sweep_rows)

