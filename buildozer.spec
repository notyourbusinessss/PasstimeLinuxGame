# Builds the Android app (an APK):   buildozer android debug      (see "Android" in the README)
# The release workflow does this for every v* tag; you need Linux, Java 17 and a few GB of disk for the Android SDK/NDK.
[app]
title = Space Miner
package.name = spaceminer
package.domain = io.github.notyourbusinessss

source.dir = .
source.include_exts = py,png,ttf,txt
source.exclude_dirs = screenshots, tools, packaging, build, dist, bin, .github, .git, .buildozer, __pycache__
source.exclude_patterns = sim.py, calibrate.py

version.regex = __version__ = ['"](.*)['"]
version.filename = %(source.dir)s/version.py

# pygame 2.1.0 is what python-for-android builds (SDL2); Python 3.10
requirements = python3,pygame

icon.filename = %(source.dir)s/assets/icon-512.png
orientation = landscape
fullscreen = 1

# no permissions needed: the save file and the log live in the app's private folder
android.permissions =
android.api = 33
android.minapi = 21
android.ndk = 25b
android.archs = arm64-v8a, armeabi-v7a
android.accept_sdk_license = True
android.logcat_filters = *:S python:D

# a python-for-android release that is known to build pygame 2.1.0 with Python 3.10
p4a.branch = v2023.09.16

[buildozer]
log_level = 2
warn_on_root = 1
