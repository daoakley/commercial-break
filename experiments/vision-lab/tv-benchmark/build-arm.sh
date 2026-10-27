#!/bin/sh
# Run inside the isolated legacy-glibc toolchain container. No TV operations.
set -eu
src=${1:?ncnn source directory}
build=${2:?new build directory}
output=${3:?output library filename}
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cmake -S "$src" -B "$build" -G Ninja \
  -DCMAKE_SYSTEM_NAME=Linux -DCMAKE_SYSTEM_PROCESSOR=arm \
  -DCMAKE_C_COMPILER=arm-linux-gnueabi-gcc \
  -DCMAKE_CXX_COMPILER=arm-linux-gnueabi-g++ \
  -DCMAKE_C_FLAGS="-march=armv7-a -mfpu=neon -mfloat-abi=softfp" \
  -DCMAKE_CXX_FLAGS="-march=armv7-a -mfpu=neon -mfloat-abi=softfp" \
  -DCMAKE_BUILD_TYPE=Release -DNCNN_VULKAN=OFF -DNCNN_OPENMP=OFF \
  -DNCNN_BF16=OFF -DNCNN_INT8=OFF -DNCNN_RUNTIME_CPU=OFF \
  -DNCNN_ARM82=OFF -DNCNN_ARM84BF16=OFF \
  -DNCNN_BUILD_TOOLS=OFF -DNCNN_BUILD_EXAMPLES=OFF \
  -DNCNN_BUILD_BENCHMARK=OFF -DNCNN_BUILD_TESTS=OFF
cmake --build "$build" -- -j4
arm-linux-gnueabi-g++ -O3 -fPIC -shared -static-libstdc++ -static-libgcc \
  -march=armv7-a -mfpu=neon -mfloat-abi=softfp \
  -I"$src/src" -I"$build/src" "$here/bench.cpp" "$build/src/libncnn.a" \
  -pthread -ldl -o "$output"
