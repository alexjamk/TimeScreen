# 📋 ПОЛНЫЙ ПЛАН ИСПРАВЛЕНИЯ И ДОРАБОТКИ TimeScreen Control

## 🎯 ЦЕЛИ ПРОЕКТА

1. **Безопасность**: Максимальная защита от попыток обхода детьми
2. **Удобство**: Простая установка/настройка для родителей
3. **Надёжность**: Служба работает независимо от пользовательских процессов
4. **Гибкость**: Настраиваемый интерфейс и функционал

---

## 🔧 АРХИТЕКТУРНЫЕ ИЗМЕНЕНИЯ

### 1. Новая структура проекта

```
TimeScreenControl/
├── src/
│   ├── __init__.py
│   ├── main.py                    # Точка входа
│   ├── config/
│   │   ├── __init__.py
│   │   ├── manager.py             # ConfigManager (единый)
│   │   ├── security.py            # Хэширование, проверка целостности
│   │   └── paths.py               # Константы путей
│   ├── service/
│   │   ├── __init__.py
│   │   ├── daemon.py              # Windows Service (service_daemon.py)
│   │   ├── monitor.py             # Логика мониторинга времени
│   │   └── installer.py           # Установка/удаление службы
│   ├── gui/
│   │   ├── __init__.py
│   │   ├── app.py                 # Главное окно настроек
│   │   ├── lock_screen.py         # Экран блокировки
│   │   ├── timer_overlay.py       # Таймер-оверлей
│   │   ├── dialogs.py             # Диалоги (пароль, интервалы)
│   │   └── components/
│   │       ├── interval_editor.py # Редактор интервалов
│   │       ├── user_selector.py   # Выбор пользователей
│   │       └── draggable_timer.py # Перетаскиваемый таймер
│   ├── utils/
│   │   ├── __init__.py
│   │   ├── logger.py              # Централизованное логирование
│   │   ├── admin.py               # Проверка прав админа
│   │   ├── users.py               # Работа со списком пользователей
│   │   └── autostart.py           # Автозагрузка
│   └── resources/
│       ├── icon.ico               # Иконка приложения
│       └── images/                # Дополнительные изображения
├── install/
│   ├── install_all_users.bat      # Установка для всех пользователей
│   ├── uninstall_all_users.bat    # Удаление
│   └── create_service.bat         # Создание службы
├── tests/
│   ├── test_config.py
│   ├── test_monitor.py
│   └── test_security.py
├── requirements.txt
├── setup.py                       # Для pip install
├── pyproject.toml
├── build_exe.bat                  # Сборка .exe
└── README.md
```

### 2. Удаление дублирования кода

**Проблема**: `parental_control.py` (662 строки) и `parental_control_gui.py` (1393 строки) дублируют ~40% кода

**Решение**:
- Удалить `parental_control.py` полностью
- Весь код разделить на модули в `src/`
- `service_daemon.py` переименовать в `src/service/daemon.py` и сократить до 150 строк

---

## 🔒 БЕЗОПАСНОСТЬ (Приоритет 1 - Критично)

### 2.1. Хэширование паролей

**Текущая проблема**: 
- Используется SHA-256 без соли
- Уязвимо к rainbow table атакам

**Решение**:
```python
# src/config/security.py
import bcrypt  # или argon2-cffi

def hash_password(password: str) -> str:
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(password.encode(), salt).decode()

def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())
```

**Действия**:
- [ ] Добавить `bcrypt` в зависимости
- [ ] Переписать `hash_password()` и `verify_password()`
- [ ] При первом запуске требовать установки пароля
- [ ] Миграция старых хэшей: при обнаружении старого формата принудительно запросить новый пароль

### 2.2. Защита от Race Condition с LOCK_FLAG

**Текущая проблема**: Можно удалить файл `lock_flag` и обойти блокировку

**Решение**:
- Использовать Windows Named Mutex вместо файла
- Служба создаёт мьютекс `Global\TimeScreenLock`
- GUI проверяет мьютекс, а не файл

```python
# src/service/monitor.py
import ctypes
from ctypes import wintypes

class LockManager:
    def __init__(self):
        self.mutex_name = "Global\\TimeScreenLock"
        self.mutex_handle = None
    
    def acquire(self) -> bool:
        self.mutex_handle = ctypes.windll.kernel32.CreateMutexW(
            None, True, self.mutex_name
        )
        return self.mutex_handle != 0
    
    def release(self):
        if self.mutex_handle:
            ctypes.windll.kernel32.CloseHandle(self.mutex_handle)
            self.mutex_handle = None
    
    def is_locked() -> bool:
        handle = ctypes.windll.kernel32.OpenMutexW(0x1F0001, False, self.mutex_name)
        if handle:
            ctypes.windll.kernel32.CloseHandle(handle)
            return True
        return False
```

### 2.3. Tamper Detection в service_daemon.py

**Текущая проблема**: Нет проверки целостности конфига перед использованием

**Решение**:
```python
# src/service/daemon.py
def load_config_secure() -> dict:
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not CONFIG_FILE.exists():
        log("Config missing - lockdown mode")
        return {"enabled": True, "_tampered": True}
    
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8-sig") as f:
            raw = json.load(f)
        
        stored_hash = raw.pop("_hash", None)
        if not stored_hash:
            log("Config has no hash - possible tampering")
            return {"enabled": True, "_tampered": True}
        
        expected = compute_hash(raw)
        if stored_hash != expected:
            log("CONFIG TAMPERED - hash mismatch")
            return {"enabled": True, "_tampered": True}
        
        # Проверка прав доступа к файлу
        acl = get_file_acl(CONFIG_FILE)
        if current_user_can_write(acl):
            log("Config writable by non-admin - insecure")
            return {"enabled": True, "_tampered": True}
        
        return raw
    except Exception as e:
        log(f"Config load error: {e}")
        return {"enabled": True, "_tampered": True}
```

### 2.4. Уязвимость Escalation через Recovery Mode

**Текущая проблема**: `--recovery` позволяет обойти защиту

**Решение**:
- Удалить `--recovery` режим
- Разблокировка только через ввод пароля на экране блокировки
- Если забыли пароль → полное удаление программы через безопасный режим Windows

### 2.5. Замена os.system() на subprocess.run()

**Текущая проблема**: 
```python
os.system("shutdown /s /t 5")  # Уязвимо к инъекциям
```

**Решение**:
```python
subprocess.run(
    ["shutdown", "/s", "/t", "5"],
    check=True,
    creationflags=subprocess.CREATE_NO_WINDOW
)
```

---

## 🏗️ АРХИТЕКТУРА (Приоритет 2)

### 3.1. Модульность

**Текущая проблема**: `parental_control_gui.py` - 1393 строки в одном файле

**Решение**: Разделение на модули:

| Модуль | Ответственность | Строк |
|--------|----------------|-------|
| `app.py` | Главное окно, навигация | ~300 |
| `lock_screen.py` | Экран блокировки | ~250 |
| `timer_overlay.py` | Таймер-оверлей | ~200 |
| `dialogs.py` | Диалоги (пароль, подтверждение) | ~150 |
| `interval_editor.py` | Редактор интервалов | ~200 |
| `user_selector.py` | Выбор пользователей | ~150 |
| `draggable_timer.py` | Перетаскиваемый таймер | ~150 |

### 3.2. Единый ConfigManager

**Проблема**: 3 разных реализации в 3 файлах

**Решение**: Один класс в `src/config/manager.py`:

```python
# src/config/manager.py
class ConfigManager:
    """Единый менеджер конфигурации для всех компонентов"""
    
    def __init__(self, read_only: bool = False):
        self.config_path = CONFIG_PATH
        self.read_only = read_only
        self.config = self._load()
    
    def _load(self) -> dict:
        # Загрузка с проверкой целостности
        pass
    
    def save(self) -> bool:
        # Сохранение с вычислением хэша
        pass
    
    def set_password(self, password: str) -> None:
        # Хэширование bcrypt + сохранение
        pass
    
    def verify_password(self, password: str) -> bool:
        # Проверка пароля
        pass
    
    def add_interval(self, start: str, end: str, days: list) -> None:
        # Добавление интервала с валидацией
        pass
    
    def remove_interval(self, index: int) -> None:
        # Удаление интервала
        pass
    
    def get_controlled_users(self) -> list:
        # Получить список контролируемых пользователей
        pass
    
    def set_controlled_users(self, users: list) -> None:
        # Установить список пользователей
        pass
    
    def is_allowed_time(self) -> bool:
        # Проверка текущего времени
        pass
    
    def get_next_event(self) -> tuple[int, str]:
        # Получить следующее событие (секунды, тип)
        pass
```

### 3.3. Централизованное логирование

```python
# src/utils/logger.py
import logging
from pathlib import Path

def setup_logger(name: str, log_file: Path) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    
    # File handler
    fh = logging.FileHandler(log_file, encoding='utf-8')
    fh.setLevel(logging.DEBUG)
    
    # Console handler (только для отладки)
    ch = logging.StreamHandler()
    ch.setLevel(logging.WARNING)
    
    # Formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    fh.setFormatter(formatter)
    ch.setFormatter(formatter)
    
    logger.addHandler(fh)
    logger.addHandler(ch)
    
    return logger

# Использование
log = setup_logger("TimeScreen", LOG_PATH)
log.info("Service started")
log.warning("Config tampered")
log.error("Failed to load config")
```

---

## 🖥️ ИНТЕРФЕЙС (Приоритет 2)

### 4.1. Список пользователей за пределами окна

**Текущая проблема**: Список пользователей может выходить за границы окна

**Решение**:
```python
# src/gui/components/user_selector.py
class UserSelector(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        
        # Scrollable frame
        self.canvas = tk.Canvas(self, highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.scrollable_frame = ttk.Frame(self.canvas)
        
        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )
        
        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")
        
        # Загрузка пользователей
        self._load_users()
    
    def _load_users(self):
        users = get_all_windows_users()
        for user in users:
            var = tk.BooleanVar(value=user in self.selected_users)
            chk = ttk.Checkbutton(
                self.scrollable_frame,
                text=user,
                variable=var,
                command=lambda u=user, v=var: self._toggle_user(u, v.get())
            )
            chk.pack(anchor="w", padx=10, pady=2)
```

### 4.2. Выбор пользователей из списка, а не ввод строкой

**Текущая проблема**: Ввод имени пользователя вручную

**Решение**:
```python
# src/utils/users.py
def get_all_windows_users() -> list[str]:
    """Получить список всех локальных пользователей Windows"""
    import subprocess
    result = subprocess.run(
        ["net", "user"],
        capture_output=True,
        text=True,
        creationflags=subprocess.CREATE_NO_WINDOW
    )
    
    # Парсинг вывода net user
    users = []
    lines = result.stdout.split('\n')
    for line in lines:
        line = line.strip()
        if line and not line.startswith('-') and 'User accounts' not in line:
            users.extend([u.strip() for u in line.split() if u.strip()])
    
    # Исключаем системные учётки
    exclude = {'Administrator', 'Guest', 'DefaultAccount', 'WDAGUtilityAccount'}
    return [u for u in users if u not in exclude]
```

### 4.3. Ввод пароля админа один раз при входе в настройки

**Текущая проблема**: Пароль спрашивается多次

**Решение**:
```python
# src/gui/app.py
class SettingsApp:
    def __init__(self):
        self.cfg = ConfigManager()
        self.admin_authenticated = False
        self.auth_timestamp = None
        
        # Проверка необходимости пароля
        if not self.cfg.has_password():
            self._force_set_password()
        else:
            self._authenticate_admin()
    
    def _force_set_password(self):
        """Принудительная установка пароля при первом запуске"""
        dialog = SetPasswordDialog(self.root)
        if dialog.result:
            self.cfg.set_password(dialog.result)
            self.admin_authenticated = True
        else:
            sys.exit(0)  # Закрыть приложение
    
    def _authenticate_admin(self):
        """Однократная аутентификация при входе в настройки"""
        dialog = PasswordDialog(self.root, title="Вход в настройки")
        if self.cfg.verify_password(dialog.password):
            self.admin_authenticated = True
            self.auth_timestamp = time.time()
            self._build_main_ui()
        else:
            sys.exit(0)
    
    def _check_auth_timeout(self):
        """Проверка таймаута сессии (30 минут)"""
        if self.admin_authenticated and self.auth_timestamp:
            if time.time() - self.auth_timestamp > 1800:  # 30 мин
                self.admin_authenticated = False
                self._authenticate_admin()
```

### 4.4. Перетаскиваемый индикатор времени

**Текущая проблема**: Таймер перекрывает важные элементы

**Решение**:
```python
# src/gui/components/draggable_timer.py
class DraggableTimerOverlay:
    def __init__(self, parent):
        self.window = tk.Toplevel(parent)
        self.window.overrideredirect(True)
        self.window.attributes("-topmost", True)
        self.window.attributes("-transparentcolor", "#00ff00")
        
        # Позиция из конфига
        position = self.cfg.get_timer_position()
        self.window.geometry(f"+{position[0]}+{position[1]}")
        
        self.frame = tk.Frame(self.window, bg="#1a1a2e", cursor="fleur")
        self.frame.pack(fill="both", expand=True)
        
        self.label = tk.Label(
            self.frame,
            text="",
            font=("Arial", 14, "bold"),
            fg="#ffffff",
            bg="#1a1a2e"
        )
        self.label.pack(padx=10, pady=5)
        
        # Drag functionality
        self._drag_data = {"x": 0, "y": 0}
        self.frame.bind("<ButtonPress-1>", self._on_drag_start)
        self.frame.bind("<ButtonRelease-1>", self._on_drag_end)
        self.frame.bind("<B1-Motion>", self._on_drag_motion)
        
        # Контекстное меню
        self.menu = tk.Menu(self.window, tearoff=0)
        self.menu.add_command(label="Скрыть", command=self.hide)
        self.menu.add_command(label="Показать", command=self.show)
        self.menu.add_command(label="Сбросить позицию", command=self.reset_position)
        self.frame.bind("<Button-3>", self._show_menu)
    
    def _on_drag_start(self, event):
        self._drag_data["x"] = event.x
        self._drag_data["y"] = event.y
    
    def _on_drag_motion(self, event):
        x = self.window.winfo_x() + event.x - self._drag_data["x"]
        y = self.window.winfo_y() + event.y - self._drag_data["y"]
        self.window.geometry(f"+{x}+{y}")
    
    def _on_drag_end(self, event):
        # Сохранение позиции в конфиг
        self.cfg.save_timer_position(
            self.window.winfo_x(),
            self.window.winfo_y()
        )
    
    def _show_menu(self, event):
        self.menu.post(event.x_root, event.y_root)
```

### 4.5. Упрощённый ввод интервалов

**Текущая проблема**: Ввод строкой "08:00-22:00"

**Решение**:
```python
# src/gui/components/interval_editor.py
class IntervalEditor(ttk.Dialog):
    def __init__(self, parent, interval=None):
        super().__init__(parent)
        self.title("Добавить интервал" if not interval else "Изменить интервал")
        self.result = None
        
        # Дни недели
        days_frame = ttk.LabelFrame(self, text="Дни недели")
        days_frame.pack(fill="x", padx=10, pady=5)
        
        self.days_vars = {}
        days = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
        for i, day in enumerate(days):
            var = tk.BooleanVar(value=True)  # или из interval
            self.days_vars[i] = var
            chk = ttk.Checkbutton(days_frame, text=day, variable=var)
            chk.grid(row=0, column=i, padx=5, pady=5)
        
        # Время начала
        time_frame = ttk.Frame(self)
        time_frame.pack(fill="x", padx=10, pady=5)
        
        ttk.Label(time_frame, text="Начало:").grid(row=0, column=0, padx=5)
        self.start_hour = ttk.Spinbox(time_frame, from_=0, to=23, width=3)
        self.start_hour.set(interval.start.hour if interval else 8)
        self.start_hour.grid(row=0, column=1)
        ttk.Label(time_frame, text=":").grid(row=0, column=2)
        self.start_min = ttk.Spinbox(time_frame, from_=0, to=59, width=3)
        self.start_min.set(interval.start.minute if interval else 0)
        self.start_min.grid(row=0, column=3)
        
        # Время конца
        ttk.Label(time_frame, text="Конец:").grid(row=1, column=0, padx=5, pady=5)
        self.end_hour = ttk.Spinbox(time_frame, from_=0, to=23, width=3)
        self.end_hour.set(interval.end.hour if interval else 22)
        self.end_hour.grid(row=1, column=1)
        ttk.Label(time_frame, text=":").grid(row=1, column=2)
        self.end_min = ttk.Spinbox(time_frame, from_=0, to=59, width=3)
        self.end_min.set(interval.end.minute if interval else 0)
        self.end_min.grid(row=1, column=3)
        
        # Кнопки
        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill="x", padx=10, pady=10)
        ttk.Button(btn_frame, text="OK", command=self._ok).pack(side="right", padx=5)
        ttk.Button(btn_frame, text="Отмена", command=self.destroy).pack(side="right")
    
    def _ok(self):
        # Валидация
        start = datetime.time(int(self.start_hour.get()), int(self.start_min.get()))
        end = datetime.time(int(self.end_hour.get()), int(self.end_min.get()))
        days = [i for i, v in self.days_vars.items() if v.get()]
        
        if not days:
            messagebox.showerror("Ошибка", "Выберите хотя бы один день")
            return
        
        self.result = {
            "start": start.strftime("%H:%M"),
            "end": end.strftime("%H:%M"),
            "days": days
        }
        self.destroy()
```

### 4.6. Интеграция иконки приложения

**Действия**:
- [ ] Создать иконку `icon.ico` (или скачать бесплатную)
- [ ] Добавить в `pyinstaller` при сборке
- [ ] Использовать в окне приложения: `root.iconbitmap('icon.ico')`
- [ ] Добавить в ярлыки

---

## 🛠️ УСТАНОВКА (Приоритет 1)

### 5.1. Установка для всех пользователей (не в профиль пользователя)

**Текущая проблема**: Установка в `%LOCALAPPDATA%`

**Решение**:
```batch
:: install/install_all_users.bat
@echo off
set INSTALL_DIR=%PROGRAMFILES%\\TimeScreenControl

if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%"

copy /Y "dist\\*" "%INSTALL_DIR%\\"
copy /Y "config\\pc_config.default.json" "%PROGRAMDATA%\\TimeScreen\\"

:: Регистрация службы
sc create TimeScreenControl binPath= "\"%INSTALL_DIR%\\service.exe\"" start=auto DisplayName= "TimeScreen Control"
sc start TimeScreenControl

:: Ярлык в меню Пуск для всех
powershell "$WshShell = New-Object -comObject WScript.Shell; $Shortcut = $WshShell.CreateShortcut('%PUBLIC%\\Desktop\\TimeScreen Настройки.lnk'); $Shortcut.TargetPath = '%INSTALL_DIR%\\settings.exe'; $Shortcut.Save()"
```

### 5.2. Служба запускается при установке

**Текущая проблема**: Служба создаётся, но не стартует автоматически

**Решение**:
```python
# src/service/installer.py
def install_service() -> bool:
    """Установка и запуск службы"""
    try:
        # Остановить если существует
        subprocess.run(["sc", "stop", SERVICE_NAME], 
                      capture_output=True, timeout=10)
        time.sleep(2)
        
        # Удалить если существует
        subprocess.run(["sc", "delete", SERVICE_NAME],
                      capture_output=True, timeout=10)
        time.sleep(2)
        
        # Создать службу
        result = subprocess.run(
            ["sc", "create", SERVICE_NAME,
             "binPath=", f'"{SERVICE_EXE}"',
             "DisplayName=", DISPLAY_NAME,
             "start=", "auto"],  # Автоматический старт
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode != 0:
            log.error(f"Failed to create service: {result.stderr}")
            return False
        
        # Запустить службу
        result = subprocess.run(
            ["sc", "start", SERVICE_NAME],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode != 0:
            log.warning(f"Service created but failed to start: {result.stderr}")
            # Не ошибка - служба может стартовать при следующей перезагрузке
        
        # Проверка статуса
        for _ in range(10):  # Ждём до 10 секунд
            time.sleep(1)
            status = subprocess.run(
                ["sc", "query", SERVICE_NAME],
                capture_output=True,
                text=True
            )
            if "RUNNING" in status.stdout:
                log.info("Service installed and running")
                return True
        
        log.info("Service installed (will start on next boot)")
        return True
        
    except Exception as e:
        log.error(f"Install service error: {e}")
        return False
```

### 5.3. Активность службы зависит от настройки "Включена защита"

**Текущая проблема**: Служба всегда активна

**Решение**:
```python
# src/service/daemon.py
def service_main():
    cfg = ConfigManager(read_only=True)
    
    while True:
        config = cfg.load()
        
        if not config.get("enabled", False):
            # Защита отключена - спим 10 секунд
            time.sleep(10)
            continue
        
        # Защита включена - выполняем мониторинг
        if should_lock(config):
            set_lock_flag()
        else:
            clear_lock_flag()
        
        time.sleep(5)
```

### 5.4. Удалить ярлык "Защита"

**Действия**:
- [ ] Удалить создание ярлыка "Защита" из `install.bat`
- [ ] Переключение защиты только через настройки
- [ ] В настройках добавить большой toggle "Включить защиту"

---

## 🧪 ТЕСТИРОВАНИЕ (Приоритет 3)

### 6.1. Unit-тесты

```python
# tests/test_config.py
import pytest
from src.config.manager import ConfigManager
from src.config.security import hash_password, verify_password

def test_password_hashing():
    hashed = hash_password("test123")
    assert hashed is not None
    assert len(hashed) > 0
    assert verify_password("test123", hashed)
    assert not verify_password("wrong", hashed)

def test_interval_validation():
    cfg = ConfigManager()
    assert cfg.add_interval("08:00", "22:00", [0,1,2,3,4])
    assert not cfg.add_interval("25:00", "10:00", [0])  # Invalid hour
    assert not cfg.add_interval("08:00", "07:00", [])   # No days

def test_time_check():
    cfg = ConfigManager()
    cfg.add_interval("08:00", "22:00", list(range(7)))
    # Mock current time to 10:00
    with patch('datetime.datetime') as mock:
        mock.now.return_value.time.return_value = datetime.time(10, 0)
        assert cfg.is_allowed_time()
```

### 6.2. Интеграционные тесты

```python
# tests/test_monitor.py
def test_lock_trigger():
    """Проверка что служба создаёт lock flag при наступлении запрещённого времени"""
    pass

def test_auto_unlock():
    """Проверка автоматической разблокировки при наступлении разрешённого времени"""
    pass
```

---

## 📝 ЗАДАЧИ ПО ПРИОРИТЕТАМ

### 🔴 Приоритет 1 (Немедленно - Безопасность и Установка)

| № | Задача | Файл(ы) | Строк | Сложность |
|---|--------|---------|-------|-----------|
| 1.1 | Добавить bcrypt для хэширования паролей | `src/config/security.py` | 50 | Средняя |
| 1.2 | Реализовать проверку целостности конфига | `src/config/manager.py` | 100 | Высокая |
| 1.3 | Заменить LOCK_FLAG на Named Mutex | `src/service/monitor.py` | 80 | Высокая |
| 1.4 | Заменить os.system() на subprocess.run() | Все файлы | 20 | Низкая |
| 1.5 | Удалить --recovery режим | `src/gui/lock_screen.py` | 30 | Низкая |
| 1.6 | Установка для всех пользователей (%PROGRAMFILES%) | `install/*.bat` | 100 | Средняя |
| 1.7 | Автозапуск службы при установке | `src/service/installer.py` | 80 | Средняя |
| 1.8 | Зависимость активности службы от настройки | `src/service/daemon.py` | 40 | Низкая |
| 1.9 | Принудительная установка пароля при первом запуске | `src/gui/app.py` | 60 | Средняя |
| 1.10 | Однократный ввод пароля для настроек | `src/gui/app.py` | 50 | Средняя |

### 🟡 Приоритет 2 (Архитектура и Интерфейс)

| № | Задача | Файл(ы) | Строк | Сложность |
|---|--------|---------|-------|-----------|
| 2.1 | Разделить parental_control_gui.py на модули | `src/gui/*` | 1400 | Высокая |
| 2.2 | Создать единый ConfigManager | `src/config/manager.py` | 200 | Высокая |
| 2.3 | Реализовать выбор пользователей из списка | `src/gui/components/user_selector.py` | 150 | Средняя |
| 2.4 | Сделать перетаскиваемый таймер | `src/gui/components/draggable_timer.py` | 150 | Высокая |
| 2.5 | Упростить ввод интервалов (отдельные поля) | `src/gui/components/interval_editor.py` | 200 | Средняя |
| 2.6 | Исправить выход списка за границы окна | `src/gui/components/user_selector.py` | 50 | Низкая |
| 2.7 | Добавить иконку приложения | `src/resources/icon.ico` | - | Низкая |
| 2.8 | Удалить ярлык "Защита" | `install/*.bat` | 20 | Низкая |
| 2.9 | Централизованное логирование | `src/utils/logger.py` | 80 | Средняя |
| 2.10 | Type hints для всех функций | Все файлы | 300 | Средняя |

### 🟢 Приоритет 3 (Дополнительно)

| № | Задача | Файл(ы) | Строк | Сложность |
|---|--------|---------|-------|-----------|
| 3.1 | Unit-тесты для ConfigManager | `tests/test_config.py` | 200 | Высокая |
| 3.2 | Unit-тесты для монитора времени | `tests/test_monitor.py` | 150 | Высокая |
| 3.3 | Интеграционные тесты | `tests/test_integration.py` | 200 | Высокая |
| 3.4 | Поддержка i18n (русский/английский) | Все GUI файлы | 100 | Средняя |
| 3.5 | Мастер первой настройки | `src/gui/wizard.py` | 250 | Высокая |
| 3.6 | Резервное копирование конфига | `src/config/backup.py` | 80 | Средняя |
| 3.7 | Уведомления перед блокировкой | `src/gui/notifications.py` | 120 | Средняя |

---

## 📊 МЕТРИКИ УЛУЧШЕНИЯ

| Метрика | До | После | Улучшение |
|---------|-----|-------|-----------|
| Строк в largest file | 1393 | 300 | **-78%** |
| Дублирование кода | ~40% | <5% | **-87%** |
| Безопасность паролей | SHA-256 | bcrypt | **🔒🔒🔒** |
| Test coverage | 0% | >80% | **+80%** |
| Modules count | 3 | 15+ | **+400%** |
| User actions to configure | 15+ | 5-7 | **-60%** |

---

## 🚀 ПЛАН РЕАЛИЗАЦИИ

### Неделя 1: Безопасность
- [ ] 1.1-1.5: Криптография, Mutex, удаление уязвимостей
- [ ] Тестирование безопасности

### Неделя 2: Архитектура
- [ ] 2.1-2.3: Рефакторинг на модули
- [ ] 2.9: Логирование
- [ ] Unit-тесты для базовых компонентов

### Неделя 3: Интерфейс
- [ ] 2.4-2.6: Drag-and-drop таймер, редактор интервалов
- [ ] 2.7: Иконка
- [ ] Юзабилити-тестирование

### Неделя 4: Установка и тестирование
- [ ] 1.6-1.10: Installer для всех пользователей
- [ ] 3.1-3.3: Полное покрытие тестами
- [ ] Финальное тестирование

---

## ⚠️ РИСКИ И МИТИГАЦИЯ

| Риск | Вероятность | Влияние | Митигация |
|------|-------------|---------|-----------|
| Дети найдут способ обхода | Средняя | Критичное | Named Mutex, защита процесса, аудит логов |
| Служба не стартует | Низкая | Высокое | Логирование, fallback на автозагрузку |
| Потеря конфига | Низкая | Среднее | Бэкапы, валидация при загрузке |
| Конфликты с антивирусом | Средняя | Среднее | White-listing, подписанный сертификат |

---

## ✅ CHECKLIST ГОТОВНОСТИ К PRODUCTION

- [ ] Все критические уязвимости исправлены
- [ ] Test coverage > 80%
- [ ] Документация обновлена
- [ ] Installer протестирован на чистой Windows
- [ ] Отсутствуют утечки ресурсов
- [ ] Обработка всех edge cases
- [ ] Логи пишутся корректно
- [ ] Производительность приемлема (<1% CPU в простое)
