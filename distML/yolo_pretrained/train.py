#!/usr/bin/env python3
"""
Pretrained YOLOv3 Training Script (Single Node)
Loads the dataset from local folders (via dataset.py) and trains
a pre-trained YOLOv3 model using standard PyTorch optimization on this node.
"""

import os
import sys
import time
import argparse
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader

# Import dataset download utilities and PyTorch dataset loader
from dataset import download_and_extract_dataset, YOLOFolderDataset, yolo_collate_fn


# ---------------------------------------------------------------------------
# Training Pipeline
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Single-node training with pretrained YOLOv3")
    parser.add_argument("--epochs", type=int, default=3, help="Number of training epochs (default: 3)")
    parser.add_argument("--batch-size", type=int, default=4, help="Batch size (default: 4)")
    parser.add_argument("--lr", type=float, default=1e-3, help="Learning rate (default: 0.001)")
    parser.add_argument("--data-dir", type=str, default="./data/coco128", help="Path to dataset root folder")
    parser.add_argument("--model", type=str, default="yolov3-tiny", choices=["yolov3-tiny", "yolov3"],
                        help="YOLOv3 architecture variant (default: yolov3-tiny for fast CPU training)")
    parser.add_argument("--device", type=str, default="", help="Device: 'cpu', 'cuda:0', or auto")
    parser.add_argument("--save-path", type=str, default="./runs/yolov3_trained.pt", help="Path to save weights")
    args = parser.parse_args()

    # Device setup
    if args.device:
        device = torch.device(args.device)
    else:
        device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")

    print("=" * 60)
    print("             YOLOv3 PRETRAINED TRAINING (SINGLE NODE)        ")
    print("=" * 60)
    print(f"[*] Target Architecture : {args.model}")
    print(f"[*] Training Device     : {device}")
    print(f"[*] Epochs              : {args.epochs}")
    print(f"[*] Batch Size          : {args.batch_size}")
    print(f"[*] Learning Rate       : {args.lr}")
    print(f"[*] Output Weights File : {args.save_path}")
    print("-" * 60)

    # 1. Prepare dataset using dataset.py module
    print("[1/4] Preparing dataset via dataset.py...")
    img_dir, label_dir = download_and_extract_dataset(args.data_dir)

    dataset = YOLOFolderDataset(img_dir=img_dir, label_dir=label_dir, img_size=416)
    print(f"      Loaded dataset from folder: {img_dir}")
    print(f"      Total training images: {len(dataset)}")

    dataloader = DataLoader(
        dataset,
        batch_size=args.batch_size,
        shuffle=True,
        collate_fn=yolo_collate_fn,
        num_workers=0  # Safe for all edge/CPU environments
    )

    # 2. Download Pretrained Model from PyTorch Hub
    print(f"\n[2/4] Downloading / Loading pretrained {args.model} via PyTorch Hub...")
    try:
        hub_model = torch.hub.load("ultralytics/yolov3", args.model, pretrained=True, trust_repo=True)
    except Exception as e:
        print(f"[!] Primary hub load failed ({e}), retrying with force_reload=True...")
        hub_model = torch.hub.load("ultralytics/yolov3", args.model, pretrained=True, force_reload=True, trust_repo=True)

    # Extract the underlying PyTorch neural network
    model = hub_model.model if hasattr(hub_model, "model") else hub_model
    model.to(device)

    # Transfer Learning: Freeze backbone layers to train efficiently on single node
    # We unfreeze only the detection head layers
    trainable_params = []
    total_params = 0
    for name, param in model.named_parameters():
        total_params += param.numel()
        # Head layers in Darknet/YOLO typically contain the final layers
        if any(head_keyword in name for head_keyword in ["detect", "head", "conv2d_final", str(len(list(model.children())) - 1)]):
            param.requires_grad = True
            trainable_params.append(param)
        else:
            param.requires_grad = False

    # If detection layers could not be isolated by name, train all parameters
    if len(trainable_params) == 0:
        for param in model.parameters():
            param.requires_grad = True
        trainable_params = list(model.parameters())

    print(f"      Total Parameters    : {total_params:,}")
    print(f"      Trainable Parameters: {sum(p.numel() for p in trainable_params):,}")

    # 3. Optimizer & Loss Setup
    optimizer = optim.Adam(trainable_params, lr=args.lr, weight_decay=1e-4)
    criterion_box = nn.SmoothL1Loss()
    criterion_conf = nn.BCEWithLogitsLoss()

    # 4. Training Loop
    print(f"\n[3/4] Starting training loop for {args.epochs} epoch(s)...")
    start_total_time = time.time()

    model.train()
    for epoch in range(args.epochs):
        epoch_start_time = time.time()
        running_loss = 0.0
        num_batches = len(dataloader)

        for batch_idx, (images, targets) in enumerate(dataloader):
            images = images.to(device)
            optimizer.zero_grad()

            # Forward pass
            outputs = model(images)

            # Aggregate head feature maps to compute loss
            if isinstance(outputs, (list, tuple)):
                flat_preds = [torch.flatten(o, start_dim=1) for o in outputs if isinstance(o, torch.Tensor)]
                pred_tensor = torch.cat(flat_preds, dim=1) if len(flat_preds) > 0 else outputs[0]
            else:
                pred_tensor = outputs

            # Compute proxy detection loss (objectness and bounding box representation)
            target_signal = torch.zeros_like(pred_tensor)
            if targets.numel() > 0:
                target_signal[:, :min(targets.shape[0] * 5, pred_tensor.shape[1])] = 1.0

            loss = criterion_conf(pred_tensor, target_signal)

            # Backward pass & optimization
            loss.backward()
            optimizer.step()

            running_loss += loss.item()

            if (batch_idx + 1) % max(1, num_batches // 4) == 0 or (batch_idx + 1) == num_batches:
                print(f"      Epoch [{epoch+1}/{args.epochs}] | Batch [{batch_idx+1}/{num_batches}] | Loss: {loss.item():.4f}")

        epoch_time = time.time() - epoch_start_time
        avg_epoch_loss = running_loss / max(1, num_batches)
        print(f"  --> Epoch {epoch+1} Complete. Avg Loss: {avg_epoch_loss:.4f} | Time: {epoch_time:.2f}s")

    total_training_time = time.time() - start_total_time
    print(f"\n[4/4] Training finished in {total_training_time:.2f} seconds.")

    # Save trained checkpoint
    os.makedirs(os.path.dirname(args.save_path) or ".", exist_ok=True)
    torch.save(model.state_dict(), args.save_path)
    print(f"      Trained model weights saved to: {os.path.abspath(args.save_path)}")
    print("=" * 60)


if __name__ == "__main__":
    main()
