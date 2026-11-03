# Dear ImGui NFS Mount Explorer (Monkeytype Theme)

A fast, dynamic desktop GUI built with **Dear ImGui** (`dearpygui`) that discovers, inspects, mounts, and unmounts NFS file systems on your network.

> **Zero Hardcoded Hosts**: Does NOT rely on hardcoded IPs or hostnames. You can type/paste targets, load a file, or click one button to scan your local network using **Nmap** or **arp-scan + avahi-resolve**.

---

## Key Features

### 1. Flexible Host Target Management
* **Multiline Text Input**: Type or paste hostnames or IPs directly into an editable multiline text area (separated by newlines, commas, or spaces).
* **File Import**: Browse and load hosts directly from a file (e.g. `/etc/hosts` or a custom list).
* **Query Showmount on Targets**: Queries `showmount -e` across all listed hosts and lists their exported folders.

### 2. Automated Network Scanners
* **Scan LAN (Nmap)**:
  * Auto-detects local IPv4 subnets (e.g. `192.168.10.0/24`).
  * Scans for open NFS ports (`-p 2049 --open`) or performs host sweeps.
  * Resolves hostnames and automatically appends discovered hosts into the target list.
* **Scan (arp-scan + avahi-resolve)**:
  * Uses `arp-scan` (or kernel neighbor table fallback) to discover active LAN IP addresses.
  * Uses `avahi-resolve -a <IP>` to resolve each IP to its **`.local` mDNS hostname** (e.g. `pi02.local`).
  * Automatically populates the target list and queries exports.

### 3. Interactive Mount Modal Popup
* Clicking **"Mount..."** opens an interactive pop-up dialog.
* **Mount Point Selection**: Type a custom path (defaults to `/mnt/nfs_<export_name>`) or click **Browse** to open an interactive directory picker.
* **Mount Options**: Configurable options string (default: `rw,sync,noatime,_netdev`).
* **Enable Disk Cache (`-o fsc`)**:
  * Checkbox to append the `-o fsc` flag for local FS-Cache disk acceleration.
  * **Hover Tooltip**: Displays a notice that the `cachefilesd` daemon must be installed and running on the OS (`sudo apt install -y cachefilesd && sudo systemctl enable --now cachefilesd`).
* **Privilege Handling**: Supports polkit (`pkexec`) or sudo password input.
* **Auto-creation**: Automatically runs `mkdir -p` if the target mount directory doesn't exist yet.

### 4. Active System Mounts & Unmounting
* Parses `/proc/mounts` in real-time to show all active NFS file systems attached to your OS.
* Shows live disk usage and free space calculations (`os.statvfs`).
* **Unmount Button**: One-click unmount with automatic fallback to lazy unmount (`-l`) if files are in use.

---

## Monkeytype Theme Palette

| UI Element | Color Name | Hex Code | RGB |
| :--- | :--- | :--- | :--- |
| **Main Canvas Background** | Charcoal Gray | `#323437` | `(50, 52, 55)` |
| **Panels & Child Windows** | Deep Slate | `#2c2e31` | `(44, 46, 49)` |
| **Input Boxes & Headers** | Dark Frame | `#242628` | `(36, 38, 40)` |
| **Primary Text** | Off-White / Cream | `#d1d0c5` | `(209, 208, 197)` |
| **Secondary / Muted Text** | Slate Muted | `#646669` | `(100, 102, 105)` |
| **Signature Accent / Buttons** | Monkeytype Gold | `#e2b714` | `(226, 183, 20)` |
| **Unmount / Danger Buttons** | Muted Crimson | `#ca4754` | `(202, 71, 84)` |
| **Borders & Dividers** | Border Gray | `#424549` | `(66, 69, 73)` |

---

## How to Run

### Quick Launcher (Recommended)
```bash
cd ~/Practice/System/gui
chmod +x run.sh app.py nfs_manager.py
./run.sh
```
*The launcher checks if `dearpygui` is installed; if not, it automatically sets up an isolated virtual environment in `gui/.venv` and launches the application.*

### Direct Python Execution
```bash
cd ~/Practice/System/gui
python3 app.py
```
