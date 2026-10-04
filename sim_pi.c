#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <time.h>

int main(int argc, char **argv) {
    long long int samples = 50000000;
    long long int hits = 0;
    int rank = 0;
    int size = 1;
    char hostname[256];

    gethostname(hostname, sizeof(hostname));

    char *env_rank = getenv("SLURM_PROCID");
    char *env_size = getenv("SLURM_NTASKS");

    if (env_rank) rank = atoi(env_rank);
    if (env_size) size = atoi(env_size);

    unsigned int seed = time(NULL) + rank * 9999;
    srand(seed);

    printf("[Task %d/%d | %s] Starting Monte Carlo simulation (%lld samples)...\n", 
           rank, size, hostname, samples);

    for (long long int i = 0; i < samples; ++i) {
        double x = (double)rand() / RAND_MAX * 2.0 - 1.0;
        double y = (double)rand() / RAND_MAX * 2.0 - 1.0;
        if (x * x + y * y <= 1.0) {
            hits++;
        }
    }

    double local_pi = 4.0 * (double)hits / samples;
    printf("[Task %d/%d | %s] Finished! Local Pi estimate: %f\n", 
           rank, size, hostname, local_pi);

    return 0;
}
