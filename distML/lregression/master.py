import subprocess
import time

print("==================================================")
print(" DISTRIBUTED LOGISTIC REGRESSION (CLASSIFICATION) ")
print("==================================================")

cmd = ["srun", "--chdir=/tmp", "--bcast=/tmp/worker.py", "-N", "2", "/home/isaac-aneek/Practice/System/distML/lregression/worker.py"]

print("[Master] Dispatching ML nodes via Slurm...")
start = time.time()
process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
stdout, stderr = process.communicate()

if process.returncode != 0:
    print("Execution failed!")
    print(stderr)
    exit(1)

print(stdout)
print(f"[Master] Training completed in {time.time() - start:.2f} seconds.")

# Extract weights
models = []
lines = stdout.split("\n")
for i, line in enumerate(lines):
    if "--- MODEL_EXPORT" in line:
        data = lines[i+1].split(",")
        w = [float(x) for x in data[:-1]]
        b = float(data[-1])
        models.append((w, b))

if not models:
    print("Failed to get models.")
    exit(1)

# Parameter Averaging (Federated Learning Join)
global_w = [sum(m[0][j] for m in models) / len(models) for j in range(5)]
global_b = sum(m[1] for m in models) / len(models)

print("\n==================================================")
print(" FINAL GLOBAL MODEL WEIGHTS (FEDERATED AVERAGING) ")
print("==================================================")
target_w = [1.5, -2.0, 0.5, 3.0, -1.0]
for j in range(5):
    print(f"Feature {j} Weight : {global_w[j]:.4f} (Target: {target_w[j]})")
print(f"Bias             : {global_b:.4f} (Target: -0.5)")
print("==================================================")
