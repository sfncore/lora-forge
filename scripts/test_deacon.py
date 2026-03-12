"""Quick inference test for the deacon LoRA adapter."""
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM
from peft import PeftModel

BASE = "Qwen/Qwen3.5-2B"
ADAPTER = "output/checkpoints/deacon-v1"

SYSTEM = """[GAS TOWN ROLE: deacon]
You are the Deacon, an autonomous patrol and coordination agent. You monitor system health, manage patrol cycles, dispatch work to polecats, and maintain the beads database. You operate without human prompting."""

print("Loading tokenizer...")
tokenizer = AutoTokenizer.from_pretrained(ADAPTER)

print("Loading base model (4-bit)...")
model = AutoModelForCausalLM.from_pretrained(
    BASE,
    load_in_4bit=True,
    device_map="auto",
    torch_dtype=torch.bfloat16,
)

print("Loading LoRA adapter...")
model = PeftModel.from_pretrained(model, ADAPTER)
model.eval()
print("Ready.\n")

def chat(user_msg, max_new_tokens=512):
    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": user_msg},
    ]
    text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = tokenizer(text, return_tensors="pt").to(model.device)
    with torch.no_grad():
        out = model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            temperature=0.7,
            do_sample=True,
            pad_token_id=tokenizer.eos_token_id,
        )
    response = tokenizer.decode(out[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)
    return response

# Test prompts that match training data patterns
tests = [
    "[GAS TOWN] deacon <- daemon • 2026-03-11T23:00 • patrol\n\nI am Deacon. Start patrol: run gt deacon heartbeat, then check gt hook.",
    "[GAS TOWN] deacon <- mayor • 2026-03-11T23:00 • wisp-compact\n\nRun wisp compaction cycle.",
]

for prompt in tests:
    print(f"PROMPT:\n{prompt}\n")
    print(f"RESPONSE:\n{chat(prompt)}\n")
    print("=" * 60 + "\n")
