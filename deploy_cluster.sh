#!/bin/bash
set -e

echo "Deploying Slurm + OpenMPI Cluster (Robust Version)..."

if [ "$EUID" -ne 0 ]; then
  echo "Please run as root (use sudo)"
  exit
fi

NODES=("pi02.local" "pi03.local")
PI_USER="pi"

echo "1. Installing base dependencies & removing incompatible Slurm versions..."
apt-get update
apt-get remove --purge -y slurm-wlm slurmctld slurm-client || true
apt-get install -y munge libmunge-dev build-essential wget bzip2 sshpass openmpi-bin libopenmpi-dev

echo "2. Setting up Munge key (Controller)..."
if [ ! -f /etc/munge/munge.key ]; then
    create-munge-key
fi
chown munge:munge /etc/munge/munge.key
chmod 400 /etc/munge/munge.key
systemctl enable munge
systemctl restart munge

echo "3. Distributing Munge key to Pis..."
for node in "${NODES[@]}"; do
    echo "Distributing to $node..."
    sshpass -p '1234' scp -o StrictHostKeyChecking=no /etc/munge/munge.key ${PI_USER}@${node}:/tmp/munge.key
    sshpass -p '1234' ssh -o StrictHostKeyChecking=no ${PI_USER}@${node} "sudo mv /tmp/munge.key /etc/munge/munge.key && sudo chown munge:munge /etc/munge/munge.key && sudo chmod 400 /etc/munge/munge.key && sudo systemctl enable munge && sudo systemctl restart munge"
done

echo "4. Compiling Slurm 22.05.8 from source (to match Pis)..."
cd /tmp
if [ ! -d "slurm-22.05.8" ]; then
    wget -q https://download.schedmd.com/slurm/slurm-22.05.8.tar.bz2
    tar -xaf slurm-22.05.8.tar.bz2
fi
cd slurm-22.05.8
make clean || true
# CFLAGS fixes GCC 14 strict prototype enforcement on older codebases. --without-pmix avoids advanced MPI plugin compile errors.
./configure --prefix=/usr --sysconfdir=/etc/slurm --with-munge --without-pmix CFLAGS="-O2 -std=gnu99 -Wno-incompatible-pointer-types"
make -j$(nproc)
make install

echo "5. Creating Slurm configuration..."
mkdir -p /etc/slurm
PC_HOSTNAME=$(hostname)
cat <<EOF > /etc/slurm/slurm.conf
ClusterName=pi_cluster
SlurmctldHost=${PC_HOSTNAME}
SlurmUser=slurm
SlurmdUser=root
AuthType=auth/munge
CryptoType=crypto/munge
SlurmctldPort=6817
SlurmdPort=6818
StateSaveLocation=/var/lib/slurmctld
SlurmdSpoolDir=/var/lib/slurmd
ProctrackType=proctrack/linuxproc
TaskPlugin=task/none
SelectType=select/cons_tres
SelectTypeParameters=CR_Core
SchedulerType=sched/backfill
SlurmctldLogFile=/var/log/slurm/slurmctld.log
SlurmdLogFile=/var/log/slurm/slurmd.log

# Nodes (Assuming Pi 4 with 4 CPUs)
NodeName=pi02 CPUs=4 State=UNKNOWN
NodeName=pi03 CPUs=4 State=UNKNOWN

# Partition
PartitionName=pi Nodes=pi02,pi03 Default=YES State=UP
EOF

echo "6. Distributing Slurm configuration to Pis..."
for node in "${NODES[@]}"; do
    sshpass -p '1234' scp -o StrictHostKeyChecking=no /etc/slurm/slurm.conf ${PI_USER}@${node}:/tmp/slurm.conf
    sshpass -p '1234' ssh -o StrictHostKeyChecking=no ${PI_USER}@${node} "sudo mv /tmp/slurm.conf /etc/slurm/slurm.conf && sudo systemctl enable slurmd && sudo systemctl restart slurmd"
done

echo "7. Starting Slurm Controller on PC..."
mkdir -p /var/lib/slurmctld /var/log/slurm
# Ensure the slurm user exists
if ! id "slurm" &>/dev/null; then
    useradd -r -s /bin/false slurm
fi
chown slurm:slurm /var/lib/slurmctld /var/log/slurm
# Wipe any old database state to prevent cluster name mismatch corruption
rm -rf /var/lib/slurmctld/*
# Copy systemd service from source
cp /tmp/slurm-22.05.8/etc/slurmctld.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable slurmctld
systemctl restart slurmctld

echo "=========================================="
echo "Deployment Complete!"
echo "Run 'sinfo' to check cluster status."
echo "To test the cluster across mixed architectures, run:"
echo ""
echo "cat << 'EOF' > /tmp/hello.c"
echo "#include <stdio.h>"
echo "#include <unistd.h>"
echo "int main() {"
echo "    char hostname[256];"
echo "    gethostname(hostname, 256);"
echo "    printf(\"Hello world from %s\\\\n\", hostname);"
echo "    return 0;"
echo "}"
echo "EOF"
echo "ssh pi@pi02.local \"cat > /tmp/hello.c\" < /tmp/hello.c"
echo "ssh pi@pi02.local \"gcc /tmp/hello.c -o /tmp/hello_arm\""
echo "scp pi@pi02.local:/tmp/hello_arm /tmp/hello_arm"
echo "srun --chdir=/tmp --bcast=/tmp/hello_arm -N 2 /tmp/hello_arm"
echo "=========================================="
