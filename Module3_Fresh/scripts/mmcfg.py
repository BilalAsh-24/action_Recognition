"""Shared configuration for the Module 3 MMAudio first-generation experiment.

Paths are absolute and live entirely inside Module3_Fresh/. The official MMAudio
repository at models/MMAudio is imported as a library and never modified: we build
our own ModelConfig instance rather than mutating the module-level ones.
"""
from pathlib import Path
import torch

ROOT = Path(__file__).resolve().parent.parent

# --- source of truth -------------------------------------------------------
SOURCE_VIDEO   = ROOT / "input" / "test_video.mp4"
CONTEXT_CLIP   = ROOT / "work" / "context_4.5_9.0.mp4"
MODULE2_JSON   = ROOT / "module2" / "module2_action_segments.json"

# --- action under test (authoritative interval, source-video coordinates) ---
ACTION          = "drink from cup"
ACTION_START    = 5.50
ACTION_END      = 8.50
# 8 s temporal-context window (report SS N): 2.00 s -> end of source video.
CONTEXT_START   = 4.50
CONTEXT_END     = 9.00
# the action inside context-clip coordinates
ACTION_IN_CLIP  = (ACTION_START - CONTEXT_START, ACTION_END - CONTEXT_START)   # 3.50 - 6.50

# --- model ------------------------------------------------------------------
VARIANT      = "small_44k"
MODE         = "44k"
NET_CKPT     = ROOT / "models" / "weights" / "mmaudio_small_44k.pth"
VAE_CKPT     = ROOT / "models" / "ext_weights" / "v1-44.pth"
SYNC_CKPT    = ROOT / "models" / "ext_weights" / "synchformer_state_dict.pth"
BIGVGAN_16K  = None                    # 44k mode pulls BigVGAN v2 from the HF cache

# --- official sampler configuration (unchanged from demo.py) -----------------
SEED           = 42
NUM_STEPS      = 25
CFG_STRENGTH   = 4.5
INFERENCE_MODE = "euler"
MIN_SIGMA      = 0
DURATION       = 4.5                   # requested; load_video may truncate to frame budget
CLIP_BS_MULT   = 40                    # official generate() default
SYNC_BS_MULT   = 40                    # official generate() default

# --- precision policy (report SS F) -----------------------------------------
DEVICE          = "mps"
DTYPE_COND      = torch.bfloat16       # CLIP + Synchformer
DTYPE_DIFFUSION = torch.float32        # MMAudio net
DTYPE_DECODE    = torch.float32        # VAE decoder + BigVGAN
# float16 is explicitly forbidden for this experiment.
FORBIDDEN_DTYPES = (torch.float16,)

# --- prompts ----------------------------------------------------------------
PROMPT = ("Realistic close-up Foley of a person drinking water from a ceramic cup, with repeated "
          "natural sips, audible swallowing, wet mouth sounds, gentle breathing, and subtle "
          "cup-to-lips sounds. Clearly recognizable continuous human drinking.")
NEGATIVE = ("music, speech, talking, voice, footsteps, background ambience, room tone, "
            "cinematic effects, clicks, pops, electronic sounds, noise")

# --- artefact paths ---------------------------------------------------------
WORK      = ROOT / "work"
RESULTS   = ROOT / "results"
FEATURES  = WORK / "phase1_conditioning_v2.pt"
LATENT    = WORK / "phase2_latent_v2.pt"
WAV_OUT   = ROOT / "mmaudio" / "results" / "drinking_mmaudio_v2.wav"
GEN_JSON  = ROOT / "mmaudio" / "results" / "drinking_mmaudio_v2_generation.json"
ANA_JSON  = ROOT / "mmaudio" / "results" / "drinking_mmaudio_v2_analysis.json"
REPORT_MD = ROOT / "mmaudio" / "results" / "drinking_mmaudio_v2_report.md"


def model_config():
    """Build a ModelConfig with absolute paths. Does not mutate MMAudio's globals."""
    from mmaudio.eval_utils import ModelConfig
    return ModelConfig(model_name=VARIANT, model_path=NET_CKPT, vae_path=VAE_CKPT,
                       bigvgan_16k_path=BIGVGAN_16K, mode=MODE, synchformer_ckpt=SYNC_CKPT)


def check_module(mod, name, expect_dtype, expect_device="mps"):
    """Assert every parameter/buffer sits on the expected device and dtype."""
    dts, devs, n = set(), set(), 0
    for p in mod.parameters():
        dts.add(p.dtype); devs.add(p.device.type); n += p.numel()
    for b in mod.buffers():
        dts.add(b.dtype); devs.add(b.device.type)
    bad = [str(d) for d in dts if d in FORBIDDEN_DTYPES]
    assert not bad, f"{name}: forbidden dtype present: {bad}"
    floats = {d for d in dts if d.is_floating_point}
    assert floats <= {expect_dtype}, f"{name}: expected {expect_dtype}, found {floats}"
    assert devs <= {expect_device}, f"{name}: expected {expect_device}, found {devs}"
    return {"name": name, "params_M": round(n / 1e6, 2),
            "dtypes": sorted(str(d) for d in dts), "devices": sorted(devs)}
