"""
STEP 7: MPS execution-path validation for Qwen2.5-VL-3B-Instruct.

NO real video. NO test_video.mp4. NO frame extraction.
ONE tiny synthetic forward pass using the smallest valid visual input.

Safety guards: abort if available memory < 1.5 GB or swap grows > 5 GB.
"""
import gc, threading, time
import numpy as np, psutil, torch
from PIL import Image
from transformers import AutoProcessor, Qwen2_5_VLForConditionalGeneration

MODEL = "Qwen/Qwen2.5-VL-3B-Instruct"
MIN_AVAIL_GB, MAX_SWAP_GROWTH_GB = 1.5, 5.0

_vm0, _sw0 = psutil.virtual_memory(), psutil.swap_memory()
BASE_SWAP = _sw0.used / 1e9
stats = {"peak_used": 0.0, "min_avail": 999.0, "peak_swap": 0.0, "breach": None}
_stop = threading.Event()

def monitor():
    while not _stop.is_set():
        vm, sw = psutil.virtual_memory(), psutil.swap_memory()
        u, a, s = vm.used/1e9, vm.available/1e9, sw.used/1e9
        stats["peak_used"] = max(stats["peak_used"], u)
        stats["min_avail"] = min(stats["min_avail"], a)
        stats["peak_swap"] = max(stats["peak_swap"], s)
        if stats["breach"] is None:
            if a < MIN_AVAIL_GB:
                stats["breach"] = f"available memory {a:.2f}GB < {MIN_AVAIL_GB}GB"
            elif s - BASE_SWAP > MAX_SWAP_GROWTH_GB:
                stats["breach"] = f"swap grew {s-BASE_SWAP:.2f}GB > {MAX_SWAP_GROWTH_GB}GB"
        time.sleep(0.05)

def snap(tag):
    vm, sw = psutil.virtual_memory(), psutil.swap_memory()
    print(f"[MEM] {tag:34s} used={vm.used/1e9:6.2f}GB avail={vm.available/1e9:5.2f}GB swap={sw.used/1e9:5.2f}GB")

print(f"baseline swap = {BASE_SWAP:.2f}GB | guards: avail<{MIN_AVAIL_GB}GB, swap growth>{MAX_SWAP_GROWTH_GB}GB")
assert torch.backends.mps.is_available(), "MPS unavailable"
snap("baseline")

t = threading.Thread(target=monitor, daemon=True); t.start()

# --- 2. load (cached) ------------------------------------------------------
print("\n>>> 2. loading model (cached) in bfloat16 <<<")
t0 = time.time()
model = Qwen2_5_VLForConditionalGeneration.from_pretrained(MODEL, dtype=torch.bfloat16)
model.eval()
print(f"    CPU load: {time.time()-t0:.2f}s")
snap("after CPU load (mmap, lazy)")

# --- 3. move to MPS --------------------------------------------------------
print("\n>>> 3. moving model to MPS (materialises 7.51GB into unified memory) <<<")
t0 = time.time()
model = model.to("mps")
torch.mps.synchronize()
transfer_s = time.time() - t0
print(f"    CPU->MPS transfer: {transfer_s:.2f}s")
snap("after .to('mps')")
if stats["breach"]:
    print(f"\n!!! MEMORY GUARD BREACHED during transfer: {stats['breach']} — STOPPING !!!")
    _stop.set(); raise SystemExit(2)

# --- 4. verify placement/dtype/count ---------------------------------------
print("\n>>> 4. parameter verification <<<")
devs, dts, total = {}, {}, 0
cpu_left = []
for n, p in model.named_parameters():
    d = str(p.device); devs[d] = devs.get(d, 0) + 1
    dts[str(p.dtype)] = dts.get(str(p.dtype), 0) + 1
    total += p.numel()
    if p.device.type != "mps": cpu_left.append(n)
print(f"    devices:        {devs}")
print(f"    dtypes:         {dts}")
print(f"    params on CPU:  {len(cpu_left)} {cpu_left[:3]}")
print(f"    total params:   {total:,}")
print(f"    == 3,754,622,976: {total == 3_754_622_976}")
print(f"    all on mps:     {set(devs) == {'mps:0'}}")
print(f"    all bfloat16:   {set(dts) == {'torch.bfloat16'}}")

# --- 8. ONE tiny synthetic forward pass ------------------------------------
print("\n>>> 8. building MINIMAL synthetic visual input (no video, no file) <<<")
# smallest valid: patch=14, spatial_merge=2 -> 28x28px minimum grid; use 56x56 to
# satisfy the processor's min_pixels while staying trivially small.
proc = AutoProcessor.from_pretrained(MODEL, min_pixels=56*56, max_pixels=56*56)
rng = np.random.default_rng(0)
synth = Image.fromarray(rng.integers(0, 256, (56, 56, 3), dtype=np.uint8))  # synthetic noise
msgs = [{"role": "user", "content": [{"type": "image"}, {"type": "text", "text": "Hi"}]}]
text = proc.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
inputs = proc(text=[text], images=[synth], return_tensors="pt")
print(f"    synthetic image: 56x56 random noise (NOT from any file)")
for k, v in inputs.items():
    if hasattr(v, "shape"): print(f"    {k}: {tuple(v.shape)} {v.dtype}")
print(f"    image_grid_thw = {inputs['image_grid_thw'].tolist()} -> "
      f"{int(inputs['image_grid_thw'].prod())} patches, "
      f"{int(inputs['image_grid_thw'].prod())//4} visual token(s)")
inputs = {k: v.to("mps") for k, v in inputs.items()}

print("\n>>> running ONE forward pass on MPS <<<")
t0 = time.time()
with torch.no_grad():
    out = model(**inputs)
torch.mps.synchronize()
fwd_s = time.time() - t0
snap("after forward pass")

logits = out.logits
print(f"\n>>> 10. RESULTS <<<")
print(f"    output type:    {type(out).__name__}")
print(f"    logits shape:   {tuple(logits.shape)}")
print(f"    logits dtype:   {logits.dtype}")
print(f"    logits device:  {logits.device}")
finite = torch.isfinite(logits.float()).all().item()
print(f"    all finite:     {finite}")
print(f"    logits range:   [{logits.float().min().item():.3f}, {logits.float().max().item():.3f}]")
print(f"    forward time:   {fwd_s:.3f}s")
print(f"    transfer time:  {transfer_s:.2f}s")

# --- 15. recovery ----------------------------------------------------------
print("\n>>> 15. releasing model, checking recovery <<<")
del model, out, logits, inputs
gc.collect(); torch.mps.empty_cache(); time.sleep(3)
snap("after release")

_stop.set(); time.sleep(0.2)
print(f"\n>>> MEMORY EXTREMES DURING TEST <<<")
print(f"    peak used:      {stats['peak_used']:.2f}GB")
print(f"    min available:  {stats['min_avail']:.2f}GB")
print(f"    baseline swap:  {BASE_SWAP:.2f}GB")
print(f"    peak swap:      {stats['peak_swap']:.2f}GB  (growth {stats['peak_swap']-BASE_SWAP:+.2f}GB)")
print(f"    guard breach:   {stats['breach'] or 'NONE'}")
print("\nRESULT:", "MPS_SYNTHETIC_TEST_PASS" if (finite and not stats["breach"]) else "MPS_SYNTHETIC_TEST_FAIL")
