#!/bin/bash

# Ensure we are in the correct directory regardless of where the script is called from
cd "$(dirname "$0")"

echo "Dispatching Distributed Neural Network..."
chmod +x worker.py
python3 master.py
