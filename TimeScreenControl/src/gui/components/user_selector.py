"""
TimeScreen Control - User Selector Component
Scrollable list of Windows users for selection.
"""

import tkinter as tk
from tkinter import ttk, messagebox
import subprocess
from typing import List


def get_all_windows_users() -> List[str]:
    """
    Get list of all local Windows users.
    
    Returns:
        List of usernames (excluding system accounts)
    """
    try:
        result = subprocess.run(
            ["net", "user"],
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
        )
        
        users = []
        lines = result.stdout.split('\n')
        
        for line in lines:
            line = line.strip()
            # Skip header/footer lines
            if not line or line.startswith('-') or 'User accounts' in line or 'command completed' in line.lower():
                continue
            
            # Parse user names (they are space-separated in columns)
            parts = line.split()
            for part in parts:
                if part and not part.startswith('-'):
                    users.append(part)
        
        # Exclude system accounts
        exclude = {
            'Administrator', 'Guest', 'DefaultAccount', 
            'WDAGUtilityAccount', 'DefaultAppPool', 'IUSR', 'IWAM'
        }
        
        return sorted([u for u in users if u not in exclude and not u.startswith('$')])
        
    except Exception as e:
        print(f"Error getting users: {e}")
        return []


class UserSelector(ttk.Frame):
    """
    Scrollable user selector with checkboxes.
    
    Features:
    - Automatic loading of Windows users
    - Scrollable list for many users
    - Select/deselect all buttons
    - Save to config on change
    """
    
    def __init__(self, parent, config_manager):
        super().__init__(parent)
        self.cfg = config_manager
        self.selected_users = set(cfg.get_controlled_users())
        self.checkboxes = {}
        
        self._build_ui()
        self._load_users()
    
    def _build_ui(self):
        """Build the UI components."""
        # Title
        title = ttk.Label(
            self,
            text="👥 Выберите контролируемых пользователей",
            font=("Arial", 14, "bold")
        )
        title.pack(pady=10)
        
        info = ttk.Label(
            self,
            text="Если список пустой - контролируются ВСЕ пользователи",
            foreground="blue"
        )
        info.pack(pady=5)
        
        # Main container with canvas for scrolling
        container = ttk.Frame(self)
        container.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Canvas and scrollbar
        self.canvas = tk.Canvas(container, highlightthickness=0)
        scrollbar = ttk.Scrollbar(container, orient=tk.VERTICAL, command=self.canvas.yview)
        
        self.scrollable_frame = ttk.Frame(self.canvas)
        
        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )
        
        self.canvas_window = self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=scrollbar.set)
        
        # Bind canvas resize to update scroll region
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        
        # Mouse wheel binding
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)
        
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Buttons frame
        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill=tk.X, padx=10, pady=10)
        
        ttk.Button(
            btn_frame,
            text="✅ Выбрать всех",
            command=self._select_all
        ).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(
            btn_frame,
            text="❌ Снять все",
            command=self._deselect_all
        ).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(
            btn_frame,
            text="💾 Сохранить",
            command=self._save_selection
        ).pack(side=tk.RIGHT, padx=5)
    
    def _on_canvas_configure(self, event):
        """Update scrollable frame width on canvas resize."""
        self.canvas.itemconfig(self.canvas_window, width=event.width)
    
    def _on_mousewheel(self, event):
        """Handle mouse wheel scrolling."""
        self.canvas.yview_scroll(int(-1*(event.delta/120)), "units")
    
    def _load_users(self):
        """Load users from Windows and create checkboxes."""
        users = get_all_windows_users()
        
        if not users:
            ttk.Label(
                self.scrollable_frame,
                text="Не удалось получить список пользователей",
                foreground="red"
            ).pack(pady=20)
            return
        
        # Create checkbox for each user
        for user in users:
            var = tk.BooleanVar(value=user.lower() in [u.lower() for u in self.selected_users])
            chk = ttk.Checkbutton(
                self.scrollable_frame,
                text=user,
                variable=var,
                command=lambda u=user, v=var: self._toggle_user(u, v.get())
            )
            chk.pack(anchor=tk.W, padx=20, pady=2)
            self.checkboxes[user] = var
    
    def _toggle_user(self, username: str, selected: bool):
        """Handle user checkbox toggle."""
        if selected:
            self.selected_users.add(username)
        else:
            self.selected_users.discard(username)
    
    def _select_all(self):
        """Select all users."""
        for user, var in self.checkboxes.items():
            var.set(True)
            self.selected_users.add(user)
    
    def _deselect_all(self):
        """Deselect all users."""
        for var in self.checkboxes.values():
            var.set(False)
        self.selected_users.clear()
    
    def _save_selection(self):
        """Save selection to config."""
        users_list = sorted(list(self.selected_users))
        
        if self.cfg.set_controlled_users(users_list):
            status = "все пользователи" if not users_list else f"{len(users_list)} пользователей"
            messagebox.showinfo(
                "Сохранено",
                f"Контролируемые пользователи сохранены.\n\n"
                f"Будут контролироваться: {status}"
            )
        else:
            messagebox.showerror("Ошибка", "Не удалось сохранить настройки")
