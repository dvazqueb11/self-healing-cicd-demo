.PHONY: configure build test coverage benchmark automation-test public-check \
        validate-easy validate-medium validate-advanced \
        apply-easy apply-medium apply-advanced reset clean help \
        demo-pr-easy demo-pr-medium demo-pr-advanced

BUILD_DIR ?= build

help:
	@echo "Targets:"
	@echo "  configure          Configure CMake (coverage instrumentation on)"
	@echo "  build              Build the project"
	@echo "  test               Run all unit tests via ctest"
	@echo "  coverage           Measure line coverage and check the 95% threshold"
	@echo "  benchmark          Run the performance benchmark"
	@echo "  automation-test    Run the Python automation test suite"
	@echo "  public-check       Scan tracked files for secrets/internal references"
	@echo "  apply-easy         Apply the easy-unit-test demo fixture to the local working tree"
	@echo "  apply-medium       Apply the medium-low-coverage demo fixture to the local working tree"
	@echo "  apply-advanced     Apply the advanced-performance demo fixture to the local working tree"
	@echo "  reset SCENARIO=<id>  Revert the named fixture and clear .evidence/"
	@echo "  demo-pr-easy       Open a real demo pull request from the easy-unit-test fixture"
	@echo "  demo-pr-medium     Open a real demo pull request from the medium-low-coverage fixture"
	@echo "  demo-pr-advanced   Open a real demo pull request from the advanced-performance fixture"
	@echo "  validate-easy      Run the unit-test-remediation validator profile against .evidence/"
	@echo "  validate-medium    Run the coverage-remediation validator profile against .evidence/"
	@echo "  validate-advanced  Run the performance-remediation validator profile against .evidence/"
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

# Local working-tree fixture helpers (optional developer convenience; the
# live remediation workflow never applies fixtures -- see demo-pr-* below
# for the supported way to exercise the full PR-driven demo end to end).
apply-easy:
	python3 scripts/create_demo_failure.py easy-unit-test

apply-medium:
	python3 scripts/create_demo_failure.py medium-low-coverage

apply-advanced:
	python3 scripts/create_demo_failure.py advanced-performance

# Usage: make reset SCENARIO=easy-unit-test
reset:
	python3 scripts/reset_demo.py $(SCENARIO)

# Open a real developer branch/commit/pull request from a fixture, so CI
# genuinely fails and the self-heal-remediation workflow genuinely reacts.
demo-pr-easy:
	python3 scripts/demo_submit_pr.py easy-unit-test

demo-pr-medium:
	python3 scripts/demo_submit_pr.py medium-low-coverage

demo-pr-advanced:
	python3 scripts/demo_submit_pr.py advanced-performance

# These validate against whatever evidence/change is already on disk in
# .evidence/ and the current working tree (as the remediation workflow
# itself does) -- no --scenario is needed or accepted any more.
validate-easy:
	python3 scripts/validate_change.py --profile unit-test-remediation --build-dir $(BUILD_DIR)

validate-medium:
	python3 scripts/validate_change.py --profile coverage-remediation --build-dir $(BUILD_DIR)

validate-advanced:
	python3 scripts/validate_change.py --profile performance-remediation --build-dir $(BUILD_DIR)

clean:
	rm -rf $(BUILD_DIR)

