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

## Part 2: Cross-Compiling & Dispatching

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

## Part 3: Drawbacks & Limitations Faced

1. **Protocol Version Drift ("Insane Message Length")**: Slurm tightly couples controller and node versions. Ubuntu 26 provided v25, while Debian 12 provided v22. This mismatch caused immediate RPC communication failures. This required abandoning the APT package on the controller and compiling from source to match the Pis.
2. **GCC 14 C23 Strictness**: Compiling the legacy Slurm v22 codebase on Ubuntu 26 failed due to modern GCC 14 enforcing strict prototypes (`()` treated as zero arguments instead of unspecified). Fixed by injecting `CFLAGS="-std=gnu99"`.
3. **PMIx Exascale Plugin Incompatibilities**: Advanced MPI plugins in older Slurm versions failed to build against modern Ubuntu 26 libraries. Fixed by skipping it (`--without-pmix`), as it isn't strictly required for standard task dispatching.
4. **Database State Corruption Prevention**: After downgrading Slurm, the controller refused to start because it detected v25 state files in `/var/lib/slurmctld/`. Required a manual purge of the directory.
5. **Debian OpenMPI Lacking PMI**: The default OpenMPI package on Debian 12 is not compiled against Slurm's PMI libraries, preventing `srun` from natively launching MPI communicators out-of-the-box (yielding `OMPI was not built with SLURM's PMI support`). This limitation was bypassed by relying on Slurm's native task environment variables (`SLURM_PROCID`) for parallelization instead of MPI.
6. **No Shared Filesystem**: Because `/home/isaac-aneek` does not exist on the Pis, Slurm failed to find the working directory or the executable. Overcome by using the `/tmp` directory and Slurm's built-in `--bcast` argument to transfer the executable dynamically.
7. **Cross-Architecture Execution (x86 vs ARM)**: Binaries compiled on the controller immediately triggered `Exec format error` on the compute nodes. Overcome by compiling natively via SSH on the edge devices.
