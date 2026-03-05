.PHONY: all extract transform validate validate-cli report stats clean rejection-lora

PYTHON ?= python3
OUTPUT_DIR ?= ../output/datasets

all: extract transform validate validate-cli report stats score

REJECTION_DIR ?= ../output/rejection_data
REJECTION_OUTPUT_DIR ?= ../output/datasets/rejection_lora

extract:
	cd .. && $(PYTHON) -m data.pipeline --step extract --output-dir $(OUTPUT_DIR)

transform:
	cd .. && $(PYTHON) -m data.pipeline --step transform --output-dir $(OUTPUT_DIR)

score:
	cd .. && $(PYTHON) -m data.pipeline --step all --output-dir $(OUTPUT_DIR)

validate:
	$(PYTHON) -m data.validate.schema $(OUTPUT_DIR)/gastown_train.jsonl

validate-cli:
	$(PYTHON) -m data.validate.cli_validator $(OUTPUT_DIR)/gastown_train.jsonl --report $(OUTPUT_DIR)/cli_validation.json

report:
	$(PYTHON) -m data.validate.reporter $(OUTPUT_DIR)/gastown_train.jsonl --output $(OUTPUT_DIR)/report.md --json $(OUTPUT_DIR)/report.json

stats:
	$(PYTHON) -m data.validate.stats $(OUTPUT_DIR)/gastown_train.jsonl

rejection-lora:
	cd .. && $(PYTHON) -m mayor.rig.training.rejection_to_lora --rejection-dir $(REJECTION_DIR) --general-dir $(OUTPUT_DIR) --output-dir $(REJECTION_OUTPUT_DIR) -v

clean:
	rm -rf $(OUTPUT_DIR)/*.jsonl $(OUTPUT_DIR)/prepared/
