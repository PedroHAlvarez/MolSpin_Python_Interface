"""Fetch a remote ``.dat`` file over SFTP and convert it to ``.npz`` locally."""

import io
import os
import sys
import time

from .reader import read_dat, write_npz


def _paramiko():
    try:
        import paramiko
    except ImportError as exc:
        raise ImportError("paramiko is required for SSH transfers (pip install paramiko).") from exc
    return paramiko


def enroll_ssh_key(ssh_client, key_path):
    """Create ``key_path`` if missing and append its public key to the remote ``authorized_keys``."""
    paramiko = _paramiko()
    key_path = os.path.expanduser(key_path)
    if not os.path.exists(key_path):
        print(f"Generating new RSA key at {key_path}...")
        key = paramiko.RSAKey.generate(2048)
        key.write_private_key_file(key_path)
    else:
        key = paramiko.RSAKey.from_private_key_file(key_path)
    public_key = f"{key.get_name()} {key.get_base64()}"
    command = (
        "mkdir -p ~/.ssh && chmod 700 ~/.ssh && "
        f'echo "{public_key}" >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys'
    )
    _, stdout, _ = ssh_client.exec_command(command)
    if stdout.channel.recv_exit_status() == 0:
        print("Successfully enrolled local key on the remote server.")
        return True
    return False


def _connect(host, user, password, key_path):
    paramiko = _paramiko()
    ssh = paramiko.SSHClient()
    known_hosts = os.path.expanduser("~/.ssh/known_hosts")
    os.makedirs(os.path.dirname(known_hosts), exist_ok=True)
    if os.path.exists(known_hosts):
        ssh.load_system_host_keys()
    # Unknown hosts are accepted automatically, as in the original module.
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    full_key_path = os.path.expanduser(key_path)
    try:
        key = paramiko.RSAKey.from_private_key_file(full_key_path)
        ssh.connect(
            hostname=host, username=user, pkey=key, look_for_keys=False, allow_agent=False, timeout=20
        )
        print(f"Connected to {host} via SSH Key.")
    except (paramiko.AuthenticationException, paramiko.SSHException, FileNotFoundError):
        if not password:
            print("No valid key found and no password provided.")
            return None
        print("Key auth failed. Attempting password login and key enrollment...")
        ssh.connect(hostname=host, username=user, password=password, timeout=15)
        ssh.save_host_keys(known_hosts)
        enroll_ssh_key(ssh, full_key_path)
    return ssh


def fetch_dat_as_npz(
    filename,
    new_filename="",
    remote_dir="",
    host="",
    user="",
    password=None,
    key_path="~/.ssh/id_rsa_generated",
):
    """Download ``<filename>.dat`` from ``host`` and save it locally as ``.npz``.

    Authenticates with the key at ``key_path``; if that fails and ``password`` is
    given, logs in with the password and enrolls the key. Returns the written
    ``.npz`` path, or ``None`` on failure.
    """
    paramiko = _paramiko()
    ssh = None
    try:
        ssh = _connect(host, user, password, key_path)
        if ssh is None:
            return None
        with ssh.open_sftp() as sftp:
            if remote_dir:
                sftp.chdir(remote_dir)
            buffer = io.BytesIO()
            state = {"bytes": 0, "time": time.time(), "speed": 0.0}
            start = state["time"]

            def progress(transferred, total):
                now = time.time()
                if now - state["time"] >= 1.0:
                    state["speed"] = ((transferred - state["bytes"]) / 1024**2) / (now - state["time"])
                    state["bytes"], state["time"] = transferred, now
                sys.stdout.write(
                    f"\rProgress: {transferred / max(total, 1) * 100:5.1f}% | "
                    f"Speed: {state['speed']:6.2f} MB/s | "
                    f"{transferred / 1024**2:7.1f}/{total / 1024**2:.1f} MB"
                )
                sys.stdout.flush()

            sftp.getfo(remotepath=filename + ".dat", fl=buffer, callback=progress)
            mins, secs = divmod(int(time.time() - start), 60)
            print(f"\nTotal time: {mins}m:{secs}s")
        buffer.seek(0)
        header, rows = read_dat(buffer)
        if not rows:
            print(f"Warning: {filename}.dat is empty.")
            return None
        return write_npz(header, rows, new_filename or filename)
    except paramiko.AuthenticationException:
        print("Error: Authentication failed. Please check your username/password.")
    except (paramiko.SSHException, OSError) as exc:
        print(f"Error: SSH transfer failed: {exc}")
    finally:
        if ssh is not None:
            ssh.close()
    return None
