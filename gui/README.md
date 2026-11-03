# Dear ImGui NFS Mount Explorer (Monkeytype Theme)

A sleek, fast desktop GUI built with **Dear ImGui** (`dearpygui`) that automatically discovers, inspects, mounts, and unmounts NFS file systems on your local network.

Styled with the iconic **Monkeytype** color palette (matte charcoal canvas, off-white text, muted slate borders, and signature gold accent buttons).

---

## Features

1. **Automatic Network Discovery (mDNS & DNS-SD)**:
   - Queries `avahi-browse` for `_nfs._tcp` and `_workstation._tcp` service records across the local area network.
   - Automatically probes `.local` hostnames (e.g. `pi02.local`, `pi03.local`) and `/etc/hosts` cluster definitions.
2. **NFS Export Inspection (`showmount`)**:
   - Executes `showmount -e <host>` behind the scenes to list all exported remote directories, permissions, and allowed client subnets.
   - Includes a manual IP/hostname query bar to probe any specific NFS server immediately.
3. **Interactive Mount Modal Popup**:
   - Clicking **"Mount..."** opens an interactive pop-up dialog.
   - Allows typing or browsing for the local mount directory (defaults to clean paths like `/mnt/nfs_<export_name>`).
   - Offers custom mount option flags (default: `rw,sync,noatime,_netdev`).
   - Handles `mkdir -p` automatically if the target directory does not yet exist.
4. **Active System Mounts & Unmounting**:
   - Parses `/proc/mounts` in real-time to display all active NFS mounts in the OS.
   - Displays live disk storage and percentage used (`os.statvfs`).
   - Provides a one-click **"Unmount"** button (with automatic fallback to lazy unmount `-l` if files are in use).
5. **Execution & Command Log**:
   - Real-time terminal log panel at the bottom displaying command outputs, timestamps, and error diagnostics.

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

### Option 1: Quick Launcher (Automatic Environment Setup)
```bash
cd ~/Practice/System/gui
chmod +x run.sh app.py nfs_manager.py
./run.sh
```
*The launcher checks if `dearpygui` is installed; if not, it automatically sets up an isolated virtual environment in `gui/.venv` and launches the application.*

### Option 2: Direct Python Execution
If you already have `dearpygui` installed:
```bash
cd ~/Practice/System/gui
python3 app.py
```

---

## Requirements

* **Python 3.8+**
* **DearPyGui**: `pip install dearpygui --break-system-packages`
* **System Utilities**: `nfs-common` (for `showmount` and `mount.nfs`):
  ```bash
  sudo apt install -y nfs-common
  ```

