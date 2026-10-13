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
    // Efficient O(n) implementation: a single pass with a hash map tracking
    // how many times each value has been seen. A value is reported exactly
    // once, at the moment its *second* occurrence is observed, which gives
    // deterministic output ordering.
    std::unordered_map<int, int> seen_counts;
    seen_counts.reserve(values.size());

    std::vector<int> duplicates;
    for (int value : values) {
        int& count = seen_counts[value];
        ++count;
        if (count == 2) {
            duplicates.push_back(value);
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
    } else if (values.size() < 1000) {
        size_class = "large";
    } else {
        size_class = "huge";
    }

    bool all_same_value = std::all_of(
        values.begin(), values.end(),
        [&values](int v) { return v == values.front(); });

    out << "job(count=" << values.size()
        << ", min=" << min_value
        << ", max=" << max_value
        << ", size=" << size_class;
    if (all_same_value) {
        out << ", uniform=true";
    }
    out << ")";
    return out.str();
}

} // namespace job_processor
