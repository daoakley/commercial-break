#!/usr/bin/env python3
"""Export frozen MobileCLIP2-S0 image tower; synthetic data only, no TV access."""
import argparse
from collections import Counter
import hashlib
import importlib.metadata
import json
from pathlib import Path
import shutil
import subprocess
import sys
import types

import ncnn
import numpy as np
import open_clip
import torch
from timm.utils import reparameterize_model


def digest(path):
    with open(path, "rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def normalize(vector):
    vector = np.asarray(vector, dtype=np.float64).reshape(-1)
    return vector / max(float(np.linalg.norm(vector)), 1e-12)


def portable_attention(self, image):
    """Equivalent eval attention without the unsupported 5D qkv/unbind graph."""
    batch, channels, height, width = image.shape
    count = height * width
    tokens = image.flatten(2).transpose(-2, -1)
    q, k, v = self.qkv(tokens).chunk(3, dim=-1)
    q = q.reshape(batch, count, self.num_heads, self.head_dim).transpose(1, 2)
    k = k.reshape(batch, count, self.num_heads, self.head_dim).transpose(1, 2)
    v = v.reshape(batch, count, self.num_heads, self.head_dim).transpose(1, 2)
    attention = ((q * self.scale) @ k.transpose(-2, -1)).softmax(dim=-1)
    result = (attention @ v).transpose(1, 2).reshape(batch, count, channels)
    result = self.proj(result)
    return result.transpose(-2, -1).reshape(batch, channels, height, width)


def run_ncnn(param, binary, inputs):
    outputs = []
    with ncnn.Net() as net:
        net.opt.use_vulkan_compute = False
        net.opt.num_threads = 1
        net.opt.use_fp16_packed = False
        net.opt.use_fp16_storage = False
        net.opt.use_fp16_arithmetic = False
        if net.load_param(str(param)) != 0 or net.load_model(str(binary)) != 0:
            raise RuntimeError("ncnn model load failed")
        names = {"input": list(net.input_names()), "output": list(net.output_names())}
        for tensor in inputs:
            with net.create_extractor() as extractor:
                array = np.ascontiguousarray(tensor.numpy()[0])
                if extractor.input(names["input"][0], ncnn.Mat(array).clone()) != 0:
                    raise RuntimeError("ncnn input failed")
                status, result = extractor.extract(names["output"][0])
                if status != 0:
                    raise RuntimeError("ncnn extract failed")
                outputs.append(np.asarray(result).copy().reshape(-1))
    return outputs, names


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--revision", default="3136ea51c8ed56b9f9abfab04cb816735aaad6cb")
    args = parser.parse_args()
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=True)
    torch.set_num_threads(2)
    torch.manual_seed(20261026)
    model, _, preprocess = open_clip.create_model_and_transforms(
        "MobileCLIP2-S0", pretrained=str(args.checkpoint.resolve()),
        image_mean=(0, 0, 0), image_std=(1, 1, 1))
    model.eval()
    model = reparameterize_model(model)
    visual = model.visual.eval()
    inputs = [torch.rand(1, 3, 256, 256), torch.zeros(1, 3, 256, 256),
              torch.ones(1, 3, 256, 256) * .5]
    with torch.inference_mode():
        reference = [visual(value).numpy().reshape(-1).copy() for value in inputs]
        # Do not change any weights. Split packed qkv before reshaping so every
        # intermediate fits ncnn's physical rank, retaining equivalent attention.
        for module in visual.modules():
            if type(module).__module__ == "timm.models.fastvit" and type(module).__name__ == "Attention":
                module.forward = types.MethodType(portable_attention, module)
        portable = [visual(value).numpy().reshape(-1).copy() for value in inputs]
        for expected, actual in zip(reference, portable):
            np.testing.assert_allclose(actual, expected, rtol=1e-4, atol=1e-4)
        traced = torch.jit.trace(visual, inputs[0], check_inputs=[(inputs[1],), (inputs[2],)])
        script = root / "mobileclip2_s0_image.pt"
        traced.save(str(script))
    for index, (value, result) in enumerate(zip(inputs, reference)):
        value.numpy().astype("<f4").tofile(root / f"synthetic_{index}_input_f32.bin")
        result.astype("<f4").tofile(root / f"synthetic_{index}_reference_f32.bin")
    report = {"model": "MobileCLIP2-S0", "revision": args.revision,
              "checkpoint_sha256": digest(args.checkpoint), "image_parameters": sum(p.numel() for p in visual.parameters()),
              "preprocessing": str(preprocess), "input": {"torch_shape": [1, 3, 256, 256],
                  "ncnn_chw": [3, 256, 256], "dtype": "float32", "color": "RGB", "range": [0, 1],
                  "mean": [0, 0, 0], "std": [1, 1, 1]},
              "output": {"elements": 512, "normalization": "raw embedding; harness L2-normalizes"},
              "synthetic_inputs": {"seed": 20261026, "cases": ["uniform random 0..1", "black", "constant gray0.5"]},
              "versions": {name: importlib.metadata.version(name) for name in ("torch", "open_clip_torch", "timm", "pnnx", "ncnn")},
              "variants": {}, "host_verification": "CPU ncnn, one thread, float32 computation, no Vulkan; not TV benchmark",
              "export_graph_rewrite": "FastViT qkv chunk before per-head reshape; eval-only exact attention formula, checked against original PyTorch outputs; no weights changed",
              "license": "Apple model weights remain governed by upstream LICENSE_MODELS; research export only"}
    converter = shutil.which("pnnx") or str(Path(sys.executable).with_name("pnnx"))
    for variant, fp16 in (("fp32", 0), ("fp16_storage", 1)):
        folder = root / variant
        folder.mkdir(exist_ok=True)
        stem = folder / "mobileclip2_s0_image"
        command = [converter, str(script), "inputshape=[1,3,256,256]", "device=cpu", "optlevel=2", f"fp16={fp16}",
                   "pnnxparam=" + str(stem) + ".pnnx.param", "pnnxbin=" + str(stem) + ".pnnx.bin",
                   "pnnxpy=" + str(stem) + "_pnnx.py", "pnnxonnx=" + str(stem) + ".pnnx.onnx",
                   "ncnnparam=" + str(stem) + ".ncnn.param", "ncnnbin=" + str(stem) + ".ncnn.bin",
                   "ncnnpy=" + str(stem) + "_ncnn.py"]
        with (folder / "conversion.log").open("w") as log:
            subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)
        param, binary = Path(str(stem) + ".ncnn.param"), Path(str(stem) + ".ncnn.bin")
        converted, names = run_ncnn(param, binary, inputs)
        comparisons = []
        for index, (expected, actual) in enumerate(zip(reference, converted)):
            if actual.shape != (512,) or not np.isfinite(actual).all():
                raise RuntimeError("invalid converted output shape/values")
            cosine = float(np.dot(normalize(expected), normalize(actual)))
            max_error = float(np.max(np.abs(expected - actual)))
            normalized_error = float(np.max(np.abs(normalize(expected) - normalize(actual))))
            comparisons.append({"case": index, "cosine": cosine, "max_raw_abs_error": max_error,
                                "max_normalized_abs_error": normalized_error})
            actual.astype("<f4").tofile(folder / f"synthetic_{index}_ncnn_f32.bin")
            if cosine < (0.99999 if not fp16 else 0.999) or normalized_error > (0.001 if not fp16 else 0.01):
                raise RuntimeError(f"conversion verification failed: {variant} {comparisons[-1]}")
        operations = Counter(line.split()[0] for line in param.read_text().splitlines()[2:] if line.strip())
        report["variants"][variant] = {"ncnn_names": names, "operations": dict(operations),
            "files": {path.name: {"bytes": path.stat().st_size, "sha256": digest(path)} for path in (param, binary)},
            "comparisons": comparisons, "verified": True,
            "weights": "float16 stored, float32 compute verified" if fp16 else "float32"}
        (root / "export_report.json").write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps({"variant": variant, "verified": True, "comparisons": comparisons}), flush=True)


if __name__ == "__main__":
    main()
