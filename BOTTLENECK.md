# Why didnt we get near 2x speed?

That is an excellent observation, and it highlights one of the most infamous problems in distributed systems engineering: The Network Bottleneck (Compute-to-Communication Ratio).

Getting a 1.1x speedup instead of a 2x speedup is completely expected on this hardware, and here is exactly why it happens:

## The Cost of Gradient Synchronization

In our earlier Monte Carlo Pi (sim_pi_mpi.c) and Logistic Regression federated examples, the Raspberry Pis computed for several seconds entirely independently and only communicated over the network exactly once at the very end of the run. That gave near-perfect 2.0x scaling.

But PyTorch's DistributedDataParallel (DDP) forces the nodes to synchronize their gradients during every single batch.

The TinyYOLO model has ~156,000 parameters (about 624 KB of floating-point data).
At a batch size of 64, CIFAR-10 requires 390 batches per epoch.
This means the Raspberry Pis are pausing their CPUs to negotiate, open TCP sockets, and transmit 624 KB of data back and forth 390 times per epoch.

## Standard Ethernet vs. Supercomputer Interconnects

In a real enterprise cluster, nodes are connected by NVLink or InfiniBand, which can transmit hundreds of gigabytes per second with microsecond latency. PyTorch's DDP was designed for that environment (via the NCCL backend).

Your Raspberry Pis are communicating over standard TCP/IP (likely standard Gigabit Ethernet or Wi-Fi) via the Gloo backend. The latency overhead of sending TCP packets completely dwarfs the time the ARM CPU saves by processing half the images. You are spending more time waiting for the network card than computing the neural network!

## CPU vs. GPU Asynchrony

On high-end systems, GPUs crunch the math while dedicated networking chips (NICs) transfer the gradients in the background simultaneously. On a Raspberry Pi, the same ARM CPU cores doing the neural network math must pause to serialize and handle the network traffic.

## How do we fix it?

If you wanted to push that 1.1x closer to 1.8x on your Pis, you would need to artificially increase the Compute-to-Communication ratio. You can do this by:

Increasing Batch Size: If we change the batch size from 64 to 512, the network syncs drop from 390 times an epoch to just 48 times an epoch. The Pis spend much longer computing before they have to talk to each other.
Gradient Accumulation: You can tell PyTorch to locally compute gradients for 5 batches in a row, sum them up locally, and only trigger the DDP network sync on the 5th batch.

Welcome to the harsh reality of Distributed Deep Learning! Moving data is always the most expensive operation in a cluster.

# The Network Bottleneck: Why Distributed Deep Learning is Hard

When running the distributed PyTorch benchmark across two Raspberry Pis, adding **100% more hardware** (moving from 1 node to 2 nodes) resulted in only a **~1.1x speedup**. 

At first glance, this seems like a failure. In reality, it perfectly demonstrates the most infamous problem in distributed systems engineering: **The Compute-to-Communication Ratio**.

---

## 1. The Core Issue: Synchronous All-Reduce
In our earlier Monte Carlo Pi calculation (`sim_pi_mpi.c`), the cluster achieved near perfect **2.0x linear scaling**. Why? Because it was an *embarrassingly parallel* problem. Both Pis computed 50 million cycles independently and only sent **one single network packet** at the very end of the script to combine the result.

PyTorch's `DistributedDataParallel` (DDP) does not have that luxury. Deep Learning relies on **Synchronous Stochastic Gradient Descent (SGD)**. 
1. `pi02` computes gradients for 32 images.
2. `pi03` computes gradients for 32 images.
3. Before the optimizer can update the weights, both nodes **must** pause and combine their math.

Our TinyYOLO model has **~156,000 parameters** (approx 624 KB of float32 data). Because we used a batch size of 64, CIFAR-10's 25,000 images per node required **390 batches** per epoch.
This means **390 times per epoch**, the CPUs had to completely freeze their neural network calculations, negotiate a TCP connection over the LAN, and transmit 624 KB of data back and forth using the Gloo ring-reduce algorithm. 

## 2. Hardware Realities: Supercomputers vs. Raspberry Pis
PyTorch DDP is heavily optimized for enterprise hardware. The framework assumes a specific architectural layout that simply doesn't exist on edge devices:

* **The Network Fabric**: Enterprise clusters use **InfiniBand** or **NVLink**, which offer bandwidths of hundreds of Gigabytes per second with single-digit microsecond latencies. Raspberry Pis rely on standard Gigabit Ethernet or Wi-Fi, where the latency alone of establishing the TCP handshake completely dwarfs the time it takes an ARM CPU to multiply a matrix.
* **GPUDirect RDMA**: In data centers, Network Interface Cards (NICs) use Remote Direct Memory Access (RDMA) to pull gradient data directly out of GPU VRAM and send it to other nodes over the network, completely bypassing the CPU. On a Pi, the exact same CPU cores responsible for the neural network math must handle the OS kernel TCP/IP networking stack overhead.

You are spending more time moving data than computing it.

## 3. Amdahl's Law in Action
Amdahl's Law states that the theoretical maximum speedup of a system is strictly limited by the portion of the task that *cannot* be parallelized.
In DDP, the network synchronization (`dist.all_reduce()`) is strictly serial and blocking. If a forward/backward pass takes 100 milliseconds, but the Gloo TCP sync takes 80 milliseconds, the absolute mathematical ceiling of your speedup is crippled before you even add a third node.

---

## 4. How to Overcome the Bottleneck
To push the cluster closer to a true 2.0x speedup, we must artificially increase the **Compute-to-Communication Ratio** so the nodes spend more time computing and less time talking.

1. **Increase the Batch Size**: If we jump from a batch size of 64 to 512, the network syncs drop from 390 times an epoch to just 48. The CPU does significantly more math per network pause. (Note: Massive batch sizes can degrade model accuracy, requiring learning rate warmup schedulers).
2. **Gradient Accumulation**: We can rewrite the PyTorch loop to compute gradients for 5 consecutive batches *locally*, sum them up, and only trigger the DDP network sync on the 5th batch (`if batch_idx % 5 == 0: optimizer.step()`).
3. **Gradient Compression**: Modern distributed frameworks can cast the 32-bit float gradients into 16-bit or even 8-bit integers before transmitting them over the network, slashing the bandwidth requirement by 75%.
4. **Federated Averaging**: Abandon batch-level syncs completely (as seen in the `distML/lregression` script). Let the Pis train independently for a full epoch, then average their final models. This is highly scalable but mathematically inferior to DDP.
