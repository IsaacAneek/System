#!/usr/bin/env python3
"""
Pretrained YOLOv3 Inference Script (Single Node)
Downloads official pretrained YOLOv3 weights and performs a single inference
on an input image, reporting detected objects, confidence scores, and bounding boxes.
"""

import os
import sys
import time
import argparse
import torch
from PIL import Image

def parse_args():
    parser = argparse.ArgumentParser(description="Run single-node inference with pretrained YOLOv3")
    parser.add_argument("--model", type=str, default="yolov3", choices=["yolov3", "yolov3-tiny", "yolov3-spp"],
                        help="YOLOv3 model variant to download from PyTorch Hub (default: yolov3)")
    parser.add_argument("--source", type=str, default="https://ultralytics.com/images/zidane.jpg",
                        help="URL or local path of the image to run inference on")
    parser.add_argument("--conf", type=float, default=0.25,
                        help="Confidence threshold for detections (default: 0.25)")
    parser.add_argument("--device", type=str, default="",
                        help="Device to run inference on: 'cpu', 'cuda:0', or auto-detect if empty")
    parser.add_argument("--save-dir", type=str, default="./runs/inference",
                        help="Directory to save the annotated inference image")
    return parser.parse_args()


def main():
    args = parse_args()

    # 1. Device selection
    if args.device:
        device = torch.device(args.device)
    else:
        device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")

    print("=" * 60)
    print("           YOLOv3 PRETRAINED INFERENCE (SINGLE NODE)         ")
    print("=" * 60)
    print(f"[*] Target Model    : {args.model}")
    print(f"[*] Execution Device: {device}")
    print(f"[*] Input Source    : {args.source}")
    print(f"[*] Conf Threshold  : {args.conf}")
    print("-" * 60)

    # 2. Download and load pretrained YOLOv3 from PyTorch Hub
    print(f"[1/3] Downloading / Loading pretrained {args.model} via PyTorch Hub...")
    try:
        # torch.hub.load handles downloading repo and weights automatically
        model = torch.hub.load("ultralytics/yolov3", args.model, pretrained=True, trust_repo=True)
    except Exception as e:
        print(f"[!] Primary hub load failed: {e}")
        print("[!] Retrying with force_reload=True...")
        try:
            model = torch.hub.load("ultralytics/yolov3", args.model, pretrained=True, force_reload=True, trust_repo=True)
        except Exception as e2:
            print(f"[X] Fatal: Failed to download/load YOLOv3 from PyTorch Hub: {e2}")
            sys.exit(1)

    model.to(device)
    model.eval()
    model.conf = args.conf  # NMS confidence threshold

    total_params = sum(p.numel() for p in model.parameters())
    print(f"      Model loaded successfully ({total_params:,} parameters).")

    # 3. Prepare Image
    print("\n[2/3] Preparing input image...")
    # If the user passed a local file that doesn't exist, provide a fallback or check
    if not args.source.startswith("http://") and not args.source.startswith("https://"):
        if not os.path.exists(args.source):
            print(f"[!] Warning: Local image '{args.source}' not found. Falling back to default URL.")
            img_source = "https://ultralytics.com/images/zidane.jpg"
        else:
            img_source = args.source
    else:
        img_source = args.source

    # 4. Run single inference and profile latency
    print(f"\n[3/3] Running single inference pass on: {img_source}")
    t0 = time.time()
    with torch.no_grad():
        results = model(img_source)
    latency_ms = (time.time() - t0) * 1000.0

    # 5. Display detection summary
    print("\n" + "=" * 60)
    print("                      INFERENCE RESULTS                     ")
    print("=" * 60)
    print(f"Inference Latency: {latency_ms:.2f} ms on {device.type.upper()}\n")

    # results.pandas().xyxy[0] returns a DataFrame with: xmin, ymin, xmax, ymax, confidence, class, name
    detections_df = results.pandas().xyxy[0]
    num_objects = len(detections_df)

    if num_objects == 0:
        print(f"No objects detected above confidence threshold {args.conf}.")
    else:
        print(f"Detected {num_objects} object(s):")
        print("-" * 60)
        printf_fmt = "{:<5} | {:<15} | {:<12} | {:<22}\n"
        sys.stdout.write(printf_fmt.format("#", "Class", "Confidence", "Bounding Box [xyxy]"))
        print("-" * 60)
        for idx, row in detections_df.iterrows():
            bbox_str = f"[{int(row['xmin'])}, {int(row['ymin'])}, {int(row['xmax'])}, {int(row['ymax'])}]"
            sys.stdout.write(printf_fmt.format(idx + 1, row["name"], f"{row['confidence'] * 100:.1f}%", bbox_str))
        print("-" * 60)

    # 6. Save annotated image to disk
    os.makedirs(args.save_dir, exist_ok=True)
    results.save(save_dir=args.save_dir)
    print(f"\nAnnotated result image saved to: {os.path.abspath(args.save_dir)}")
    print("=" * 60)


if __name__ == "__main__":
    main()

