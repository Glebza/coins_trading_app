"""
DeviTrade — Скрипт сборки в EXE через PyInstaller.

Запуск:
    python build.py
"""

import subprocess
import sys
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)


def ensure_pyinstaller():
    """Убеждаемся что PyInstaller установлен."""
    try:
        import PyInstaller  # noqa: F401
        print("[OK] PyInstaller найден")
    except ImportError:
        print("[*] Устанавливаю PyInstaller...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])


def build():
    """Собираем EXE."""
    # Исключаем тяжёлые модули PySide6 которые не используются
    excludes = [
        "PySide6.Qt3DAnimation", "PySide6.Qt3DCore", "PySide6.Qt3DExtras",
        "PySide6.Qt3DInput", "PySide6.Qt3DLogic", "PySide6.Qt3DRender",
        "PySide6.QtBluetooth", "PySide6.QtCharts", "PySide6.QtDataVisualization",
        "PySide6.QtDesigner", "PySide6.QtHelp", "PySide6.QtHttpServer",
        "PySide6.QtLocation", "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets",
        "PySide6.QtNetworkAuth", "PySide6.QtNfc", "PySide6.QtPdf",
        "PySide6.QtPdfWidgets", "PySide6.QtPositioning", "PySide6.QtPrintSupport",
        "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuick3D",
        "PySide6.QtQuickControls2", "PySide6.QtQuickWidgets",
        "PySide6.QtRemoteObjects", "PySide6.QtScxml", "PySide6.QtSensors",
        "PySide6.QtSerialBus", "PySide6.QtSerialPort", "PySide6.QtSpatialAudio",
        "PySide6.QtSql", "PySide6.QtStateMachine", "PySide6.QtSvg",
        "PySide6.QtSvgWidgets", "PySide6.QtTest", "PySide6.QtTextToSpeech",
        "PySide6.QtUiTools", "PySide6.QtWebChannel", "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineQuick", "PySide6.QtWebEngineWidgets",
        "PySide6.QtWebSockets", "PySide6.QtXml", "PySide6.QtOpenGL",
        "PySide6.QtOpenGLWidgets", "PySide6.QtDBus", "PySide6.QtConcurrent",
        "PySide6.QtAsyncio", "PySide6.QtAxContainer", "PySide6.QtExampleIcons",
        "PySide6.QtGraphs",
    ]

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--onefile",
        "--windowed",
        "--name", "DeviTrade",
        "--add-data", f"detector.py{os.pathsep}.",
        "--add-data", f"engine.py{os.pathsep}.",
        "--add-data", f"STRATEGY.md{os.pathsep}.",
        # PySide6 — только нужные модули
        "--hidden-import", "PySide6.QtWidgets",
        "--hidden-import", "PySide6.QtCore",
        "--hidden-import", "PySide6.QtGui",
        "--hidden-import", "PySide6.QtNetwork",
        # numpy / requests
        "--hidden-import", "numpy",
        "--hidden-import", "requests",
    ]
    # Исключения
    for ex in excludes:
        cmd.extend(["--exclude-module", ex])

    cmd.append("trading_app.py")

    print("=" * 50)
    print("  DeviTrade — Сборка в EXE")
    print("=" * 50)
    print()
    print(f"  Команда: {' '.join(cmd)}")
    print()

    result = subprocess.run(cmd)

    if result.returncode != 0:
        print("\n[!] Ошибка сборки!")
        sys.exit(1)

    # Создаём папку logs рядом с exe и копируем STRATEGY.md
    dist_logs = ROOT / "dist" / "logs"
    dist_logs.mkdir(parents=True, exist_ok=True)

    import shutil
    strategy_src = ROOT / "STRATEGY.md"
    strategy_dst = ROOT / "dist" / "STRATEGY.md"
    if strategy_src.exists():
        shutil.copy2(strategy_src, strategy_dst)
        print(f"  Скопирован: {strategy_dst}")

    exe_path = ROOT / "dist" / "DeviTrade.exe"

    print()
    print("=" * 50)
    print(f"  Готово! EXE: {exe_path}")
    print("=" * 50)
    print()
    print("  Для запуска: dist\\DeviTrade.exe")
    print("  Логи будут сохраняться в: dist\\logs\\")


if __name__ == "__main__":
    ensure_pyinstaller()
    build()
