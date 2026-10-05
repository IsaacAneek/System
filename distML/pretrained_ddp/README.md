# Distributed Transfer Learning (Pre-trained ResNet-18)

This directory demonstrates how to perform **Distributed Transfer Learning** on an edge cluster using PyTorch's `DistributedDataParallel` (DDP) framework. Instead of training a model entirely from scratch (which can take days or weeks), we download a heavy **ResNet-18** model that has already been pre-trained by researchers on millions of images from the ImageNet dataset.

## Directory Structure
To match our standard cluster convention, this pipeline is split into distinct production and benchmarking suites:
* `worker.py`: The primary PyTorch worker script. Runs on the edge nodes, executes the full DDP transfer learning loop, and saves the final model weights (`.pt`).
* `inference.py`: Runs locally on the master PC controller. It initializes a blank ResNet-18, loads the distributed weights retrieved from the cluster, and evaluates the final accuracy.
* `dispatch.sh`: The standard bash orchestrator. It handles deployment, dataset syncing, DDP rendezvous, weight retrieval, and local inference execution.
* `benchmark_node.py` & `benchmark.sh`: Segregated scripts used purely for profiling speedup metrics on a 1,000-image subset.

## The Transfer Learning Pipeline

1. **Pre-trained Weights**: The script downloads the `ResNet18_Weights.DEFAULT` weights. These weights already "know" how to detect edges, shapes, textures, and complex objects.
2. **Layer Freezing**: We freeze the entire massive convolutional backbone of the model by setting `requires_grad = False`. This saves an enormous amount of CPU calculation time because we don't need to backpropagate through 18 deep layers.
3. **Head Replacement**: We replace the final Fully Connected (FC) layer (which originally predicted 1000 ImageNet classes) with a fresh, untrained layer designed to predict the 10 classes of CIFAR-10.
4. **Targeted Optimization**: The `Adam` optimizer is instructed to *only* update the parameters of this single new FC layer.
5. **Model Retrieval & Inference**: Once `worker.py` completes, `dispatch.sh` pulls the weights over SSH back to the local PC, where `inference.py` scores it against the test set.

## Behind the Scenes: PyTorch DDP Orchestration

### 1. DDP Dispatching & Connection Setup
When `dist.init_process_group(backend="gloo")` is called:
* `pi02` (Rank 0) looks at the `MASTER_PORT` environment variable and opens a TCP rendezvous server on that port.
* `pi03` (Rank 1) looks at the `MASTER_ADDR` and `MASTER_PORT` variables, and establishes a TCP handshake with `pi02`. 
* Once both nodes have checked in, the barrier lifts and training begins.

### 2. The Distributed Sampler
CIFAR-10 contains 50,000 images. The `DistributedSampler` guarantees that nodes do not process the same data. 
* `pi02` receives indices: `[0, 2, 4, 6...]`
* `pi03` receives indices: `[1, 3, 5, 7...]`
This effectively cuts the local epoch workload in half.

### 3. Gradient Synchronization (All-Reduce)
Because we wrapped the model in `DDP(model)`, PyTorch injects hooks into the computational graph.
When `loss.backward()` is called, PyTorch calculates the gradients for the final FC layer. As soon as the gradients are ready, the DDP hooks fire and execute the **Gloo All-Reduce Algorithm** over the physical network:
* `pi02` and `pi03` split their gradient tensors into chunks.
* They stream these chunks to each other over TCP (Ring-Reduce).
* They mathematically sum the chunks together, divide by the `WORLD_SIZE` (2), and overwrite their local `.grad` attributes with the exact global average.
* Finally, `optimizer.step()` applies the identical gradient update to both nodes, ensuring the models remain mathematically identical clones.

## Execution

### Run the Benchmark (Speedup Test)
```bash
cd ~/Practice/System/distML/pretrained_ddp
chmod +x *.sh *.py
./benchmark.sh
```

### Standard Run (Full Dataset + Local Evaluation)
```bash
cd ~/Practice/System/distML/pretrained_ddp
chmod +x *.sh *.py
./dispatch.sh
```
