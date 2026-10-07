// Engineering Job Processor
//
// Small, intentionally simple C++17 library used as the demo application
// for the self-healing CI/CD framework in this repository. The functions
// below process collections of numeric "engineering job" results.
//
// This code is illustrative only and is NOT intended for production use.
#pragma once

#include <string>
#include <vector>

namespace job_processor {

// Returns the arithmetic mean of `values`.
//
// - Empty input returns 0.0 (documented, deterministic behavior; there is
//   no "undefined" average for an empty job set in this demo).
// - Negative values are valid (e.g. a job score representing a deviation
//   from a baseline) and are included in the average like any other value.
double calculate_average(const std::vector<double>& values);

// Returns the values that occur more than once in `values`, with each
// duplicate reported exactly once.
//
// Ordering is deterministic: duplicates are returned in the order their
// *second* occurrence appears in the input.
std::vector<int> find_duplicates(const std::vector<int>& values);

// Returns a short, human-readable summary of a job's integer results.
//
// The summary always reports the count and, for non-empty input, the
// minimum and maximum values. Jobs are classified by size as "small"
// (fewer than 10 results), "medium" (10-99 results), or "large"
// (100 or more results); this classification is included in the summary.
std::string summarize_job(const std::vector<int>& values);

} // namespace job_processor
