cmake_minimum_required(VERSION 3.20)
project(precompiled_header C)
add_executable(app main.c p1.c p2.c)
target_precompile_headers(app PRIVATE common.h)
