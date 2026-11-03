# Standalone Pretrained YOLOv3: Single-Node Inference & Training

This folder provides a clean, self-contained implementation of **Pretrained YOLOv3** for raw single-node execution (no MPI, no DDP, no Slurm, no distributed cluster overhead).

---

## Directory Structure

```text
yolo_pretrained/
├── dataset.py       # Downloads dataset and provides PyTorch YOLOFolderDataset loader
├── inference.py     # Downloads pretrained YOLOv3 and runs a single inference pass
├── train.py         # Standalone training loop with transfer learning on pretrained YOLOv3
└── README.md        # Comprehensive pipeline documentation and usage guide
```

---

## 1. Pretrained Inference (`inference.py`)

### How It Works Behind the Scenes
1. **Model Download via PyTorch Hub**:
   Calls `torch.hub.load("ultralytics/yolov3", "yolov3", pretrained=True)`.
   PyTorch automatically pulls the repository and downloads the official Darknet/COCO pretrained weights (`yolov3.pt`).
2. **Device Selection**:
   Automatically detects GPU/CUDA if available, otherwise defaults to CPU.
3. **Inference Execution**:
   Feeds an input image (by URL or local file path) into the model.
4. **Result Parsing**:
   Extracts detection bounding boxes `[xmin, ymin, xmax, ymax]`, confidence scores, and class names, printing a formatted detection table to the terminal.
5. **Image Output**:
   Saves the resulting image with bounding box annotations drawn to `./runs/inference/`.

### Run Inference
```bash
# Default: downloads YOLOv3 and runs inference on a sample image
python3 inference.py

# Run on a custom local image:
python3 inference.py --source /path/to/my_image.jpg

# Use the lightweight YOLOv3-tiny model for faster CPU inference:
python3 inference.py --model yolov3-tiny
```

---

## 2. Dataset Management & Loader (`dataset.py`)

### How It Works Behind the Scenes
1. **Automated Small Dataset Acquisition (`download_and_extract_dataset`)**:
   - Downloads **COCO128** (an official 7MB mini-dataset with 128 labeled images) into `./data/coco128/` containing `images/` and `labels/`.
   - **Offline Fallback**: If network is unavailable, it automatically synthesizes sample labeled images with valid YOLO annotations (`class xc yc w h`) so workflows never break.
2. **Folder Dataset Loader (`YOLOFolderDataset`)**:
   - Standard PyTorch `Dataset` that reads images and matching `.txt` annotation files from local folders.
   - Resizes and normalizes images to `(3, 416, 416)` tensors.
   - Includes `yolo_collate_fn` to batch variable numbers of object bounding boxes per image.

### Run Dataset Download Standalone:
```bash
# Downloads and verifies dataset in ./data/coco128:
python3 dataset.py

# Or specify custom destination directory:
python3 dataset.py --data-dir ./data/my_dataset
```

---

## 3. Training Loop (`train.py`)
```bash
# Train with default settings (yolov3-tiny, 3 epochs, batch size 4):
python3 train.py

# Train full YOLOv3 for 5 epochs:
python3 train.py --model yolov3 --epochs 5 --batch-size 8 --lr 0.0005

# Train using a custom dataset folder:
python3 train.py --data-dir ./data/my_custom_dataset
```

---

## Command Line Arguments Reference

### `inference.py`
| Argument | Default | Description |
| :--- | :--- | :--- |
| `--model` | `yolov3` | Model architecture (`yolov3`, `yolov3-tiny`, `yolov3-spp`) |
| `--source` | `https://ultralytics.com/images/zidane.jpg` | Image URL or local file path |
| `--conf` | `0.25` | Confidence score detection threshold |
| `--device` | Auto | Hardware device (`cpu` or `cuda:0`) |
| `--save-dir` | `./runs/inference` | Directory where annotated output image is saved |

### `train.py`
| Argument | Default | Description |
| :--- | :--- | :--- |
| `--model` | `yolov3-tiny` | Model architecture (`yolov3-tiny` or `yolov3`) |
| `--epochs` | `3` | Number of training epochs |
| `--batch-size` | `4` | Training batch size per step |
| `--lr` | `0.001` | Learning rate for the optimizer |
| `--data-dir` | `./data/coco128` | Local dataset directory path |
| `--save-path` | `./runs/yolov3_trained.pt`| Destination path for saving trained weights |

