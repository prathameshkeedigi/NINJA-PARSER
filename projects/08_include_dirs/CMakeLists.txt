cmake_minimum_required(VERSION 3.20)
project(include_dirs C)
add_executable(app src/main.c src/alpha.c src/beta.c)
target_include_directories(app PRIVATE include/alpha include/beta)
