cmake_minimum_required(VERSION 3.20)
project(custom_target_postbuild C)
add_executable(app main.c x.c y.c)
add_custom_command(TARGET app POST_BUILD
                   COMMAND ${CMAKE_COMMAND} -E copy $<TARGET_FILE:app> ${CMAKE_BINARY_DIR}/app_copy.exe)
add_custom_target(banner ALL COMMAND ${CMAKE_COMMAND} -E echo "banner target ran" VERBATIM)
