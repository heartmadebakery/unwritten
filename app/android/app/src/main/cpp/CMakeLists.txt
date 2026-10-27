cmake_minimum_required(VERSION 3.22.1)

project(uwcore)

add_library(uwcore SHARED
        uwcore.cpp
        jni_bridge.cpp)

find_library(log-lib log)
find_library(aaudio-lib aaudio)

target_link_libraries(uwcore
        ${log-lib}
        ${aaudio-lib})

target_compile_features(uwcore PRIVATE cxx_std_17)
