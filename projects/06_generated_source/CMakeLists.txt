cmake_minimum_required(VERSION 3.20)
project(generated_source C)
add_executable(mkparse gen/mkparse.c)
add_custom_command(OUTPUT ${CMAKE_BINARY_DIR}/parse.c ${CMAKE_BINARY_DIR}/parse.h
                   COMMAND mkparse ${CMAKE_BINARY_DIR}/parse.c ${CMAKE_BINARY_DIR}/parse.h
                   DEPENDS mkparse)
add_executable(app main.c lexer.c ${CMAKE_BINARY_DIR}/parse.c)
target_include_directories(app PRIVATE ${CMAKE_BINARY_DIR})
