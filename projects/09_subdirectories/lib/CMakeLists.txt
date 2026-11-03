add_library(core STATIC core1.c core2.c)
target_include_directories(core PUBLIC ${CMAKE_CURRENT_SOURCE_DIR})
