// Deterministic performance check for job_processor::find_duplicates.
//
// This is a small, intentionally simple benchmark harness (not a general
// benchmarking library). It measures find_duplicates over a fixed,
// synthetic input with a warm-up phase and a small number of measured
// iterations, then reports the median measured duration in milliseconds.
//
// Design notes (see docs/architecture.md for the full tradeoff discussion):
//   - Fixed input size and fixed deterministic content (no RNG) so results
//     are reproducible across runs and runners.
//   - A warm-up iteration is run and discarded before measurement.
//   - The median of several measured iterations is used instead of the
//     minimum or mean, to reduce sensitivity to a single slow sample while
//     still being deterministic given a fixed input.
//   - The efficient (healthy) implementation and the intentionally
//     inefficient fixture implementation differ by roughly two orders of
//     magnitude on this input size, giving a conservative, noise-tolerant
//     separation between "healthy" and "regressed" without a fragile
//     microsecond-level threshold.
#include <algorithm>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <vector>

#include "job_processor.hpp"

namespace {

// Fixed, deterministic synthetic input: a repeating pattern over a range of
// values, large enough to make an O(n^2) implementation clearly observable,
// while small enough to keep the healthy O(n) implementation well under a
// second even on a modest runner.
std::vector<int> make_benchmark_input() {
    constexpr int kSize = 20000;
    constexpr int kDistinctValues = 5000; // guarantees duplicates exist
    std::vector<int> values;
    values.reserve(kSize);
    for (int i = 0; i < kSize; ++i) {
        values.push_back(i % kDistinctValues);
    }
    return values;
}

double run_once_ms(const std::vector<int>& input) {
    auto start = std::chrono::steady_clock::now();
    auto result = job_processor::find_duplicates(input);
    auto end = std::chrono::steady_clock::now();
    // Prevent the optimizer from eliding the call.
    if (result.size() == static_cast<size_t>(-1)) {
        std::printf("unreachable\n");
    }
    return std::chrono::duration<double, std::milli>(end - start).count();
}

double median(std::vector<double> values) {
    std::sort(values.begin(), values.end());
    return values[values.size() / 2];
}

} // namespace

int main() {
    const auto input = make_benchmark_input();

    constexpr int kWarmupIterations = 2;
    constexpr int kMeasuredIterations = 5;
    // Explicit, documented performance policy threshold (milliseconds).
    // The healthy O(n) implementation on the fixed input above typically
    // completes in a few milliseconds; the fixture's inefficient O(n^2)
    // implementation takes well over a second. This threshold is set far
    // above healthy performance and far below regressed performance to
    // give a conservative, noise-tolerant margin.
    constexpr double kThresholdMs = 200.0;

    for (int i = 0; i < kWarmupIterations; ++i) {
        run_once_ms(input);
    }

    std::vector<double> measurements;
    measurements.reserve(kMeasuredIterations);
    for (int i = 0; i < kMeasuredIterations; ++i) {
        measurements.push_back(run_once_ms(input));
    }

    const double median_ms = median(measurements);

    std::printf("benchmark=find_duplicates\n");
    std::printf("input_size=%zu\n", input.size());
    std::printf("warmup_iterations=%d\n", kWarmupIterations);
    std::printf("measured_iterations=%d\n", kMeasuredIterations);
    for (size_t i = 0; i < measurements.size(); ++i) {
        std::printf("measurement_ms[%zu]=%.3f\n", i, measurements[i]);
    }
    std::printf("median_ms=%.3f\n", median_ms);
    std::printf("threshold_ms=%.3f\n", kThresholdMs);

    if (median_ms > kThresholdMs) {
        std::printf("result=FAIL\n");
        return 1;
    }
    std::printf("result=PASS\n");
    return 0;
}
