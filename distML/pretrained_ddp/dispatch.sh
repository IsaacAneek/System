#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WORKER="$SCRIPT_DIR/worker.py"
INFERENCE="$SCRIPT_DIR/inference.py"

PI02="pi02.local"
PI03="pi03.local"
PI_USER="pi"
MASTER_PORT="29503" # Unique port

echo "============================================================"
echo "    DISTRIBUTED PRE-TRAINED RESNET-18 (DDP TRANSFER LEARNING)"
echo "============================================================"

echo -e "\n[1/4] Deploying script to edge nodes..."
scp -q "$WORKER" ${PI_USER}@${PI02}:/tmp/worker.py
scp -q "$WORKER" ${PI_USER}@${PI03}:/tmp/worker.py

echo -e "\n[2/4] Verifying CIFAR-10 dataset (downloading if necessary)..."
ssh ${PI_USER}@${PI02} "python3 -c \"import torchvision; torchvision.datasets.CIFAR10(root='/tmp/cifar10_data', train=True, download=True)\"" >/dev/null 2>&1
ssh ${PI_USER}@${PI02} "scp -q -r -o StrictHostKeyChecking=no /tmp/cifar10_data ${PI_USER}@${PI03}:/tmp/" 2>/dev/null || true

echo -e "\n[3/4] Launching Distributed Training (Transfer Learning)..."
MASTER_IP=$(ssh ${PI_USER}@${PI02} "ip -4 addr show eth0 | grep -oP '(?<=inet\s)\d+(\.\d+){3}'")

ssh ${PI_USER}@${PI02} "GLOO_SOCKET_IFNAME=eth0 MASTER_ADDR=$MASTER_IP MASTER_PORT=$MASTER_PORT RANK=0 WORLD_SIZE=2 python3 -u /tmp/worker.py --epochs 1" &
PID0=$!

ssh ${PI_USER}@${PI03} "GLOO_SOCKET_IFNAME=eth0 MASTER_ADDR=$MASTER_IP MASTER_PORT=$MASTER_PORT RANK=1 WORLD_SIZE=2 python3 -u /tmp/worker.py --epochs 1" &
PID1=$!

wait $PID0
wait $PID1

echo -e "\n[4/4] Retrieving combined weights from master node..."
cd "$SCRIPT_DIR"
scp -q ${PI_USER}@${PI02}:/tmp/pretrained_weights.pt ./pretrained_weights.pt

echo -e "\n      Distributed training complete! Running local evaluation..."
python3 -u "$INFERENCE"

