cmake_minimum_required(VERSION 3.20)
project(generated_header C)
add_executable(mkhash gen/mkhash.c)
add_custom_command(OUTPUT ${CMAKE_BINARY_DIR}/keywordhash.h
                   COMMAND mkhash ${CMAKE_BINARY_DIR}/keywordhash.h
                   DEPENDS mkhash)
add_executable(app main.c tokenize.c ${CMAKE_BINARY_DIR}/keywordhash.h)
target_include_directories(app PRIVATE ${CMAKE_BINARY_DIR})
