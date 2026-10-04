import subprocess
import time

print("==================================================")
print(" DISTRIBUTED FEDERATED LEARNING (DATA PARALLELISM)")
print("==================================================")
print("Target Equation: y = 4.5*x1 - 2.0*x2 + 1.5\n")

print("[Master] Dispatching ML training workers to the Slurm cluster...")
# Run srun to execute the python worker script on all 2 nodes
# --bcast copies the python file to the nodes automatically
start_time = time.time()
cmd = ["srun", "--chdir=/tmp", "--bcast=/tmp/train_worker.py", "-N", "2", "/home/isaac-aneek/Practice/System/train_worker.py"]

process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
stdout, stderr = process.communicate()

print(stdout)

if process.returncode != 0:
    print("Error during cluster execution:")
    print(stderr)
    exit(1)

print(f"[Master] Cluster training completed in {time.time() - start_time:.2f} seconds.")

# Parse the models back from the workers
weights_list = []
lines = stdout.split('\n')
for i, line in enumerate(lines):
    if "--- MODEL_EXPORT" in line:
        # The next line contains the CSV weights
        w_csv = lines[i+1]
        w1, w2, bias = map(float, w_csv.split(','))
        weights_list.append((w1, w2, bias))

if not weights_list:
    print("[Master] Failed to retrieve weights from workers.")
    exit(1)

print("\n[Master] Joining models (Parameter Averaging)...")
avg_w1 = sum(w[0] for w in weights_list) / len(weights_list)
avg_w2 = sum(w[1] for w in weights_list) / len(weights_list)
avg_bias = sum(w[2] for w in weights_list) / len(weights_list)

print("==================================================")
print(" FINAL GLOBAL MODEL WEIGHTS")
print("==================================================")
print(f"Weight 1 (Target 4.5) : {avg_w1:.4f}")
print(f"Weight 2 (Target -2.0): {avg_w2:.4f}")
print(f"Bias     (Target 1.5) : {avg_bias:.4f}")
print("==================================================")
