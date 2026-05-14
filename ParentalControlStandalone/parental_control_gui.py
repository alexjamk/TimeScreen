import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import json
import os
import sys
import time
import threading
import hashlib
import datetime
import subprocess
import ctypes
import socket

# --- Конфигурация ---
CONFIG_FILE = "pc_config.json"
APP_NAME = "TimeScreen Control"

# --- Утилиты ---
def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

def run_as_admin():
    if not is_admin():
        ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, " ".join(sys.argv), None, 1)
        sys.exit()

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def get_current_time_str():
    return datetime.datetime.now().strftime("%H:%M")

# --- Менеджер конфигурации ---
class ConfigManager:
    def __init__(self):
        self.config = self.load()

    def load(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        return {"password_hash": None, "intervals": [], "blocked": False}

    def save(self):
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.config, f, indent=4)

    def set_password(self, pwd):
        self.config["password_hash"] = hash_password(pwd)
        self.save()

    def check_password(self, pwd):
        if not self.config["password_hash"]:
            return True
        return self.config["password_hash"] == hash_password(pwd)

    def set_intervals(self, intervals):
        # intervals: список строк "HH:MM-HH:MM"
        self.config["intervals"] = intervals
        self.save()

    def is_allowed_time(self):
        if not self.config["intervals"]:
            return True
        
        now = datetime.datetime.now().time()
        for interval in self.config["intervals"]:
            try:
                start_str, end_str = interval.split('-')
                start = datetime.datetime.strptime(start_str, "%H:%M").time()
                end = datetime.datetime.strptime(end_str, "%H:%M").time()
                
                if start <= end:
                    if start <= now <= end:
                        return True
                else: # Переход через полночь
                    if now >= start or now <= end:
                        return True
            except:
                continue
        return False

    def get_next_change_time(self):
        # Возвращает время до следующего события (блокировка или разблокировка)
        if not self.config["intervals"]:
            return None, "always_allowed"
        
        now = datetime.datetime.now()
        events = []
        
        for interval in self.config["intervals"]:
            try:
                start_str, end_str = interval.split('-')
                start = datetime.datetime.combine(now.date(), datetime.datetime.strptime(start_str, "%H:%M").time())
                end = datetime.datetime.combine(now.date(), datetime.datetime.strptime(end_str, "%H:%M").time())
                
                if start < now and end < now: # Интервал прошел сегодня
                    continue
                if start > now:
                    events.append((start, "unlock"))
                if end > now:
                    events.append((end, "lock"))
                    
                # Обработка перехода через полночь (упрощенно)
                if start > end: 
                    # Если сейчас между end и start, то следующий событие start завтра
                    pass 
            except:
                continue
        
        if not events:
            # Проверка на завтрашний день (упрощено)
            return None, "unknown"
            
        events.sort(key=lambda x: x[0])
        next_event = events[0]
        delta = next_event[0] - now
        return delta, next_event[1]

# --- Экран блокировки ---
class LockScreen(tk.Tk):
    def __init__(self, config_manager):
        super().__init__()
        self.config_manager = config_manager
        self.title("Компьютер заблокирован")
        self.attributes('-fullscreen', True)
        self.attributes('-topmost', True)
        self.configure(bg="#1a1a1a")
        
        # Блокировка закрытия
        self.protocol("WM_DELETE_WINDOW", lambda: None)
        
        # Фрейм по центру
        center_frame = tk.Frame(self, bg="#2d2d2d", padx=40, pady=40)
        center_frame.place(relx=0.5, rely=0.5, anchor="center")
        
        tk.Label(center_frame, text="ВРЕМЯ ИСТЕКЛО", font=("Arial", 24, "bold"), fg="#ff4444", bg="#2d2d2d").pack(pady=(0, 20))
        tk.Label(center_frame, text="Компьютер заблокирован родителем.", font=("Arial", 12), fg="#cccccc", bg="#2d2d2d").pack(pady=(0, 30))
        
        tk.Label(center_frame, text="Пароль администратора:", font=("Arial", 10), fg="#aaaaaa", bg="#2d2d2d").pack(anchor="w")
        self.pass_entry = tk.Entry(center_frame, show="*", font=("Arial", 14), width=20)
        self.pass_entry.pack(pady=(5, 20), fill="x")
        self.pass_entry.bind("<Return>", lambda e: self.try_unlock())
        self.pass_entry.focus_set()
        
        btn_frame = tk.Frame(center_frame, bg="#2d2d2d")
        btn_frame.pack(fill="x")
        
        self.btn_unlock = tk.Button(btn_frame, text="Разблокировать", command=self.try_unlock, bg="#4CAF50", fg="white", font=("Arial", 12, "bold"), relief="flat", padx=20, pady=10)
        self.btn_unlock.pack(side="left", padx=5)
        
        tk.Button(btn_frame, text="Выключить ПК", command=self.shutdown, bg="#f44336", fg="white", font=("Arial", 12), relief="flat", padx=20, pady=10).pack(side="left", padx=5)
        tk.Button(btn_frame, text="Перезагрузить", command=self.restart, bg="#FF9800", fg="white", font=("Arial", 12), relief="flat", padx=20, pady=10).pack(side="left", padx=5)
        
        self.status_label = tk.Label(center_frame, text="", fg="#ff4444", bg="#2d2d2d", font=("Arial", 10))
        self.status_label.pack(pady=(10,0))

    def try_unlock(self):
        pwd = self.pass_entry.get()
        if self.config_manager.check_password(pwd):
            self.destroy()
        else:
            self.status_label.config(text="Неверный пароль!")
            self.pass_entry.delete(0, tk.END)

    def shutdown(self):
        if messagebox.askyesno("Подтверждение", "Выключить компьютер?"):
            os.system("shutdown /s /t 1")

    def restart(self):
        if messagebox.askyesno("Подтверждение", "Перезагрузить компьютер?"):
            os.system("shutdown /r /t 1")

# -- Мини-виджет таймера (поверх окон) --
class TimerWidget(tk.Tk):
    def __init__(self, config_manager):
        super().__init__()
        self.config_manager = config_manager
        self.overrideredirect(True) # Убрать рамки
        self.attributes('-topmost', True) # Всегда сверху
        self.geometry("+10+10") # Позиция左上角
        
        self.label = tk.Label(self, text="", font=("Consolas", 16, "bold"), bg="black", fg="#00ff00", padx=10, pady=5)
        self.label.pack()
        
        # Прозрачность фона (работает на Windows)
        self.wm_attributes("-transparentcolor", "black")
        
        self.update_timer()

    def update_timer(self):
        allowed = self.config_manager.is_allowed_time()
        delta, status = self.config_manager.get_next_change_time()
        
        if allowed:
            if delta:
                mins = int(delta.total_seconds() // 60)
                secs = int(delta.total_seconds() % 60)
                text = f"До блокировки: {mins:02d}:{secs:02d}"
                self.label.config(fg="#00ff00") # Зеленый
            else:
                text = "Доступ разрешен"
                self.label.config(fg="#00ff00")
        else:
            text = "ЗАБЛОКИРОВАНО"
            self.label.config(fg="#ff0000") # Красный
            
        self.label.config(text=text)
        
        # Обновляем каждую секунду
        self.after(1000, self.update_timer)

# --- Главное окно настроек ---
class MainApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.config_manager = ConfigManager()
        self.title(APP_NAME)
        self.geometry("500x600")
        self.resizable(False, False)
        
        # Стили
        style = ttk.Style()
        style.theme_use('clam')
        style.configure("TButton", padding=10, font=("Arial", 10))
        style.configure("TLabel", font=("Arial", 11))
        
        self.create_widgets()
        self.check_status()

    def create_widgets(self):
        # Заголовок
        header = tk.Frame(self, bg="#2c3e50", height=80)
        header.pack(fill="x")
        tk.Label(header, text=APP_NAME, font=("Arial", 20, "bold"), bg="#2c3e50", fg="white").pack(pady=20)
        
        # Контент
        content = tk.Frame(self, padx=20, pady=20)
        content.pack(fill="both", expand=True)
        
        # Статус
        self.status_var = tk.StringVar(value="Загрузка...")
        tk.Label(content, textvariable=self.status_var, font=("Arial", 12, "bold"), fg="#333").pack(anchor="w", pady=(0, 20))
        
        # Настройка пароля
        pwd_frame = tk.LabelFrame(content, text="Безопасность", padx=15, pady=15)
        pwd_frame.pack(fill="x", pady=10)
        
        tk.Label(pwd_frame, text="Пароль администратора:").pack(anchor="w")
        self.pass_entry = tk.Entry(pwd_frame, show="*", font=("Arial", 12))
        self.pass_entry.pack(fill="x", pady=(5, 10))
        
        tk.Button(pwd_frame, text="Установить/Изменить пароль", command=self.set_password).pack(fill="x")
        
        # Настройка времени
        time_frame = tk.LabelFrame(content, text="Расписание доступа", padx=15, pady=15)
        time_frame.pack(fill="x", pady=10)
        
        tk.Label(time_frame, text="Интервалы (ЧЧ:ММ-ЧЧ:ММ), через запятую:").pack(anchor="w")
        tk.Label(time_frame, text="Пример: 08:00-22:00, 14:00-15:00", font=("Arial", 9), fg="#666").pack(anchor="w")
        
        self.time_entry = tk.Entry(time_frame, font=("Arial", 12))
        self.time_entry.pack(fill="x", pady=(5, 10))
        
        tk.Button(time_frame, text="Сохранить расписание", command=self.save_schedule).pack(fill="x")
        
        # Управление службой
        svc_frame = tk.Frame(content)
        svc_frame.pack(fill="x", pady=20)
        
        self.btn_start = tk.Button(svc_frame, text="Запустить защиту", command=self.start_protection, bg="#27ae60", fg="white", font=("Arial", 11, "bold"))
        self.btn_start.pack(fill="x", pady=5)
        
        self.btn_stop = tk.Button(svc_frame, text="Остановить защиту", command=self.stop_protection, bg="#c0392b", fg="white", font=("Arial", 11, "bold"), state="disabled")
        self.btn_stop.pack(fill="x", pady=5)
        
        # Таймер виджет кнопка
        tk.Button(content, text="Показать таймер поверх окон", command=self.show_timer).pack(fill="x", pady=10)
        
        # Инфо
        tk.Label(content, text="Для полной защиты запустите программу от имени Администратора.", font=("Arial", 9), fg="#e74c3c", wraplength=400).pack(pady=10)

    def check_status(self):
        has_pass = self.config_manager.config.get("password_hash") is not None
        if has_pass:
            self.status_var.set("Статус: Настроено (Пароль задан)")
            self.pass_entry.insert(0, "********")
        else:
            self.status_var.set("Статус: Требуется настройка!")
            
        # Проверка запущенного процесса (упрощенно)
        # В реальном приложении нужно проверять наличие процесса службы

    def set_password(self):
        pwd = self.pass_entry.get()
        if len(pwd) < 4:
            messagebox.showerror("Ошибка", "Пароль должен быть длиннее 4 символов")
            return
        self.config_manager.set_password(pwd)
        messagebox.showinfo("Успех", "Пароль установлен!")
        self.check_status()

    def save_schedule(self):
        raw = self.time_entry.get()
        if not raw:
            messagebox.showerror("Ошибка", "Введите интервалы")
            return
        intervals = [x.strip() for x in raw.split(',')]
        # Простая валидация
        valid = True
        for i in intervals:
            if '-' not in i:
                valid = False
        if not valid:
            messagebox.showerror("Ошибка", "Неверный формат. Используйте ЧЧ:ММ-ЧЧ:ММ")
            return
            
        self.config_manager.set_intervals(intervals)
        messagebox.showinfo("Успех", "Расписание сохранено!")

    def start_protection(self):
        if not self.config_manager.config.get("password_hash"):
            messagebox.showwarning("Внимание", "Сначала установите пароль!")
            return
        if not self.config_manager.config.get("intervals"):
            messagebox.showwarning("Внимание", "Сначала задайте расписание!")
            return
            
        # Запуск в фоне (имитация службы для простоты)
        # В реальном .exe это будет отдельный процесс или служба
        threading.Thread(target=self.run_monitor, daemon=True).start()
        self.btn_start.config(state="disabled")
        self.btn_stop.config(state="normal")
        messagebox.showinfo("Запущено", "Мониторинг времени активирован.\nТаймер появится в углу экрана.")
        self.show_timer()

    def stop_protection(self):
        # Требует пароль
        pwd = simpledialog.askstring("Подтверждение", "Введите пароль администратора для остановки:", show="*")
        if pwd and self.config_manager.check_password(pwd):
            self.btn_start.config(state="normal")
            self.btn_stop.config(state="disabled")
            messagebox.showinfo("Стоп", "Защита остановлена.")
            # Здесь нужно убить процесс монитора, в рамках одного скрипта просто флаг
        elif pwd:
            messagebox.showerror("Ошибка", "Неверный пароль")

    def run_monitor(self):
        while True:
            time.sleep(5)
            if not self.config_manager.is_allowed_time():
                # Запуск экрана блокировки
                # В реальном приложении нужно создавать новое окно в главном потоке или использовать IPC
                # Для демо просто вызываем (это заблокирует поток, поэтому лучше отдельный процесс)
                # Здесь упрощенно:
                print("BLOCKING NOW!") 
                # subprocess.run([sys.executable, __file__, "--lock"]) 

    def show_timer(self):
        # Создание отдельного окна таймера
        timer = TimerWidget(self.config_manager)
        timer.mainloop()

if __name__ == "__main__":
    # Проверка прав админа для критических операций
    # if len(sys.argv) > 1 and sys.argv[1] == "--lock":
    #     config = ConfigManager()
    #     app = LockScreen(config)
    #     app.mainloop()
    # else:
        app = MainApp()
        app.mainloop()
