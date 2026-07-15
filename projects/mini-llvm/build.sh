#!/bin/bash
# 一鍵編譯 mini.cpp（用 llvm-config 拿正確的 include/lib 旗標）
set -e
LLVM=/usr/lib/llvm-20/bin/llvm-config
g++ -std=c++17 mini.cpp -o mini \
    $($LLVM --cxxflags --ldflags --libs core) $($LLVM --system-libs)
echo "build OK → ./mini program.mini"
