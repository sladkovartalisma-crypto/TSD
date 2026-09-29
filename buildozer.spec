[app]
# (str) Title of your application
title = BeerAggregation

# (str) Package name
package.name = beeragg

# (str) Package domain (needed for android/ios packaging)
package.domain = com.beeragg

# (str) Source code where the main.py live
source.dir = .

# (list) Source files to include (let empty to include all the files)
source.include_exts = py,png,jpg,kv,atlas,txt,wav

# (list) Source files to exclude (let empty to not exclude anything)
source.exclude_dirs = bin, venv, __pycache__, .git, .github, .claude, output, report

# (list) Glob patterns of files to exclude (резервная копия и тесты в APK не нужны)
source.exclude_patterns = *копия*, test_*.py, *.pyc, *.log

# (str) Application versioning (method 1)
version = 0.2

# (list) Application requirements
# Kivy, pyjnius (доступ к Android API), plyer (вибрация)
requirements = python3,kivy,pyjnius,plyer

# (str) Orientation (portrait|landscape)
orientation = portrait

# (bool) Indicate if the application should be fullscreen or not
fullscreen = 0

# ---------- Android ----------
android.permissions = MANAGE_EXTERNAL_STORAGE,READ_EXTERNAL_STORAGE,WRITE_EXTERNAL_STORAGE,VIBRATE
android.api = 31
android.minapi = 24
android.archs = arm64-v8a

# ---------- Сборка ----------
android.ndk_api = 24

# Автоматически принимать лицензии Android SDK (нужно для сборки без человека)
android.accept_sdk_license = True

[buildozer]
# (int) Log level (0 = error only, 1 = info, 2 = debug)
log_level = 1

# (int) Maximum number of concurrent log lines
log_max_lines = 10000
