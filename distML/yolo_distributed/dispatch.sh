#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WORKER="$SCRIPT_DIR/worker.py"
INFERENCE="$SCRIPT_DIR/inference.py"

PI02="pi02.local"
PI03="pi03.local"
PI_USER="pi"
MASTER_PORT="29500"

echo "============================================================"
echo "  DISTRIBUTED PYTORCH TRAINING DISPATCHER (TinyYOLO + DDP)  "
echo "============================================================"

# ---------------------------------------------------------------
# Step 1: Deploy the worker script to both Pis
# ---------------------------------------------------------------
echo -e "\n[1/5] Deploying worker script to compute nodes..."
for node in $PI02 $PI03; do
    scp -q "$WORKER" ${PI_USER}@${node}:/tmp/worker.py
done
echo "      Deployed to $PI02 and $PI03."

# ---------------------------------------------------------------
# Step 2: Pre-download CIFAR-10 on rank 0 to avoid race conditions
# ---------------------------------------------------------------
echo -e "\n[2/5] Pre-downloading CIFAR-10 dataset on $PI02..."
ssh ${PI_USER}@${PI02} "python3 -c \"
import torchvision
torchvision.datasets.CIFAR10(root='/tmp/cifar10_data', train=True, download=True)
print('Dataset ready.')
\""

# Copy dataset to pi03 so both have it locally
echo "      Syncing dataset to $PI03..."
ssh ${PI_USER}@${PI02} "scp -q -r -o StrictHostKeyChecking=no /tmp/cifar10_data ${PI_USER}@${PI03}:/tmp/" 2>/dev/null || \
    ssh ${PI_USER}@${PI02} "tar cf - /tmp/cifar10_data" | ssh ${PI_USER}@${PI03} "tar xf - -C /"

# ---------------------------------------------------------------
# Step 3: Launch distributed training across both Pis
# ---------------------------------------------------------------
echo -e "\n[3/5] Launching distributed training..."
echo "      Master: $PI02:$MASTER_PORT | World size: 2"
echo "      Backend: Gloo (CPU-only distributed)"
echo ""

# Get pi02's physical LAN IP for MASTER_ADDR
MASTER_IP=$(ssh ${PI_USER}@${PI02} "ip -4 addr show eth0 | grep -oP '(?<=inet\s)\d+(\.\d+){3}'")

# Launch rank 0 on pi02 (background)
ssh ${PI_USER}@${PI02} "GLOO_SOCKET_IFNAME=eth0 MASTER_ADDR=$MASTER_IP MASTER_PORT=$MASTER_PORT RANK=0 WORLD_SIZE=2 python3 /tmp/worker.py" &
PID0=$!

# Launch rank 1 on pi03
ssh ${PI_USER}@${PI03} "GLOO_SOCKET_IFNAME=eth0 MASTER_ADDR=$MASTER_IP MASTER_PORT=$MASTER_PORT RANK=1 WORLD_SIZE=2 python3 /tmp/worker.py" &
PID1=$!

# Wait for both to finish
wait $PID0
wait $PID1

echo -e "\n      Distributed training complete!"

# ---------------------------------------------------------------
# Step 4: Retrieve the final model weights from rank 0
# ---------------------------------------------------------------
echo -e "\n[4/5] Retrieving trained model weights from $PI02..."
scp -q ${PI_USER}@${PI02}:/tmp/tinyyolo_distributed.pt /tmp/tinyyolo_distributed.pt
echo "      Saved to /tmp/tinyyolo_distributed.pt"

# ---------------------------------------------------------------
# Step 5: Run inference on the PC
# ---------------------------------------------------------------
echo -e "\n[5/5] Running inference on the PC (x86_64)..."
python3 "$INFERENCE" /tmp/tinyyolo_distributed.pt

echo -e "\nDone!"
