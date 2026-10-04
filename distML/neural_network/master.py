import subprocess
import time

print("==================================================")
print(" DISTRIBUTED MULTI-LAYER NEURAL NETWORK (MLP)     ")
print("==================================================")

cmd = ["srun", "--chdir=/tmp", "--bcast=/tmp/worker_nn.py", "-N", "2", "/home/isaac-aneek/Practice/System/distML/neural_network/worker.py"]

print("[Master] Dispatching ML nodes via Slurm...")
start = time.time()
process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
stdout, stderr = process.communicate()

if process.returncode != 0:
    print("Execution failed!")
    print(stderr)
    exit(1)

print(stdout)
print(f"[Master] Deep Learning Training completed in {time.time() - start:.2f} seconds.")

models = []
lines = stdout.split("\n")
for i, line in enumerate(lines):
    if "--- MODEL_EXPORT" in line:
        data = lines[i+1].split("|")
        W1 = [float(x) for x in data[0].split(",")]
        b1 = [float(x) for x in data[1].split(",")]
        W2 = [float(x) for x in data[2].split(",")]
        b2 = [float(x) for x in data[3].split(",")]
        models.append((W1, b1, W2, b2))

if not models:
    print("Failed to get models.")
    exit(1)

# Parameter Averaging across all nodes
N = len(models)
global_W1 = [sum(m[0][j] for m in models)/N for j in range(len(models[0][0]))]
global_b1 = [sum(m[1][j] for m in models)/N for j in range(len(models[0][1]))]
global_W2 = [sum(m[2][j] for m in models)/N for j in range(len(models[0][2]))]
global_b2 = [sum(m[3][j] for m in models)/N for j in range(len(models[0][3]))]

print("\n==================================================")
print(" FINAL GLOBAL NEURAL NETWORK WEIGHTS")
print("==================================================")
print(f"Hidden Layer W1 (8 params): {[round(w, 4) for w in global_W1]}")
print(f"Hidden Layer b1 (4 params): {[round(b, 4) for b in global_b1]}")
print(f"Output Layer W2 (4 params): {[round(w, 4) for w in global_W2]}")
print(f"Output Layer b2 (1 param) : {[round(b, 4) for b in global_b2]}")
print("==================================================")
