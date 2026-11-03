#!/usr/bin/env python3
"""
NFS Manager Backend:
Handles dynamic network discovery (nmap subnet scan, arp-scan + avahi-resolve, mDNS DNS-SD),
querying showmount on user-defined host lists, parsing active OS mounts from /proc/mounts,
and mounting/unmounting NFS shares. No hardcoded hosts.
"""

import os
import re
import socket
import shutil
import subprocess
import ipaddress


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
    Manages dynamic discovery, querying, mounting, and unmounting of NFS shares.
    Zero hardcoded hosts.
    """

    def __init__(self):
        pass

    # -----------------------------------------------------------------------
    # Subnet Detection
    # -----------------------------------------------------------------------
    def get_local_subnets(self):
        """
        Auto-detects active IPv4 subnets from system network interfaces using 'ip'.
        Returns list of CIDRs, e.g. ['192.168.10.0/24'].
        """
        subnets = set()
        try:
            proc = subprocess.run(["ip", "-o", "-f", "inet", "addr", "show"], capture_output=True, text=True, timeout=3)
            for line in proc.stdout.splitlines():
                parts = line.strip().split()
                # Line format: <ifindex>: <ifname> inet <ip/prefix> ...
                if len(parts) >= 4 and parts[2] == "inet":
                    cidr = parts[3]
                    if not cidr.startswith("127."):
                        try:
                            net = ipaddress.IPv4Interface(cidr).network
                            subnets.add(str(net))
                        except Exception:
                            pass
        except Exception:
            pass

        return sorted(list(subnets))

    # -----------------------------------------------------------------------
    # Discovery Method 1: Nmap Subnet Scan
    # -----------------------------------------------------------------------
    def scan_network_nmap(self, subnet=None, scan_nfs_port=True, progress_cb=None):
        """
        Scans LAN using nmap.
        If scan_nfs_port=True, scans for open NFS port 2049 directly.
        Returns a list of dicts: [{'host': hostname_or_ip, 'ip': ip, 'name': hostname}]
        """
        nmap_bin = shutil.which("nmap")
        if not nmap_bin:
            raise FileNotFoundError("nmap is not installed or not in PATH.")

        if not subnet:
            detected = self.get_local_subnets()
            subnet = detected[0] if detected else "192.168.1.0/24"

        if progress_cb:
            mode_str = "NFS port 2049" if scan_nfs_port else "ping sweep"
            progress_cb(f"Running nmap ({mode_str}) on {subnet}...")

        # If scan_nfs_port, probe port 2049 to find NFS servers fast
        if scan_nfs_port:
            cmd = [nmap_bin, "-p", "2049", "--open", "-T4", subnet]
        else:
            cmd = [nmap_bin, "-sn", "-T4", subnet]

        discovered = []
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=45)
            lines = proc.stdout.splitlines()

            current_host = None
            current_ip = None

            for line in lines:
                line = line.strip()
                # Format: "Nmap scan report for pi02.local (192.168.10.150)"
                # or:     "Nmap scan report for 192.168.10.150"
                if line.startswith("Nmap scan report for"):
                    parts = line.replace("Nmap scan report for ", "").strip()
                    m = re.match(r"^(.*?)\s+\((.*?)\)$", parts)
                    if m:
                        current_host = m.group(1)
                        current_ip = m.group(2)
                    else:
                        current_host = parts
                        current_ip = parts

                    # If nmap gave an IP without hostname, try avahi-resolve
                    resolved_name = current_host
                    if current_host == current_ip:
                        avahi_name = self.resolve_avahi_ip(current_ip)
                        if avahi_name:
                            resolved_name = avahi_name

                    discovered.append({
                        "host": resolved_name,
                        "ip": current_ip,
                        "name": resolved_name
                    })

        except Exception as e:
            if progress_cb:
                progress_cb(f"Nmap scan error: {e}")

        return discovered

    # -----------------------------------------------------------------------
    # Discovery Method 2: arp-scan + avahi-resolve
    # -----------------------------------------------------------------------
    def resolve_avahi_ip(self, ip):
        """
        Uses avahi-resolve -a <IP> to resolve IP to .local mDNS hostname.
        """
        avahi_res = shutil.which("avahi-resolve")
        if not avahi_res:
            return None
        try:
            proc = subprocess.run([avahi_res, "-a", ip], capture_output=True, text=True, timeout=2)
            if proc.returncode == 0:
                # Output: "192.168.10.150\tpi02.local"
                parts = proc.stdout.strip().split()
                if len(parts) >= 2:
                    return parts[1]
        except Exception:
            pass
        return None

    def scan_network_arpscan(self, interface=None, progress_cb=None):
        """
        Scans LAN via arp-scan (or /proc/net/arp fallback), then resolves each IP using avahi-resolve.
        Returns a list of dicts: [{'host': resolved_name_or_ip, 'ip': ip, 'name': resolved_name}]
        """
        arp_bin = shutil.which("arp-scan") or "/usr/sbin/arp-scan"
        discovered_ips = set()

        if progress_cb:
            progress_cb("Running arp-scan to discover active LAN devices...")

        # 1. Try running arp-scan
        if os.path.exists(arp_bin):
            cmd = [arp_bin, "--localnet"]
            if interface:
                cmd.extend(["-I", interface])

            # arp-scan may require privileges; test unprivileged or pkexec
            try:
                proc = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                if proc.returncode == 0:
                    for line in proc.stdout.splitlines():
                        parts = line.strip().split()
                        if len(parts) >= 2 and re.match(r"^\d+\.\d+\.\d+\.\d+$", parts[0]):
                            discovered_ips.add(parts[0])
            except Exception:
                pass

        # 2. Fallback: Parse /proc/net/arp and 'ip neigh' for active LAN IPs
        if not discovered_ips:
            if progress_cb:
                progress_cb("Reading kernel ARP cache & neighbor table...")
            try:
                with open("/proc/net/arp", "r") as f:
                    for line in f:
                        parts = line.strip().split()
                        if len(parts) >= 4 and parts[2] != "0x0" and re.match(r"^\d+\.\d+\.\d+\.\d+$", parts[0]):
                            if not parts[0].startswith("127."):
                                discovered_ips.add(parts[0])
            except Exception:
                pass

            try:
                proc = subprocess.run(["ip", "neigh", "show"], capture_output=True, text=True, timeout=3)
                for line in proc.stdout.splitlines():
                    parts = line.strip().split()
                    if parts and re.match(r"^\d+\.\d+\.\d+\.\d+$", parts[0]):
                        if "REACHABLE" in line or "STALE" in line or "DELAY" in line:
                            discovered_ips.add(parts[0])
            except Exception:
                pass

        # 3. For each IP, run avahi-resolve to get the .local hostname
        results = []
        for idx, ip in enumerate(sorted(list(discovered_ips))):
            if progress_cb:
                progress_cb(f"Resolving mDNS for {ip} via avahi-resolve ({idx + 1}/{len(discovered_ips)})...")

            hostname = self.resolve_avahi_ip(ip)

            # Fallback to reverse DNS socket lookup
            if not hostname:
                try:
                    host_info = socket.gethostbyaddr(ip)
                    if host_info and host_info[0]:
                        hostname = host_info[0]
                except Exception:
                    hostname = ip

            results.append({
                "host": hostname if hostname else ip,
                "ip": ip,
                "name": hostname if hostname else ip
            })

        return results

    # -----------------------------------------------------------------------
    # Discovery Method 3: DNS-SD (_nfs._tcp via avahi-browse)
    # -----------------------------------------------------------------------
    def scan_dnssd_nfs(self, progress_cb=None):
        """
        Discovers machines advertising NFS via DNS-SD (_nfs._tcp).
        """
        avahi_bin = shutil.which("avahi-browse")
        if not avahi_bin:
            return []

        if progress_cb:
            progress_cb("Querying DNS-SD for _nfs._tcp records...")

        hosts = set()
        try:
            proc = subprocess.run(
                [avahi_bin, "-rt", "_nfs._tcp", "--parsable"],
                capture_output=True,
                text=True,
                timeout=4
            )
            for line in proc.stdout.splitlines():
                parts = line.split(";")
                if len(parts) >= 8:
                    if parts[6]:
                        hosts.add(parts[6].strip())
                    if parts[7]:
                        hosts.add(parts[7].strip())
        except Exception:
            pass

        return [{"host": h, "ip": h, "name": h} for h in sorted(list(hosts))]

    # -----------------------------------------------------------------------
    # User Input & File Loading
    # -----------------------------------------------------------------------
    @staticmethod
    def parse_hosts_text(text):
        """
        Parses multiline, space, or comma-separated text into a clean list of unique hosts.
        Ignores blank lines and comments (#).
        """
        hosts = []
        seen = set()
        for raw_line in text.splitlines():
            # Strip comments
            line = raw_line.split("#")[0].strip()
            if not line:
                continue
            # Split by comma or whitespace
            tokens = re.split(r"[,\s]+", line)
            for token in tokens:
                token = token.strip()
                if token and token not in seen:
                    seen.add(token)
                    hosts.append(token)
        return hosts

    @staticmethod
    def load_hosts_from_file(file_path):
        """
        Reads candidate hosts from a specified file (e.g. /etc/hosts or custom hosts.txt).
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        hosts = []
        seen = set()
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.split("#")[0].strip()
                if not line:
                    continue
                parts = line.split()
                # If /etc/hosts format: IP host1 host2 ...
                for part in parts:
                    part = part.strip()
                    if part and part not in seen and not part.startswith("127.") and part != "::1":
                        seen.add(part)
                        hosts.append(part)
        return hosts

    # -----------------------------------------------------------------------
    # Query Showmount on Target Hosts
    # -----------------------------------------------------------------------
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
        except Exception:
            pass

        return shares

    def query_multiple_hosts(self, host_list, progress_callback=None):
        """
        Queries showmount across a list of user-provided hosts.
        """
        all_shares = []
        for idx, host in enumerate(host_list):
            if progress_callback:
                progress_callback(f"Querying exports on: {host} ({idx + 1}/{len(host_list)})...")
            shares = self.query_showmount(host)
            all_shares.extend(shares)
        return all_shares

    # -----------------------------------------------------------------------
    # Mount & Unmount Operations
    # -----------------------------------------------------------------------
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

    def mount_share(self, source, mount_point, options="rw,sync,_netdev", sudo_password=None):
        """
        Mounts the NFS export to a local directory.
        Creates mount point if missing.
        """
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
        if os.geteuid() == 0:
            full_cmd = cmd
            input_text = None
        elif sudo_password:
            full_cmd = ["sudo", "-S"] + cmd
            input_text = f"{sudo_password}\n"
        elif shutil.which("pkexec") and (os.environ.get("WAYLAND_DISPLAY") or os.environ.get("DISPLAY")):
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
