# Network & Compute Profiling Report: Neural Network

## 1. Live Benchmark Results
* **Single Node (pi02)**: 18.932 seconds
* **Distributed (2 Nodes)**: 9.801 seconds
* **Speedup**: 1.93x (Near Linear Scaling)

## 2. Compute vs. Network Split
Using the benchmark data, we can isolate the time the cluster spent calculating forward/backward propagation via NumPy versus the time spent dealing with network overhead.

* **Ideal Compute Time** (Single Node / 2): 9.466 seconds
* **Actual Distributed Time**: 9.801 seconds
* **Network Overhead** (Actual - Ideal): 0.335 seconds

**Time Distribution:**
* **Compute-Bound Time:** 96.58%
* **Network-Bound Time:** 3.42%

## 3. Bandwidth Assessment
This architecture uses **Federated Averaging** (Data Parallelism without intermediate syncs). 
* **Parameters synchronized per batch**: 0 
* **Parameters synchronized per epoch**: 0
* **Total Payload**: After all 500 epochs finish, the nodes serialize two small weight matrices (17 total parameters) = **68 Bytes**.

**Conclusion**: The network bandwidth utilized during training is 0 Bytes per second. The 3.42% network overhead is primarily the latency of Slurm (`srun`) orchestrating the parallel execution across the network and collecting the stdout stream. Because the training loop itself is 100% compute-bound, the cluster achieves a massive 1.93x speedup.
