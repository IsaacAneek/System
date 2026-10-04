# 1. Send source to pi02 and compile with mpicc (MPI C Compiler)
ssh pi@pi02.local "cat > /tmp/sim_pi_mpi.c" < /home/isaac-aneek/Practice/System/sim_pi_mpi.c
ssh pi@pi02.local "mpicc -O3 /tmp/sim_pi_mpi.c -o /tmp/sim_pi_mpi_arm"

# 2. Copy the binary from pi02 over to pi03
ssh pi@pi02.local "scp -o StrictHostKeyChecking=no /tmp/sim_pi_mpi_arm pi@pi03.local:/tmp/"

# 3. Launch the combined job via mpirun!
ssh pi@pi02.local "mpirun --mca plm_rsh_args \"-o StrictHostKeyChecking=no\" --host pi02.local,pi03.local -n 2 /tmp/sim_pi_mpi_arm"