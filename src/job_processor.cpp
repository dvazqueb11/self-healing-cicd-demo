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
    // NOTE: this is an intentionally inefficient O(n^2) implementation
    // used as a performance-regression fixture. It remains correct (and
    // preserves the original deterministic "report on second occurrence"
    // ordering) but does not scale: for each position it rescans all
    // prior positions to check whether the current value has been seen
    // before, and rescans the duplicates collected so far to avoid
    // reporting the same value twice.
    std::vector<int> duplicates;
    for (size_t i = 0; i < values.size(); ++i) {
        bool already_reported = false;
        for (size_t k = 0; k < duplicates.size(); ++k) {
            if (duplicates[k] == values[i]) {
                already_reported = true;
                break;
            }
        }
        if (already_reported) {
            continue;
        }

        bool seen_before = false;
        for (size_t j = 0; j < i; ++j) {
            if (values[j] == values[i]) {
                seen_before = true;
                break;
            }
        }
        if (seen_before) {
            duplicates.push_back(values[i]);
        }
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
