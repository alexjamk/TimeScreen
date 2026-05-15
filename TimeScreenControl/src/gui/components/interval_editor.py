"""
TimeScreen Control - Interval Editor Dialog
User-friendly dialog for adding/editing time intervals.
"""

import tkinter as tk
from tkinter import ttk, messagebox
import datetime
from typing import Optional, Dict, Any, List


class IntervalEditor(tk.Toplevel):
    """
    Dialog for editing a time interval.
    
    Features:
    - Separate spinboxes for hours and minutes
    - Day of week checkboxes
    - Validation
    - Clean UI
    """
    
    def __init__(self, parent, interval: Optional[Dict[str, Any]] = None):
        super().__init__(parent)
        
        self.title("Добавить интервал" if not interval else "Изменить интервал")
        self.result: Optional[Dict[str, Any]] = None
        
        # Modal settings
        self.transient(parent)
        self.grab_set()
        self.resizable(False, False)
        
        # Center on parent
        self.geometry("+%d+%d" % (
            parent.winfo_rootx() + 100,
            parent.winfo_rooty() + 100
        ))
        
        # Parse existing interval if provided
        self.initial_interval = interval
        self._parse_initial_interval(interval)
        
        self._build_ui()
        self.wait_window(self)
    
    def _parse_initial_interval(self, interval: Optional[Dict[str, Any]]):
        """Parse initial interval data."""
        if interval:
            try:
                start_parts = interval["start"].split(":")
                end_parts = interval["end"].split(":")
                
                self.start_hour = int(start_parts[0])
                self.start_min = int(start_parts[1])
                self.end_hour = int(end_parts[0])
                self.end_min = int(end_parts[1])
                self.days = interval.get("days", list(range(7)))
            except (KeyError, ValueError, IndexError):
                self._set_defaults()
        else:
            self._set_defaults()
    
    def _set_defaults(self):
        """Set default values."""
        self.start_hour = 8
        self.start_min = 0
        self.end_hour = 22
        self.end_min = 0
        self.days = list(range(7))  # All days
    
    def _build_ui(self):
        """Build the dialog UI."""
        main_frame = ttk.Frame(self, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Days of week
        days_frame = ttk.LabelFrame(main_frame, text="Дни недели")
        days_frame.pack(fill=tk.X, pady=(0, 15))
        
        self.days_vars: Dict[int, tk.BooleanVar] = {}
        day_names = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
        
        days_inner = ttk.Frame(days_frame)
        days_inner.pack(pady=10)
        
        for i, day in enumerate(day_names):
            var = tk.BooleanVar(value=i in self.days)
            self.days_vars[i] = var
            
            chk = ttk.Checkbutton(
                days_inner,
                text=day,
                variable=var,
                width=3
            )
            chk.grid(row=0, column=i, padx=5)
        
        # Time frame
        time_frame = ttk.Frame(main_frame)
        time_frame.pack(fill=tk.X, pady=15)
        
        # Start time
        start_frame = ttk.LabelFrame(time_frame, text="Начало")
        start_frame.grid(row=0, column=0, padx=10, sticky="nsew")
        
        self.start_hour_var = tk.StringVar(value=str(self.start_hour).zfill(2))
        self.start_min_var = tk.StringVar(value=str(self.start_min).zfill(2))
        
        hour_label = ttk.Label(start_frame, text="Часы:")
        hour_label.grid(row=0, column=0, padx=5, pady=5, sticky=tk.W)
        
        self.start_hour_spin = ttk.Spinbox(
            start_frame,
            from_=0, to=23,
            textvariable=self.start_hour_var,
            width=3,
            format="%02.0f"
        )
        self.start_hour_spin.grid(row=0, column=1, padx=5, pady=5)
        
        min_label = ttk.Label(start_frame, text="Минуты:")
        min_label.grid(row=1, column=0, padx=5, pady=5, sticky=tk.W)
        
        self.start_min_spin = ttk.Spinbox(
            start_frame,
            from_=0, to=59,
            textvariable=self.start_min_var,
            width=3,
            format="%02.0f"
        )
        self.start_min_spin.grid(row=1, column=1, padx=5, pady=5)
        
        # End time
        end_frame = ttk.LabelFrame(time_frame, text="Конец")
        end_frame.grid(row=0, column=1, padx=10, sticky="nsew")
        
        self.end_hour_var = tk.StringVar(value=str(self.end_hour).zfill(2))
        self.end_min_var = tk.StringVar(value=str(self.end_min).zfill(2))
        
        hour_label = ttk.Label(end_frame, text="Часы:")
        hour_label.grid(row=0, column=0, padx=5, pady=5, sticky=tk.W)
        
        self.end_hour_spin = ttk.Spinbox(
            end_frame,
            from_=0, to=23,
            textvariable=self.end_hour_var,
            width=3,
            format="%02.0f"
        )
        self.end_hour_spin.grid(row=0, column=1, padx=5, pady=5)
        
        min_label = ttk.Label(end_frame, text="Минуты:")
        min_label.grid(row=1, column=0, padx=5, pady=5, sticky=tk.W)
        
        self.end_min_spin = ttk.Spinbox(
            end_frame,
            from_=0, to=59,
            textvariable=self.end_min_var,
            width=3,
            format="%02.0f"
        )
        self.end_min_spin.grid(row=1, column=1, padx=5, pady=5)
        
        # Buttons
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=15)
        
        ttk.Button(btn_frame, text="OK", command=self._ok).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_frame, text="Отмена", command=self.destroy).pack(side=tk.RIGHT)
    
    def _validate(self) -> bool:
        """Validate input data."""
        try:
            start_h = int(self.start_hour_var.get())
            start_m = int(self.start_min_var.get())
            end_h = int(self.end_hour_var.get())
            end_m = int(self.end_min_var.get())
            
            if not (0 <= start_h <= 23 and 0 <= start_m <= 59):
                messagebox.showerror("Ошибка", "Неверное время начала")
                return False
            
            if not (0 <= end_h <= 23 and 0 <= end_m <= 59):
                messagebox.showerror("Ошибка", "Неверное время конца")
                return False
            
            # Check if at least one day is selected
            selected_days = [i for i, v in self.days_vars.items() if v.get()]
            if not selected_days:
                messagebox.showerror("Ошибка", "Выберите хотя бы один день")
                return False
            
            return True
            
        except ValueError:
            messagebox.showerror("Ошибка", "Неверный формат времени")
            return False
    
    def _ok(self):
        """Handle OK button click."""
        if not self._validate():
            return
        
        try:
            start_h = int(self.start_hour_var.get())
            start_m = int(self.start_min_var.get())
            end_h = int(self.end_hour_var.get())
            end_m = int(self.end_min_var.get())
            
            start_time = datetime.time(start_h, start_m)
            end_time = datetime.time(end_h, end_m)
            
            selected_days = sorted([i for i, v in self.days_vars.items() if v.get()])
            
            self.result = {
                "start": start_time.strftime("%H:%M"),
                "end": end_time.strftime("%H:%M"),
                "days": selected_days,
            }
            
            self.destroy()
            
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось создать интервал: {e}")
