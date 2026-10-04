#include <mpi.h>
#include <stdio.h>
#include <stdlib.h>
#include <time.h>
#include <unistd.h>

int main(int argc, char **argv) {
    // Initialize the MPI Environment
    MPI_Init(&argc, &argv);

    int rank, size;
    MPI_Comm_rank(MPI_COMM_WORLD, &rank); // Get the rank (0 or 1)
    MPI_Comm_size(MPI_COMM_WORLD, &size); // Get total nodes (2)

    long long int samples_per_node = 50000000;
    long long int local_hits = 0;
    long long int global_hits = 0; // Only rank 0 will use this
    char hostname[256];

    gethostname(hostname, sizeof(hostname));

    // Ensure completely unique random seed per node
    srand(time(NULL) + rank * 9999);

    // 1. Independent Parallel Execution (Each node does its own chunk)
    for (long long int i = 0; i < samples_per_node; ++i) {
        double x = (double)rand() / RAND_MAX * 2.0 - 1.0;
        double y = (double)rand() / RAND_MAX * 2.0 - 1.0;
        if (x * x + y * y <= 1.0) {
            local_hits++;
        }
    }

    printf("[Node %s | Rank %d] Computed %lld samples locally.\n", hostname, rank, samples_per_node);

    // 2. Combining the Results (MPI Reduction)
    // This takes the 'local_hits' from ALL nodes, SUMS them together, and saves the total into 'global_hits' on Rank 0
    MPI_Reduce(&local_hits, &global_hits, 1, MPI_LONG_LONG, MPI_SUM, 0, MPI_COMM_WORLD);

    // 3. Output the combined result only from the master node (Rank 0)
    if (rank == 0) {
        long long int total_samples = samples_per_node * size;
        double global_pi = 4.0 * (double)global_hits / total_samples;
        printf("\n--- MPI COMBINED RESULT ---\n");
        printf("Total Nodes: %d\n", size);
        printf("Total Samples: %lld\n", total_samples);
        printf("Combined Global Pi Estimate: %f\n", global_pi);
    }

    // Shut down MPI
    MPI_Finalize();
    return 0;
}
