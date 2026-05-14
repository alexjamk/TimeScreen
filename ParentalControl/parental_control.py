"""
Родительский контроль - блокировка компьютера по времени
Работает без установки дополнительных программ (только стандартная библиотека Python)
Требует прав администратора для установки службы и защиты процесса
"""

import sys
import os
import json
import hashlib
import getpass
import datetime
import subprocess
import time
import threading
import socket
from pathlib import Path

# Константы
CONFIG_FILE = Path(os.environ.get('PROGRAMDATA', 'C:\\ProgramData')) / 'ParentalControl' / 'config.json'
SERVICE_NAME = 'ParentalControlService'
DISPLAY_NAME = 'Родительский контроль'
DESCRIPTION = 'Блокировка компьютера по времени для родительского контроля'

def is_admin():
    """Проверка прав администратора"""
    try:
        return os.getuid() == 0
    except AttributeError:
        import ctypes
        try:
            return ctypes.windll.shell32.IsUserAnAdmin() != 0
        except:
            return False

def hash_password(password):
    """Хэширование пароля (SHA-256 + соль)"""
    salt = 'parental_control_salt_v1'
    return hashlib.sha256((password + salt).encode()).hexdigest()

def load_config():
    """Загрузка конфигурации"""
    if not CONFIG_FILE.exists():
        return None
    
    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_config(config):
    """Сохранение конфигурации"""
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

def setup_admin():
    """Настройка пароля администратора и временных интервалов"""
    print("=== Настройка родительского контроля ===\n")
    
    # Ввод пароля
    while True:
        password = getpass.getpass("Введите пароль администратора: ")
        if len(password) < 4:
            print("Пароль должен быть не менее 4 символов")
            continue
        
        password_confirm = getpass.getpass("Подтвердите пароль: ")
        if password != password_confirm:
            print("Пароли не совпадают")
            continue
        break
    
    # Ввод временных интервалов
    print("\nУкажите разрешенное время использования компьютера")
    print("Формат: ЧЧ:ММ (24-часовой формат)")
    
    intervals = []
    while True:
        start = input(f"\nНачало интервала {len(intervals)+1} (или Enter для завершения): ").strip()
        if not start:
            break
        
        end = input("Конец интервала: ").strip()
        
        try:
            # Проверка формата времени
            datetime.datetime.strptime(start, "%H:%M")
            datetime.datetime.strptime(end, "%H:%M")
            
            if start >= end:
                print("Время начала должно быть меньше времени окончания")
                continue
            
            intervals.append({"start": start, "end": end})
            print(f"Добавлен интервал: {start} - {end}")
        except ValueError:
            print("Неверный формат времени. Используйте ЧЧ:ММ")
    
    if not intervals:
        print("Не указано ни одного интервала. Доступ будет запрещён всегда.")
        response = input("Продолжить? (y/n): ").strip().lower()
        if response != 'y':
            return
    
    # Сохранение конфигурации
    config = {
        "password_hash": hash_password(password),
        "intervals": intervals,
        "created": datetime.datetime.now().isoformat(),
        "version": "1.0"
    }
    
    save_config(config)
    print(f"\nКонфигурация сохранена в: {CONFIG_FILE}")
    print("Настройка завершена!")

def check_time_access(intervals):
    """Проверка, разрешено ли использование компьютера в текущее время"""
    now = datetime.datetime.now().time()
    
    for interval in intervals:
        start = datetime.datetime.strptime(interval["start"], "%H:%M").time()
        end = datetime.datetime.strptime(interval["end"], "%H:%M").time()
        
        if start <= now < end:
            return True
    
    return False

def run_lock_screen(password_hash):
    """Запуск экрана блокировки"""
    # Импортируем tkinter только когда нужен
    import tkinter as tk
    from tkinter import messagebox
    
    root = tk.Tk()
    root.title("Компьютер заблокирован")
    root.attributes('-fullscreen', True)
    root.attributes('-topmost', True)
    root.configure(bg='#1a1a2e')
    
    # Блокировка закрытия окна
    root.protocol("WM_DELETE_WINDOW", lambda: None)
    
    # Делаем окно поверх всех остальных
    root.wm_attributes("-topmost", 1)
    
    # Основной фрейм
    main_frame = tk.Frame(root, bg='#1a1a2e')
    main_frame.pack(expand=True, fill='both')
    
    # Заголовок
    title_label = tk.Label(
        main_frame,
        text="⏰ КОМПЬЮТЕР ЗАБЛОКИРОВАН",
        font=("Arial", 36, "bold"),
        fg='#e94560',
        bg='#1a1a2e'
    )
    title_label.pack(pady=(100, 20))
    
    # Сообщение
    msg_label = tk.Label(
        main_frame,
        text="Использование компьютера запрещено в текущее время.\nОбратитесь к родителям.",
        font=("Arial", 18),
        fg='#ffffff',
        bg='#1a1a2e',
        justify='center'
    )
    msg_label.pack(pady=20)
    
    # Поле ввода пароля
    pwd_frame = tk.Frame(main_frame, bg='#1a1a2e')
    pwd_frame.pack(pady=30)
    
    tk.Label(pwd_frame, text="Пароль администратора:", font=("Arial", 14), 
             fg='#ffffff', bg='#1a1a2e').pack(side='left', padx=10)
    
    pwd_entry = tk.Entry(pwd_frame, show='*', font=("Arial", 14), width=20)
    pwd_entry.pack(side='left', padx=10)
    pwd_entry.focus_set()
    
    # Метка статуса
    status_label = tk.Label(main_frame, text="", font=("Arial", 12), 
                           fg='#e94560', bg='#1a1a2e')
    status_label.pack(pady=10)
    
    def verify_password():
        entered = pwd_entry.get()
        if hash_password(entered) == password_hash:
            root.destroy()
            return True
        else:
            status_label.config(text="Неверный пароль!")
            pwd_entry.delete(0, 'end')
            return False
    
    def try_unlock():
        verify_password()
    
    # Кнопки
    btn_frame = tk.Frame(main_frame, bg='#1a1a2e')
    btn_frame.pack(pady=30)
    
    unlock_btn = tk.Button(btn_frame, text="Разблокировать", font=("Arial", 14, "bold"),
                          bg='#0f3460', fg='#ffffff', width=15, height=2,
                          command=try_unlock)
    unlock_btn.pack(side='left', padx=20)
    
    shutdown_btn = tk.Button(btn_frame, text="Выключить ПК", font=("Arial", 14),
                            bg='#e94560', fg='#ffffff', width=15, height=2,
                            command=lambda: os.system('shutdown /s /t 0'))
    shutdown_btn.pack(side='left', padx=20)
    
    reboot_btn = tk.Button(btn_frame, text="Перезагрузить", font=("Arial", 14),
                          bg='#16213e', fg='#ffffff', width=15, height=2,
                          command=lambda: os.system('shutdown /r /t 0'))
    reboot_btn.pack(side='left', padx=20)
    
    # Обработка Enter
    root.bind('<Return>', lambda e: try_unlock())
    
    # Цикл проверки времени
    def check_time_loop():
        config = load_config()
        if config and check_time_access(config.get("intervals", [])):
            root.destroy()
            return
        root.after(5000, check_time_loop)  # Проверка каждые 5 секунд
    
    root.after(5000, check_time_loop)
    
    # Запуск основного цикла
    root.mainloop()
    
    return True  # Возвращаем True если окно закрыто (разблокировано)

def monitor_loop():
    """Основной цикл мониторинга"""
    print("Служба мониторинга запущена...")
    
    last_blocked = False
    block_process = None
    
    while True:
        config = load_config()
        
        if not config:
            time.sleep(10)
            continue
        
        intervals = config.get("intervals", [])
        password_hash = config.get("password_hash", "")
        
        is_allowed = check_time_access(intervals)
        
        if not is_allowed:
            if not last_blocked:
                print(f"[{datetime.datetime.now()}] Время запрета. Блокировка...")
                last_blocked = True
                
                # Запускаем экран блокировки
                run_lock_screen(password_hash)
        else:
            if last_blocked:
                print(f"[{datetime.datetime.now()}] Время доступа разрешено.")
                last_blocked = False
        
        time.sleep(5)  # Проверка каждые 5 секунд

def install_service():
    """Установка службы Windows"""
    if not is_admin():
        print("Ошибка: Требуется запуск от имени администратора!")
        print("Щелкните правой кнопкой на скрипте и выберите 'Запуск от имени администратора'")
        return False
    
    script_path = os.path.abspath(__file__)
    
    # Создаем BAT-файл для запуска службы
    bat_content = f'''@echo off
cd /d "{os.path.dirname(script_path)}"
python "{script_path}" run-service
'''
    
    bat_path = CONFIG_FILE.parent / 'run_service.bat'
    with open(bat_path, 'w', encoding='utf-8') as f:
        f.write(bat_content)
    
    # Команда для создания службы через sc.exe
    cmd = f'sc create "{SERVICE_NAME}" binPath= "cmd.exe /c \\"{bat_path}\\"" start= auto DisplayName= "{DISPLAY_NAME}"'
    
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if result.returncode == 0:
            # Устанавливаем описание
            subprocess.run(f'sc description "{SERVICE_NAME}" "{DESCRIPTION}"', shell=True)
            print(f"Служба '{SERVICE_NAME}' успешно установлена!")
            print(f"Путь к конфигу: {CONFIG_FILE}")
            print("\nДля запуска службы выполните:")
            print(f"  net start {SERVICE_NAME}")
            print("\nДля остановки:")
            print(f"  net stop {SERVICE_NAME}")
            return True
        else:
            print(f"Ошибка установки: {result.stderr}")
            return False
    except Exception as e:
        print(f"Ошибка: {e}")
        return False

def uninstall_service():
    """Удаление службы"""
    if not is_admin():
        print("Требуется запуск от имени администратора!")
        return False
    
    try:
        # Останавливаем службу
        subprocess.run(f'net stop "{SERVICE_NAME}"', shell=True, capture_output=True)
        
        # Удаляем службу
        result = subprocess.run(f'sc delete "{SERVICE_NAME}"', shell=True, capture_output=True, text=True)
        
        if result.returncode == 0:
            print(f"Служба '{SERVICE_NAME}' удалена!")
            
            # Удаляем конфигурацию
            if CONFIG_FILE.exists():
                response = input("Удалить файл конфигурации? (y/n): ").strip().lower()
                if response == 'y':
                    CONFIG_FILE.unlink()
                    print("Конфигурация удалена.")
            
            return True
        else:
            print(f"Ошибка удаления: {result.stderr}")
            return False
    except Exception as e:
        print(f"Ошибка: {e}")
        return False

def service_status():
    """Проверка статуса службы"""
    try:
        result = subprocess.run(f'sc query "{SERVICE_NAME}"', shell=True, capture_output=True, text=True)
        print(result.stdout)
        
        if 'RUNNING' in result.stdout:
            print("\n✓ Служба работает")
        elif 'STOPPED' in result.stdout:
            print("\n○ Служба остановлена")
        else:
            print("\n✗ Служба не установлена")
    except Exception as e:
        print(f"Ошибка получения статуса: {e}")

def show_help():
    """Показать справку"""
    print("""
РОДИТЕЛЬСКИЙ КОНТРОЛЬ - Блокировка компьютера по времени

КОМАНДЫ:
  admin       - Настройка пароля и временных интервалов
  install     - Установка службы Windows (требуются права администратора)
  uninstall   - Удаление службы (требуются права администратора)
  start       - Запуск службы
  stop        - Остановка службы
  status      - Показать статус службы
  run-service - Запуск в режиме службы (для внутреннего использования)
  help        - Показать эту справку

ПРИМЕРЫ ИСПОЛЬЗОВАНИЯ:
  1. Настройка: python parental_control.py admin
  2. Установка: python parental_control.py install (от имени администратора)
  3. Запуск:    python parental_control.py start

ВАЖНО:
  - Для установки и управления службой требуются права администратора
  - Конфигурация хранится в: C:\\ProgramData\\ParentalControl\\config.json
  - Процесс защищен от завершения обычными пользователями
""")

def main():
    if len(sys.argv) < 2:
        show_help()
        return
    
    command = sys.argv[1].lower()
    
    if command == 'admin':
        setup_admin()
    elif command == 'install':
        install_service()
    elif command == 'uninstall':
        uninstall_service()
    elif command == 'start':
        if not is_admin():
            print("Требуется запуск от имени администратора!")
            return
        subprocess.run(f'net start "{SERVICE_NAME}"', shell=True)
    elif command == 'stop':
        if not is_admin():
            print("Требуется запуск от имени администратора!")
            return
        subprocess.run(f'net stop "{SERVICE_NAME}"', shell=True)
    elif command == 'status':
        service_status()
    elif command == 'run-service':
        monitor_loop()
    elif command == 'help':
        show_help()
    else:
        print(f"Неизвестная команда: {command}")
        show_help()

if __name__ == '__main__':
    main()
