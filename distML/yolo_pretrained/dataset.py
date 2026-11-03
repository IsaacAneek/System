#!/usr/bin/env python3
"""
YOLO Dataset Downloader and PyTorch Folder Dataset Loader.
Handles downloading mini datasets (e.g., COCO128 with offline synthetic fallback)
and provides PyTorch Dataset and collate implementations for loading YOLO-format data.
"""

import os
import sys
import zipfile
import urllib.request
import argparse
import torch
from torch.utils.data import Dataset
from torchvision import transforms
from PIL import Image, ImageDraw


# ---------------------------------------------------------------------------
# 1. Dataset Downloader & Extractor
# ---------------------------------------------------------------------------
COCO128_URL = "https://github.com/ultralytics/yolov5/releases/download/v1.0/coco128.zip"

def download_and_extract_dataset(data_dir="./data/coco128"):
    """
    Downloads COCO128 (a ~7MB mini object detection dataset).
    If download fails or network is unavailable, automatically creates a small
    synthetic detection dataset in the destination folder so training never fails.

    Returns:
        tuple (images_dir, labels_dir)
    """
    os.makedirs(data_dir, exist_ok=True)
    images_dir = os.path.join(data_dir, "images", "train2017")
    labels_dir = os.path.join(data_dir, "labels", "train2017")

    # If dataset already exists with images, return immediately
    if os.path.isdir(images_dir) and len(os.listdir(images_dir)) > 0:
        print(f"[Dataset] Found existing dataset in '{data_dir}' ({len(os.listdir(images_dir))} images).")
        return images_dir, labels_dir

    print(f"[Dataset] Downloading small benchmark dataset (COCO128) from:\n          {COCO128_URL}...")
    zip_path = os.path.join(data_dir, "coco128.zip")
    try:
        def _progress(block_num, block_size, total_size):
            downloaded = block_num * block_size
            if total_size > 0:
                percent = downloaded / total_size * 100
                sys.stdout.write(f"\r          Progress: {percent:.1f}% ({downloaded // (1024*1024)}MB / {total_size // (1024*1024)}MB)")
                sys.stdout.flush()

        urllib.request.urlretrieve(COCO128_URL, zip_path, reporthook=_progress)
        print("\n          Extracting dataset...")
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(os.path.dirname(data_dir))
        if os.path.exists(zip_path):
            os.remove(zip_path)
        print(f"[Dataset] COCO128 ready at '{data_dir}'.")
    except Exception as e:
        print(f"\n[!] Note: Online download could not be completed ({e}).")
        print("[*] Generating local small dataset in folder for training...")
        images_dir = os.path.join(data_dir, "images")
        labels_dir = os.path.join(data_dir, "labels")
        os.makedirs(images_dir, exist_ok=True)
        os.makedirs(labels_dir, exist_ok=True)

        # Generate 16 sample synthetic images with bounding boxes (YOLO format: class x_c y_c w h)
        colors = [(220, 50, 50), (50, 220, 50), (50, 50, 220), (220, 220, 50)]
        for i in range(16):
            img = Image.new("RGB", (416, 416), color=(30 + i * 5, 30 + i * 5, 30 + i * 5))
            draw = ImageDraw.Draw(img)
            cls_id = i % 4
            x1, y1 = 50 + (i * 10) % 150, 50 + (i * 15) % 150
            x2, y2 = x1 + 100, y1 + 100
            draw.rectangle([x1, y1, x2, y2], fill=colors[cls_id], outline="white")
            img_path = os.path.join(images_dir, f"sample_{i:03d}.jpg")
            img.save(img_path)

            xc = (x1 + x2) / 2.0 / 416.0
            yc = (y1 + y2) / 2.0 / 416.0
            w = (x2 - x1) / 416.0
            h = (y2 - y1) / 416.0
            lbl_path = os.path.join(labels_dir, f"sample_{i:03d}.txt")
            with open(lbl_path, "w") as f:
                f.write(f"{cls_id} {xc:.6f} {yc:.6f} {w:.6f} {h:.6f}\n")

        print(f"[Dataset] Created 16 synthetic labeled images in '{images_dir}'.")

    return images_dir, labels_dir


# ---------------------------------------------------------------------------
# 2. PyTorch Dataset Loader for Local Folders
# ---------------------------------------------------------------------------
class YOLOFolderDataset(Dataset):
    """
    Loads images and YOLO-format bounding box label files (.txt) from local folders.
    """
    def __init__(self, img_dir, label_dir, img_size=416):
        self.img_dir = img_dir
        self.label_dir = label_dir
        self.img_size = img_size
        valid_exts = (".jpg", ".jpeg", ".png", ".bmp")
        self.img_files = sorted([f for f in os.listdir(img_dir) if f.lower().endswith(valid_exts)])

        self.transform = transforms.Compose([
            transforms.Resize((img_size, img_size)),
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
        ])

    def __len__(self):
        return len(self.img_files)

    def __getitem__(self, idx):
        img_filename = self.img_files[idx]
        img_path = os.path.join(self.img_dir, img_filename)
        img = Image.open(img_path).convert("RGB")
        img_tensor = self.transform(img)

        # Look for matching .txt label file
        label_filename = os.path.splitext(img_filename)[0] + ".txt"
        label_path = os.path.join(self.label_dir, label_filename)

        boxes = []
        if os.path.exists(label_path):
            with open(label_path, "r") as f:
                for line in f:
                    parts = line.strip().split()
                    if len(parts) >= 5:
                        cls_id = int(float(parts[0]))
                        xc, yc, w, h = map(float, parts[1:5])
                        boxes.append([cls_id, xc, yc, w, h])

        if len(boxes) == 0:
            boxes = torch.zeros((0, 5), dtype=torch.float32)
        else:
            boxes = torch.tensor(boxes, dtype=torch.float32)

        return img_tensor, boxes


def yolo_collate_fn(batch):
    """
    Custom collate function to handle variable numbers of bounding boxes per image.
    Appends image index as the first column: [batch_idx, class, xc, yc, w, h].
    """
    images, targets = zip(*batch)
    images = torch.stack(images, dim=0)

    batched_targets = []
    for i, target_boxes in enumerate(targets):
        if target_boxes.numel() > 0:
            num_boxes = target_boxes.shape[0]
            idx_column = torch.full((num_boxes, 1), i, dtype=torch.float32)
            batched_targets.append(torch.cat([idx_column, target_boxes], dim=1))

    if len(batched_targets) > 0:
        batched_targets = torch.cat(batched_targets, dim=0)
    else:
        batched_targets = torch.zeros((0, 6), dtype=torch.float32)

    return images, batched_targets


# ---------------------------------------------------------------------------
# 3. Direct Execution CLI
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Download and verify YOLO dataset")
    parser.add_argument("--data-dir", type=str, default="./data/coco128",
                        help="Destination directory for dataset (default: ./data/coco128)")
    args = parser.parse_args()

    print("=" * 60)
    print("                 YOLO DATASET DOWNLOADER                     ")
    print("=" * 60)
    img_dir, lbl_dir = download_and_extract_dataset(args.data_dir)
    print(f"Images directory: {img_dir}")
    print(f"Labels directory: {lbl_dir}")
    ds = YOLOFolderDataset(img_dir=img_dir, label_dir=lbl_dir)
    print(f"Dataset successfully verified! Total samples: {len(ds)}")
    print("=" * 60)

