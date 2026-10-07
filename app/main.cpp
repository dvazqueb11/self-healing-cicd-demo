// Engineering Job Processor - CLI demo entry point.
//
// This is a minimal command-line front end for the job_processor library.
// It exists to make the library runnable/demoable; the unit tests are the
// source of truth for correctness.
#include <iostream>
#include <vector>

#include "job_processor.hpp"

int main() {
    std::vector<double> averages_input{10.0, 20.0, 30.0, 40.0};
    std::vector<int> duplicates_input{1, 2, 2, 3, 4, 4, 4, 5};
    std::vector<int> summary_input{3, 1, 4, 1, 5, 9, 2, 6};

    std::cout << "Engineering Job Processor (demo)\n";
    std::cout << "average = " << job_processor::calculate_average(averages_input) << "\n";

    std::cout << "duplicates =";
    for (int d : job_processor::find_duplicates(duplicates_input)) {
        std::cout << " " << d;
    }
    std::cout << "\n";

    std::cout << "summary = " << job_processor::summarize_job(summary_input) << "\n";
    return 0;
}
