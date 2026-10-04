# Distributed TinyYOLO CNN with PyTorch DDP

This folder contains a **real distributed deep learning pipeline** built with PyTorch's native `DistributedDataParallel` (DDP) framework. It trains a YOLO-inspired Convolutional Neural Network on the CIFAR-10 image dataset across two Raspberry Pi compute nodes, then retrieves the trained weights and runs inference on the x86 PC controller.

---

## High-Level Pipeline

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         dispatch.sh (PC Controller)                     │
│                                                                         │
│  1. SCP worker.py ──────────────────────► pi02 + pi03                  │
│  2. Download CIFAR-10 on pi02 ──────────► sync to pi03                 │
│  3. SSH launch with env vars:                                           │
│     ┌──────────────────────┐    ┌──────────────────────┐               │
│     │ pi02 (RANK=0)        │◄──►│ pi03 (RANK=1)        │               │
│     │ - Loads 25,000 imgs  │    │ - Loads 25,000 imgs  │               │
│     │ - Forward pass       │    │ - Forward pass       │               │
│     │ - Compute gradients  │    │ - Compute gradients  │               │
│     │ - ALL-REDUCE sync ◄──┼────┼──► ALL-REDUCE sync   │               │
│     │ - Optimizer step     │    │ - Optimizer step     │               │
│     │ - Save .pt weights   │    │                      │               │
│     └──────────────────────┘    └──────────────────────┘               │
│  4. SCP tinyyolo_distributed.pt ◄─────── pi02                         │
│  5. python3 inference.py (on PC) ─────── Evaluate on test set          │
└─────────────────────────────────────────────────────────────────────────┘
```

### What Makes This Different from the Previous Examples

The `lregression/` and `neural_network/` examples used **Federated Averaging** — each node trained independently and their weights were averaged at the end. This is simple but mathematically suboptimal because the nodes never communicate during training.

This example uses **PyTorch DDP (DistributedDataParallel)** with **synchronized gradient all-reduce**. During every single `loss.backward()` call, the gradients computed on `pi02` and `pi03` are automatically averaged over the network via the Gloo backend *before* the optimizer updates the weights. This means both nodes maintain **identical model weights at all times**, producing a single, mathematically correct model — as if it were trained on a single machine with double the batch size.

---

## Low-Level Codebase Explanation

### `worker.py` — The Distributed Training Engine

#### Model Architecture: `TinyYOLONet`
A 3-block convolutional neural network inspired by the YOLO (You Only Look Once) family of object detectors. It uses the same fundamental building blocks:

| Layer | Operation | Output Shape | Parameters |
|-------|-----------|-------------|------------|
| Input | — | 3×32×32 | — |
| Block 1 | Conv2d(3→16, 3×3) + BatchNorm + LeakyReLU(0.1) + MaxPool | 16×16×16 | 448 + 32 |
| Block 2 | Conv2d(16→32, 3×3) + BatchNorm + LeakyReLU(0.1) + MaxPool | 32×8×8 | 4,640 + 64 |
| Block 3 | Conv2d(32→64, 3×3) + BatchNorm + LeakyReLU(0.1) + MaxPool | 64×4×4 | 18,496 + 128 |
| Flatten | — | 1024 | — |
| FC 1 | Linear(1024→128) + ReLU + Dropout(0.3) | 128 | 131,200 |
| FC 2 | Linear(128→10) | 10 | 1,290 |
| **Total** | | | **~156,000** |

- **Conv2d**: The 2D convolution. Slides a 3×3 kernel across the image, computing dot products to extract spatial features (edges, corners, textures).
- **BatchNorm2d**: Normalizes each channel to zero-mean, unit-variance. Stabilizes training and allows higher learning rates.
- **LeakyReLU(0.1)**: The activation function used by all real YOLO models. Unlike standard ReLU (which zeroes negative values), LeakyReLU passes a small slope (0.1) for negative inputs, preventing "dead neurons".
- **MaxPool2d(2,2)**: Halves the spatial resolution. Reduces computation and forces the network to learn translation-invariant features.
- **Dropout(0.3)**: Randomly zeros 30% of neurons during training to prevent overfitting.

#### Distributed Setup: `setup_distributed()`
```python
dist.init_process_group(backend="gloo", rank=rank, world_size=world_size)
```
- **Gloo Backend**: PyTorch's CPU-only distributed communication library. Since Raspberry Pis have no GPUs, we cannot use NCCL (which requires CUDA). Gloo uses TCP sockets over the local network to exchange tensor data between nodes.
- **MASTER_ADDR / MASTER_PORT**: The IP and port of rank 0 (`pi02`). When `pi03` (rank 1) calls `init_process_group`, it connects to this address to perform a **rendezvous** — a handshake where both nodes discover each other and establish persistent TCP connections for gradient synchronization.

#### Data Sharding: `DistributedSampler`
```python
sampler = DistributedSampler(dataset, num_replicas=world_size, rank=rank)
```
CIFAR-10 has 50,000 training images. The `DistributedSampler` automatically partitions the dataset:
- **Rank 0 (pi02)**: Gets images at indices [0, 2, 4, 6, ...] → 25,000 images
- **Rank 1 (pi03)**: Gets images at indices [1, 3, 5, 7, ...] → 25,000 images

Each node only loads and processes its own shard. This is the core of **data parallelism**: the model is replicated, but the data is split.

#### The DDP Wrapper
```python
model = DDP(model)
```
This wraps the model with PyTorch's `DistributedDataParallel`. Under the hood, DDP:
1. Registers **gradient hooks** on every parameter tensor.
2. When `loss.backward()` is called, each node computes its local gradients.
3. The hooks trigger an **all-reduce** operation over the Gloo backend, which:
   - Sends each node's gradients to every other node via TCP.
   - Computes the element-wise average of all gradients.
   - Writes the averaged result back into each node's `.grad` tensor.
4. After all-reduce completes, `optimizer.step()` applies the *same* averaged gradient on *both* nodes, keeping the model weights perfectly synchronized.

#### The Training Loop
```python
for epoch in range(epochs):
    sampler.set_epoch(epoch)  # Re-shuffle the data shard each epoch
    for inputs, targets in dataloader:
        optimizer.zero_grad()
        outputs = model(inputs)          # Forward pass (local)
        loss = criterion(outputs, targets)
        loss.backward()                  # Triggers all-reduce (NETWORK I/O)
        optimizer.step()                 # Apply averaged gradients (local)
```

### `inference.py` — The PC-Side Model Runner

After training, only rank 0 saves the `.pt` weight file. The dispatch script SCPs it back to the PC. The inference script:
1. Reconstructs the same `TinyYOLONet` architecture.
2. Loads the state dict via `torch.load(..., map_location="cpu")` — this transparently handles the ARM→x86 tensor conversion.
3. Downloads the CIFAR-10 **test set** (10,000 images, never seen during training).
4. Runs a forward pass on every test image and computes overall + per-class accuracy.

### `dispatch.sh` — The Orchestrator

The bash script automates the entire pipeline in 5 stages:
1. **Deploy**: SCPs `worker.py` to both Pis.
2. **Data Prep**: Downloads CIFAR-10 on `pi02`, then syncs it to `pi03` via inter-node SCP.
3. **Launch DDP**: SSHs into both Pis simultaneously, setting the 4 required DDP environment variables (`MASTER_ADDR`, `MASTER_PORT`, `RANK`, `WORLD_SIZE`). Both processes run in parallel (`&`), and the script `wait`s for both to complete.
4. **Retrieve Weights**: SCPs the `.pt` file from `pi02` back to the PC.
5. **Inference**: Runs `inference.py` locally on the x86 PC to evaluate the model.

---

## Behind-the-Scenes: Hardware & Network

### What Happens During `loss.backward()`

```
┌─────────── pi02 (Rank 0) ──────────┐     ┌─────────── pi03 (Rank 1) ──────────┐
│ ARM CPU computes local gradients    │     │ ARM CPU computes local gradients    │
│ for 156K parameters                 │     │ for 156K parameters                 │
│                                     │     │                                     │
│ DDP hook fires ──────────────────►  │     │  ◄────────────────── DDP hook fires │
│                                     │     │                                     │
│ ┌─────────────────────────────────┐ │     │ ┌─────────────────────────────────┐ │
│ │ Gloo All-Reduce (Ring):         │ │     │ │ Gloo All-Reduce (Ring):         │ │
│ │ 1. Split grads into N chunks   │ │     │ │ 1. Split grads into N chunks   │ │
│ │ 2. Send chunk[0] ──► pi03      │◄┼─TCP─┼►│ 2. Send chunk[1] ──► pi02      │ │
│ │ 3. Receive chunk[1] from pi03  │ │     │ │ 3. Receive chunk[0] from pi02  │ │
│ │ 4. Average received chunks     │ │     │ │ 4. Average received chunks     │ │
│ │ 5. Broadcast averaged result   │◄┼─TCP─┼►│ 5. Broadcast averaged result   │ │
│ └─────────────────────────────────┘ │     │ └─────────────────────────────────┘ │
│                                     │     │                                     │
│ optimizer.step() with avg grads     │     │ optimizer.step() with avg grads     │
│ (weights now identical on both)     │     │ (weights now identical on both)     │
└─────────────────────────────────────┘     └─────────────────────────────────────┘
```

The Gloo backend uses a **ring all-reduce** algorithm:
1. Gradients are split into chunks.
2. Each node sends one chunk to its neighbor and receives one chunk.
3. After `N-1` rounds (where N = world size), every node has the sum of all gradients.
4. Each node divides by N to get the average.

This happens over raw **TCP sockets** on the Raspberry Pis' physical Ethernet/Wi-Fi interfaces. For 156K float32 parameters, approximately **624 KB** of gradient data is exchanged per backward pass. With a batch size of 64 and ~390 batches per epoch, that's roughly **244 MB of network traffic per epoch**.

---

## Execution Instructions

### Prerequisites
PyTorch and torchvision must be installed on both Raspberry Pis:
```bash
ssh pi@pi02.local "pip3 install --break-system-packages torch torchvision"
ssh pi@pi03.local "pip3 install --break-system-packages torch torchvision"
```

And on the PC controller:
```bash
sudo apt-get install -y python3-torch python3-torchvision
# or: pip3 install torch torchvision
```

### Run
```bash
cd ~/Practice/System/distML/yolo_distributed
./dispatch.sh
```

This single command will:
1. Deploy code to both Pis.
2. Download CIFAR-10 (170 MB).
3. Train the TinyYOLO CNN across both Pis with gradient synchronization.
4. Retrieve the final `.pt` weight file to the PC.
5. Run inference and print per-class accuracy.
