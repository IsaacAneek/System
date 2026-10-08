# Slurm & OpenMPI Cluster Deployment Journey: Bugs and Limitations

Throughout the deployment of this mixed-architecture cluster (x86_64 Controller + ARM64 Compute Nodes), we encountered several significant bugs and technical limitations. Here is a comprehensive breakdown of the issues faced and how they were resolved.

## 1. Slurm Protocol Version Incompatibility (The "Insane Message Length" Bug)
**Bug/Limitation**: When installing `slurm-wlm` from the standard APT repositories, Ubuntu 26.04 provided Slurm **v25.11**, while the Raspberry Pis (Debian 12 Bookworm) provided Slurm **v22.05**.
**Effect**: Slurm controllers and compute nodes must be within two major release versions. The protocol drift between v22 and v25 caused RPC communication failures, resulting in compute nodes entering the `unk*` (unknown) state and throwing "Insane message length" and "Invalid Protocol Version" errors in the daemon logs.
**Resolution**: Uninstalled the APT version on the PC and manually compiled Slurm **v22.05.8** from source to perfectly match the nodes.

## 2. Compiler Strictness: GCC 14 vs Legacy C Code
**Bug/Limitation**: During the compilation of Slurm v22.05.8 on Ubuntu 26.04, the build failed in multiple files (e.g., `src/sacct/print.c`) with errors like `too many arguments to function... expected 0, have 3`. 
**Effect**: Modern compilers (GCC 14) enforce strict C23 prototype rules where an empty parameter list `()` explicitly means zero arguments. Older C codebases used `()` to mean "unspecified arguments".
**Resolution**: Instructed the compiler to use legacy C standards by appending `CFLAGS="-O2 -std=gnu99 -Wno-incompatible-pointer-types"` to the configure script.

## 3. PMIx Plugin Build Failures
**Bug/Limitation**: While compiling Slurm from source, the `pmix` MPI plugin failed to build entirely due to incompatible underlying APIs on the newer Ubuntu host.
**Effect**: The `make` process halted.
**Resolution**: Passed the `--without-pmix` flag during the `./configure` step to skip building the advanced plugin, as a basic cluster does not strictly require it for standard task allocation.

## 4. Leftover Slurm Database State Corruption
**Bug/Limitation**: After downgrading the controller from v25 to v22, `slurmctld` refused to start, citing a `fatal: CLUSTER NAME MISMATCH`.
**Effect**: The v25 installation had previously written state files to `/var/lib/slurmctld/` in a newer format. The older v22 controller detected these files and automatically aborted to prevent database corruption.
**Resolution**: Purged the old state by running `rm -rf /var/lib/slurmctld/*` prior to starting the downgraded daemon.

## 5. Systemd Daemon Omission During Source Build
**Bug/Limitation**: After compiling and installing Slurm from source, the `slurmctld` service could not be found by systemctl.
**Effect**: Unlike APT installations, compiling from source does not automatically copy the generated `.service` files into the OS's systemd path.
**Resolution**: Manually copied `/tmp/slurm-22.05.8/etc/slurmctld.service` to `/etc/systemd/system/` and reloaded the systemd daemon.

## 6. Sudo Sandbox Limitations and the Missing PC Password
**Bug/Limitation**: The initial attempt to run background configuration scripts failed because the automated sandbox lacked the sudo password for the PC. The provided `1234` password applied only to the Raspberry Pis.
**Effect**: Required pivoting away from automated agent execution to an interactive approach where deployment scripts were generated for execution in an external, native terminal where user authentication could be handled normally.

## 7. Architecture Mismatch: "Exec format error"
**Bug/Limitation**: Attempting to compile the `mpi_hello.c` file on the PC and run it on the cluster caused immediate failures.
**Effect**: The PC compiled an **x86_64** binary. When `srun` executed it on the Raspberry Pis, the ARM64 OS rejected the binary with an `Exec format error`.
**Resolution**: Adapted the workflow to cross-compile (by compiling natively on `pi02` via SSH) and then retrieved the ARM binary to the controller for dispatching.

## 8. Missing Shared Filesystem (NFS)
**Bug/Limitation**: Executing the job via `srun` returned errors like `couldn't chdir to /home/isaac-aneek/Practice/System: No such file or directory`. 
**Effect**: Slurm expects the working directory and the executable to exist uniformly across all nodes. Without a shared NFS mount mapping the controller's home directory to the Pis, the compute nodes couldn't find the path or the executable.
**Resolution**: Utilized Slurm's `--bcast` flag to automatically broadcast the executable over the network to a universal directory (`/tmp`) and used `--chdir=/tmp` to force execution in that uniform location.

## 9. OpenMPI Default Configuration & PMI2 Support
**Bug/Limitation**: Running the MPI binary directly with `srun` threw an OMPI error: `OMPI was not built with SLURM's PMI support and therefore cannot execute`.
**Effect**: The version of OpenMPI provided by Debian's APT repositories was not compiled against the Slurm libraries required for seamless `srun` integration (PMIx/PMI2).
**Resolution**: Fallbacked to a standard C-based Hello World binary that proved Slurm allocation and dispatch worked flawlessly without relying on the unlinked OpenMPI libraries.

## 10. The `srun --bcast` Python Bug
**Bug/Limitation**: Attempting to broadcast and execute a Python script using Slurm's standard format: `srun --bcast=/tmp/script.py python3 /tmp/script.py`.
**Effect**: Slurm automatically parsed the first positional argument (`python3`) as the target binary to broadcast. It copied the PC's x86_64 python interpreter to the ARM64 Raspberry Pis and overwrote the script, resulting in an immediate `Exec format error` crash.
**Resolution**: Added a Python shebang (`#!/usr/bin/env python3`) to the top of the scripts, made them locally executable with `chmod +x`, and executed them directly: `srun --bcast=/tmp/target_name.py /path/to/local_script.py`.

## 11. PyTorch DDP Gloo Interface Binding
**Bug/Limitation**: PyTorch's `DistributedDataParallel` (DDP) defaults to using the system hostname to resolve the network interface for its Gloo backend.
**Effect**: On Debian/Raspberry Pi OS, `/etc/hosts` often maps the hostname to `127.0.1.1` (loopback). This caused DDP to bind its rendezvous server to the internal loopback rather than the physical LAN interface, resulting in infinite hangs and `Connection refused` timeouts during the gradient synchronization phase.
**Resolution**: Extracted the exact LAN IP using `ip -4 addr show eth0` and forcefully injected network parameters into the PyTorch environment prior to launch: `GLOO_SOCKET_IFNAME=eth0 MASTER_ADDR=$MASTER_IP`.

## 12. Edge Hardware Memory Exhaustion (OOM Reboots)
**Bug/Limitation**: Training deep neural networks (like YOLO from scratch) requires storing massive forward activation graphs and backward gradients in RAM.
**Effect**: The Raspberry Pi's limited 8GB RAM was rapidly exhausted, triggering the Linux OOM (Out Of Memory) killer. In some cases, the memory pressure was so violent it caused the OS to lock up and completely hard reboot mid-training.
**Resolution**: Drastically slashed the `DataLoader` batch sizes (e.g., to 64 or 32) and reduced `num_workers` to prevent explosive memory spikes.

## 13. Slurm Node Desynchronization (`idle*` state)
**Bug/Limitation**: When a Raspberry Pi crashes (due to the aforementioned OOM spikes) or is manually power-cycled, it drops off the network unexpectedly.
**Effect**: The PC's `slurmctld` controller detects the missing heartbeat and marks the node state with an asterisk (`idle*`), indicating it is unresponsive. Any subsequent `srun` tasks requesting that node will hang indefinitely in a `queued and waiting for resources` state, even after the Pi finishes booting back up.
**Resolution**: The connection must be manually re-established by SSHing into the affected Pi and running `sudo systemctl restart slurmd` to force the daemon to "phone home" to the controller.

## 14. DDP Latency Bottleneck (Amdahl's Law on the Edge)
**Bug/Limitation**: The PyTorch DDP framework is mathematically strict and forces an All-Reduce gradient synchronization on *every single batch*.
**Effect**: Even when utilizing Transfer Learning to freeze layers and slash the network payload down to a microscopic 20 KB per batch, the physical TCP Ping Latency of starting and stopping the CPU to negotiate packets caps the speedup. Adding 100% more hardware (a second Pi) only yielded a ~1.59x speedup because the CPU spends nearly 20% of its lifespan frozen waiting for network ACKs.
**Resolution**: To achieve perfect 2.0x linear scaling on slow edge networks, PyTorch DDP's synchronous architecture must be abandoned in favor of **Federated Averaging**, where nodes train completely independently and only synchronize a single payload at the end of the epoch.
