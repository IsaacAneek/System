# Network & Compute Profiling Report: TinyYOLO (PyTorch DDP)

## 1. Live Benchmark Results
* **Single Node (pi02)**: 64.07 seconds
* **Distributed (2 Nodes)**: 57.58 seconds
* **Speedup**: 1.11x (Poor Scaling)

## 2. Compute vs. Network Split
PyTorch's DistributedDataParallel (DDP) framework hides network syncing inside the `loss.backward()` call. By comparing the single-node baseline to the distributed time, we can reverse-engineer exactly how long PyTorch's Gloo backend blocked the CPU to wait for TCP packets.

* **Ideal Compute Time** (Single Node / 2): 32.03 seconds
* **Actual Distributed Time**: 57.58 seconds
* **Network Overhead** (Actual - Ideal): 25.55 seconds

**Time Distribution:**
* **Compute-Bound Time:** 55.6%
* **Network-Bound Time:** 44.4%

## 3. Bandwidth Assessment
Unlike Federated Averaging, PyTorch DDP uses **Synchronous All-Reduce**. The nodes must guarantee mathematically identical weights by syncing gradients on *every single batch*.
* **Parameters synchronized per batch**: ~156,000 (TinyYOLO parameters)
* **Payload Size per batch**: 624 Kilobytes
* **Batches per epoch per node**: 391 batches (50,000 images / 64 batch size / 2 nodes)
* **Total Bandwidth Payload per epoch**: 624 KB * 391 = **~244 Megabytes**

**Conclusion**: To complete a single epoch, the Raspberry Pis had to transmit and acknowledge 244 MB of TCP data back and forth. The network overhead was so severe that the CPUs spent 44.4% of their lifespan frozen, waiting for network buffers to clear. This massive bandwidth requirement is the reason adding 100% more hardware only yielded an 11% speed increase.
