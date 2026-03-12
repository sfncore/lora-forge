import sys, json, torch
from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig
from peft import PeftModel
from pathlib import Path

ADAPTER = str(Path(__file__).parent.parent / "output/checkpoints/deacon-v3")
PROMPTS = str(Path(__file__).parent.parent / "data/transform/gt_prime_prompts.json")

_model = None
_tok = None

def load():
    global _model, _tok
    if _model is not None:
        return
    _tok = AutoTokenizer.from_pretrained("Qwen/Qwen3.5-2B")
    bnb = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_compute_dtype=torch.bfloat16)
    base = AutoModelForCausalLM.from_pretrained("Qwen/Qwen3.5-2B", quantization_config=bnb, device_map="auto")
    _model = PeftModel.from_pretrained(base, ADAPTER)
    _model.eval()

def call_api(prompt, options, context):
    load()
    system = json.loads(Path(PROMPTS).read_text())["deacon"]
    messages = [{"role": "system", "content": system}, {"role": "user", "content": prompt}]
    text = _tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = _tok(text, return_tensors="pt").to(_model.device)
    with torch.no_grad():
        out = _model.generate(**inputs, max_new_tokens=300, do_sample=False, pad_token_id=_tok.eos_token_id)
    new_tokens = out[0][inputs["input_ids"].shape[1]:]
    response = _tok.decode(new_tokens, skip_special_tokens=True).strip()
    return {"output": response}
