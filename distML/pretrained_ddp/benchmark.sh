#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BENCHMARK_PY="$SCRIPT_DIR/benchmark_node.py"

PI02="pi02.local"
PI03="pi03.local"
PI_USER="pi"
MASTER_PORT="29502" # Unique port

echo "============================================================"
echo "    PRE-TRAINED RESNET-18 DDP BENCHMARK SUITE               "
echo "============================================================"

# Deploy the script
echo -e "\n[1/3] Deploying benchmark script to edge nodes..."
scp -q "$BENCHMARK_PY" ${PI_USER}@${PI02}:/tmp/pretrained_ddp_bench.py
scp -q "$BENCHMARK_PY" ${PI_USER}@${PI03}:/tmp/pretrained_ddp_bench.py

# Ensure dataset exists on pi02 and sync to pi03
ssh ${PI_USER}@${PI02} "python3 -c \"import torchvision; torchvision.datasets.CIFAR10(root='/tmp/cifar10_data', train=True, download=True)\"" >/dev/null 2>&1
ssh ${PI_USER}@${PI02} "scp -q -r -o StrictHostKeyChecking=no /tmp/cifar10_data ${PI_USER}@${PI03}:/tmp/" 2>/dev/null || true


echo -e "\n[2/3] Running Single-Node Benchmark (pi02 only, 1 epoch, 1000 samples)..."
ssh ${PI_USER}@${PI02} "python3 -u /tmp/pretrained_ddp_bench.py --epochs 1 --samples 1000" > /tmp/bench_resnet_single.log
SINGLE_OUT=$(cat /tmp/bench_resnet_single.log | grep "BENCHMARK_RESULT")
SINGLE_TIME=$(echo $SINGLE_OUT | cut -d'|' -f3)
echo "      Single node finished in ${SINGLE_TIME} seconds."


echo -e "\n[3/3] Running Distributed Benchmark (pi02 + pi03, 1 epoch, 1000 samples total)..."
MASTER_IP=$(ssh ${PI_USER}@${PI02} "ip -4 addr show eth0 | grep -oP '(?<=inet\s)\d+(\.\d+){3}'")

ssh ${PI_USER}@${PI02} "GLOO_SOCKET_IFNAME=eth0 MASTER_ADDR=$MASTER_IP MASTER_PORT=$MASTER_PORT RANK=0 WORLD_SIZE=2 python3 -u /tmp/pretrained_ddp_bench.py --epochs 1 --samples 1000 --distributed" > /tmp/bench_resnet_dist.log &
PID0=$!

ssh ${PI_USER}@${PI03} "GLOO_SOCKET_IFNAME=eth0 MASTER_ADDR=$MASTER_IP MASTER_PORT=$MASTER_PORT RANK=1 WORLD_SIZE=2 python3 -u /tmp/pretrained_ddp_bench.py --epochs 1 --samples 1000 --distributed" &
PID1=$!

wait $PID0
wait $PID1

DIST_OUT=$(cat /tmp/bench_resnet_dist.log | grep "BENCHMARK_RESULT")
DIST_TIME=$(echo $DIST_OUT | cut -d'|' -f3)
echo "      Distributed cluster finished in ${DIST_TIME} seconds."

# ---------------------------------------------------------------
# Output comparison
# ---------------------------------------------------------------
echo -e "\n============================================================"
echo -e "                    BENCHMARK RESULTS"
echo -e "============================================================"
printf "%-30s | %-15s\n" "Configuration" "Time (seconds)"
echo "------------------------------------------------------------"
printf "%-30s | %-15s\n" "Single Node (pi02 alone)" "${SINGLE_TIME} s"
printf "%-30s | %-15s\n" "Distributed Cluster (2 Nodes)" "${DIST_TIME} s"
echo "------------------------------------------------------------"

# Compute speedup ratio
SPEEDUP=$(awk "BEGIN {printf \"%.2f\", $SINGLE_TIME / $DIST_TIME}")
IDEAL_TIME=$(awk "BEGIN {printf \"%.3f\", $SINGLE_TIME / 2}")
NETWORK_TIME=$(awk "BEGIN { net = $DIST_TIME - $IDEAL_TIME; if (net < 0) net = 0.000; printf \"%.3f\", net }")
COMPUTE_PCT=$(awk "BEGIN {printf \"%.1f\", ($IDEAL_TIME / $DIST_TIME) * 100}")
NETWORK_PCT=$(awk "BEGIN {printf \"%.1f\", ($NETWORK_TIME / $DIST_TIME) * 100}")

echo "Speedup Multiplier: ${SPEEDUP}x"
echo ""
echo "------------------------------------------------------------"
echo "               COMPUTE VS NETWORK PROFILING                 "
echo "------------------------------------------------------------"
printf "%-30s | %-15s\n" "Ideal Compute Time (Expected)" "${IDEAL_TIME} s"
printf "%-30s | %-15s\n" "Network / Sync Overhead" "${NETWORK_TIME} s"
echo "------------------------------------------------------------"
printf "%-30s | %-15s\n" "Time Computing Math" "${COMPUTE_PCT}%%"
printf "%-30s | %-15s\n" "Time Blocked by Network" "${NETWORK_PCT}%%"
echo "============================================================"
