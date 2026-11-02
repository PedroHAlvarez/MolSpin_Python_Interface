import os
from . import RecursiveRenderer
import numpy as np
import sys
import math
import random
import json
import gzip
from itertools import compress, count
from operator import ne

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
        self.baseline_str = None
        self.variable_indices = set()
        self.sweep_deltas = [] 
        self.total_files = 0
    def process_rendered_string(self, rendered_str):
        if self.baseline_lines is None:
            self.baseline_str = rendered_str
            self.baseline_lines = rendered_str.splitlines()
            self.sweep_deltas.append({})
            self.total_files += 1
            return

        # Identical output is common in sweeps; skip the line diff entirely.
        if rendered_str == self.baseline_str:
            self.sweep_deltas.append({})
            self.total_files += 1
            return

        baseline = self.baseline_lines
        current_lines = rendered_str.splitlines()
        file_delta = {}
        n_base = len(baseline)
        n_curr = len(current_lines)

        # Comparison and index selection run in C; Python only touches changed lines.
        for line_num in compress(count(), map(ne, baseline, current_lines)):
            file_delta[line_num] = current_lines[line_num]
        for line_num in range(min(n_base, n_curr), max(n_base, n_curr)):
            file_delta[line_num] = current_lines[line_num] if line_num < n_curr else ""

        self.variable_indices.update(file_delta)
        self.sweep_deltas.append(file_delta)
        self.total_files += 1

    def build_payloads(self):
        """Returns (template, defaults, sparse_rows).

        Rows only contain the lines that differ from the baseline; `defaults`
        holds the baseline value of every variable line.
        """
        if not self.baseline_lines:
            return "", {}, []

        n_base = len(self.baseline_lines)
        # Sweep files longer than the baseline need placeholders past its end.
        n_total = max(n_base, max(self.variable_indices, default=-1) + 1)
        template_lines = [
            f"{{line_{i}}}" if i in self.variable_indices else self.baseline_lines[i]
            for i in range(n_total)
        ]
        master_template = "\n".join(template_lines)
        defaults = {
            f"line_{i}": (self.baseline_lines[i] if i < n_base else "")
            for i in self.variable_indices
        }
        rows = [{f"line_{i}": v for i, v in d.items()} for d in self.sweep_deltas]
        return master_template, defaults, rows

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

def writeIndexedCompressed(master_template, defaults, sparse_rows, local_filepath, chunk_size=512):
    """Writes a multi-member gzip manifest plus `<file>.idx`.

    Member 0 is the header line; each later member holds `chunk_size` rows, so
    a worker can seek straight to one chunk instead of scanning the whole file.
    """
    offsets = []
    with open(local_filepath, "wb") as raw:
        header = json.dumps({"content": master_template, "defaults": defaults}) + "\n"
        raw.write(gzip.compress(header.encode("utf-8"), compresslevel=6, mtime=0))
        for start in range(0, len(sparse_rows), chunk_size):
            offsets.append(raw.tell())
            block = "".join(
                json.dumps({"params": row}, separators=(",", ":")) + "\n"
                for row in sparse_rows[start:start + chunk_size]
            )
            raw.write(gzip.compress(block.encode("utf-8"), compresslevel=6, mtime=0))
    with open(local_filepath + ".idx", "w", encoding="utf-8") as f:
        json.dump({"chunk_size": chunk_size, "rows": len(sparse_rows), "offsets": offsets}, f)

def writeSFTP(master_template, param_sweep_rows, remote_filepath, sftp_client):
    with sftp_client.open(remote_filepath, "w") as remote_file:
        ParseTokenizedStringsToJSONL(remote_file, master_template, param_sweep_rows)

