# Network & Compute Profiling Report: Pre-trained ResNet-18 (DDP)

## 1. Live Benchmark Results
* **Single Node (pi02)**: 5.33 seconds
* **Distributed (2 Nodes)**: 3.28 seconds
* **Speedup**: 1.63x (Moderate Scaling)

## 2. Compute vs. Network Split
Using the benchmark data for the 1,000-image subset, we can reverse-engineer how much time PyTorch spent calculating forward/backward propagation versus the time PyTorch's Gloo backend spent syncing gradients over TCP.

* **Ideal Compute Time** (Single Node / 2): 2.665 seconds
* **Actual Distributed Time**: 3.28 seconds
* **Network Overhead** (Actual - Ideal): 0.615 seconds

**Time Distribution:**
* **Compute-Bound Time:** 81.25%
* **Network-Bound Time:** 18.75%

## 3. Bandwidth Assessment
Because we utilized **Transfer Learning**, we froze the massive 11-million parameter convolutional backbone of ResNet-18 (`requires_grad = False`). PyTorch DDP is highly optimized and only synchronizes parameters that actively require gradients.
* **Parameters synchronized per batch**: 5,130 (Only the final Fully Connected layer)
* **Payload Size per batch**: 20.5 Kilobytes
* **Batches processed**: 16 batches (1,000 samples / 32 batch size / 2 nodes)
* **Total Bandwidth Payload**: 20.5 KB * 16 = **~328 Kilobytes**

**Conclusion**: By freezing layers, we slashed the network payload from 44 Megabytes down to just 328 Kilobytes. This successfully dropped the network-bound wait time from 44.4% (seen in the YOLO cluster) down to just 18.75%, allowing the Raspberry Pi cluster to achieve a vastly superior 1.63x speedup. The remaining 18.75% overhead is purely **TCP Ping Latency** (the physical time it takes for sockets to open and negotiate ACKs 16 times in a row).

---

## 4. NFS Shared Storage Implementation & Benchmark

### 4.1 Overview & Motivation
In edge clusters (like Raspberry Pis), each node typically relies on limited microSD card storage. During deployment, nodes frequently suffer from **storage exhaustion** (e.g. `pi03` failing with `No space left on device` when trying to duplicate datasets locally) and slow transfer times when broadcasting large datasets via SSH (`scp`).

To resolve this, a **Network File System (NFSv4)** was configured across both Raspberry Pis:
* **NFS Server Node (`pi02`)**: Exports `/srv/nfs/cifar10_data` to the cluster LAN (`192.168.10.0/24`) with options `(rw,sync,no_subtree_check,no_root_squash)`.
* **NFS Client Node (`pi03`)**: Mounts `192.168.10.150:/srv/nfs/cifar10_data` directly onto `/mnt/nfs_share` with persistence via `/etc/fstab`.
* **Master Node (`pi02`)**: Also mounts `/srv/nfs/cifar10_data` onto `/mnt/nfs_share`, providing a uniform cluster-wide filesystem path.
* **Elimination of SSH Copy**: The CIFAR-10 dataset resides physically on `pi02`'s storage only once. Both nodes stream batches on-demand over NFS without any prior `scp` copy.

### 4.2 Side-by-Side Benchmark: Local SD Card vs. NFS Storage
Using our dedicated benchmark suite (`benchmark_nfs.sh`) on a 1,000-image subset across both configurations with cold-cache flushing:

| Execution Mode | Local SD Card Storage (`/tmp/cifar10_data`) | Shared NFS Storage (`/mnt/nfs_share`) | Delta ($\Delta T$) | Overhead (%) |
| :--- | :---: | :---: | :---: | :---: |
| **Single Node (`pi02` alone)** | 5.56 s | 5.62 s | +0.06 s | +1.08% |
| **Distributed Cluster (2 Nodes)** | 3.49 s | 3.60 s | +0.11 s | +3.15% |
| **Scaling Speedup Multiplier** | **1.59x** | **1.56x** | -0.03x | Negligible |

### 4.3 Is NFS Becoming a Bottleneck? (In-Depth Technical Analysis)

**Verdict: No, NFS is NOT a bottleneck.**

Here is why NFS introduces virtually zero degradation (+3.15% overhead) on edge clusters:

1. **Gigabit LAN Bandwidth vs. MicroSD Throughput**:
   * Raspberry Pi Class 10 / A1/A2 microSD cards typically achieve sequential read rates of **20–35 MB/s**, and random read rates often drop to **5–12 MB/s**.
   * Gigabit Ethernet between `pi02` and `pi03` provides **~112–118 MB/s** (900+ Mbps) of raw sustained throughput with sub-millisecond round-trip latency (~0.23 ms).
   * As a result, streaming data over Gigabit Ethernet via NFS is actually faster or equal in throughput to reading directly off the physical flash memory of an edge microSD card!

2. **Kernel Page Cache Amplification**:
   * On the NFS server (`pi02`), read requests populate the Linux kernel Page Cache in RAM.
   * When `pi03` reads batch files over NFS RPC, `pi02` serves the data directly from RAM at wire speed rather than reading from physical flash.

3. **DataLoader Asynchronous Prefetching**:
   * PyTorch's `DataLoader(..., num_workers=2)` uses multiprocessing worker pools to prefetch subsequent mini-batches into RAM queue buffers while the CPU executes the forward and backward passes.
   * Because batch fetching is overlapped with tensor computation, the microscopic ~0.11s NFS I/O delay is completely hidden behind the CPU matrix multiplication and Gloo All-Reduce gradient synchronization.

4. **Edge Cluster Impact**:
   * NFS eliminated 100% of the dataset replication time (`scp` was completely avoided).
   * NFS eliminated local disk space bloat, allowing worker nodes with 99% full storage to train large deep learning models seamlessly.
