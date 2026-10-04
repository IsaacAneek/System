# Distributed Multi-Layer Neural Network (Deep Learning)

This folder contains a from-scratch **Multi-Layer Perceptron (MLP)** Neural Network implemented purely in NumPy and dispatched via Slurm. 

While Linear/Logistic regression is great for linearly separable data, real-world data is often highly non-linear. This code trains a network to solve a continuous **XOR classification problem** ($x_1 \times x_2 > 0$), which is mathematically impossible for a single-layer algorithm to solve.

## High-Level Pipeline
Because the compute nodes (Raspberry Pis) have limited memory, moving massive datasets to a central server is inefficient. Instead, we use **Federated Learning (Data Parallelism)**.

1. **Slurm Dispatch**: The master script uses `--bcast` to send the Neural Network python code to the edge nodes simultaneously.
2. **Local Edge Data**: Each node dynamically bootstraps a localized dataset of 100,000 continuous XOR coordinates.
3. **Deep Learning Optimization**: The Pis use `numpy` to perform heavy matrix multiplications. They compute the forward pass, calculate the loss, and backpropagate the gradients across the Hidden and Output layers for 500 epochs.
4. **Federated Averaging**: The 17 resulting parameters (W1, b1, W2, b2) are flattened into a string and transmitted back to the central server via standard output, where they are mathematically averaged to construct a highly generalized Global Model.

## Low-Level Codebase Explanation

### `worker.py` (The Neural Network)
* **Architecture**: Input(2 nodes) -> Hidden Layer(4 nodes) -> Output Layer(1 node).
* **`generate_non_linear_data`**: Generates 2D coordinates. If the product of the coordinates is positive (Quadrants I and III), the label is 1. Otherwise, 0.
* **The Forward Pass**:
  ```python
  Z1 = np.dot(X, W1) + b1
  A1 = sigmoid(Z1)
  Z2 = np.dot(A1, W2) + b2
  A2 = sigmoid(Z2)
  ```
  This projects the input data into a higher-dimensional space (A1) where the non-linear XOR data becomes linearly separable by the output layer (A2).
* **Backpropagation**: Calculates the partial derivatives (`dZ2`, `dW2`, `dW1`) using the chain rule, stepping backwards from the output error to update the hidden weights. This is heavily vectorized using NumPy for performance on the ARM processors.

### `master.py` (The Aggregator)
* Submits the job to the Slurm controller.
* Intercepts the serialized weights (`W1|b1|W2|b2`).
* Performs the **Federated Averaging** function: $W_{global} = \frac{1}{N} \sum_{i=1}^{N} W_i$.

## Execution Instructions

Ensure you make the worker executable, then run the master python script:

```bash
cd /home/isaac-aneek/Practice/System/distML/neural_network
chmod +x worker.py
python3 master.py
```
