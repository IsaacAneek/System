# Mixed-Architecture Slurm Cluster: Setup & Dispatch Guide

This guide documents the complete end-to-end process for deploying a Slurm cluster across an x86_64 Controller (Ubuntu 26.04) and ARM64 Compute Nodes (Raspberry Pi Debian 12), including parallel job dispatching and the technical limitations overcome during the build.

---

## Part 1: Installation & Setup

### 1. Base Dependencies
First, ensure `munge`, `openmpi`, and necessary build tools are installed across all machines.

**On the Controller (PC):**
```bash
sudo apt-get update
# Remove incompatible APT versions of Slurm if present
sudo apt-get remove --purge -y slurm-wlm slurmctld slurm-client
# Install dependencies
sudo apt-get install -y munge libmunge-dev build-essential wget bzip2 sshpass openmpi-bin libopenmpi-dev
```

**On the Compute Nodes (Pis):**
```bash
# Executed via SSH from the controller
for node in pi02.local pi03.local; do
    ssh pi@$node "sudo apt-get update && sudo apt-get install -y munge slurmd slurm-client openmpi-bin libopenmpi-dev"
done
```

### 2. Munge Key Synchronization
Munge handles authentication between the controller and nodes. All machines **must** share the exact same key.

```bash
# On Controller: Generate and secure the key
sudo create-munge-key
sudo chown munge:munge /etc/munge/munge.key
sudo chmod 400 /etc/munge/munge.key
sudo systemctl enable --now munge

# Push the key to the Pis
for node in pi02.local pi03.local; do
    sshpass -p '1234' scp -o StrictHostKeyChecking=no /etc/munge/munge.key pi@${node}:/tmp/munge.key
    sshpass -p '1234' ssh -o StrictHostKeyChecking=no pi@${node} "sudo mv /tmp/munge.key /etc/munge/munge.key && sudo chown munge:munge /etc/munge/munge.key && sudo chmod 400 /etc/munge/munge.key && sudo systemctl enable --now munge"
done
```

### 3. Compiling Slurm from Source (Version Matching)
Because Ubuntu 26.04 provides Slurm v25 and Debian 12 provides Slurm v22, we must compile Slurm v22.05.8 from source on the controller to prevent RPC protocol mismatch errors.

```bash
cd /tmp
wget -q https://download.schedmd.com/slurm/slurm-22.05.8.tar.bz2
tar -xaf slurm-22.05.8.tar.bz2
cd slurm-22.05.8

# Configure with legacy C-standards to bypass GCC 14 strictness, and disable PMIx to prevent build errors
sudo ./configure --prefix=/usr --sysconfdir=/etc/slurm --with-munge --without-pmix CFLAGS="-O2 -std=gnu99 -Wno-incompatible-pointer-types"
sudo make -j$(nproc)
sudo make install
```

### 4. Configuration & Daemon Startup
Create `/etc/slurm/slurm.conf` on the controller (mapping `pi02` and `pi03` to the `pi` partition) and distribute it.

```bash
# Push config to Pis
for node in pi02.local pi03.local; do
    scp /etc/slurm/slurm.conf pi@${node}:/tmp/slurm.conf
    ssh pi@${node} "sudo mv /tmp/slurm.conf /etc/slurm/slurm.conf && sudo systemctl enable --now slurmd"
done

# Start Controller
sudo mkdir -p /var/lib/slurmctld /var/log/slurm
sudo chown slurm:slurm /var/lib/slurmctld /var/log/slurm

# CRITICAL: Wipe any leftover database state from older/newer installations
sudo rm -rf /var/lib/slurmctld/*

# Copy systemd service from source tree and start
sudo cp /tmp/slurm-22.05.8/etc/slurmctld.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now slurmctld
```

---

## Part 2: Shared Network Storage Setup (NFS)

In an edge cluster, replicating heavy datasets (e.g., CIFAR-10, ImageNet) onto every individual node via SSH/SCP quickly exhausts limited microSD card storage and creates network transfer bottlenecks. To solve this, a **Network File System (NFSv4)** was deployed across the Raspberry Pi nodes so both compute nodes access a unified shared directory without local duplication.

### 1. NFS Server Configuration (`pi02.local` - 192.168.10.150)
Install `nfs-kernel-server` on `pi02` and export the shared dataset directory to the cluster:

```bash
# On pi02:
sudo apt-get update && sudo apt-get install -y nfs-kernel-server
sudo mkdir -p /srv/nfs/cifar10_data
sudo chown -R pi:pi /srv/nfs
sudo chmod -R 777 /srv/nfs

# Configure export in /etc/exports
sudo bash -c 'cat << "EOF" > /etc/exports
/srv/nfs/cifar10_data *(rw,sync,no_subtree_check,no_root_squash)
EOF'

# Apply export and enable daemon
sudo exportfs -arv
sudo systemctl restart nfs-kernel-server
sudo systemctl enable nfs-kernel-server
```

### 2. NFS Client & Mount Setup (`pi02.local` & `pi03.local`)
Create the mount point `/mnt/nfs_share` on both compute nodes and mount the NFS share:

```bash
# Executed on both pi02 and pi03:
sudo apt-get install -y nfs-common
sudo mkdir -p /mnt/nfs_share
sudo mount -t nfs 192.168.10.150:/srv/nfs/cifar10_data /mnt/nfs_share

# Persist mount across reboots in /etc/fstab:
echo "192.168.10.150:/srv/nfs/cifar10_data /mnt/nfs_share nfs defaults,_netdev 0 0" | sudo tee -a /etc/fstab
```

### 3. Verification & Zero-Copy Dataset Streaming
With NFS active, the dataset resides physically only on `pi02`'s disk:
* Worker nodes (`pi02` and `pi03`) stream training batches directly from `/mnt/nfs_share` via PyTorch `DataLoader`.
* Eliminates dataset SSH broadcast time (`scp` step removed).
* Bypasses the edge node storage limits (prevents `No space left on device` on worker Pis).
* Benchmarking demonstrates that Gigabit LAN streaming (~115 MB/s) delivers throughput comparable to or faster than local microSD flash reads with only +3.15% overhead.

---

## Part 3: Cross-Compiling & Dispatching

Because the controller is `x86_64` and the nodes are `ARM64`, binaries compiled on the PC will return an `Exec format error` on the Pis. Furthermore, without a shared Network File System (NFS), the binary must be manually broadcasted.

### 1. Write the Simulation
Create a Monte Carlo simulation utilizing Slurm's native environment variables (`SLURM_PROCID`) instead of relying on OpenMPI.

```bash
cat << 'EOF' > ~/Practice/System/sim_pi.c
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <time.h>

int main(int argc, char **argv) {
    long long int samples = 50000000;
    long long int hits = 0;
    int rank = 0, size = 1;
    char hostname[256];

    gethostname(hostname, sizeof(hostname));
    if (getenv("SLURM_PROCID")) rank = atoi(getenv("SLURM_PROCID"));
    if (getenv("SLURM_NTASKS")) size = atoi(getenv("SLURM_NTASKS"));

    srand(time(NULL) + rank * 9999);
    for (long long int i = 0; i < samples; ++i) {
        double x = (double)rand() / RAND_MAX * 2.0 - 1.0;
        double y = (double)rand() / RAND_MAX * 2.0 - 1.0;
        if (x * x + y * y <= 1.0) hits++;
    }

    printf("[Task %d/%d | %s] Local Pi estimate: %f\n", rank, size, hostname, 4.0 * hits / samples);
    return 0;
}
EOF
```

### 2. Native ARM Compilation via SSH
Send the code to a Pi, compile it natively for ARM, and retrieve the binary.

```bash
ssh pi@pi02.local "cat > /tmp/sim_pi.c" < ~/Practice/System/sim_pi.c
ssh pi@pi02.local "gcc -O3 /tmp/sim_pi.c -o /tmp/sim_pi_arm"
scp pi@pi02.local:/tmp/sim_pi_arm /tmp/sim_pi_arm
```

### 3. Dispatch the Job
Use `--bcast` to automatically copy the binary over the network, and `--chdir` to execute it in a universal directory (`/tmp`) that exists on all nodes.

```bash
srun --chdir=/tmp --bcast=/tmp/sim_pi_arm -N 2 /tmp/sim_pi_arm
```

---

## Part 4: Drawbacks & Limitations Faced

1. **Protocol Version Drift ("Insane Message Length")**: Slurm tightly couples controller and node versions. Ubuntu 26 provided v25, while Debian 12 provided v22. This mismatch caused immediate RPC communication failures. This required abandoning the APT package on the controller and compiling from source to match the Pis.
2. **GCC 14 C23 Strictness**: Compiling the legacy Slurm v22 codebase on Ubuntu 26 failed due to modern GCC 14 enforcing strict prototypes (`()` treated as zero arguments instead of unspecified). Fixed by injecting `CFLAGS="-std=gnu99"`.
3. **PMIx Exascale Plugin Incompatibilities**: Advanced MPI plugins in older Slurm versions failed to build against modern Ubuntu 26 libraries. Fixed by skipping it (`--without-pmix`), as it isn't strictly required for standard task dispatching.
4. **Database State Corruption Prevention**: After downgrading Slurm, the controller refused to start because it detected v25 state files in `/var/lib/slurmctld/`. Required a manual purge of the directory.
5. **Debian OpenMPI Lacking PMI**: The default OpenMPI package on Debian 12 is not compiled against Slurm's PMI libraries, preventing `srun` from natively launching MPI communicators out-of-the-box (yielding `OMPI was not built with SLURM's PMI support`). This limitation was bypassed by relying on Slurm's native task environment variables (`SLURM_PROCID`) for parallelization instead of MPI.
6. **No Shared Filesystem (Resolved via NFS)**: Because `/home/isaac-aneek` does not exist on the Pis, Slurm originally failed to find the working directory or the executable without `--bcast`. Furthermore, edge worker nodes quickly ran out of disk space (`No space left on device`) when trying to copy machine learning datasets locally via `scp`. This limitation was comprehensively solved by configuring an **NFSv4 mount (`/mnt/nfs_share`)** across both Pis, allowing datasets and scripts to be shared with zero-copy overhead.
7. **Cross-Architecture Execution (x86 vs ARM)**: Binaries compiled on the controller immediately triggered `Exec format error` on the compute nodes. Overcome by compiling natively via SSH on the edge devices.


---

## Part 5: Standalone Pretrained YOLOv3 (`distML/yolo_pretrained/`)

A completely self-contained, single-node implementation of **YOLOv3-Tiny** with official Darknet pretrained weights. Designed for standalone execution on a single node without any distributed cluster, Slurm, or multi-node overhead.

### 1. Zero-Ultralytics Pure PyTorch Architecture
* Uses native PyTorch modules with a custom binary parser (`yolo_model.py`) that reads official Darknet `.weights` files (`yolov3-tiny.weights`) directly into PyTorch tensors.
* Eliminates heavy third-party framework dependencies (`ultralytics` package is NOT required).

### 2. Modular Structure
* `yolo_model.py`: Pure PyTorch YOLOv3-Tiny architecture, native Darknet weight loader, and PyTorch Non-Maximum Suppression (NMS).
* `dataset.py`: Standalone dataset module that downloads COCO128 (~7MB) into `images/` and `labels/` folders (with an automatic synthetic fallback generator for offline environments), and provides the `YOLOFolderDataset` loader.
* `inference.py`: Runs a single inference pass on a local image or URL, prints a formatted detection table, and saves the annotated bounding-box image to `./runs/inference/output.jpg`.
* `train.py`: Fine-tunes the detection heads on local dataset folders and saves checkpoint weights to `./runs/yolov3_trained.pt`.

### 3. Execution Commands
```bash
cd ~/Practice/System/distML/yolo_pretrained

# Pre-download & verify dataset
python3 dataset.py

# Run standalone inference
python3 inference.py --source /path/to/image.jpg

# Run single-node training (3 epochs, batch size 4)
python3 train.py --epochs 3 --batch-size 4
```

---

## Part 6: Dear ImGui NFS Mount Explorer GUI (`gui/`)

A desktop graphical user interface built with **Dear ImGui** (`dearpygui`) styled in the **Monkeytype** color palette. It automates finding, inspecting, mounting, and unmounting NFS file systems across your local network.

### 1. Dynamic Network Discovery (Zero Hardcoded Hosts)
* **Editable Targets Multiline Box**: Directly enter, paste, or edit hostnames and IPs (e.g. `pi02.local`, `192.168.10.150`).
* **File Import**: Browse and load candidate hosts from files such as `/etc/hosts` or custom lists.
* **Scan LAN (Nmap)**: Auto-detects local IPv4 subnets (e.g. `192.168.10.0/24`) and scans for open NFS ports (`-p 2049 --open`) to locate servers instantly.
* **Scan (arp-scan + avahi-resolve)**: Discovers active LAN devices using ARP sweeps and resolves each IP to its **`.local` mDNS hostname** using `avahi-resolve -a <IP>`.
* **Export Inspection (`showmount`)**: Queries `showmount -e` across all identified hosts to display exported directories and allowed client subnets.

### 2. Interactive Mount Modal & Local FS-Cache
* **Mount Point Selection**: Enter a custom path or use the built-in directory browser dialog. Automatically executes `mkdir -p` if the folder doesn't exist.
* **Enable Disk Cache (`-o fsc`)**: Checkbox that appends the `-o fsc` flag to mount options for local SSD/disk read acceleration via Linux FS-Cache.
  * *Hover Tooltip*: Informs the user that the `cachefilesd` daemon must be running (`sudo apt install -y cachefilesd && sudo systemctl enable --now cachefilesd`).
* **Privilege Handling**: Seamlessly executes mount operations using `pkexec` (Polkit GUI prompt) or user-supplied sudo credentials.

### 3. Active OS Mounts Management
* Parses `/proc/mounts` in real-time to display active NFS mounts attached to the system.
* Displays live disk capacity and available storage percentages (`os.statvfs`).
* Provides a one-click **"Unmount"** button with automatic fallback to lazy unmounting (`-l`).

### 4. Monkeytype Visual Styling
* Background: Matte Charcoal (`#323437`)
* Panels & Frames: Deep Slate (`#2c2e31` / `#242628`)
* Primary Text: Off-White / Cream (`#d1d0c5`)
* Action Buttons & Accents: Monkeytype Gold (`#e2b714`)
* Danger / Unmount: Muted Crimson (`#ca4754`)

### 5. Launching the GUI
```bash
cd ~/Practice/System/gui
chmod +x run.sh app.py nfs_manager.py
./run.sh
```
*(The `run.sh` script automatically checks for `dearpygui`, sets up an isolated virtual environment if missing, and launches the application).*
