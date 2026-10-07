// Test runner entry point. See test_framework.hpp for the supported
// command-line interface (--list, --run <name>, or run everything).
#include "test_framework.hpp"

#include <cstring>
#include <iostream>

int main(int argc, char** argv) {
    using namespace minitest;

    std::string only_name;
    bool list_only = false;

    for (int i = 1; i < argc; ++i) {
        if (std::strcmp(argv[i], "--list") == 0) {
            list_only = true;
        } else if (std::strcmp(argv[i], "--run") == 0 && i + 1 < argc) {
            only_name = argv[++i];
        }
    }

    if (list_only) {
        for (const auto& t : registry()) {
            std::cout << t.name << "\n";
        }
        return 0;
    }

    int executed = 0;
    for (auto& t : registry()) {
        if (!only_name.empty() && t.name != only_name) {
            continue;
        }
        current_test_name() = t.name;
        t.fn();
        ++executed;
    }

    if (!only_name.empty() && executed == 0) {
        std::cerr << "No such test: " << only_name << "\n";
        return 1;
    }

    if (!failures().empty()) {
        for (const auto& f : failures()) {
            std::cout << "FAIL " << f.test_name << " | " << f.file << ":" << f.line
                       << " | " << f.expression << "\n";
        }
        std::cout << executed - static_cast<int>(failures().size())
                   << "/" << executed << " tests passed\n";
        return 1;
    }

    std::cout << executed << "/" << executed << " tests passed\n";
    return 0;
}
