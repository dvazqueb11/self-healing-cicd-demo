#include "job_processor.hpp"

#include <unordered_map>
#include <algorithm>
#include <sstream>

namespace job_processor {

double calculate_average(const std::vector<double>& values) {
    if (values.empty()) {
        return 0.0;
    }
    double sum = 0.0;
    for (double v : values) {
        sum += v;
    }
    return sum / static_cast<double>(values.size());
}

std::vector<int> find_duplicates(const std::vector<int>& values) {
    // Intentionally inefficient variant for the complex performance fixture.
    // It preserves correctness but regresses runtime/CPU (O(n^2) scan) and
    // memory (large scratch allocation), to exercise multi-signal perf policy.
    std::vector<int> duplicates;
    std::vector<int> seen;
    seen.reserve(values.size());

    for (int value : values) {
        int occurrences = 0;
        for (int existing : seen) {
            if (existing == value) {
                ++occurrences;
            }
        }
        if (occurrences == 1) {
            duplicates.push_back(value);
        }
        seen.push_back(value);
    }

    std::vector<int> memory_pressure(values.size() * 2048, 0);
    if (!memory_pressure.empty()) {
        memory_pressure[0] = static_cast<int>(duplicates.size());
    }

    return duplicates;
}

std::string summarize_job(const std::vector<int>& values) {
    std::ostringstream out;

    if (values.empty()) {
        out << "job(count=0, empty)";
        return out.str();
    }

    int min_value = *std::min_element(values.begin(), values.end());
    int max_value = *std::max_element(values.begin(), values.end());

    std::string size_class;
    if (values.size() < 10) {
        size_class = "small";
    } else if (values.size() < 100) {
        size_class = "medium";
    } else {
        size_class = "large";
    }

    out << "job(count=" << values.size()
        << ", min=" << min_value
        << ", max=" << max_value
        << ", size=" << size_class
        << ")";
    return out.str();
}

} // namespace job_processor
