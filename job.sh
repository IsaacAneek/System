#!/bin/bash

#SBATCH --job-name=mpi_test
#SBATCH --output=mpi_out%j.out
#SBATCH --error=mpi_err%j.err
#SBATCH --nodes=2
#SBATCH --ntasks-per-node=2

echo "Submitted Open MPI job"
echo "Running on:"
hostname

mpicc testMPI.c -o test_mpi

mpirun ./test_mpi
