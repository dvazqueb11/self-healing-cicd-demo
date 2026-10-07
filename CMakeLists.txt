cmake_minimum_required(VERSION 3.16)
project(engineering_job_processor CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

if(NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE Debug)
endif()

option(ENABLE_COVERAGE "Build with gcov coverage instrumentation" OFF)

add_library(job_processor src/job_processor.cpp)
target_include_directories(job_processor PUBLIC include)

if(ENABLE_COVERAGE)
    target_compile_options(job_processor PUBLIC --coverage -O0 -g)
    target_link_options(job_processor PUBLIC --coverage)
endif()

add_executable(job_processor_app app/main.cpp)
target_link_libraries(job_processor_app PRIVATE job_processor)

add_executable(job_processor_tests tests/test_main.cpp tests/job_processor_tests.cpp)
target_link_libraries(job_processor_tests PRIVATE job_processor)
target_include_directories(job_processor_tests PRIVATE tests)

add_executable(performance_check benchmarks/performance_check.cpp)
target_link_libraries(performance_check PRIVATE job_processor)

enable_testing()

# Each unit test case is registered individually with CTest (rather than
# running the whole suite as a single CTest test) so that a single failing
# test can be identified precisely by name, which the evidence collector
# relies on for the "easy-unit-test" scenario.
set(JOB_PROCESSOR_TEST_NAMES
    average_empty_input
    average_normal_input
    average_negative_values
    duplicates_empty_input
    duplicates_no_duplicates
    duplicates_repeated_values
    duplicates_deterministic_ordering
    summary_empty_input
    summary_small_job
    summary_medium_job
    summary_large_job
)

foreach(test_name ${JOB_PROCESSOR_TEST_NAMES})
    add_test(NAME ${test_name} COMMAND job_processor_tests --run ${test_name})
endforeach()

add_test(NAME performance_policy COMMAND performance_check)
