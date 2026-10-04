# 1. Send source to pi02 and compile it for ARM
ssh pi@pi02.local "cat > /tmp/sim_pi.c" < /home/isaac-aneek/Practice/System/sim_pi.c
ssh pi@pi02.local "gcc -O3 /tmp/sim_pi.c -o /tmp/sim_pi_arm"

# 2. Pull the compiled ARM binary back to the controller
scp pi@pi02.local:/tmp/sim_pi_arm /tmp/sim_pi_arm

# 3. Dispatch the job across the entire cluster!
srun --chdir=/tmp --bcast=/tmp/sim_pi_arm -N 2 /tmp/sim_pi_arm