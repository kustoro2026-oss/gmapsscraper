cmake_minimum_required(VERSION 3.14)
project(runner LANGUAGES CXX)

# Define the application target. To change its name, change BINARY_NAME in the
# top-level CMakeLists.txt, not the value here, or `flutter run` will no longer
# work.
#
# Any new source files that you add to the application should be added here.
add_executable(${BINARY_NAME} WIN32
  "flutter_window.cpp"
  "main.cpp"
  "utils.cpp"
  "win32_window.cpp"
  "${FLUTTER_MANAGED_DIR}/generated_plugin_registrant.cc"
  "Runner.rc"
  "runner.exe.manifest"
)

# Apply the standard set of build settings. This can be removed for applications
# that need different build settings.
apply_standard_settings(${BINARY_NAME})

# Add preprocessor definitions for the build version.
target_compile_definitions(${BINARY_NAME} PRIVATE "FLUTTER_VERSION=\"${FLUTTER_VERSION}\"")
target_compile_definitions(${BINARY_NAME} PRIVATE "FLUTTER_VERSION_MAJOR=${FLUTTER_VERSION_MAJOR}")
target_compile_definitions(${BINARY_NAME} PRIVATE "FLUTTER_VERSION_MINOR=${FLUTTER_VERSION_MINOR}")
target_compile_definitions(${BINARY_NAME} PRIVATE "FLUTTER_VERSION_PATCH=${FLUTTER_VERSION_PATCH}")
target_compile_definitions(${BINARY_NAME} PRIVATE "FLUTTER_VERSION_BUILD=${FLUTTER_VERSION_BUILD}")

# Disable Windows macros that collide with C++ standard library functions.
target_compile_definitions(${BINARY_NAME} PRIVATE "NOMINMAX")

# Add dependency libraries and include directories. Add any application-specific
# dependencies here.
target_link_libraries(${BINARY_NAME} PRIVATE flutter flutter_wrapper_app)
target_link_libraries(${BINARY_NAME} PRIVATE "dwmapi.lib")
target_include_directories(${BINARY_NAME} PRIVATE "${CMAKE_SOURCE_DIR}")

# Run the Flutter tool portions of the build. This must not be removed.
add_dependencies(${BINARY_NAME} flutter_assemble)

# ── Launcher (no CRT — always starts, checks VC++ Redist) ───────
# Strategy:
#   1. Flutter build produces gmaps_scraper_desktop.exe (needs VC++)
#   2. We build gmaps_launcher.exe (no CRT, always starts)
#   3. POST_BUILD: rename Flutter app → gmaps_app.exe (internal)
#                  rename launcher → gmaps_scraper_desktop.exe (user clicks)
add_executable(gmaps_launcher WIN32 "launcher.c" "launcher.rc")
target_link_libraries(gmaps_launcher PRIVATE kernel32.lib user32.lib shell32.lib)
target_compile_options(gmaps_launcher PRIVATE /O1 /GS-)
target_link_options(gmaps_launcher PRIVATE /NODEFAULTLIB /ENTRY:wWinMainCRTStartup /SUBSYSTEM:WINDOWS)
add_custom_command(TARGET gmaps_launcher POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E remove -f
        "$<TARGET_FILE_DIR:${BINARY_NAME}>/gmaps_app.exe"
    COMMAND ${CMAKE_COMMAND} -E rename
        "$<TARGET_FILE:${BINARY_NAME}>"
        "$<TARGET_FILE_DIR:${BINARY_NAME}>/gmaps_app.exe"
    COMMAND ${CMAKE_COMMAND} -E copy
        "$<TARGET_FILE:gmaps_launcher>"
        "$<TARGET_FILE_DIR:${BINARY_NAME}>/gmaps_scraper_desktop.exe"
    COMMAND ${CMAKE_COMMAND} -E remove -f
        "$<TARGET_FILE_DIR:${BINARY_NAME}>/gmaps_launcher.exe"
)
