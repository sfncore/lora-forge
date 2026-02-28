.PHONY: all extract transform validate validate-cli report stats clean

PYTHON ?= python3
OUTPUT_DIR ?= ../output/datasets

all: extract transform validate validate-cli report stats score

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

clean:
	rm -rf $(OUTPUT_DIR)/*.jsonl $(OUTPUT_DIR)/prepared/
