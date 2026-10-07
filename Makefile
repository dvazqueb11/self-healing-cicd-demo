.PHONY: configure build test coverage benchmark automation-test public-check \
        validate-easy validate-medium validate-advanced \
        apply-easy apply-medium apply-advanced reset clean help

BUILD_DIR ?= build

help:
	@echo "Targets:"
	@echo "  configure          Configure CMake (coverage instrumentation on)"
	@echo "  build              Build the project"
	@echo "  test               Run all unit tests via ctest"
	@echo "  coverage           Measure line coverage and check the 95% threshold"
	@echo "  benchmark          Run the performance benchmark"
	@echo "  automation-test    Run the Python automation test suite (40 tests)"
	@echo "  public-check       Scan tracked files for secrets/internal references"
	@echo "  apply-easy         Apply the easy-unit-test demo fixture"
	@echo "  apply-medium       Apply the medium-low-coverage demo fixture"
	@echo "  apply-advanced     Apply the advanced-performance demo fixture"
	@echo "  reset SCENARIO=<id>  Revert the named fixture and clear .evidence/"
	@echo "  validate-easy      Run the unit-test-remediation validator profile"
	@echo "  validate-medium    Run the coverage-remediation validator profile"
	@echo "  validate-advanced  Run the performance-remediation validator profile"
	@echo "  clean              Remove the build directory"

configure:
	cmake -S . -B $(BUILD_DIR) -DENABLE_COVERAGE=ON -DCMAKE_BUILD_TYPE=Debug

build: configure
	cmake --build $(BUILD_DIR) -j 4

test: build
	ctest --test-dir $(BUILD_DIR) --output-on-failure -E performance_policy

coverage: build
	ctest --test-dir $(BUILD_DIR) --output-on-failure -E performance_policy
	python3 scripts/measure_coverage.py --build-dir $(BUILD_DIR) --threshold 95 \
		--output $(BUILD_DIR)/coverage.json
	@cat $(BUILD_DIR)/coverage.json

benchmark: build
	./$(BUILD_DIR)/performance_check

automation-test:
	python3 tests/automation/run_all.py

public-check:
	python3 scripts/check_public_repo.py

apply-easy:
	python3 scripts/create_demo_failure.py easy-unit-test

apply-medium:
	python3 scripts/create_demo_failure.py medium-low-coverage

apply-advanced:
	python3 scripts/create_demo_failure.py advanced-performance

# Usage: make reset SCENARIO=easy-unit-test
reset:
	python3 scripts/reset_demo.py $(SCENARIO)

validate-easy:
	python3 scripts/validate_change.py --profile unit-test-remediation --scenario easy-unit-test --build-dir $(BUILD_DIR)

validate-medium:
	python3 scripts/validate_change.py --profile coverage-remediation --scenario medium-low-coverage --build-dir $(BUILD_DIR)

validate-advanced:
	python3 scripts/validate_change.py --profile performance-remediation --scenario advanced-performance --build-dir $(BUILD_DIR)

clean:
	rm -rf $(BUILD_DIR)
