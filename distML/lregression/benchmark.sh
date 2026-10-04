#!/bin/bash
set -e

echo "============================================================"
echo "   LOGISTIC REGRESSION DISTRIBUTED BENCHMARK SUITE          "
echo "============================================================"

cd "$(dirname "$0")"
LOCAL_WORKER="$(pwd)/benchmark_worker.py"
TARGET_WORKER="/tmp/lr_bench.py"

echo -e "\n[1/2] Running Single-Node Benchmark (30,000 samples on 1 Pi)..."
# Force 1 node, process 30,000 rows
srun -N 1 --nodelist=pi02 --bcast=$TARGET_WORKER --chdir=/tmp $LOCAL_WORKER --samples 30000 > /tmp/lr_single.log
SINGLE_OUT=$(cat /tmp/lr_single.log | grep "TIME|")
SINGLE_TIME=$(echo $SINGLE_OUT | cut -d'|' -f2)
echo "      Finished in ${SINGLE_TIME} seconds."

echo -e "\n[2/2] Running Distributed Benchmark (15,000 samples per Pi, 2 Pis)..."
# Spread 30,000 total rows across 2 nodes (15k each) to demonstrate Data Parallelism speedup
srun -N 2 --bcast=$TARGET_WORKER --chdir=/tmp $LOCAL_WORKER --samples 15000 > /tmp/lr_dist.log
DIST_OUT=$(cat /tmp/lr_dist.log | grep "TIME|")
DIST_TIME=$(echo $DIST_OUT | cut -d'|' -f2)
echo "      Finished in ${DIST_TIME} seconds."

echo -e "\n============================================================"
echo -e "                    BENCHMARK RESULTS"
echo -e "============================================================"
printf "%-30s | %-15s\n" "Configuration" "Time (seconds)"
echo "------------------------------------------------------------"
printf "%-30s | %-15s\n" "Single Node (pi02)" "${SINGLE_TIME} s"
printf "%-30s | %-15s\n" "Distributed Cluster (2 Nodes)" "${DIST_TIME} s"
echo "------------------------------------------------------------"

SPEEDUP=$(awk "BEGIN {printf \"%.2f\", $SINGLE_TIME / $DIST_TIME}")
echo "Speedup Multiplier: ${SPEEDUP}x"
echo "============================================================"
