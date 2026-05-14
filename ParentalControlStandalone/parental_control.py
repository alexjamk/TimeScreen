"""
Родительский контроль - Главный модуль
Работает как служба Windows и как обычное приложение
Требуются права администратора для установки службы
"""

import sys
import os
import json
import hashlib
import secrets
import subprocess
import ctypes
import time
import threading
from datetime import datetime, timedelta
from pathlib import Path

# Проверка прав администратора
def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

def run_as_admin():
    """Перезапуск скрипта с правами администратора"""
    if sys.platform == 'win32':
        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable, " ".join(sys.argv), None, 1
        )
    sys.exit(0)

# Пути к файлам конфигурации
if getattr(sys, 'frozen', False):
    # Запущен как .exe
    BASE_DIR = Path(sys.executable).parent
    CONFIG_FILE = BASE_DIR / "config.json"
    LOG_FILE = BASE_DIR / "service.log"
else:
    # Запущен как скрипт
    BASE_DIR = Path(__file__).parent
    CONFIG_FILE = BASE_DIR / "config.json"
    LOG_FILE = BASE_DIR / "service.log"

# Глобальные переменные
config = {
    "password_hash": "",
    "salt": "",
    "schedule": [],  # [{"start": "08:00", "end": "22:00"}, ...]
    "enabled": True
}

def log_message(message):
    """Запись в лог файл"""
    try:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {message}\n")
    except:
        pass

def hash_password(password, salt=None):
    """Хэширование пароля с солью (SHA-256)"""
    if salt is None:
        salt = secrets.token_hex(16)
    salted = salt + password
    hash_obj = hashlib.sha256(salted.encode('utf-8'))
    return hash_obj.hexdigest(), salt

def verify_password(password, stored_hash, salt):
    """Проверка пароля"""
    computed_hash, _ = hash_password(password, salt)
    return computed_hash == stored_hash

def load_config():
    """Загрузка конфигурации"""
    global config
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                config = json.load(f)
        except:
            log_message("Ошибка загрузки конфигурации")
    else:
        log_message("Конфигурация не найдена, создание новой")

def save_config():
    """Сохранение конфигурации"""
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        log_message("Конфигурация сохранена")
    except Exception as e:
        log_message(f"Ошибка сохранения конфигурации: {e}")

def set_password():
    """Установка пароля администратора"""
    print("\n=== Установка пароля администратора ===")
    while True:
        password = input("Введите пароль: ").strip()
        if len(password) < 4:
            print("Пароль должен быть минимум 4 символа")
            continue
        confirm = input("Подтвердите пароль: ").strip()
        if password != confirm:
            print("Пароли не совпадают")
            continue
        break
    
    password_hash, salt = hash_password(password)
    config["password_hash"] = password_hash
    config["salt"] = salt
    save_config()
    print("[OK] Пароль успешно установлен\n")

def add_schedule():
    """Добавление временного интервала"""
    print("\n=== Добавление временного интервала ===")
    while True:
        start = input("Начало времени (ЧЧ:ММ, например 08:00): ").strip()
        try:
            datetime.strptime(start, "%H:%M")
        except:
            print("Неверный формат времени")
            continue
        break
    
    while True:
        end = input("Конец времени (ЧЧ:ММ, например 22:00): ").strip()
        try:
            datetime.strptime(end, "%H:%M")
        except:
            print("Неверный формат времени")
            continue
        break
    
    config["schedule"].append({"start": start, "end": end})
    save_config()
    print(f"[OK] Интервал {start} - {end} добавлен\n")

def show_schedule():
    """Показать текущее расписание"""
    print("\n=== Текущее расписание ===")
    if not config["schedule"]:
        print("Расписание пустое")
    else:
        for i, interval in enumerate(config["schedule"], 1):
            print(f"{i}. {interval['start']} - {interval['end']}")
    print()

def clear_schedule():
    """Очистить расписание"""
    config["schedule"] = []
    save_config()
    print("[OK] Расписание очищено\n")

def admin_menu():
    """Меню администратора"""
    # Для управления конфигурацией права администратора не требуются
    # (только для установки/удаления службы Windows)
    load_config()
    
    while True:
        print("\n=== Панель администратора ===")
        print("1. Установить/изменить пароль")
        print("2. Добавить временной интервал")
        print("3. Показать расписание")
        print("4. Очистить расписание")
        print("5. Включить/выключить защиту")
        print("6. Выход")
        
        choice = input("\nВыберите действие: ").strip()
        
        if choice == "1":
            set_password()
        elif choice == "2":
            add_schedule()
        elif choice == "3":
            show_schedule()
        elif choice == "4":
            clear_schedule()
        elif choice == "5":
            config["enabled"] = not config["enabled"]
            status = "включена" if config["enabled"] else "выключена"
            save_config()
            print(f"[OK] Защита {status}\n")
        elif choice == "6":
            break
        else:
            print("Неверный выбор")

def is_time_allowed():
    """Проверка, разрешено ли использование компьютера сейчас"""
    if not config["enabled"] or not config["schedule"]:
        return True
    
    now = datetime.now()
    current_time = now.strftime("%H:%M")
    
    for interval in config["schedule"]:
        start = interval["start"]
        end = interval["end"]
        
        if start <= end:
            # Обычный интервал (например, 08:00 - 22:00)
            if start <= current_time <= end:
                return True
        else:
            # Интервал через полночь (например, 22:00 - 08:00)
            if current_time >= start or current_time <= end:
                return True
    
    return False

def lock_screen():
    """Запуск экрана блокировки"""
    # Импорт tkinter только при необходимости
    import tkinter as tk
    from tkinter import messagebox
    
    root = tk.Tk()
    root.title("Компьютер заблокирован")
    root.attributes("-fullscreen", True)
    root.attributes("-topmost", True)
    root.configure(bg="#1a1a2e")
    
    # Блокировка закрытия окна
    root.protocol("WM_DELETE_WINDOW", lambda: None)
    
    # Фрейм для центрирования
    main_frame = tk.Frame(root, bg="#1a1a2e")
    main_frame.pack(expand=True)
    
    # Заголовок
    title_label = tk.Label(
        main_frame,
        text="КОМПЬЮТЕР ЗАБЛОКИРОВАН",
        font=("Arial", 32, "bold"),
        fg="#e94560",
        bg="#1a1a2e"
    )
    title_label.pack(pady=(0, 20))
    
    # Информация
    info_label = tk.Label(
        main_frame,
        text="Использование компьютера запрещено в это время.\nОбратитесь к администратору.",
        font=("Arial", 16),
        fg="#ffffff",
        bg="#1a1a2e",
        justify="center"
    )
    info_label.pack(pady=(0, 30))
    
    # Поле ввода пароля
    password_var = tk.StringVar()
    password_entry = tk.Entry(
        main_frame,
        textvariable=password_var,
        font=("Arial", 14),
        show="*",
        width=30,
        justify="center"
    )
    password_entry.pack(pady=10)
    
    # Метка статуса
    status_label = tk.Label(
        main_frame,
        text="",
        font=("Arial", 12),
        fg="#e94560",
        bg="#1a1a2e"
    )
    status_label.pack(pady=5)
    
    def check_password():
        password = password_var.get()
        if verify_password(password, config["password_hash"], config["salt"]):
            root.destroy()
            return True
        else:
            status_label.config(text="Неверный пароль!")
            password_var.set("")
            return False
    
    def on_enter(event):
        check_password()
    
    password_entry.bind("<Return>", on_enter)
    password_entry.focus_set()
    
    # Кнопка разблокировки
    unlock_btn = tk.Button(
        main_frame,
        text="Разблокировать",
        font=("Arial", 14),
        bg="#0f3460",
        fg="#ffffff",
        activebackground="#16213e",
        activeforeground="#ffffff",
        command=check_password,
        width=20,
        height=2
    )
    unlock_btn.pack(pady=10)
    
    # Кнопки выключения и перезагрузки
    button_frame = tk.Frame(main_frame, bg="#1a1a2e")
    button_frame.pack(pady=20)
    
    def shutdown_pc():
        if messagebox.askyesno("Подтверждение", "Вы действительно хотите выключить компьютер?"):
            subprocess.call(["shutdown", "/s", "/t", "0"])
    
    def restart_pc():
        if messagebox.askyesno("Подтверждение", "Вы действительно хотите перезагрузить компьютер?"):
            subprocess.call(["shutdown", "/r", "/t", "0"])
    
    shutdown_btn = tk.Button(
        button_frame,
        text="Выключить ПК",
        font=("Arial", 12),
        bg="#c0392b",
        fg="#ffffff",
        command=shutdown_pc,
        width=15,
        height=2
    )
    shutdown_btn.pack(side=tk.LEFT, padx=10)
    
    restart_btn = tk.Button(
        button_frame,
        text="Перезагрузить",
        font=("Arial", 12),
        bg="#e67e22",
        fg="#ffffff",
        command=restart_pc,
        width=15,
        height=2
    )
    restart_btn.pack(side=tk.LEFT, padx=10)
    
    # Обновление времени
    time_label = tk.Label(
        root,
        text="",
        font=("Arial", 14),
        fg="#ffffff",
        bg="#1a1a2e"
    )
    time_label.place(relx=0.5, rely=0.95, anchor="center")
    
    def update_time():
        current = datetime.now().strftime("%H:%M:%S")
        time_label.config(text=f"Текущее время: {current}")
        root.after(1000, update_time)
    
    update_time()
    
    # Запуск основного цикла
    root.mainloop()
    
    # Возвращаем True если разблокировано
    return True

def service_loop():
    """Основной цикл службы"""
    load_config()
    log_message("Служба запущена")
    
    last_check = None
    
    while True:
        try:
            # Перезагружаем конфигурацию каждый цикл
            load_config()
            
            current_minute = datetime.now().strftime("%Y-%m-%d %H:%M")
            
            # Проверяем только раз в минуту
            if current_minute != last_check:
                last_check = current_minute
                
                if not is_time_allowed():
                    log_message("Время заблокировано, запуск экрана блокировки")
                    lock_screen()
                    log_message("Экран блокировки закрыт")
            
            time.sleep(5)  # Проверка каждые 5 секунд
            
        except KeyboardInterrupt:
            log_message("Служба остановлена пользователем")
            break
        except Exception as e:
            log_message(f"Ошибка в службе: {e}")
            time.sleep(10)

def install_service():
    """Установка службы Windows"""
    if not is_admin():
        print("Требуется запуск от имени администратора!")
        run_as_admin()
    
    exe_path = sys.executable if getattr(sys, 'frozen', False) else __file__
    
    # Создаем bat-файл для запуска службы
    service_bat = BASE_DIR / "run_service.bat"
    with open(service_bat, "w", encoding="utf-8") as f:
        if getattr(sys, 'frozen', False):
            f.write(f'@echo off\n"{exe_path}" --service\n')
        else:
            f.write(f'@echo off\npython "{exe_path}" --service\n')
    
    # Используем sc для создания службы
    service_name = "ParentalControlService"
    display_name = "Родительский контроль"
    
    try:
        # Удаляем службу если существует
        subprocess.call(["sc", "stop", service_name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.call(["sc", "delete", service_name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(1)
        
        # Создаем службу
        result = subprocess.run(
            ["sc", "create", service_name, 
             "binPath=", f'"{service_bat}"',
             "DisplayName=", display_name,
             "start=", "auto"],
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            # Запускаем службу
            subprocess.call(["sc", "start", service_name])
            print("[OK] Служба успешно установлена и запущена")
            print(f"  Имя службы: {service_name}")
            print(f"  Отображаемое имя: {display_name}")
        else:
            print(f"[ERROR] Ошибка установки службы: {result.stderr}")
            
    except Exception as e:
        print(f"[ERROR] Ошибка: {e}")

def uninstall_service():
    """Удаление службы Windows"""
    if not is_admin():
        print("Требуется запуск от имени администратора!")
        run_as_admin()
    
    service_name = "ParentalControlService"
    
    try:
        subprocess.call(["sc", "stop", service_name])
        time.sleep(1)
        result = subprocess.run(["sc", "delete", service_name], capture_output=True, text=True)
        
        if result.returncode == 0:
            print("[OK] Служба успешно удалена")
        else:
            print(f"[ERROR] Ошибка удаления: {result.stderr}")
            
    except Exception as e:
        print(f"[ERROR] Ошибка: {e}")

def install_user_mode():
    """Установка для текущего пользователя (без прав администратора)"""
    install_dir = Path(os.environ["LOCALAPPDATA"]) / "ParentalControl"
    install_dir.mkdir(parents=True, exist_ok=True)
    
    exe_path = Path(sys.executable)
    
    # Копируем exe в папку установки (если мы не уже там)
    target_exe = install_dir / "ParentalControl.exe"
    if exe_path.resolve() != target_exe.resolve():
        import shutil
        shutil.copy2(str(exe_path), str(target_exe))
        print(f"[OK] Программа скопирована в {install_dir}")
    
    # Создаём VBS-скрипт для скрытого запуска фонового процесса
    vbs_path = install_dir / "run_hidden.vbs"
    with open(vbs_path, "w") as f:
        f.write(f'CreateObject("WScript.Shell").Run """{target_exe}"" --user-mode", 0, False\n')
    print("[OK] Создан скрипт скрытого запуска")
    
    # Добавляем в автозагрузку
    startup_dir = Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
    startup_dir.mkdir(parents=True, exist_ok=True)
    
    # Создаём ярлык в папке автозагрузки через VBS
    shortcut_vbs = install_dir / "_create_startup_shortcut.vbs"
    shortcut_path = startup_dir / "ParentalControl.lnk"
    with open(shortcut_vbs, "w") as f:
        f.write(f'''
Set oWS = WScript.CreateObject("WScript.Shell")
sLinkFile = "{shortcut_path}"
Set oLink = oWS.CreateShortcut(sLinkFile)
oLink.TargetPath = "wscript.exe"
oLink.Arguments = """{vbs_path}"""
oLink.WorkingDirectory = "{install_dir}"
oLink.WindowStyle = 7
oLink.Description = "Родительский контроль - фоновый процесс"
oLink.IconLocation = "{target_exe}, 0"
oLink.Save
''')
    subprocess.call(["cscript", "//nologo", str(shortcut_vbs)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    shortcut_vbs.unlink(missing_ok=True)
    print("[OK] Добавлено в автозагрузку")
    
    # Создаём ярлыки на рабочем столе
    desktop = Path.home() / "Desktop"
    
    # Ярлык 1: Панель администратора
    admin_vbs = install_dir / "_create_admin_shortcut.vbs"
    admin_shortcut = desktop / "Родительский контроль - Админ.lnk"
    with open(admin_vbs, "w") as f:
        f.write(f'''
Set oWS = WScript.CreateObject("WScript.Shell")
sLinkFile = "{admin_shortcut}"
Set oLink = oWS.CreateShortcut(sLinkFile)
oLink.TargetPath = "{target_exe}"
oLink.Arguments = "admin"
oLink.WorkingDirectory = "{install_dir}"
oLink.Description = "Панель администратора родительского контроля"
oLink.IconLocation = "{target_exe}, 0"
oLink.Save
''')
    subprocess.call(["cscript", "//nologo", str(admin_vbs)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    admin_vbs.unlink(missing_ok=True)
    
    # Ярлык 2: Включить/выключить защиту
    toggle_vbs = install_dir / "_create_toggle_shortcut.vbs"
    toggle_shortcut = desktop / "Родительский контроль - Защита.lnk"
    with open(toggle_vbs, "w") as f:
        f.write(f'''
Set oWS = WScript.CreateObject("WScript.Shell")
sLinkFile = "{toggle_shortcut}"
Set oLink = oWS.CreateShortcut(sLinkFile)
oLink.TargetPath = "{target_exe}"
oLink.Arguments = "toggle"
oLink.WorkingDirectory = "{install_dir}"
oLink.Description = "Включить/выключить родительский контроль"
oLink.IconLocation = "{target_exe}, 0"
oLink.Save
''')
    subprocess.call(["cscript", "//nologo", str(toggle_vbs)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    toggle_vbs.unlink(missing_ok=True)
    
    print("[OK] Ярлыки созданы на рабочем столе:")
    print(f"  - {admin_shortcut}")
    print(f"  - {toggle_shortcut}")
    
    # Запускаем фоновый процесс
    subprocess.Popen(["wscript", str(vbs_path)], 
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print("[OK] Фоновый процесс запущен")
    
    print("\n=== Установка завершена! ===")
    print(f"Программа установлена в: {install_dir}")
    print("Фоновый процесс работает в автостарте.")
    print("\nСЛЕДУЮЩИЕ ШАГИ:")
    print("1. Откройте 'Родительский контроль - Админ' на рабочем столе")
    print("2. Установите пароль администратора")
    print("3. Добавьте разрешённые временные интервалы")

def uninstall_user_mode():
    """Удаление пользовательской установки"""
    install_dir = Path(os.environ["LOCALAPPDATA"]) / "ParentalControl"
    
    # Убиваем фоновый процесс
    subprocess.call(["taskkill", "/f", "/im", "ParentalControl.exe"], 
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.call(["taskkill", "/f", "/im", "wscript.exe", "/fi", "WINDOWTITLE eq ParentalControl"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    # Удаляем из автозагрузки
    startup_dir = Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
    startup_link = startup_dir / "ParentalControl.lnk"
    if startup_link.exists():
        startup_link.unlink()
        print("[OK] Удалено из автозагрузки")
    
    # Удаляем ярлыки с рабочего стола
    desktop = Path.home() / "Desktop"
    for lnk in ["Родительский контроль - Админ.lnk", "Родительский контроль - Защита.lnk"]:
        path = desktop / lnk
        if path.exists():
            path.unlink()
            print(f"[OK] Удалён ярлык: {lnk}")
    
    # Удаляем папку программы
    if install_dir.exists():
        import shutil
        shutil.rmtree(str(install_dir))
        print(f"[OK] Удалена папка программы: {install_dir}")
    
    print("\n=== Удаление завершено! ===")

def toggle_protection():
    """Быстрое включение/выключение защиты (для ярлыка)"""
    load_config()
    config["enabled"] = not config["enabled"]
    save_config()
    status = "ВКЛЮЧЕНА" if config["enabled"] else "ВЫКЛЮЧЕНА"
    print(f"\nЗащита {status}")
    print("Это окно закроется автоматически через 3 секунды...")
    time.sleep(3)

def main():
    """Точка входа"""
    if len(sys.argv) > 1:
        arg = sys.argv[1].lower()
        
        if arg == "admin":
            admin_menu()
        elif arg == "toggle":
            toggle_protection()
        elif arg == "install":
            install_service()
        elif arg == "uninstall":
            uninstall_service()
        elif arg == "install-user":
            install_user_mode()
        elif arg == "uninstall-user":
            uninstall_user_mode()
        elif arg == "--service":
            service_loop()
        elif arg == "--user-mode":
            # Фоновый режим для текущего пользователя (без прав админа)
            service_loop()
        elif arg == "start":
            if not is_admin():
                print("Требуется запуск от имени администратора!")
                run_as_admin()
            service_loop()
        elif arg == "help":
            print("\n=== Родительский контроль ===")
            print("Команды (права администратора НЕ требуются):")
            print("  ParentalControl.exe admin         - Панель администратора")
            print("  ParentalControl.exe toggle        - Включить/выключить защиту")
            print("  ParentalControl.exe install-user  - Установка для текущего пользователя")
            print("  ParentalControl.exe uninstall-user - Удаление пользовательской установки")
            print("")
            print("Команды (права администратора ТРЕБУЮТСЯ):")
            print("  ParentalControl.exe install       - Установить как службу Windows")
            print("  ParentalControl.exe uninstall     - Удалить службу Windows")
            print("  ParentalControl.exe start         - Запустить службу вручную")
            print("  ParentalControl.exe help          - Эта справка")
        else:
            print(f"Неизвестная команда: {arg}")
            print("Используйте 'help' для справки")
    else:
        # Запуск без аргументов - открываем панель администратора
        print("Родительский контроль v2.0")
        print("Запуск панели администратора...\n")
        admin_menu()

if __name__ == "__main__":
    main()
