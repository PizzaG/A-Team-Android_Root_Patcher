# Patcher engines

The patcher keeps each root solution isolated under `app/engines/`. The GUI selects an engine and calls its patch adapter; manager APK installation is a separate ADB workflow handled by the **ROOT MANAGER** panel.

## Magisk

- The bundled Magisk 31.1 patch payload is under `app/engines/magisk/32bit/` and `app/engines/magisk/64bit/`.
- The patch adapter stages the selected payload in a temporary working directory, runs `boot_patch.sh`, and copies the generated image to the requested output.
- The original input image is not overwritten.
- Windows currently requires Git for Windows/Git Bash and compatible Windows-host Magisk tools. Linux payload executables are not interchangeable with Windows binaries.

## KernelSU

- Linux host executable: `app/engines/kernelsu/linux/ksud`
- Windows host executable: `app/engines/kernelsu/windows/ksud.exe`
- Bundled host binaries are KernelSU v3.3.1 x86-64 builds.
- The adapter invokes `ksud boot-patch`, captures its output, stages the generated image in a temporary directory, and copies that image to the output path selected in the GUI.
- The optional KMI field is passed through to `ksud` when supplied.

These are desktop-host `ksud` executables, not Android-device `ksud` or `ksuinit` binaries. KernelSU patching depends on the image containing a compatible kernel and on the device's kernel/KMI and installation mode. A ramdisk-only `init_boot.img` with no kernel is not a valid kernel input for a patch operation that needs to embed the KernelSU LKM. Always verify image type and device compatibility before flashing.

## Manager APKs and ADB

The GUI's manager installer is not part of the patch engine interface. It installs:

- `app/managers/Magisk.apk`
- `app/managers/KernelSU.apk`

The installer requires the Android platform-tools `adb` executable on `PATH`, an authorized connected device, and explicit target-device confirmation. It does not bypass USB debugging authorization.

## Adding or updating an engine

Keep host-specific executables in clearly named platform folders. Verify upstream provenance and SHA-256 checksums before replacing bundled binaries. Update the corresponding version in `app/config/config.json`, refresh the user-facing documentation, and record the change under the current version heading in `CHANGELOG.md`.
