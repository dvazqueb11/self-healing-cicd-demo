#include "job_processor.hpp"
#include "test_framework.hpp"

using job_processor::calculate_average;
using job_processor::find_duplicates;
using job_processor::summarize_job;

// ---- calculate_average ----------------------------------------------

TEST_CASE("average_empty_input") {
    REQUIRE(calculate_average({}) == 0.0);
}

TEST_CASE("average_normal_input") {
    REQUIRE(calculate_average({10.0, 20.0, 30.0, 40.0}) == 25.0);
}

TEST_CASE("average_negative_values") {
    REQUIRE(calculate_average({-10.0, 10.0, -5.0}) == -5.0 / 3.0);
}

// ---- find_duplicates ---------------------------------------------------

TEST_CASE("duplicates_empty_input") {
    REQUIRE(find_duplicates({}).empty());
}

TEST_CASE("duplicates_no_duplicates") {
    REQUIRE(find_duplicates({1, 2, 3, 4}).empty());
}

TEST_CASE("duplicates_repeated_values") {
    auto result = find_duplicates({1, 2, 2, 3, 3, 3});
    REQUIRE_EQ(result.size(), 2u);
    REQUIRE(result[0] == 2);
    REQUIRE(result[1] == 3);
}

TEST_CASE("duplicates_deterministic_ordering") {
    // Duplicates must be reported in order of each value's *second*
    // occurrence, regardless of first-occurrence order. Here 1 appears
    // before 2 first, but 2's second occurrence happens before 1's, so
    // the expected output order is reversed relative to first occurrence.
    auto result = find_duplicates({1, 2, 2, 1});
    REQUIRE_EQ(result.size(), 2u);
    REQUIRE(result[0] == 2);
    REQUIRE(result[1] == 1);
}

// ---- summarize_job -------------------------------------------------------

TEST_CASE("summary_empty_input") {
    REQUIRE(summarize_job({}) == "job(count=0, empty)");
}

TEST_CASE("summary_small_job") {
    REQUIRE(summarize_job({3, 1, 4}) == "job(count=3, min=1, max=4, size=small)");
}

TEST_CASE("summary_medium_job") {
    std::vector<int> values(20, 7);
    values[0] = 1;
    values[1] = 99;
    REQUIRE(summarize_job(values) == "job(count=20, min=1, max=99, size=medium)");
}

TEST_CASE("summary_large_job") {
    std::vector<int> values(150, 5);
    values[0] = -3;
    values[1] = 42;
    REQUIRE(summarize_job(values) == "job(count=150, min=-3, max=42, size=large)");

    std::vector<int> huge(1000, 5);
    huge[0] = 1;
    REQUIRE(summarize_job(huge) == "job(count=1000, min=1, max=5, size=huge)");

    std::vector<int> uniform(3, 7);
    REQUIRE(summarize_job(uniform) == "job(count=3, min=7, max=7, size=small, uniform=true)");
}
