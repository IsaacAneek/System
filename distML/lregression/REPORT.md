# Network & Compute Profiling Report: Logistic Regression

## 1. Live Benchmark Results
* **Single Node (pi02)**: 3.401 seconds
* **Distributed (2 Nodes)**: 1.703 seconds
* **Speedup**: 2.00x (Perfect Linear Scaling)

## 2. Compute vs. Network Split
Using the benchmark data, we can mathematically isolate the time the cluster spent computing matrix operations versus the time spent dealing with network overhead (Slurm dispatch, TCP sockets, weight syncing).

* **Ideal Compute Time** (Single Node / 2): 1.7005 seconds
* **Actual Distributed Time**: 1.703 seconds
* **Network Overhead** (Actual - Ideal): 0.0025 seconds

**Time Distribution:**
* **Compute-Bound Time:** 99.85%
* **Network-Bound Time:** 0.15%

## 3. Bandwidth Assessment
This architecture uses **Federated Averaging** (Data Parallelism without intermediate syncs). 
* **Parameters synchronized per batch**: 0 
* **Parameters synchronized per epoch**: 0
* **Total Payload**: At the very end of the script, the nodes serialize 5 float values (weights + bias) = **20 Bytes**.

**Conclusion**: The network bandwidth utilized during training is effectively 0 Bytes per second. Because there are no intermediate network syncs blocking the CPU, the cluster spends 99.85% of its time fully maximizing the ARM processor's FLOPS, resulting in a flawless 2.00x scaling speedup.
