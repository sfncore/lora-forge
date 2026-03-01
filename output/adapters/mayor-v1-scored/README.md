# Mayor LoRA Adapter v1 (Scored)

Trained on scored mayor dataset from D.1.

## Training Configuration
- Model: Qwen/Qwen2.5-7B-Instruct
- Adapter: QLoRA (r=64, alpha=128)
- Epochs: 3
- Learning Rate: 2e-4 (cosine scheduler)
- Batch Size: 8 (micro_batch_size=2, gradient_accumulation_steps=4)
- Sequence Length: 4096

## Dataset
- Training: output/datasets/mayor_train.jsonl (14,192,322 bytes)
- Validation: output/datasets/mayor_val.jsonl (created from first 1000 training samples)

## Training Metrics
- Final Loss: [To be recorded after training]
- Duration: [To be recorded after training]
- Hardware: [To be recorded - RunPod A100/L40S]

## Usage
This adapter can be loaded with the base model for inference:
```python
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel

base_model = "Qwen/Qwen2.5-7B-Instruct"
adapter_path = "output/adapters/mayor-v1-scored/"

tokenizer = AutoTokenizer.from_pretrained(base_model)
model = AutoModelForCausalLM.from_pretrained(base_model, load_in_4bit=True)
model = PeftModel.from_pretrained(model, adapter_path)
```