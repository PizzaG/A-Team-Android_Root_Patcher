## v1.0
- Initial Release v1.0

## v0.8
- Added Magisk and KernelSU engine version labels beneath their respective PATCHING METHOD buttons, sourced from `magisk_version` and `kernelsu_version` in `app/config/config.json`.
- Renamed the KernelSU selection button to **KERNEL-SU**.
- Reworked the top bar into a responsive three-column layout, centering the application title and subtitle between the A-Team logo and right-side actions at different window snap sizes.
- Added a matching lightning strike to the right side of **PATCH IMAGE**.
- Added a desktop-computer icon to **DESKTOP SHORTCUT** and package-install icons to both **ROOT MANAGER** install buttons.
- Added Magisk and KernelSU visual marks to the corresponding PATCHING METHOD buttons.
- Rewrote the main README with current v0.8 launch, patching, ADB manager-installation, update, version-config, shortcut, and troubleshooting instructions.
- Rewrote `PATCHER_ENGINES_README.md` to document the bundled Magisk and KernelSU host payloads, output handling, manager APKs, and ADB requirements.
- Updated the release manifest changelog to describe the v0.8 changes.
- Reduced the vertical padding and spacing inside **PATCHING METHOD** to reclaim space and help prevent an unnecessary scrollbar in shorter windows.
- Replaced the Magisk and KernelSU button marks with the supplied 148×148 images, preserving their dimensions and making the backgrounds transparent.
- Added a small amount of extra spacing between the computer icon and **DESKTOP SHORTCUT** text.

## v0.5
- Added official KernelSU v3.3.1 Linux and Windows x86-64 `ksud` host binaries.
- Fixed KernelSU output handling by staging the generated image and copying it to the requested output filename.
- Added a **ROOT MANAGER** panel beside **IMAGE SELECTION**, with ADB installation actions for Magisk Manager and KernelSU Manager.
- Added ADB device detection, authorized-device selection, target-device confirmation, and an interactive setup/retry prompt when no working ADB device is detected.
- Updated the application subtitle to **Cross-Platform Root Patching**.
- Fixed Linux desktop shortcut working-directory handling and centered **DESKTOP SHORTCUT** above **CHECK FOR UPDATE**.
- Separated update comparison version (`version`) from the displayed application version (`display`) in `app/config/config.json`.
- Updated the updater to compare the repository manifest `version` field against the local config `version` field; the footer displays `display`.
- Added first-run terminal setup guidance to the README for interactive dependency installation.

## v0.1
- Added the black/red cross-platform PySide6 interface with the application version displayed in the footer.
- Added modular Magisk and KernelSU engine selection and separate patched-image output with SHA256 verification.
- Preserved the supplied Magisk 31.1 ARM32/ARM64 patching payload and moved the Magisk manager APK to `app/managers/MagiskManager.apk`.
- Added `app/config/config.json` as the single source for the application version; the GUI and updater read the configured version.
- Added a **DESKTOP SHORTCUT** action that creates an application launcher on the desktop, runs the GUI without opening a terminal, and uses `app/images/ateam-root-patcher-icon.png` as its icon. The shortcut is named **A-Team Android Root Patcher**.
- Removed the application name from the operating-system title bar while retaining the in-app branding.
- Renamed **CHECK FOR UPDATES** to **CHECK FOR UPDATE**, **BOOT IMAGE SELECTION** to **IMAGE SELECTION**, and **OUTPUT AND SAFETY** to **PATCHED IMAGE OUTPUT**.
- Moved the engine documentation to the project root as `PATCHER_ENGINES_README.md`.
- Added the GitHub version-manifest check and full-package updater workflow.
- Added project-local virtual environments for Linux and Windows launchers, plus Linux Qt/XCB dependency detection and distribution-aware installation guidance.
- Kept application code, dependencies, root-solution engines, managers, configuration, logs, and internal resources under `app/`.
- Kept the operating-system application icon, A-Team branding, and approved red metallic Operation Log watermark assets.
- Made the main content vertically scrollable at compact window sizes to support Linux Cinnamon quarter-screen snapping.
- Routed worker-thread log messages through a Qt signal so patch workers update the UI safely on the GUI thread.
- Added persistent application, launcher, and faulthandler logs under `app/logs/`.
