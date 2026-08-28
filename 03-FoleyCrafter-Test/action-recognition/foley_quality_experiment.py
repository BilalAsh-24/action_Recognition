"""
CONTROLLED FOLEY QUALITY EXPERIMENT — single new generation.

Only ONE variable changes vs the previous run: the text prompt.
Seed, steps, scales, device split, checkpoints and input segment are identical,
so any difference in the output is attributable to the prompt.

Action: "drink from cup" 5.50-8.50s (Module 2, confirmed, windows [5,6,7]).
Input video segment has NO audio stream (created with -an): source audio cannot
reach the model. Qwen is not loaded.
"""
import gc, json, os, os.path as osp, sys, threading, time
import numpy as np, psutil, soundfile as sf, torch, torchvision

FOLEY = "/Users/bilalashfaque/Desktop/Silent-Video-Project/03-FoleyCrafter-Test/foleycrafter"
sys.path.insert(0, FOLEY); os.chdir(FOLEY)

from transformers import CLIPImageProcessor, CLIPVisionModelWithProjection  # noqa: E402
from foleycrafter.models.onset import torch_utils                            # noqa: E402
from foleycrafter.models.time_detector.model import VideoOnsetNet            # noqa: E402
from foleycrafter.pipelines.auffusion_pipeline import Generator, denormalize_spectrogram  # noqa: E402
from foleycrafter.utils.util import build_foleycrafter, read_frames_with_moviepy          # noqa: E402

AR = "/Users/bilalashfaque/Desktop/Silent-Video-Project/03-FoleyCrafter-Test/action-recognition"
OUT_DIR = osp.join(AR, "results", "foley_quality_experiment")
SEGMENT = osp.join(AR, "results", "foley_integration_test", "segment_input", "drink_from_cup.mp4")
CKPT, MPS, CPU = "checkpoints", "mps", "cpu"
SEED, STEPS, SEM_SCALE, TEMP_SCALE = 42, 25, 1.0, 0.2      # IDENTICAL to previous run

PROMPT = ("Natural realistic close-up Foley recording of a person drinking from a ceramic cup "
          "indoors, subtle realistic drinking and cup-contact sounds, clean isolated Foley, "
          "natural human movement, intimate room recording, no music, no speech, "
          "no background noise, no exaggerated effects.")
NPROMPT = ""

MIN_AVAIL_GB, MAX_SWAP_GROWTH_GB = 1.5, 8.0
BASE_SWAP = psutil.swap_memory().used/1e9
st = {"peak_used":0.0,"min_avail":999.0,"peak_swap":0.0,"breach":None}
_stop = threading.Event()

def monitor():
    while not _stop.is_set():
        vm, sw = psutil.virtual_memory(), psutil.swap_memory()
        a, s = vm.available/1e9, sw.used/1e9
        st["peak_used"]=max(st["peak_used"],vm.used/1e9); st["min_avail"]=min(st["min_avail"],a)
        st["peak_swap"]=max(st["peak_swap"],s)
        if st["breach"] is None:
            if a < MIN_AVAIL_GB: st["breach"]=f"available {a:.2f}GB < {MIN_AVAIL_GB}GB"
            elif s-BASE_SWAP > MAX_SWAP_GROWTH_GB: st["breach"]=f"swap +{s-BASE_SWAP:.2f}GB"
        time.sleep(0.05)

def mem(tag):
    vm, sw = psutil.virtual_memory(), psutil.swap_memory()
    print(f"[MEM] {tag:30s} used={vm.used/1e9:6.2f}GB avail={vm.available/1e9:5.2f}GB swap={sw.used/1e9:5.2f}GB")

t_all=time.time(); mem("baseline")
threading.Thread(target=monitor, daemon=True).start()
print(f"\nPROMPT: {PROMPT}\nSEED={SEED} STEPS={STEPS} (identical to previous run)")

print("\n>>> loading FoleyCrafter (cached only) <<<")
t0=time.time()
vocoder = Generator.from_pretrained(CKPT, subfolder="vocoder").to(MPS)
td = VideoOnsetNet(False)
td,_ = torch_utils.load_model(osp.join(CKPT,"timestamp_detector.pth.tar"), td, device=CPU, strict=True)
td = td.to(CPU)
pipe = build_foleycrafter().to(MPS)
ck = torch.load(osp.join(CKPT,"temporal_adapter.ckpt"), map_location="cpu")
if "state_dict" in ck: ck = ck["state_dict"]
sd = {(k[len("module."):] if k.startswith("module.") else k):v for k,v in ck.items()}
m,u = pipe.controlnet.load_state_dict(sd, strict=False); del ck, sd; gc.collect()
pipe.load_ip_adapter(osp.join(CKPT,"semantic"), subfolder="", weight_name="semantic_adapter.bin", image_encoder_folder=None)
pipe.set_ip_adapter_scale(SEM_SCALE)
ip = CLIPImageProcessor()
ie = CLIPVisionModelWithProjection.from_pretrained("h94/IP-Adapter", subfolder="models/image_encoder").to(MPS)
load_s=time.time()-t0
print(f"    load {load_s:.2f}s | ControlNet missing={len(m)} unexpected={len(u)}")
print(f"    devices vocoder:{next(vocoder.parameters()).device} unet:{next(pipe.unet.parameters()).device} "
      f"vae:{next(pipe.vae.parameters()).device} controlnet:{next(pipe.controlnet.parameters()).device} "
      f"text:{next(pipe.text_encoder.parameters()).device} clip:{next(ie.parameters()).device} "
      f"time_detector:{next(td.parameters()).device}")
mem("after load")
if st["breach"]:
    print(f"!!! ABORT: {st['breach']}"); _stop.set(); sys.exit(2)

vt = torchvision.transforms.Compose([
    torchvision.transforms.Resize((128,128)), torchvision.transforms.CenterCrop((112,112)),
    torchvision.transforms.Normalize(mean=[0.485,0.456,0.406], std=[0.229,0.224,0.225])])
gen = torch.Generator(device=MPS); gen.manual_seed(SEED)
os.makedirs(OUT_DIR, exist_ok=True)

with torch.no_grad():
    frames, duration = read_frames_with_moviepy(SEGMENT, max_frame_nums=150)
    tf = vt(torch.FloatTensor(frames).permute(0,3,1,2))
    preds = torch.sigmoid(td({"frames": tf.unsqueeze(0).permute(0,2,1,3,4).to(CPU)}))
    tc = [-1 if preds[0][int(i/(1024/10*duration)*150)] < 0.5 else 1 for i in range(int(1024/10*duration))]
    tc = tc + [-1]*(1024-len(tc))
    time_condition = torch.FloatTensor(tc).unsqueeze(0).unsqueeze(0).unsqueeze(0).repeat(1,1,256,1).to(MPS)
    images = ip(images=frames, return_tensors="pt").to(MPS)
    emb = ie(**images).image_embeds
    emb = torch.mean(emb,dim=0,keepdim=True).unsqueeze(0).unsqueeze(0)
    emb = torch.cat([torch.zeros_like(emb), emb], dim=1)

    mem("before generation")
    print(f"\n>>> ONE generation ({STEPS} steps) <<<")
    t0=time.time()
    sample = pipe(prompt=PROMPT, negative_prompt=NPROMPT, ip_adapter_image_embeds=emb,
                  image=time_condition, controlnet_conditioning_scale=TEMP_SCALE,
                  num_inference_steps=STEPS, height=256, width=1024, output_type="pt", generator=gen)
    gen_s=time.time()-t0
    mem("after generation")
    audio = denormalize_spectrogram(sample.images[0])
    audio = vocoder.inference(audio, lengths=160000)[0][: int(duration*16000)]

out_wav = osp.join(OUT_DIR, "new_drink_from_cup.wav")
sf.write(out_wav, audio, 16000)
print(f"\nwrote {out_wav}")

del pipe, vocoder, ie, td, sample; gc.collect(); torch.mps.empty_cache(); time.sleep(3)
mem("after release")
_stop.set(); time.sleep(0.2)
total_s=time.time()-t_all

json.dump({"prompt":PROMPT,"seed":SEED,"steps":STEPS,"semantic_scale":SEM_SCALE,
           "temporal_scale":TEMP_SCALE,"segment_input":SEGMENT,"output":out_wav,
           "timing":{"load_s":round(load_s,2),"generation_s":round(gen_s,2),"total_s":round(total_s,2)},
           "memory":{"baseline_swap_gb":round(BASE_SWAP,2),"peak_used_gb":round(st["peak_used"],2),
                     "min_avail_gb":round(st["min_avail"],2),"peak_swap_gb":round(st["peak_swap"],2),
                     "final_swap_gb":round(psutil.swap_memory().used/1e9,2),"breach":st["breach"]}},
          open(osp.join(OUT_DIR,"generation_meta.json"),"w"), indent=2)

print(f"\n  load {load_s:.2f}s | generation {gen_s:.2f}s | total {total_s:.2f}s")
print(f"  peak used {st['peak_used']:.2f}GB | min avail {st['min_avail']:.2f}GB | "
      f"peak swap {st['peak_swap']:.2f}GB (base {BASE_SWAP:.2f}) | breach: {st['breach'] or 'NONE'}")
print("\nRESULT:", "QUALITY_EXPERIMENT_PASS" if not st["breach"] else "ABORTED_MEMORY_GUARD")
