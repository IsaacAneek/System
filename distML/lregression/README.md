# Distributed Logistic Regression (Federated Learning)

This folder contains a from-scratch implementation of a **Distributed Multivariate Logistic Regression** binary classifier. It operates using the Data Parallelism / Federated Averaging paradigm, utilizing Slurm as the execution engine.

## High-Level Pipeline
Instead of transferring massive amounts of raw data to a central location (which causes network bottlenecks), the code pushes the *math* to the data. 

1. **Dispatch**: The master node uses `srun` to broadcast the `worker.py` script to all compute nodes in the cluster simultaneously.
2. **Local Data Generation**: Each worker dynamically generates its own unique synthetic dataset consisting of 15,000 samples and 5 features. In a real-world scenario, this represents local edge data (e.g., patient records at different hospitals).
3. **Local Training**: Each worker runs **Stochastic Gradient Descent (SGD)** locally. By calculating the derivative of the Log Loss function against the sigmoid output, it learns the coefficients (weights) that map the 5 features to the binary classification label.
4. **Parameter Export**: Instead of returning 15,000 rows of data, the worker only returns the 6 optimized floats (5 weights + 1 bias) via `stdout`.
5. **Global Joining (Parameter Averaging)**: The master script catches these floats over the network, averages them together, and constructs the final "Global Model".

## Low-Level Details & Codebase Explanation

### `worker.py` (The Compute Engine)
* **`sigmoid(z)`**: Maps the raw linear equation (`w·x + b`) to a probability between 0 and 1. We bound the inputs between -20 and 20 to prevent floating-point overflow (`math.exp` crash).
* **`generate_classification_data`**: Creates a synthetic dataset with known target weights `[1.5, -2.0, 0.5, 3.0, -1.0]` and adds Gaussian noise to simulate the messy nature of real-world datasets. The random seed is offset by the `SLURM_PROCID` to ensure no two nodes train on the same data.
* **The SGD Loop**:
  ```python
  pred = sigmoid(dot(w, X[i]) + b)
  error = pred - y[i]
  ```
  The core of the Deep Learning/ML process. The error determines how far off the prediction is. We multiply this error by the learning rate and the feature value to step the weights down the gradient curve.

### `master.py` (The Orchestrator)
* Uses `subprocess.Popen` to inject the Slurm job into the controller.
* Identifies the weights from the terminal output by scanning for the `--- MODEL_EXPORT RANK_X ---` string.
* Executes **Federated Averaging**: `global_w = sum(node_weights) / N`.

## Execution Instructions

To dispatch the job and train the model, simply run the master script on the controller node:

```bash
cd /home/isaac-aneek/Practice/System/distML/lregression
chmod +x worker.py
python3 master.py
```
