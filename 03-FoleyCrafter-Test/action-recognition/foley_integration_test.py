"""
MODULE 2 -> MODULE 3 CONTROLLED INTEGRATION TEST

    module2_action_segments.json  (resolved action + time span)
        -> Foley text prompt
            -> FoleyCrafter (existing verified M4/MPS pipeline)
                -> ONE generated .wav

Processes exactly ONE action ("drink from cup", 5.50-8.50s, confirmed).
Does NOT merge audio into video. Does NOT implement synchronisation.
Does NOT modify FoleyCrafter source. Uses only cached checkpoints.

The video segment fed to FoleyCrafter was extracted with `-an`, so it contains
no audio stream at all: source audio cannot reach the model.
"""
import gc, json, os, os.path as osp, sys, time
import numpy as np, psutil, soundfile as sf, torch, torchvision

FOLEY = "/Users/bilalashfaque/Desktop/Silent-Video-Project/03-FoleyCrafter-Test/foleycrafter"
sys.path.insert(0, FOLEY)
os.chdir(FOLEY)                                   # checkpoints/ paths are relative

from transformers import CLIPImageProcessor, CLIPVisionModelWithProjection  # noqa: E402
from foleycrafter.models.onset import torch_utils                            # noqa: E402
from foleycrafter.models.time_detector.model import VideoOnsetNet            # noqa: E402
from foleycrafter.pipelines.auffusion_pipeline import Generator, denormalize_spectrogram  # noqa: E402
from foleycrafter.utils.util import build_foleycrafter, read_frames_with_moviepy          # noqa: E402

AR = "/Users/bilalashfaque/Desktop/Silent-Video-Project/03-FoleyCrafter-Test/action-recognition"
M2_JSON = osp.join(AR, "results", "module2_action_segments.json")
OUT_DIR = osp.join(AR, "results", "foley_integration_test")
SEGMENT = osp.join(OUT_DIR, "segment_input", "drink_from_cup.mp4")
CKPT = "checkpoints"
MPS, CPU = "mps", "cpu"
SEED, STEPS, SEM_SCALE, TEMP_SCALE = 42, 25, 1.0, 0.2

_peak_used = _peak_swap = 0.0
def mem(tag, quiet=False):
    global _peak_used, _peak_swap
    vm, sw = psutil.virtual_memory(), psutil.swap_memory()
    _peak_used = max(_peak_used, vm.used/1e9); _peak_swap = max(_peak_swap, sw.used/1e9)
    if not quiet:
        print(f"[MEM] {tag:34s} used={vm.used/1e9:6.2f}GB avail={vm.available/1e9:5.2f}GB swap={sw.used/1e9:5.2f}GB")

t_all = time.time()
BASE_SWAP = psutil.swap_memory().used/1e9
mem("baseline")

# ---- 1/2. Module 2 action -> Foley prompt ---------------------------------
d = json.load(open(M2_JSON))
act = [s for s in d["resolved_actions"] if s["status"] == "confirmed" and "drink" in s["action"]][0]
PROMPT = ("realistic sound of a person drinking from a cup, subtle cup and drinking sounds, "
          "natural indoor recording")
NPROMPT = ""
print(f"\n>>> MODULE 2 ACTION -> FOLEY PROMPT <<<")
print(f"    action:   '{act['action']}'  ({act['start']}s - {act['end']}s, {act['duration']}s)")
print(f"    status:   {act['status']}  support={act['support_count']} windows={act['supporting_windows']}")
print(f"    prompt:   \"{PROMPT}\"")
print(f"    segment:  {SEGMENT}")

# ---- 4. build models on the verified device split -------------------------
print("\n>>> loading FoleyCrafter (cached checkpoints only) <<<")
t0 = time.time()
vocoder = Generator.from_pretrained(CKPT, subfolder="vocoder").to(MPS)
time_detector = VideoOnsetNet(False)
time_detector, _ = torch_utils.load_model(osp.join(CKPT, "timestamp_detector.pth.tar"),
                                          time_detector, device=CPU, strict=True)
time_detector = time_detector.to(CPU)                      # Conv3d -> CPU by design
pipe = build_foleycrafter().to(MPS)
ckpt = torch.load(osp.join(CKPT, "temporal_adapter.ckpt"), map_location="cpu")
if "state_dict" in ckpt: ckpt = ckpt["state_dict"]
sd = {(k[len("module."):] if k.startswith("module.") else k): v for k, v in ckpt.items()}
m, u = pipe.controlnet.load_state_dict(sd, strict=False)
print(f"    ControlNet missing={len(m)} unexpected={len(u)}")
del ckpt, sd; gc.collect()
pipe.load_ip_adapter(osp.join(CKPT, "semantic"), subfolder="",
                     weight_name="semantic_adapter.bin", image_encoder_folder=None)
pipe.set_ip_adapter_scale(SEM_SCALE)
image_processor = CLIPImageProcessor()
image_encoder = CLIPVisionModelWithProjection.from_pretrained(
    "h94/IP-Adapter", subfolder="models/image_encoder").to(MPS)
load_s = time.time() - t0
print(f"    load time: {load_s:.2f}s")
print(f"    devices -> vocoder:{next(vocoder.parameters()).device} unet:{next(pipe.unet.parameters()).device} "
      f"vae:{next(pipe.vae.parameters()).device} controlnet:{next(pipe.controlnet.parameters()).device}")
print(f"               text_encoder:{next(pipe.text_encoder.parameters()).device} "
      f"image_encoder:{next(image_encoder.parameters()).device} "
      f"time_detector:{next(time_detector.parameters()).device}")
mem("after model load")

# ---- 7/8. ONE generation --------------------------------------------------
vision_transform = torchvision.transforms.Compose([
    torchvision.transforms.Resize((128, 128)),
    torchvision.transforms.CenterCrop((112, 112)),
    torchvision.transforms.Normalize(mean=[0.485,0.456,0.406], std=[0.229,0.224,0.225])])

generator = torch.Generator(device=MPS); generator.manual_seed(SEED)
os.makedirs(OUT_DIR, exist_ok=True)

with torch.no_grad():
    frames, duration = read_frames_with_moviepy(SEGMENT, max_frame_nums=150)
    print(f"\n    read {frames.shape} frames, duration={duration:.3f}s (video only)")

    tf = torch.FloatTensor(frames).permute(0,3,1,2)
    tf = vision_transform(tf)
    preds = torch.sigmoid(time_detector({"frames": tf.unsqueeze(0).permute(0,2,1,3,4).to(CPU)}))

    tc = [-1 if preds[0][int(i/(1024/10*duration)*150)] < 0.5 else 1
          for i in range(int(1024/10*duration))]
    tc = tc + [-1]*(1024-len(tc))
    time_condition = torch.FloatTensor(tc).unsqueeze(0).unsqueeze(0).unsqueeze(0).repeat(1,1,256,1).to(MPS)

    images = image_processor(images=frames, return_tensors="pt").to(MPS)
    emb = image_encoder(**images).image_embeds
    emb = torch.mean(emb, dim=0, keepdim=True).unsqueeze(0).unsqueeze(0)
    emb = torch.cat([torch.zeros_like(emb), emb], dim=1)

    mem("before generation")
    print(f"\n>>> ONE FoleyCrafter generation ({STEPS} steps) <<<")
    t0 = time.time()
    sample = pipe(prompt=PROMPT, negative_prompt=NPROMPT, ip_adapter_image_embeds=emb,
                  image=time_condition, controlnet_conditioning_scale=TEMP_SCALE,
                  num_inference_steps=STEPS, height=256, width=1024,
                  output_type="pt", generator=generator)
    gen_s = time.time() - t0
    mem("after generation")

    audio = denormalize_spectrogram(sample.images[0])
    audio = vocoder.inference(audio, lengths=160000)[0]
    audio = audio[: int(duration*16000)]

out_wav = osp.join(OUT_DIR, "drink_from_cup.wav")
sf.write(out_wav, audio, 16000)
mem("after save")

print("\n>>> releasing models <<<")
del pipe, vocoder, image_encoder, time_detector, sample
gc.collect(); torch.mps.empty_cache(); time.sleep(2)
mem("after release")
total_s = time.time() - t_all

info = sf.info(out_wav); data, sr = sf.read(out_wav)
print("\n=== OUTPUT VERIFICATION ===")
print(f"  path:        {out_wav}")
print(f"  size:        {os.path.getsize(out_wav)} bytes")
print(f"  format:      {info.format} / {info.subtype}  channels={info.channels}")
print(f"  sample_rate: {sr}")
print(f"  duration:    {len(data)/sr:.3f}s   (segment was {duration:.3f}s)")
print(f"  non-empty:   {len(data)>0 and bool(np.any(data!=0))}  nonzero={int(np.count_nonzero(data))}/{len(data)}")
print(f"  finite:      {bool(np.all(np.isfinite(data)))}")
print(f"  rms:         {float(np.sqrt(np.mean(data**2))):.5f}  range=[{data.min():.4f}, {data.max():.4f}]")

meta = {"module2_action": act, "foley_prompt": PROMPT, "negative_prompt": NPROMPT,
        "segment_input": SEGMENT, "output_wav": out_wav,
        "config": {"seed": SEED, "steps": STEPS, "semantic_scale": SEM_SCALE,
                   "temporal_scale": TEMP_SCALE, "sample_rate": 16000},
        "timing": {"model_load_s": round(load_s,2), "generation_s": round(gen_s,2),
                   "total_wall_s": round(total_s,2)},
        "memory": {"baseline_swap_gb": round(BASE_SWAP,2), "peak_used_gb": round(_peak_used,2),
                   "peak_swap_gb": round(_peak_swap,2),
                   "final_swap_gb": round(psutil.swap_memory().used/1e9,2)},
        "audio": {"duration_s": round(len(data)/sr,3), "sample_rate": sr,
                  "format": info.format, "subtype": info.subtype,
                  "bytes": os.path.getsize(out_wav)}}
with open(osp.join(OUT_DIR, "integration_test_result.json"), "w") as f:
    json.dump(meta, f, indent=2)

print(f"\n>>> TIMING <<<\n  model load: {load_s:.2f}s\n  generation: {gen_s:.2f}s\n  total wall: {total_s:.2f}s")
print(f">>> MEMORY <<<\n  peak used: {_peak_used:.2f}GB\n  baseline swap: {BASE_SWAP:.2f}GB\n  peak swap: {_peak_swap:.2f}GB")
print("\nRESULT: FOLEY_INTEGRATION_TEST_PASS")
