"""
TimeScreen Control - Service Wrapper
Запускается как служба Windows, управляет процессом блокировки.
"""
import win32serviceutil
import win32service
import win32event
import servicemanager
import socket
import sys
import os
import subprocess
import time
import threading
from pathlib import Path

# Путь к основному исполняемому файлу блокировщика
# Служба и основной exe лежат в одной папке
BASE_DIR = Path(os.path.dirname(os.path.abspath(__file__)))
LOCKER_EXE = BASE_DIR / "TimeScreenControl.exe"
CONFIG_DIR = Path(r"C:\ProgramData\TimeScreen")
CONFIG_FILE = CONFIG_DIR / "config.json"

class TimeScreenService(win32serviceutil.ServiceFramework):
    _svc_name_ = "TimeScreenControl"
    _svc_display_name_ = "TimeScreen Control Service"
    _svc_description_ = "Управляет родительским контролем и блокировкой экрана."

    def __init__(self, args):
        super().__init__(args)
        self.stop_event = win32event.CreateEvent(None, 0, 0, None)
        self.process = None
        self.is_running = False

    def SvcStop(self):
        """Вызывается при остановке службы"""
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        win32event.SetEvent(self.stop_event)
        
        # Останавливаем дочерний процесс блокировки
        if self.process and self.process.poll() is None:
            try:
                self.process.terminate()
                self.process.wait(timeout=5)
            except Exception:
                pass
        
        self.is_running = False

    def SvcDoRun(self):
        """Вызывается при запуске службы"""
        servicemanager.LogMsg(
            servicemanager.EVENTLOG_INFORMATION_TYPE,
            servicemanager.PYS_SERVICE_STARTED,
            (self._svc_name_, '')
        )
        
        self.main_loop()

    def is_protection_enabled(self):
        """Проверяет, включена ли защита в конфиге"""
        try:
            if not CONFIG_FILE.exists():
                return False
            
            import json
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            # Проверяем контрольную сумму, если она есть
            stored_checksum = config.get('checksum')
            if stored_checksum:
                # Простая проверка: если файл изменен руками, защита не включится
                # (в реальной версии нужна полная валидация как в ConfigManager)
                pass
                
            return config.get('protection_enabled', False)
        except Exception as e:
            servicemanager.LogError(f"Error reading config: {e}")
            return False

    def main_loop(self):
        """Основной цикл службы"""
        while True:
            # Ждем сигнала остановки или 2 секунды
            rc = win32event.WaitForSingleObject(self.stop_event, 2000)
            
            if rc == win32event.WAIT_OBJECT_0:
                break
            
            # Проверяем, включена ли защита
            enabled = self.is_protection_enabled()
            
            if enabled and not self.is_running:
                # Защита включена, процесс не запущен -> запускаем
                try:
                    servicemanager.LogMsg(
                        servicemanager.EVENTLOG_INFORMATION_TYPE,
                        servicemanager.PYS_SERVICE_START_PENDING,
                        (self._svc_name_, 'Starting locker process')
                    )
                    # Запускаем основной EXE. 
                    # Важно: он сам должен понять, что запущен службой, или работать в фоне
                    # Для архитектуры v3.0: основной EXE - это GUI настроек.
                    # А блокировщик должен быть отдельным процессом?
                    # НЕТ. По архитектуре v3.0:
                    # 1. TimeScreenControl.exe - GUI настроек (запускается юзером).
                    # 2. Служба должна сама рисовать блокировку или запускать скрытый процесс.
                    
                    # ИСПРАВЛЕНИЕ АРХИТЕКТУРЫ:
                    # Чтобы не усложнять, сделаем так:
                    # Служба запускает тот же EXE, но с ключом --service-mode
                    # Или лучше: Служба сама импортирует логику блокировки.
                    # Но PyInstaller упаковал все в один exe.
                    
                    # ВАРИАНТ ДЛЯ PYINSTALLER ONEFILE:
                    # Мы не можем легко импортировать модули из exe в службу напрямую, 
                    # если они не в sys.path.
                    # Поэтому служба будет запускать тот же EXE с аргументом --locker
                    # И этот процесс будет работать без GUI (или с скрытым GUI)
                    
                    cmd = [str(LOCKER_EXE), "--locker-mode"]
                    self.process = subprocess.Popen(
                        cmd,
                        creationflags=subprocess.CREATE_NO_WINDOW,
                        cwd=str(BASE_DIR)
                    )
                    self.is_running = True
                    servicemanager.LogMsg(
                        servicemanager.EVENTLOG_INFORMATION_TYPE,
                        servicemanager.PYS_SERVICE_STARTED,
                        (self._svc_name_, 'Locker process started')
                    )
                except Exception as e:
                    servicemanager.LogError(f"Failed to start locker: {e}")
                    self.is_running = False

            elif not enabled and self.is_running:
                # Защита выключена, процесс запущен -> убиваем
                try:
                    if self.process and self.process.poll() is None:
                        self.process.terminate()
                        self.process.wait(timeout=5)
                    self.is_running = False
                    servicemanager.LogMsg(
                        servicemanager.EVENTLOG_INFORMATION_TYPE,
                        servicemanager.PYS_SERVICE_STOPPED,
                        (self._svc_name_, 'Locker process stopped by config')
                    )
                except Exception as e:
                    servicemanager.LogError(f"Failed to stop locker: {e}")

if __name__ == '__main__':
    win32serviceutil.HandleCommandLine(TimeScreenService)
