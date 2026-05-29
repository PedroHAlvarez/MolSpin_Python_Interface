
import time
import numpy as np
import sys
import os
import mmap
import io

def ProcessSingleFile(filename, output_dir, **kwargs):
    silent = kwargs.get("silent", False)
    if not silent:
        print(f"Processing file: {filename}")
    lines = _ReadFile(filename, silent=silent)
    base_name = os.path.basename(filename)
    output_path = os.path.join(output_dir, f"{base_name}.npz")
    _SaveToNPZ(lines, output_path, silent=silent)

#def _BatchProcess(file_paths, output_dir, **kwargs):
#    # Implement the logic to process multiple files in a batch
#    pass

def _ReadFile(filename, **kwargs):
    silent = kwargs.get("silent", False)
    stats = {'last_bytes': 0, 'last_time': time.time(), 'current_speed': 0.0}
    
    def update_ui(current_bytes, total_bytes):
        if silent:
            return
        current_time = time.time()
        time_diff = current_time - stats['last_time']
        if time_diff >= 0.5:
            bytes_diff = current_bytes - stats['last_bytes']
            stats['current_speed'] = (bytes_diff / (1024**2)) / time_diff
            stats['last_bytes'] = current_bytes
            stats['last_time'] = current_time
            
            percent = (current_bytes / total_bytes) * 100
            msg = f"\rParsing Data: {percent:5.1f}% | Speed: {stats['current_speed']:6.2f} MB/s"
            sys.stdout.write(msg)
            sys.stdout.flush()
    if isinstance(filename,str):
        filesize = os.path.getsize(filename)
        with open(filename, "rb") as f:
            with mmap.mmap(f.fileno(), length=0, access=mmap.ACCESS_READ) as mm:
                lines = []
                for line in iter(mm.readline, b""):
                    lines.append(line.decode('utf-8').split())
                    if len(lines) % 1000 == 0:
                        update_ui(mm.tell(), filesize)
                if not silent:
                    print()
                return lines
    elif isinstance(filename,io.BytesIO):
        lines = []
        for line in filename:
            lines.append(line.decode('utf-8').split())
        return lines

def _SaveToNPZ(lines, filename, **kwargs):
    silent = kwargs.get("silent", False)
    header_names = lines[0]
    data_rows = np.array(lines[1:])
    save_dict = {}
    save_dict['_group_map'] = data_rows[:,0]
    for i,name in enumerate(header_names):
        percent = int(((i+1) / len(header_names)) * 100)
        bar_length = 20
        filled_length = int(bar_length * (i+1) // len(header_names))
        bar = '█' * filled_length + '-' * (bar_length - filled_length)
        if not silent:
            sys.stdout.write(f"\rSaving Data: |{bar}| {percent}% ({name[:15]})")
            sys.stdout.flush()

        if i == 0: continue
        col_data = data_rows[:,i]
        try:
            save_dict[name] = col_data.astype(float)
        except ValueError:
            save_dict[name] = col_data
    np.savez(filename, **save_dict)
    if not silent:
        print(f"Saved {filename} to .npz file")

    # Implement the logic to process multiple files in a batch
    pass