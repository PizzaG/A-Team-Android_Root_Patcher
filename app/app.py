#!/usr/bin/env python3
from __future__ import annotations
import hashlib, json, os, platform, shutil, subprocess, sys, tempfile, re
from datetime import datetime
from pathlib import Path
import requests
from PySide6.QtCore import QThread, Signal, Qt, QSize, qInstallMessageHandler
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import *

APP_NAME = "A-Team Android Root Patcher"
ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parent
CONFIG_FILE = ROOT / "config" / "config.json"
try:
    APP_CONFIG = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    VERSION = str(APP_CONFIG["version"]).strip()
    DISPLAY_VERSION = str(APP_CONFIG["display"]).strip()
    if not VERSION or not DISPLAY_VERSION:
        raise ValueError("The version and display fields must both be non-empty.")
except Exception as exc:
    raise RuntimeError(f"Unable to load application version from {CONFIG_FILE}: {exc}") from exc
VERSION_URL = "https://raw.githubusercontent.com/PizzaG/A-Team-Android_Root_Patcher/main/Updates/version.json"
LOG_DIR = ROOT / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "application.log"

import logging
import faulthandler
import traceback

LOGGER = logging.getLogger("ateam_root_patcher")
LOGGER.setLevel(logging.DEBUG)
if not LOGGER.handlers:
    _handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    _handler.setFormatter(logging.Formatter(
        "%(asctime)s | %(levelname)s | %(threadName)s | %(message)s"
    ))
    LOGGER.addHandler(_handler)
    LOGGER.propagate = False

_FAULT_LOG = (LOG_DIR / "faulthandler.log").open("a", encoding="utf-8", buffering=1)
_FAULT_LOG.write(f"\\n===== {datetime.now().isoformat(timespec='seconds')} | {APP_NAME} v{VERSION} | PID {os.getpid()} =====\\n")
_FAULT_LOG.flush()
faulthandler.enable(file=_FAULT_LOG, all_threads=True)

def _uncaught_exception(exc_type, exc_value, exc_tb):
    LOGGER.critical("Uncaught main-thread exception",
                    exc_info=(exc_type, exc_value, exc_tb))
    sys.__excepthook__(exc_type, exc_value, exc_tb)

sys.excepthook = _uncaught_exception
LOGGER.info("Application startup; root=%s", ROOT)

def file_hash(path):
    digest=hashlib.sha256()
    with open(path,"rb") as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b""):
            digest.update(chunk)
    return digest.hexdigest()

class Job(QThread):
    completed=Signal(bool,str)
    def __init__(self, task):
        super().__init__()
        self.task=task
    def run(self):
        try:
            self.completed.emit(True,str(self.task()))
        except Exception as exc:
            self.completed.emit(False,str(exc))

class MagiskEngine:
    def patch(self, image, output, arch, log):
        payload=ROOT/"engines"/"magisk"/arch
        required=("boot_patch.sh","util_functions.sh","magiskboot","magisk","magiskinit","init-ld")
        missing=[name for name in required if not (payload/name).is_file()]
        if missing:
            raise RuntimeError("Magisk payload incomplete: "+", ".join(missing))
        with tempfile.TemporaryDirectory(prefix="ateam-magisk-") as temp:
            work=Path(temp)
            for item in payload.iterdir():
                if item.is_file():
                    shutil.copy2(item,work/item.name)
            if os.name=="nt":
                shell=shutil.which("bash")
                if not shell:
                    raise RuntimeError("Windows requires Git Bash for the supplied Magisk shell patcher. Install Git for Windows first.")
                command=[shell,str(work/"boot_patch.sh"),str(image.resolve())]
            else:
                for item in work.iterdir():
                    if item.is_file() and item.name not in ("boot_patch.sh","util_functions.sh","stub.apk"):
                        item.chmod(0o755)
                shell=shutil.which("bash") or shutil.which("sh")
                if not shell:
                    raise RuntimeError("No POSIX shell found.")
                command=[shell,str(work/"boot_patch.sh"),str(image.resolve())]
            env=os.environ.copy()
            env.update({"BOOTMODE":"false","KEEPVERITY":"false","KEEPFORCEENCRYPT":"false",
                        "PATCHVBMETAFLAG":"false","RECOVERYMODE":"false","LEGACYSAR":"false"})
            process=subprocess.Popen(command,cwd=work,env=env,stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT,text=True,errors="replace")
            for line in process.stdout:
                log(line.rstrip())
            code=process.wait()
            patched=work/"new-boot.img"
            if code!=0 or not patched.is_file() or patched.stat().st_size==0:
                raise RuntimeError(f"Magisk patch failed (exit {code}); original image was not changed.")
            output.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(patched,output)
        return output

class KernelSUEngine:
    def patch(self,image,output,kmi,log):
        host="windows" if os.name=="nt" else "linux"
        executable=ROOT/"engines"/"kernelsu"/host/("ksud.exe" if host=="windows" else "ksud")
        if not executable.is_file():
            raise RuntimeError(f"Add a verified {host} ksud binary to {executable.parent}.")
        output.parent.mkdir(parents=True,exist_ok=True)
        # ksud chooses its own generated filename inside the --out directory.
        # Stage it in a fresh directory, then copy it to the user's requested path.
        with tempfile.TemporaryDirectory(prefix="ateam-kernelsu-") as temp_dir:
            staged_dir=Path(temp_dir)
            command=[str(executable),"boot-patch","-b",str(image.resolve()),"--out",str(staged_dir)]
            if kmi.strip():
                command.extend(["--kmi",kmi.strip()])
            process=subprocess.Popen(command,cwd=executable.parent,stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT,text=True,errors="replace")
            reported_output=None
            for line in process.stdout:
                clean=line.rstrip()
                log(clean)
                if clean.strip().startswith("/") and clean.strip().lower().endswith((".img",".bin")):
                    candidate=Path(clean.strip())
                    if candidate.is_file():
                        reported_output=candidate
            code=process.wait()
            if code:
                raise RuntimeError(f"ksud exited with code {code}.")
            if reported_output is None:
                candidates=[p for p in staged_dir.iterdir() if p.is_file() and p.suffix.lower() in (".img",".bin") and p.stat().st_size>0]
                if len(candidates)==1:
                    reported_output=candidates[0]
            if reported_output is None or not reported_output.is_file() or reported_output.stat().st_size==0:
                raise RuntimeError("ksud completed but no non-empty output image was found in its staging directory.")
            shutil.copy2(reported_output,output)
            log(f"Staged KernelSU image copied to requested output: {output}")
        return output


def _friendly_error(exc):
    """Render subprocess/decoder errors without Python's bytes repr (for example b'\\n')."""
    def clean(value):
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace").strip()
        if isinstance(value, (tuple, list)):
            return "; ".join(part for part in (clean(item) for item in value) if part)
        return str(value).strip()
    return clean(exc) or exc.__class__.__name__


class UpdateCheckJob(QThread):
    available = Signal(str, str, str)
    completed = Signal(bool, str)

    def run(self):
        try:
            response = requests.get(VERSION_URL, timeout=25)
            response.raise_for_status()
            manifest = response.json()
            version = str(manifest.get("version", "")).strip()
            filename = str(manifest.get("file", "")).strip()
            display = str(manifest.get("display", "")).strip()
            if not version or not filename or not display:
                raise RuntimeError("The update manifest is missing version, display, or file.")
            if not filename.lower().endswith(".7z"):
                raise RuntimeError("The release manifest must point to a .7z application package.")
            if version == VERSION:
                self.completed.emit(True, f"Already running the latest version ({display}).")
                return
            self.available.emit(version, display, filename)
        except Exception as exc:
            self.completed.emit(False, _friendly_error(exc))


class UpdateInstallJob(QThread):
    completed = Signal(bool, str)
    progress = Signal(str)

    def __init__(self, version, display, filename):
        super().__init__()
        self.version = version
        self.display = display
        self.filename = filename

    def run(self):
        try:
            try:
                import py7zr
            except ImportError as exc:
                raise RuntimeError("The 7z extractor is missing. Reopen the launcher so it can install app/requirements.txt.") from exc

            data_dir = Path.home() / ".ateam-root-patcher"
            data_dir.mkdir(parents=True, exist_ok=True)
            archive = data_dir / self.filename
            url = "https://github.com/PizzaG/A-Team-Android_Root_Patcher/raw/refs/heads/main/" + self.filename
            self.progress.emit("Downloading the 7z update package…")
            with requests.get(url, stream=True, timeout=180) as download:
                download.raise_for_status()
                with archive.open("wb") as output:
                    for chunk in download.iter_content(1024 * 1024):
                        if chunk:
                            output.write(chunk)

            staging = data_dir / "update-staging"
            if staging.exists():
                shutil.rmtree(staging)
            staging.mkdir(parents=True)
            self.progress.emit("Extracting the 7z package…")
            # The release is a 7z archive, not a ZIP. py7zr is the required
            # extractor; pass an explicit output path and reject unsafe paths.
            extraction_error = None
            try:
                with py7zr.SevenZipFile(archive, mode="r") as package:
                    for member in package.getnames():
                        member_path = (staging / member).resolve()
                        if member_path != staging.resolve() and staging.resolve() not in member_path.parents:
                            raise RuntimeError("The update archive contains an unsafe path: " + member)
                    package.extractall(path=staging)
            except Exception as exc:
                extraction_error = _friendly_error(exc)
                # A current 7z command-line extractor can handle codecs that
                # may not be supported by an older Python extractor build.
                extractor = next((shutil.which(name) for name in ("7z", "7zz", "7za") if shutil.which(name)), None)
                if not extractor:
                    raise RuntimeError(
                        "Could not extract the 7z update package. "
                        "Update py7zr (the launcher installs py7zr>=1.0.0) or install 7-Zip. "
                        f"Extractor detail: {extraction_error}"
                    ) from exc
                shutil.rmtree(staging, ignore_errors=True)
                staging.mkdir(parents=True, exist_ok=True)
                result = subprocess.run(
                    [extractor, "x", "-y", f"-o{staging}", str(archive)],
                    capture_output=True, text=True, errors="replace", timeout=300
                )
                if result.returncode != 0:
                    detail = result.stderr.strip() or result.stdout.strip() or extraction_error
                    raise RuntimeError("7-Zip extraction failed: " + detail)

            entries = list(staging.iterdir())
            if len(entries) == 1 and entries[0].is_dir():
                staging = entries[0]
            if not (staging / "app" / "app.py").is_file():
                raise RuntimeError("The downloaded 7z package does not contain the expected app/app.py layout.")

            destination = PROJECT_ROOT.resolve()
            helper = data_dir / "apply_update.py"
            helper_source = f"""#!/usr/bin/env python3
import os
import shutil
import subprocess
import sys
import time
import traceback
from pathlib import Path

SOURCE = Path({str(staging)!r})
DEST = Path({str(destination)!r})
PARENT_PID = {os.getpid()}
LOG = Path.home() / ".ateam-root-patcher" / "update-apply.log"

def log(message):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as stream:
        stream.write(message + "\\n")
        stream.flush()

try:
    log("Waiting for the patcher process to exit…")
    while True:
        try:
            os.kill(PARENT_PID, 0)
        except OSError:
            break
        time.sleep(0.5)

    log(f"Applying update from {{SOURCE}} to {{DEST}}")
    if not (SOURCE / "app" / "app.py").is_file():
        raise RuntimeError("Staged update is missing app/app.py")
    if not (DEST / "app").is_dir():
        raise RuntimeError("Install directory does not contain app/")

    shutil.copytree(
        SOURCE,
        DEST,
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns(".git", ".venv", "logs", "data", "output", "__pycache__")
    )

    if not (DEST / "app" / "app.py").is_file():
        raise RuntimeError("Updated app/app.py is missing after copy")

    log("Update files copied successfully. Restarting application…")
    if os.name == "nt":
        subprocess.Popen(
            ["cmd.exe", "/c", "start", "", str(DEST / "run-windows.bat")],
            cwd=str(DEST),
            creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                | getattr(subprocess, "DETACHED_PROCESS", 0)
        )
    else:
        launcher = DEST / "run-linux.sh"
        launcher.chmod(launcher.stat().st_mode | 0o111)
        subprocess.Popen(
            [str(launcher)],
            cwd=str(DEST),
            start_new_session=True
        )
    log("Restart command launched.")
except Exception:
    log("UPDATE FAILED:\\n" + traceback.format_exc())
    raise
"""
            helper.write_text(helper_source, encoding="utf-8")
            self.progress.emit("Update extracted. Closing and restarting the application…")
            flags = 0
            if os.name == "nt":
                flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
            subprocess.Popen(
                [sys.executable, str(helper)],
                cwd=str(data_dir),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True,
                start_new_session=(os.name != "nt"),
                creationflags=flags
            )
            self.completed.emit(True, f"Version {self.display} is ready. The app will close, update, and restart automatically.")
        except Exception as exc:
            self.completed.emit(False, _friendly_error(exc))

class MainWindow(QMainWindow):
    # Worker threads emit log text through this Qt signal; Qt queues the
    # connected slot onto the GUI thread before touching QTextEdit.
    log_message = Signal(str)

    def __init__(self):
        super().__init__()
        self.log_message.connect(self.log_line)
        self.setWindowTitle("")
        icon_path = ROOT / "images" / "ateam-root_patcher-icon.ico"
        if icon_path.is_file():
            self.setWindowIcon(QIcon(str(icon_path)))
        # Keep the window resizable into Cinnamon's quarter-screen snap regions.
        # The content scrolls when the available height is smaller than its natural size.
        self.setMinimumSize(600, 400)
        self.resize(1020, 760)
        self.setStyleSheet("""
        QMainWindow,QWidget { background:#090909; color:#f3f3f3; font-family:Segoe UI,Inter,sans-serif; font-size:10pt; }
        QGroupBox { border:1px solid #571c1c; border-radius:10px; margin-top:12px; padding:14px; font-weight:600; }
        QGroupBox::title { subcontrol-origin:margin; left:13px; padding:0 7px; color:#ff5a5a; }
        QPushButton { background:#171717; border:1px solid #742525; border-radius:8px; padding:11px; color:#fff; }
        QPushButton:hover { background:#281010; border-color:#ff4141; }
        QPushButton:checked { background:#3a1010; border:2px solid #ff4545; font-weight:800; }
        QLineEdit,QComboBox { background:#111; border:1px solid #444; border-radius:6px; padding:9px; color:#fff; }
        QTextEdit { background:#050505; border:1px solid #333; border-radius:8px; color:#ddd; font-family:Consolas,monospace; }
        """)
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.NoFrame)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        central=QWidget()
        scroll_area.setWidget(central)
        self.setCentralWidget(scroll_area)
        layout=QVBoxLayout(central)
        layout.setContentsMargins(24,20,24,20)
        layout.setSpacing(14)
        header=QGridLayout()
        header.setHorizontalSpacing(10)
        brand_mark = QLabel()
        brand_pixmap = QPixmap(str(ROOT / "images" / "ateam-root-patcher-header.png"))
        brand_mark.setPixmap(brand_pixmap.scaledToHeight(68, Qt.SmoothTransformation))
        brand_mark.setFixedHeight(72)
        brand_mark.setMinimumWidth(0)
        brand_mark.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        title_col=QVBoxLayout()
        title=QLabel("Android Root Patcher")
        title.setAlignment(Qt.AlignCenter)
        title.setWordWrap(True)
        title.setStyleSheet("font-size:21pt;font-weight:800;color:#fff")
        subtitle=QLabel("Cross-Platform Root Patching")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color:#ff6262")
        title_col.addWidget(title)
        title_col.addWidget(subtitle)
        action_col=QVBoxLayout()
        action_col.setSpacing(7)
        shortcut=QPushButton("\u2002DESKTOP SHORTCUT")
        shortcut.setIcon(self.style().standardIcon(QStyle.SP_ComputerIcon))
        shortcut.setMinimumWidth(0)
        shortcut.clicked.connect(self.create_desktop_shortcut)
        action_col.addWidget(shortcut)
        update=QPushButton("↻  CHECK FOR UPDATE")
        update.setMinimumWidth(0)
        update.clicked.connect(self.check_updates)
        action_col.addWidget(update)
        header.addWidget(brand_mark,0,0,Qt.AlignLeft | Qt.AlignVCenter)
        header.addLayout(title_col,0,1)
        header.addLayout(action_col,0,2)
        header.setColumnStretch(0,1)
        header.setColumnStretch(1,2)
        header.setColumnStretch(2,1)
        layout.addLayout(header)

        method=QGroupBox("PATCHING METHOD")
        method.setStyleSheet("QGroupBox { padding: 8px 12px 6px 12px; }")
        row=QHBoxLayout(method)
        # Tighten only this group so the version labels and outline fit
        # comfortably in shorter snapped windows.
        row.setContentsMargins(8,4,8,4)
        row.setSpacing(8)
        magisk_col=QVBoxLayout()
        magisk_col.setSpacing(2)
        self.magisk_button=QPushButton("MAGISK")
        self.magisk_button.setIcon(QIcon(str(ROOT/"images"/"magisk-logo.png")))
        self.magisk_button.setIconSize(QSize(26,26))
        self.magisk_version_label=QLabel(f"Version: {APP_CONFIG['magisk_version']}")
        self.magisk_version_label.setAlignment(Qt.AlignCenter)
        magisk_col.addWidget(self.magisk_button)
        magisk_col.addWidget(self.magisk_version_label)
        ksu_col=QVBoxLayout()
        ksu_col.setSpacing(2)
        self.ksu_button=QPushButton("KERNEL-SU")
        self.ksu_button.setIcon(QIcon(str(ROOT/"images"/"kernelsu-logo.png")))
        self.ksu_button.setIconSize(QSize(26,26))
        self.kernelsu_version_label=QLabel(f"Version: {APP_CONFIG['kernelsu_version']}")
        self.kernelsu_version_label.setAlignment(Qt.AlignCenter)
        ksu_col.addWidget(self.ksu_button)
        ksu_col.addWidget(self.kernelsu_version_label)
        for button in (self.magisk_button,self.ksu_button):
            button.setCheckable(True)
            button.setMinimumHeight(56)
        row.addLayout(magisk_col,1)
        row.addLayout(ksu_col,1)
        self.magisk_button.clicked.connect(lambda:self.select_engine("magisk"))
        self.ksu_button.clicked.connect(lambda:self.select_engine("kernelsu"))
        layout.addWidget(method)
        workspace_row=QHBoxLayout()
        workspace_row.setSpacing(12)
        image_group=QGroupBox("IMAGE SELECTION")
        image_layout=QVBoxLayout(image_group)
        image_row=QHBoxLayout()
        self.image_path=QLineEdit()
        self.image_path.setPlaceholderText("Select boot.img, init_boot.img, or supported image…")
        browse=QPushButton("BROWSE")
        browse.clicked.connect(self.browse_image)
        image_row.addWidget(self.image_path,1)
        image_row.addWidget(browse)
        image_layout.addLayout(image_row)
        option_row=QHBoxLayout()
        option_row.addWidget(QLabel("Magisk architecture"))
        self.architecture=QComboBox()
        self.architecture.addItems(["ARM64 (64-bit)","ARM (32-bit)"])
        option_row.addWidget(self.architecture,1)
        image_layout.addLayout(option_row)
        partition_row=QHBoxLayout()
        partition_row.addWidget(QLabel("Partition type"))
        self.partition=QComboBox()
        self.partition.addItems(["boot","init_boot","vendor_boot","recovery","Other / auto-detect"])
        partition_row.addWidget(self.partition,1)
        image_layout.addLayout(partition_row)
        self.kmi=QLineEdit()
        self.kmi.setPlaceholderText("KernelSU KMI (optional, e.g. android13-5.10)")
        image_layout.addWidget(self.kmi)
        image_group.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Preferred)
        workspace_row.addWidget(image_group,1)

        manager_group=QGroupBox("ROOT MANAGER")
        manager_layout=QVBoxLayout(manager_group)
        self.install_magisk_button=QPushButton("Install - Magisk Manager")
        self.install_magisk_button.setIcon(QIcon(str(ROOT/"images"/"install-package.png")))
        self.install_ksu_button=QPushButton("Install - Kernel-SU Manager")
        self.install_ksu_button.setIcon(QIcon(str(ROOT/"images"/"install-package.png")))
        self.install_magisk_button.setIconSize(QSize(20,20))
        self.install_ksu_button.setIconSize(QSize(20,20))
        self.install_magisk_button.setIconSize(QSize(20,20))
        self.install_ksu_button.setIconSize(QSize(20,20))
        for manager_button in (self.install_magisk_button,self.install_ksu_button):
            manager_button.setMinimumHeight(42)
            manager_layout.addWidget(manager_button)
        manager_layout.addStretch(1)
        self.install_magisk_button.clicked.connect(lambda:self.install_manager("magisk"))
        self.install_ksu_button.clicked.connect(lambda:self.install_manager("kernelsu"))
        manager_group.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Preferred)
        workspace_row.addWidget(manager_group,1)
        layout.addLayout(workspace_row)
        output_group=QGroupBox("PATCHED IMAGE OUTPUT")
        output_layout=QHBoxLayout(output_group)
        self.output_path=QLineEdit()
        self.output_path.setPlaceholderText("Patched output path (defaults beside the original)")
        save=QPushButton("SAVE AS")
        save.clicked.connect(self.browse_output)
        output_layout.addWidget(self.output_path,1)
        output_layout.addWidget(save)
        layout.addWidget(output_group)
        self.patch_button=QPushButton("⚡  PATCH IMAGE  ⚡")
        self.patch_button.setMinimumHeight(48)
        self.patch_button.setStyleSheet("background:#8e1717;border:1px solid #ff5757;font-size:12pt;font-weight:800")
        self.patch_button.clicked.connect(self.patch_image)
        layout.addWidget(self.patch_button)
        log_group=QGroupBox("OPERATION LOG")
        log_layout=QVBoxLayout(log_group)
        self.log=QTextEdit()
        self.log.setReadOnly(True)
        watermark_path = (ROOT / "images" / "operation-log-watermark.png").as_posix()
        self.log.setStyleSheet(
            "QTextEdit { background-color:#050505; "
            f"background-image:url('{watermark_path}'); "
            "background-repeat:no-repeat; background-position:center center; "
            "border:1px solid #333; border-radius:8px; color:#ddd; "
            "font-family:Consolas,monospace; }"
        )
        # Avoid forcing a tall minimum window size that blocks quarter snapping.
        self.log.setMinimumHeight(80)
        self.log.setMaximumHeight(220)
        log_layout.addWidget(self.log)
        layout.addWidget(log_group,1)
        footer=QHBoxLayout()
        footer.addWidget(QLabel(f"A-Team Digital Solutions  •  {platform.system()} {platform.machine()}"))
        footer.addStretch()
        footer.addWidget(QLabel("v"+DISPLAY_VERSION))
        layout.addLayout(footer)
        central.setMinimumSize(0, 0)
        self.select_engine("magisk")
    def log_line(self,message):
        LOGGER.info("%s", message)
        self.log.append(f"[{datetime.now():%H:%M:%S}] {message}")
    def select_engine(self,name):
        self.engine=name
        self.magisk_button.setChecked(name=="magisk")
        self.ksu_button.setChecked(name=="kernelsu")
        self.architecture.setEnabled(name=="magisk")
        self.kmi.setEnabled(name=="kernelsu")
    def browse_image(self):
        path,_=QFileDialog.getOpenFileName(self,"Select boot image","","Images (*.img *.bin);;All files (*)")
        if path:
            self.image_path.setText(path)
    def browse_output(self):
        path,_=QFileDialog.getSaveFileName(self,"Save patched image","","Image (*.img)")
        if path:
            self.output_path.setText(path)
    def patch_image(self):
        image=Path(self.image_path.text()).expanduser()
        if not image.is_file():
            QMessageBox.warning(self,"Image required","Select an existing image first.")
            return
        output=Path(self.output_path.text()).expanduser() if self.output_path.text().strip() else image.with_name(image.stem+"_patched.img")
        if image.resolve()==output.resolve():
            QMessageBox.critical(self,"Unsafe output","The patched image must not overwrite the original.")
            return
        if output.exists() and QMessageBox.question(self,"Overwrite output?","Replace the existing output image?")!=QMessageBox.Yes:
            return
        self.patch_button.setEnabled(False)
        self.log.clear()
        self.log_line("Original image is protected; patching will write a separate output.")
        if self.engine=="magisk":
            arch="64bit" if self.architecture.currentIndex()==0 else "32bit"
            task=lambda:MagiskEngine().patch(image,output,arch,self.log_message.emit)
        else:
            task=lambda:KernelSUEngine().patch(image,output,self.kmi.text(),self.log_message.emit)
        self.job=Job(task)
        self.job.completed.connect(lambda success,message:self.patch_finished(success,message,output))
        self.job.start()
    def patch_finished(self,success,message,output):
        self.patch_button.setEnabled(True)
        if success:
            checksum=file_hash(output)
            self.log_line("SUCCESS: "+message)
            self.log_line("SHA256: "+checksum)
            QMessageBox.information(self,"Patching complete",f"Patched image:\n{output}\n\nSHA256:\n{checksum}")
        else:
            self.log_line("FAILED: "+message)
            QMessageBox.critical(self,"Patching failed",message)
    def _adb_devices(self):
        adb=shutil.which("adb")
        if not adb:
            return None, [], "ADB executable was not found in PATH."
        try:
            result=subprocess.run([adb,"devices","-l"],capture_output=True,text=True,
                                  errors="replace",timeout=10)
        except Exception as exc:
            return adb, [], f"Unable to query ADB: {exc}"
        devices=[]
        for line in result.stdout.splitlines():
            fields=line.split()
            if len(fields)>=2 and fields[1]=="device" and fields[0]!="List":
                serial=fields[0]
                details=" ".join(fields[2:])
                model_match=re.search(r"model:([^ ]+)",details)
                model=model_match.group(1).replace("_"," ") if model_match else "Android device"
                devices.append((serial,model,details))
        return adb,devices,result.stdout.strip()

    def install_manager(self,manager):
        apk_name="Magisk.apk" if manager=="magisk" else "KernelSU.apk"
        apk=ROOT/"managers"/apk_name
        if not apk.is_file():
            QMessageBox.critical(self,"Manager APK missing",f"Could not find the bundled manager APK:\n{apk}")
            return
        adb,devices,details=self._adb_devices()
        if not adb or not devices:
            self.log_line("ADB device not ready; installation paused.")
            prompt=QMessageBox(self)
            prompt.setWindowTitle("ADB Setup Required")
            prompt.setIcon(QMessageBox.Warning)
            prompt.setText("Please Connect Device & Setup Working ADB Access")
            continue_button=prompt.addButton("* I Confirm Proper ADB Setup, Continue *",QMessageBox.AcceptRole)
            prompt.addButton(QMessageBox.Cancel)
            prompt.exec()
            if prompt.clickedButton()!=continue_button:
                return
            adb,devices,details=self._adb_devices()
            if not adb or not devices:
                QMessageBox.warning(self,"ADB device not found",
                    "No authorized ADB device was detected. Check USB debugging, accept the RSA prompt, "
                    "and verify `adb devices` before continuing.\n\n"+(details or "ADB is unavailable."))
                self.log_line("ADB setup confirmation received, but no authorized device was found.")
                return
        labels=[f"{model}  [{serial}]" for serial,model,_ in devices]
        if len(devices)>1:
            selected,ok=QInputDialog.getItem(self,"Select ADB device",
                "Choose the device that should receive the manager APK:",labels,0,False)
            if not ok:
                return
            index=labels.index(selected)
        else:
            index=0
        serial,model,_=devices[index]
        answer=QMessageBox.question(self,"Confirm target device",
            f"Install {apk_name} on this device?\n\nDevice: {model}\nSerial: {serial}",
            QMessageBox.Yes|QMessageBox.No,QMessageBox.No)
        if answer!=QMessageBox.Yes:
            self.log_line(f"Manager installation cancelled for {serial}.")
            return
        self.install_magisk_button.setEnabled(False)
        self.install_ksu_button.setEnabled(False)
        self.log_line(f"Installing {apk_name} on {model} [{serial}]…")
        def install_task():
            result=subprocess.run([adb,"-s",serial,"install","-r",str(apk)],
                                  capture_output=True,text=True,errors="replace",timeout=180)
            output=(result.stdout+"\n"+result.stderr).strip()
            if result.returncode!=0 or "Success" not in result.stdout:
                raise RuntimeError(output or f"adb install failed with exit code {result.returncode}.")
            return f"{apk_name} installed successfully on {model} [{serial}]."
        self.manager_job=Job(install_task)
        self.manager_job.completed.connect(self.manager_install_finished)
        self.manager_job.start()

    def manager_install_finished(self,success,message):
        self.install_magisk_button.setEnabled(True)
        self.install_ksu_button.setEnabled(True)
        self.log_line(("SUCCESS: " if success else "FAILED: ")+message)
        (QMessageBox.information if success else QMessageBox.critical)(
            self,"Manager installation",message)

    def create_desktop_shortcut(self):
        """Create a desktop launcher that starts the GUI without a terminal."""
        icon = ROOT / "images" / "ateam-root-patcher-icon.png"
        desktop_name = "A-Team Android Root Patcher"
        try:
            if os.name == "nt":
                pythonw = ROOT / ".venv" / "Scripts" / "pythonw.exe"
                if not pythonw.is_file():
                    raise RuntimeError("The app virtual environment is not ready. Run run-windows.bat once, then create the shortcut again.")
                desktop = Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Desktop"
                desktop.mkdir(parents=True, exist_ok=True)
                shortcut_path = desktop / (desktop_name + ".lnk")
                ps = """$w = New-Object -ComObject WScript.Shell
$sc = $w.CreateShortcut($args[0])
$sc.TargetPath = $args[1]
$sc.Arguments = '"' + $args[2] + '"'
$sc.WorkingDirectory = $args[3]
$sc.IconLocation = $args[4]
$sc.Description = 'A-Team Android Root Patcher'
$sc.Save()"""
                subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps,
                                str(shortcut_path), str(pythonw), str(ROOT / "app.py"), str(PROJECT_ROOT), str(icon)],
                               check=True, capture_output=True, text=True)
            else:
                desktop_result = subprocess.run(["xdg-user-dir", "DESKTOP"], capture_output=True, text=True) if shutil.which("xdg-user-dir") else None
                desktop = Path(desktop_result.stdout.strip()) if desktop_result and desktop_result.returncode == 0 and desktop_result.stdout.strip() else Path.home() / "Desktop"
                desktop.mkdir(parents=True, exist_ok=True)
                python = ROOT / ".venv" / "bin" / "python"
                if not python.is_file():
                    raise RuntimeError("The app virtual environment is not ready. Run ./run-linux.sh once, then create the shortcut again.")
                shortcut_path = desktop / (desktop_name + ".desktop")
                def desktop_quote(value):
                    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"').replace("`", "\\`").replace("$", "\\$") + '"'
                shortcut_path.write_text(
                    "[Desktop Entry]\nType=Application\nName=A-Team Android Root Patcher\n"
                    f"Exec={desktop_quote(python)} {desktop_quote(ROOT / 'app.py')}\n"
                    f"Path={PROJECT_ROOT}\nIcon={icon}\nTerminal=false\nCategories=Utility;System;\n",
                    encoding="utf-8")
                shortcut_path.chmod(0o755)
            self.log_line(f"Desktop shortcut created: {shortcut_path}")
            QMessageBox.information(self, "Desktop shortcut", f"Created desktop shortcut:\n{shortcut_path}")
        except Exception as exc:
            self.log_line(f"Desktop shortcut failed: {exc}")
            QMessageBox.warning(self, "Desktop shortcut", str(exc))

    def check_updates(self):
        self.log_line("Checking GitHub version manifest…")
        self.update_check_job = UpdateCheckJob()
        self.update_check_job.available.connect(self.confirm_update)
        self.update_check_job.completed.connect(self.update_check_finished)
        self.update_check_job.start()

    def update_check_finished(self, success, message):
        self.log_line(message)
        (QMessageBox.information if success else QMessageBox.warning)(self, "Updater", message)

    def confirm_update(self, version, display, filename):
        answer = QMessageBox.question(
            self,
            "Update available",
            f"A-Team Android Root Patcher {display} is available.\n\n"
            f"Current version: {DISPLAY_VERSION}\nNew version: {display}\n\n"
            "Download and install this update now?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes
        )
        if answer != QMessageBox.Yes:
            self.log_line(f"Update to {display} declined by user.")
            return

        self.log_line(f"User accepted update to {display}.")
        self.update_install_job = UpdateInstallJob(version, display, filename)
        self.update_install_job.progress.connect(self.log_line)
        self.update_install_job.completed.connect(self.update_install_finished)
        self.update_install_job.start()

    def update_install_finished(self, success, message):
        self.log_line(message)
        if success:
            QMessageBox.information(self, "Applying update", message)
            self.close()
        else:
            QMessageBox.warning(self, "Updater", message)

if __name__=="__main__":
    application=QApplication(sys.argv)
    application.setApplicationName(APP_NAME)
    window=MainWindow()
    window.show()
    sys.exit(application.exec())
