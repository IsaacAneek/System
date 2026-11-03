#!/usr/bin/env python3
"""
NFS Manager Backend:
Handles mDNS & DNS-SD service discovery, querying showmount/showexports,
parsing active OS mounts from /proc/mounts, and mounting/unmounting NFS shares.
"""

import os
import re
import socket
import shutil
import subprocess


class NFSShare:
    def __init__(self, host, export_path, clients="*", status="Available"):
        self.host = host
        self.export_path = export_path
        self.clients = clients
        self.status = status

    @property
    def full_source(self):
        return f"{self.host}:{self.export_path}"

    def __repr__(self):
        return f"<NFSShare {self.full_source} ({self.clients})>"


class ActiveMount:
    def __init__(self, source, mount_point, fs_type="nfs4", options=""):
        self.source = source
        self.mount_point = mount_point
        self.fs_type = fs_type
        self.options = options
        self.size_str = self._calc_disk_usage()

    def _calc_disk_usage(self):
        try:
            st = os.statvfs(self.mount_point)
            total_bytes = st.f_blocks * st.f_frsize
            free_bytes = st.f_bavail * st.f_frsize
            used_bytes = total_bytes - free_bytes

            def _fmt(b):
                for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
                    if b < 1024.0:
                        return f"{b:.1f} {unit}"
                    b /= 1024.0
                return f"{b:.1f} PB"

            if total_bytes > 0:
                pct = (used_bytes / total_bytes) * 100
                return f"{_fmt(used_bytes)} / {_fmt(total_bytes)} ({pct:.0f}%)"
            return "N/A"
        except Exception:
            return "Active"

    def __repr__(self):
        return f"<ActiveMount {self.source} -> {self.mount_point}>"


class NFSManager:
    """
    Manages discovery, querying, mounting, and unmounting of NFS shares.
    """

    def __init__(self):
        self.known_candidate_hosts = [
            "pi02.local",
            "pi03.local",
            "pi01.local",
            "localhost",
            "127.0.0.1",
            "192.168.10.150",
            "192.168.10.101",
        ]

    def discover_mdns_hosts(self):
        """
        Scans for hosts advertising services or resolves .local hostnames via mDNS / avahi / system resolver.
        """
        found_hosts = set()

        # 1. Check avahi-browse for DNS-SD (_nfs._tcp, _workstation._tcp)
        avahi_bin = shutil.which("avahi-browse")
        if avahi_bin:
            try:
                # Query _nfs._tcp
                proc = subprocess.run(
                    [avahi_bin, "-rt", "_nfs._tcp", "--parsable"],
                    capture_output=True,
                    text=True,
                    timeout=3
                )
                for line in proc.stdout.splitlines():
                    parts = line.split(";")
                    # Format: =;eth0;IPv4;Service Name;_nfs._tcp;local;hostname.local;ip;port
                    if len(parts) >= 8 and parts[6]:
                        found_hosts.add(parts[6].strip())
                        if parts[7]:
                            found_hosts.add(parts[7].strip())

                # Query general workstations on mDNS
                proc2 = subprocess.run(
                    [avahi_bin, "-rt", "_workstation._tcp", "--parsable"],
                    capture_output=True,
                    text=True,
                    timeout=3
                )
                for line in proc2.stdout.splitlines():
                    parts = line.split(";")
                    if len(parts) >= 8 and parts[6]:
                        host = parts[6].strip()
                        if host.endswith(".local"):
                            found_hosts.add(host)
            except Exception:
                pass

        # 2. Check /etc/hosts for cluster definitions
        try:
            with open("/etc/hosts", "r") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        parts = line.split()
                        for p in parts[1:]:
                            if "pi" in p.lower() or "cluster" in p.lower() or p.endswith(".local"):
                                found_hosts.add(p)
        except Exception:
            pass

        # 3. Add known cluster defaults
        for cand in self.known_candidate_hosts:
            found_hosts.add(cand)

        # 4. Filter only hosts that resolve or respond
        live_hosts = []
        for h in sorted(found_hosts):
            # Test socket resolution
            try:
                socket.getaddrinfo(h, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
                live_hosts.append(h)
            except Exception:
                # If resolution fails, keep it if it's a known IP or cluster host
                if re.match(r"^\d+\.\d+\.\d+\.\d+$", h) or "pi0" in h:
                    live_hosts.append(h)

        return live_hosts

    def query_showmount(self, host):
        """
        Executes 'showmount -e <host>' to inspect all NFS exported directories on target.
        """
        showmount_bin = shutil.which("showmount") or "/usr/sbin/showmount"
        if not os.path.exists(showmount_bin):
            showmount_bin = "showmount"

        cmd = [showmount_bin, "-e", "--no-headers", host]
        shares = []

        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            if proc.returncode == 0:
                for line in proc.stdout.splitlines():
                    line = line.strip()
                    if not line or line.lower().startswith("export list"):
                        continue
                    parts = line.split()
                    if len(parts) >= 2:
                        export_path = parts[0]
                        clients = " ".join(parts[1:])
                        shares.append(NFSShare(host=host, export_path=export_path, clients=clients))
                    elif len(parts) == 1:
                        shares.append(NFSShare(host=host, export_path=parts[0], clients="*"))
            else:
                err_msg = proc.stderr.strip() or "Connection refused / RPC error"
                # If RPC failed or showmount failed, return empty
                pass
        except Exception:
            pass

        return shares

    def scan_all_exports(self, progress_callback=None):
        """
        Discovers all mDNS hosts and queries their NFS exports.
        """
        hosts = self.discover_mdns_hosts()
        all_shares = []

        for idx, host in enumerate(hosts):
            if progress_callback:
                progress_callback(f"Querying exports on {host} ({idx + 1}/{len(hosts)})...")
            shares = self.query_showmount(host)
            all_shares.extend(shares)

        return all_shares

    def get_active_mounts(self):
        """
        Inspects /proc/mounts to list currently mounted NFS file systems on this OS.
        """
        active = []
        try:
            with open("/proc/mounts", "r") as f:
                for line in f:
                    parts = line.strip().split()
                    if len(parts) >= 4:
                        source, target, fstype, opts = parts[0], parts[1], parts[2], parts[3]
                        if fstype in ["nfs", "nfs4"]:
                            active.append(ActiveMount(source=source, mount_point=target, fs_type=fstype, options=opts))
        except Exception:
            pass
        return active

    def is_mounted(self, source, mount_point=None):
        """
        Checks if a given NFS source or local mount point is actively mounted.
        """
        active_mounts = self.get_active_mounts()
        for m in active_mounts:
            if m.source == source or (mount_point and m.mount_point == mount_point):
                return True, m.mount_point
        return False, None

    def mount_share(self, source, mount_point, options="rw,sync,_netdev", sudo_password=None):
        """
        Mounts the NFS export to a local directory.
        Creates mount point if missing.
        """
        # Ensure local mount point directory exists
        if not os.path.exists(mount_point):
            mkdir_cmd = ["mkdir", "-p", mount_point]
            self._run_privileged(mkdir_cmd, sudo_password)

        cmd = ["mount", "-t", "nfs", "-o", options, source, mount_point]
        return self._run_privileged(cmd, sudo_password)

    def unmount_share(self, mount_point, lazy=False, sudo_password=None):
        """
        Unmounts an active NFS share.
        """
        cmd = ["umount"]
        if lazy:
            cmd.append("-l")
        cmd.append(mount_point)
        return self._run_privileged(cmd, sudo_password)

    def _run_privileged(self, cmd, sudo_password=None):
        """
        Runs command via sudo or pkexec.
        """
        # If already root
        if os.geteuid() == 0:
            full_cmd = cmd
            input_text = None
        elif sudo_password:
            full_cmd = ["sudo", "-S"] + cmd
            input_text = f"{sudo_password}\n"
        elif shutil.which("pkexec") and os.environ.get("WAYLAND_DISPLAY") or os.environ.get("DISPLAY"):
            full_cmd = ["pkexec"] + cmd
            input_text = None
        else:
            full_cmd = ["sudo", "-n"] + cmd
            input_text = None

        proc = subprocess.run(
            full_cmd,
            input=input_text,
            capture_output=True,
            text=True,
            timeout=10
        )
        success = (proc.returncode == 0)
        output = proc.stdout.strip()
        error = proc.stderr.strip()
        return success, output if success else error

