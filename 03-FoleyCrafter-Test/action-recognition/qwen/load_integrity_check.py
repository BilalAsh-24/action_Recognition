"""Step 6 load-integrity check for Qwen2.5-VL-3B-Instruct. No inference, no MPS move."""
import time, torch, psutil, transformers
from transformers import Qwen2_5_VLForConditionalGeneration, AutoConfig

MODEL = "Qwen/Qwen2.5-VL-3B-Instruct"
def mem(tag):
    vm, sw = psutil.virtual_memory(), psutil.swap_memory()
    print(f"[MEM] {tag:28s} used={vm.used/1e9:6.2f}GB avail={vm.available/1e9:5.2f}GB "
          f"pct={vm.percent:5.1f}% swap={sw.used/1e9:5.2f}GB")
    return vm.used/1e9, sw.used/1e9

print(f"transformers={transformers.__version__} torch={torch.__version__}")
mem("baseline")

t0 = time.time()
model, info = Qwen2_5_VLForConditionalGeneration.from_pretrained(
    MODEL, dtype=torch.bfloat16, output_loading_info=True,
)
load_s = time.time() - t0
peak_used, peak_swap = mem("after load (CPU)")

print("\n=== 8/9: LOADING DIAGNOSTICS ===")
for k in ("missing_keys", "unexpected_keys", "mismatched_keys", "error_msgs"):
    v = info.get(k, [])
    print(f"   {k:16s}: {len(v)}  {'' if not v else v[:5]}")
ok = all(len(info.get(k, [])) == 0 for k in ("missing_keys","unexpected_keys","mismatched_keys","error_msgs"))
print(f"   ALL FOUR EMPTY -> CHECKPOINT VALID: {ok}")

print("\n=== 10: parameter count ===")
total = sum(p.numel() for p in model.parameters())
vis = sum(p.numel() for n,p in model.named_parameters() if "visual" in n)
print(f"   total parameters:  {total:,}  ({total/1e9:.3f} B)")
print(f"   vision encoder:    {vis:,}  ({vis/1e9:.3f} B)")
print(f"   language+other:    {total-vis:,}  ({(total-vis)/1e9:.3f} B)")

print("\n=== 12: dtype ===")
dts = {}
for _, p in model.named_parameters():
    dts[str(p.dtype)] = dts.get(str(p.dtype), 0) + 1
print(f"   parameter dtypes: {dts}")
print(f"   config dtype:     {getattr(model.config,'dtype',None) or getattr(model.config,'torch_dtype',None)}")
print(f"   devices:          {set(str(p.device) for p in model.parameters())}")

print("\n=== 11: config identity ===")
c = model.config
print(f"   model_type: {c.model_type} | class: {type(model).__name__}")
tc = getattr(c, "text_config", c)
print(f"   text: hidden={getattr(tc,'hidden_size',None)} layers={getattr(tc,'num_hidden_layers',None)} "
      f"heads={getattr(tc,'num_attention_heads',None)} kv_heads={getattr(tc,'num_key_value_heads',None)}")

print(f"\n   load time: {load_s:.1f}s | peak used {peak_used:.2f}GB | swap {peak_swap:.2f}GB")
print("RESULT:", "LOAD_INTEGRITY_PASS" if ok else "LOAD_INTEGRITY_FAIL")
