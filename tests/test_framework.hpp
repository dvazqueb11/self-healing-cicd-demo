// Minimal, dependency-free unit test framework for this repository's demo
// application. This intentionally avoids pulling in an external test
// framework so the project has no network/vendoring dependency for CI.
//
// Usage:
//   TEST_CASE("name") { REQUIRE(expr); REQUIRE_EQ(a, b); }
//
// The resulting binary supports:
//   --list            list all registered test case names, one per line
//   --run <name>      run only the named test case
//   (no arguments)     run every registered test case
//
// Exit code is 0 if all executed tests passed, 1 otherwise. On failure,
// a line of the form:
//   FAIL <test-name> | <file>:<line> | <expression>
// is printed to stdout for each failed assertion, which the evidence
// collector script parses to produce a concise, normalized failure report.
#pragma once

#include <functional>
#include <iostream>
#include <string>
#include <vector>

namespace minitest {

struct TestCase {
    std::string name;
    std::function<void()> fn;
};

struct Failure {
    std::string test_name;
    std::string file;
    int line;
    std::string expression;
};

inline std::vector<TestCase>& registry() {
    static std::vector<TestCase> tests;
    return tests;
}

inline std::vector<Failure>& failures() {
    static std::vector<Failure> fails;
    return fails;
}

inline std::string& current_test_name() {
    static std::string name;
    return name;
}

struct Registrar {
    Registrar(const std::string& name, std::function<void()> fn) {
        registry().push_back(TestCase{name, std::move(fn)});
    }
};

inline void record_failure(const char* file, int line, const std::string& expr) {
    failures().push_back(Failure{current_test_name(), file, line, expr});
}

} // namespace minitest

#define MINITEST_CONCAT_INNER(a, b) a##b
#define MINITEST_CONCAT(a, b) MINITEST_CONCAT_INNER(a, b)

#define TEST_CASE(name)                                                      \
    static void MINITEST_CONCAT(minitest_fn_, __LINE__)();                   \
    static ::minitest::Registrar MINITEST_CONCAT(minitest_reg_, __LINE__)(   \
        name, MINITEST_CONCAT(minitest_fn_, __LINE__));                     \
    static void MINITEST_CONCAT(minitest_fn_, __LINE__)()

#define REQUIRE(expr)                                                        \
    do {                                                                     \
        if (!(expr)) {                                                      \
            ::minitest::record_failure(__FILE__, __LINE__, #expr);          \
        }                                                                    \
    } while (0)

#define REQUIRE_EQ(a, b) REQUIRE((a) == (b))
