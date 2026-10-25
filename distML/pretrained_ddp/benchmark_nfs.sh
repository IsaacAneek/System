#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BENCHMARK_PY="$SCRIPT_DIR/benchmark_node.py"

PI02="pi02.local"
PI03="pi03.local"
PI_USER="pi"
MASTER_PORT="29505" # Unique port for NFS benchmark

SAMPLES=1000
EPOCHS=1

echo "============================================================"
echo "    PRE-TRAINED RESNET-18: LOCAL vs. NFS BENCHMARK SUITE    "
echo "============================================================"

# Deploy the script
echo -e "\n[0/4] Deploying benchmark script to edge nodes..."
scp -q "$BENCHMARK_PY" ${PI_USER}@${PI02}:/tmp/pretrained_ddp_bench.py
scp -q "$BENCHMARK_PY" ${PI_USER}@${PI03}:/tmp/pretrained_ddp_bench.py

# Verify directories
echo "Verifying local storage (/tmp/cifar10_data) and NFS mount (/mnt/nfs_share)..."
ssh ${PI_USER}@${PI02} "test -d /tmp/cifar10_data && test -d /mnt/nfs_share" || { echo "Error: pi02 missing storage directories"; exit 1; }
ssh ${PI_USER}@${PI03} "test -d /tmp/cifar10_data && test -d /mnt/nfs_share" || { echo "Error: pi03 missing storage directories"; exit 1; }

MASTER_IP=$(ssh ${PI_USER}@${PI02} "ip -4 addr show eth0 | grep -oP '(?<=inet\s)\d+(\.\d+){3}'")

# =========================================================================
# PHASE 1: LOCAL SD CARD STORAGE (BEFORE NFS)
# =========================================================================
echo -e "\n============================================================"
echo "  PHASE 1: LOCAL STORAGE BENCHMARK (Before NFS / Baseline)  "
echo "============================================================"

echo -e "\n[1/4] Running Local Single-Node Benchmark (pi02, $SAMPLES samples, local /tmp)..."
ssh ${PI_USER}@${PI02} "python3 -u /tmp/pretrained_ddp_bench.py --epochs $EPOCHS --samples $SAMPLES --data-dir /tmp/cifar10_data" > /tmp/bench_local_single.log
LOCAL_SINGLE_OUT=$(grep "BENCHMARK_RESULT" /tmp/bench_local_single.log)
LOCAL_SINGLE_TIME=$(echo "$LOCAL_SINGLE_OUT" | cut -d'|' -f3)
echo "      Local Single Node finished in ${LOCAL_SINGLE_TIME} seconds."

echo -e "\n[2/4] Running Local Distributed Benchmark (2 Nodes, $SAMPLES samples total, local /tmp)..."
ssh ${PI_USER}@${PI02} "GLOO_SOCKET_IFNAME=eth0 MASTER_ADDR=$MASTER_IP MASTER_PORT=$MASTER_PORT RANK=0 WORLD_SIZE=2 python3 -u /tmp/pretrained_ddp_bench.py --epochs $EPOCHS --samples $SAMPLES --data-dir /tmp/cifar10_data --distributed" > /tmp/bench_local_dist.log &
PID0=$!

ssh ${PI_USER}@${PI03} "GLOO_SOCKET_IFNAME=eth0 MASTER_ADDR=$MASTER_IP MASTER_PORT=$MASTER_PORT RANK=1 WORLD_SIZE=2 python3 -u /tmp/pretrained_ddp_bench.py --epochs $EPOCHS --samples $SAMPLES --data-dir /tmp/cifar10_data --distributed" &
PID1=$!

wait $PID0
wait $PID1

LOCAL_DIST_OUT=$(grep "BENCHMARK_RESULT" /tmp/bench_local_dist.log)
LOCAL_DIST_TIME=$(echo "$LOCAL_DIST_OUT" | cut -d'|' -f3)
echo "      Local Distributed cluster finished in ${LOCAL_DIST_TIME} seconds."

LOCAL_SPEEDUP=$(awk "BEGIN {printf \"%.2f\", $LOCAL_SINGLE_TIME / $LOCAL_DIST_TIME}")
echo "      Local Storage Speedup: ${LOCAL_SPEEDUP}x"

# =========================================================================
# PHASE 2: NETWORK FILE SYSTEM STORAGE (AFTER NFS)
# =========================================================================
echo -e "\n============================================================"
echo "  PHASE 2: NFS STORAGE BENCHMARK (After NFS Implementation) "
echo "============================================================"

# Flush OS page caches to ensure true read behavior
ssh ${PI_USER}@${PI02} "echo 1234 | sudo -S sh -c 'sync; echo 3 > /proc/sys/vm/drop_caches'" 2>/dev/null || true
ssh ${PI_USER}@${PI03} "echo 1234 | sudo -S sh -c 'sync; echo 3 > /proc/sys/vm/drop_caches'" 2>/dev/null || true

echo -e "\n[3/4] Running NFS Single-Node Benchmark (pi02, $SAMPLES samples, NFS /mnt/nfs_share)..."
ssh ${PI_USER}@${PI02} "python3 -u /tmp/pretrained_ddp_bench.py --epochs $EPOCHS --samples $SAMPLES --data-dir /mnt/nfs_share" > /tmp/bench_nfs_single.log
NFS_SINGLE_OUT=$(grep "BENCHMARK_RESULT" /tmp/bench_nfs_single.log)
NFS_SINGLE_TIME=$(echo "$NFS_SINGLE_OUT" | cut -d'|' -f3)
echo "      NFS Single Node finished in ${NFS_SINGLE_TIME} seconds."

echo -e "\n[4/4] Running NFS Distributed Benchmark (2 Nodes, $SAMPLES samples total, NFS /mnt/nfs_share)..."
ssh ${PI_USER}@${PI02} "GLOO_SOCKET_IFNAME=eth0 MASTER_ADDR=$MASTER_IP MASTER_PORT=$MASTER_PORT RANK=0 WORLD_SIZE=2 python3 -u /tmp/pretrained_ddp_bench.py --epochs $EPOCHS --samples $SAMPLES --data-dir /mnt/nfs_share --distributed" > /tmp/bench_nfs_dist.log &
PID0=$!

ssh ${PI_USER}@${PI03} "GLOO_SOCKET_IFNAME=eth0 MASTER_ADDR=$MASTER_IP MASTER_PORT=$MASTER_PORT RANK=1 WORLD_SIZE=2 python3 -u /tmp/pretrained_ddp_bench.py --epochs $EPOCHS --samples $SAMPLES --data-dir /mnt/nfs_share --distributed" &
PID1=$!

wait $PID0
wait $PID1

NFS_DIST_OUT=$(grep "BENCHMARK_RESULT" /tmp/bench_nfs_dist.log)
NFS_DIST_TIME=$(echo "$NFS_DIST_OUT" | cut -d'|' -f3)
echo "      NFS Distributed cluster finished in ${NFS_DIST_TIME} seconds."

NFS_SPEEDUP=$(awk "BEGIN {printf \"%.2f\", $NFS_SINGLE_TIME / $NFS_DIST_TIME}")
echo "      NFS Storage Speedup: ${NFS_SPEEDUP}x"

# =========================================================================
# PHASE 3: SIDE-BY-SIDE COMPARISON & BOTTLENECK ANALYSIS
# =========================================================================
echo -e "\n============================================================"
echo "          SIDE-BY-SIDE BENCHMARK: LOCAL vs. NFS             "
echo "============================================================"
printf "%-32s | %-12s | %-12s\n" "Execution Mode" "Local Storage" "NFS Storage"
echo "------------------------------------------------------------"
printf "%-32s | %-12s | %-12s\n" "Single Node (pi02 alone)" "${LOCAL_SINGLE_TIME} s" "${NFS_SINGLE_TIME} s"
printf "%-32s | %-12s | %-12s\n" "Distributed Cluster (2 Nodes)" "${LOCAL_DIST_TIME} s" "${NFS_DIST_TIME} s"
echo "------------------------------------------------------------"
printf "%-32s | %-12s | %-12s\n" "Scaling Speedup Multiplier" "${LOCAL_SPEEDUP}x" "${NFS_SPEEDUP}x"
echo "============================================================"

# Compute Differences
DELTA_DIST=$(awk "BEGIN {printf \"%+.2f\", $NFS_DIST_TIME - $LOCAL_DIST_TIME}")
DELTA_PCT=$(awk "BEGIN {printf \"%+.1f\", (($NFS_DIST_TIME - $LOCAL_DIST_TIME) / $LOCAL_DIST_TIME) * 100}")

echo ""
echo "------------------------------------------------------------"
echo "                  NFS BOTTLENECK ANALYSIS                   "
echo "------------------------------------------------------------"
echo "Distributed Time Difference (NFS vs Local): ${DELTA_DIST} s (${DELTA_PCT}%)"

awk -v delta="$DELTA_DIST" 'BEGIN {
    if (delta > 1.0) {
        print "Verdict: NFS IS a noticeable bottleneck. Network I/O latency adds significant overhead.";
    } else if (delta < -0.2) {
        print "Verdict: NFS is FASTER than Local SD Card (due to server OS page caching in RAM)!";
    } else {
        print "Verdict: NFS is NOT a bottleneck. Overhead is negligible compared to compute and DDP sync.";
    }
}'
echo "============================================================"

