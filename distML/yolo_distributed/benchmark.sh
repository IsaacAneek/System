#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BENCHMARK_PY="$SCRIPT_DIR/benchmark_node.py"

PI02="pi02.local"
PI03="pi03.local"
PI_USER="pi"
MASTER_PORT="29501" # Using a slightly different port to avoid conflicts

echo "============================================================"
echo "       TINYYOLO DISTRIBUTED BENCHMARK SUITE                 "
echo "============================================================"

# Ensure the dataset is ready on both nodes so network downloads don't skew the results
echo -e "\n[1/3] Deploying benchmark script and verifying datasets..."
scp -q "$BENCHMARK_PY" ${PI_USER}@${PI02}:/tmp/benchmark_node.py
scp -q "$BENCHMARK_PY" ${PI_USER}@${PI03}:/tmp/benchmark_node.py


echo -e "\n[2/3] Running Single-Node Benchmark (pi02 only, 1 epoch)..."
# We run without the --distributed flag. It processes all 50,000 images on 1 node.
ssh ${PI_USER}@${PI02} "python3 /tmp/benchmark_node.py --epochs 1" > /tmp/bench_single.log
SINGLE_OUT=$(cat /tmp/bench_single.log | grep "BENCHMARK_RESULT")
SINGLE_TIME=$(echo $SINGLE_OUT | cut -d'|' -f3)
echo "      Single node finished in ${SINGLE_TIME} seconds."


echo -e "\n[3/3] Running Distributed Benchmark (pi02 + pi03, 1 epoch)..."
MASTER_IP=$(ssh ${PI_USER}@${PI02} "ip -4 addr show eth0 | grep -oP '(?<=inet\s)\d+(\.\d+){3}'")

# Start Master (pi02)
ssh ${PI_USER}@${PI02} "GLOO_SOCKET_IFNAME=eth0 MASTER_ADDR=$MASTER_IP MASTER_PORT=$MASTER_PORT RANK=0 WORLD_SIZE=2 python3 /tmp/benchmark_node.py --epochs 1 --distributed" > /tmp/bench_dist.log &
PID0=$!

# Start Worker (pi03)
ssh ${PI_USER}@${PI03} "GLOO_SOCKET_IFNAME=eth0 MASTER_ADDR=$MASTER_IP MASTER_PORT=$MASTER_PORT RANK=1 WORLD_SIZE=2 python3 /tmp/benchmark_node.py --epochs 1 --distributed" &
PID1=$!

wait $PID0
wait $PID1

DIST_OUT=$(cat /tmp/bench_dist.log | grep "BENCHMARK_RESULT")
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
echo "Speedup Multiplier: ${SPEEDUP}x"
echo "============================================================"
