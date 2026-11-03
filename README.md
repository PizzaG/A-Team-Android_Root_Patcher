# A-Team Android Root Patcher

A cross-platform PySide6 GUI for patching Android boot images with Magisk or KernelSU, and installing the bundled root-manager APKs to an Android device over ADB.


## Launch

### Linux
**First run: launch from a terminal.** Initial setup may create the virtual environment, install Python dependencies, or request permission to install missing native Qt/system libraries. Those prompts need an interactive terminal.

```bash
chmod +x run-linux.sh
./run-linux.sh
```

Finish the setup and confirm the GUI opens successfully. After that, use the **A-Team Android Root Patcher** desktop shortcut to launch without a terminal.

The launcher creates `app/.venv`; Python packages are isolated from the system-managed Python environment. If the launcher reports missing Linux system packages, follow its distribution-specific instructions. For Mint/Ubuntu/Debian, common prerequisites include:

```bash
sudo apt update
sudo apt install python3-venv python3-full libxcb-cursor0
```

### Windows

Install Python 3.10+ and run `run-windows.bat` from Command Prompt or PowerShell for the first launch. Keep the terminal open while the virtual environment and dependencies are prepared. After a successful first launch, use the desktop shortcut.

Magisk patching on Windows requires Git for Windows/Git Bash and compatible Windows-host Magisk tools. KernelSU uses the bundled Windows `ksud.exe`.


## Main interface

### Patching method
Choose **MAGISK** or **KERNEL-SU** under **PATCHING METHOD**. The version labels beneath each button are read from `app/config/config.json`:

- `magisk_version`: displayed beneath MAGISK.
- `kernelsu_version`: displayed beneath KERNEL-SU.

### Image selection and patching
1. Select the root method.
2. Browse to the source image (`boot.img`, `init_boot.img`, `vendor_boot.img`, or another supported image).
3. Select the Magisk architecture when using Magisk. Enter a KernelSU KMI only when required by the target kernel.
4. Optionally choose a separate output path under **PATCHED IMAGE OUTPUT**.
5. Click **PATCH IMAGE** and review the operation log.

The original image is protected: the app writes a separate patched output. On success, it reports the output path and SHA-256 checksum.

KernelSU's `ksud` creates its output using its own generated filename. The application stages that output and copies it to the requested output path. A successful `ksud` run does not guarantee every image type or device kernel is supported. In particular, an `init_boot.img` without a kernel cannot be patched by a kernel-based workflow that requires a kernel.


## Root manager installation
The **ROOT MANAGER** panel installs the bundled manager APKs to a connected Android device:

- **Install - Magisk Manager** installs `app/managers/Magisk.apk`.
- **Install - Kernel-SU Manager** installs `app/managers/KernelSU.apk`.

Before installation:

1. Connect the Android device over USB.
2. Enable USB debugging in Developer options.
3. Connect to the computer and accept the device's USB debugging/RSA authorization prompt.
4. Ensure `adb devices` lists the device with status `device` (not `unauthorized` or `offline`).
5. Click the relevant install button and confirm the target device shown by the application.

If no authorized device is detected, installation pauses and the app asks you to connect the device and establish working ADB access. The retry action checks again; it does not bypass ADB authorization. If multiple devices are connected, choose the intended target before confirming.

The app uses the `adb` executable available in `PATH`. Install Android platform-tools and ensure `adb` is available from the terminal before using this feature.


## Desktop shortcut
Click **DESKTOP SHORTCUT** to create a launcher named **A-Team Android Root Patcher** using `app/images/ateam-root-patcher-icon.png`. It starts the GUI directly without opening a terminal. Run the platform launcher successfully once before creating the shortcut so `app/.venv` exists.


## Updating and version configuration
The local configuration is `app/config/config.json`:

```json
{
    "version": "2",
    "display": "1.0",
    "kernelsu_version": "3.3.1",
    "magisk_version": "31.1"
}
```

- `version` is the comparison value used by the updater.
- `display` is the version shown in the application footer.
- `kernelsu_version` and `magisk_version` are shown under the corresponding PATCHING METHOD buttons.

The updater compares the local `version` against the `version` field in the repository's `Updates/version.json`. The remote `display` value is the release's user-facing version. The update manifest also supplies the archive filename and changelog.

The release archive should contain the project root, including `app/`, launchers, documentation, and `Updates/`. The manifest and matching `.7z` release archive must be published to GitHub before online updating can succeed. When a newer version is found, the app asks whether to accept or decline it. If accepted, it downloads and extracts the 7z package, applies the update after the current process closes, and automatically relaunches the application. If declined, no package is downloaded. The updater uses `py7zr` (minimum 1.0.0) and can fall back to an installed 7-Zip command-line extractor.


## Project layout
```text
A-Team-Android_Root_Patcher/
├── run-linux.sh
├── run-windows.bat
├── README.md
├── PATCHER_ENGINES_README.md
├── CHANGELOG.md
├── Updates/version.json
└── app/
    ├── app.py
    ├── config/config.json
    ├── managers/
    │   ├── Magisk.apk
    │   └── KernelSU.apk
    ├── images/
    ├── logs/
    └── engines/
        ├── magisk/
        └── kernelsu/
            ├── linux/ksud
            └── windows/ksud.exe
```


## Logs and troubleshooting
Runtime logs are stored in `app/logs/`:

- `application.log` — application activity, patch output, ADB installation results, and Python exceptions.
- `faulthandler.log` — interpreter/thread diagnostics for fatal faults.
- `latest-launcher.log` — most recent Linux launcher output and exit status.

For a patching or startup problem, include the relevant logs and the exact image type being processed. For ADB installation problems, also include the output of `adb devices -l` (remove serial numbers if you do not want to share them).

See [PATCHER_ENGINES_README.md](PATCHER_ENGINES_README.md) for engine-specific payload and platform notes.
