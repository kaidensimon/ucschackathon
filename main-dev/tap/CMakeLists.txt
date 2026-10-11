cmake_minimum_required(VERSION 3.14)
project(council-actdump CXX C)

# Path to a llama.cpp source tree. It is built into this build directory; the tree is not modified.
set(LLAMA_CPP_DIR "$ENV{HOME}/llama.cpp" CACHE PATH "llama.cpp source tree")
set(LLAMA_BUILD_TESTS OFF CACHE BOOL "" FORCE)
set(LLAMA_BUILD_EXAMPLES OFF CACHE BOOL "" FORCE)
set(LLAMA_BUILD_TOOLS OFF CACHE BOOL "" FORCE)
set(LLAMA_BUILD_SERVER OFF CACHE BOOL "" FORCE)
set(LLAMA_CURL OFF CACHE BOOL "" FORCE)

add_subdirectory(${LLAMA_CPP_DIR} ${CMAKE_BINARY_DIR}/llama EXCLUDE_FROM_ALL)

add_executable(actdump actdump.cpp)
target_include_directories(actdump PRIVATE ${LLAMA_CPP_DIR}/vendor ${LLAMA_CPP_DIR}/ggml/include ${LLAMA_CPP_DIR}/include)
target_link_libraries(actdump PRIVATE llama ggml)
target_compile_features(actdump PRIVATE cxx_std_17)
