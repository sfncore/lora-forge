.PHONY: all extract transform validate stats clean

PYTHON ?= python3
OUTPUT_DIR ?= ../output/datasets

all: extract transform validate stats

extract:
	$(PYTHON) -m data.pipeline --step extract --output-dir $(OUTPUT_DIR)

transform:
	$(PYTHON) -m data.pipeline --step transform --output-dir $(OUTPUT_DIR)

validate:
	$(PYTHON) -m data.validate.schema $(OUTPUT_DIR)/gastown_train.jsonl

stats:
	$(PYTHON) -m data.validate.stats $(OUTPUT_DIR)/gastown_train.jsonl

clean:
	rm -rf $(OUTPUT_DIR)/*.jsonl $(OUTPUT_DIR)/prepared/
