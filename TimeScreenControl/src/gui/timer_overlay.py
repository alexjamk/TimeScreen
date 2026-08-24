"""
TimeScreen Control - Timer Overlay Component
Draggable, configurable timer showing remaining time.
"""

import tkinter as tk
from typing import Optional
import json
import os

from config.paths import TIMER_STATE_PATH


class TimerOverlay:
    """
    Draggable timer overlay that shows remaining time until next event.
    
    Features:
    - Draggable by mouse
    - Position saved to config
    - Context menu (hide/show/reset position)
    - Always on top
    - Configurable appearance
    """
    
    def __init__(self, parent, config_manager):
        self.cfg = config_manager
        self.parent = parent
        self.window: Optional[tk.Toplevel] = None
        self.label: Optional[tk.Label] = None
        
        # Drag state
        self._drag_data = {"x": 0, "y": 0}
        
        # Visibility state
        self._visible = False
        
        # Update callback
        self._update_id = None
        self._preview_mode = False
    
    def create(self):
        """Create the timer window."""
        if self.window is not None:
            return
        
        self.window = tk.Toplevel(self.parent)
        self.window.overrideredirect(True)  # No window decorations
        self.window.attributes("-topmost", True)
        
        # Set position from config
        x, y = self._get_user_position()
        self.window.geometry(f"+{x}+{y}")
        
        # Semi-transparent background frame
        self.frame = tk.Frame(
            self.window,
            bg="#1a1a2e",
            cursor="fleur",  # Flower cursor for dragging
            relief=tk.RIDGE,
            borderwidth=2
        )
        self.frame.pack(fill=tk.BOTH, expand=True)
        
        # Timer label
        self.label = tk.Label(
            self.frame,
            text="--:--:--",
            font=("Consolas", 14, "bold"),
            fg="#ffffff",
            bg="#1a1a2e",
            padx=15,
            pady=8
        )
        self.label.pack()
        
        # Bind drag/context events to both frame and label so dragging works on text.
        for widget in (self.frame, self.label):
            widget.bind("<ButtonPress-1>", self._on_drag_start)
            widget.bind("<ButtonRelease-1>", self._on_drag_end)
            widget.bind("<B1-Motion>", self._on_drag_motion)
            widget.bind("<Button-3>", self._show_context_menu)
        
        # Initially hide if configured
        if not self.cfg.show_timer():
            self.window.withdraw()
        else:
            self._visible = True
    
    def destroy(self):
        """Destroy the timer window."""
        if self._update_id:
            try:
                self.parent.after_cancel(self._update_id)
            except tk.TclError:
                pass
            self._update_id = None
        
        if self.window:
            try:
                if self.window.winfo_exists():
                    self.window.destroy()
            except tk.TclError:
                pass
            self.window = None
            self.frame = None
            self.label = None
    
    def _on_drag_start(self, event):
        """Start dragging."""
        self._drag_data["x"] = event.x
        self._drag_data["y"] = event.y
    
    def _on_drag_motion(self, event):
        """Handle drag motion."""
        if self.window is None:
            return
        
        x = self.window.winfo_x() + event.x - self._drag_data["x"]
        y = self.window.winfo_y() + event.y - self._drag_data["y"]
        
        self.window.geometry(f"+{x}+{y}")
    
    def _on_drag_end(self, event):
        """End dragging - save position."""
        if self.window is None:
            return
        
        x = self.window.winfo_x()
        y = self.window.winfo_y()
        
        self._save_user_position(x, y)
    
    def _show_context_menu(self, event):
        """Show context menu on right-click."""
        menu = tk.Menu(self.window, tearoff=0)
        
        if self._visible:
            menu.add_command(label="Скрыть", command=self.hide)
        else:
            menu.add_command(label="Показать", command=self.show)
        
        menu.add_separator()
        menu.add_command(label="Сбросить позицию", command=self._reset_position)
        menu.add_command(label="Закрыть", command=self.hide)
        
        menu.post(event.x_root, event.y_root)
    
    def _reset_position(self):
        """Reset timer position to default."""
        if self.window:
            self.window.geometry("+100+100")
            self._save_user_position(100, 100)

    def _get_user_position(self):
        """Read movable UI state from the current user's profile, not shared config."""
        try:
            data = json.loads(TIMER_STATE_PATH.read_text(encoding="utf-8"))
            x, y = data["position"]
            return int(x), int(y)
        except (OSError, ValueError, KeyError, TypeError):
            return self.cfg.get_timer_position()

    @staticmethod
    def _save_user_position(x, y):
        try:
            TIMER_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
            temp = TIMER_STATE_PATH.with_suffix(".tmp")
            temp.write_text(json.dumps({"position": [int(x), int(y)]}), encoding="utf-8")
            os.replace(str(temp), str(TIMER_STATE_PATH))
        except OSError:
            pass
    
    def show(self):
        """Show the timer."""
        if self.window:
            self.window.deiconify()
            self._visible = True
    
    def hide(self):
        """Hide the timer."""
        if self.window:
            self.window.withdraw()
            self._visible = False
    
    def toggle(self):
        """Toggle visibility."""
        if self._visible:
            self.hide()
        else:
            self.show()
    
    def update_time(self, seconds: Optional[int], event_type: str):
        """
        Update timer display.

        Args:
            seconds: Seconds until event, or None
            event_type: "lock", "unlock", "grace", or "blocked_no_schedule"
        """
        if self.label is None:
            return

        if seconds is None:
            if event_type == "blocked_no_schedule":
                self.label.config(text="Заблокировано", fg="#e94560")
            else:
                self.label.config(text="Пауза", fg="#ffd700")
            return

        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60

        if event_type == "grace":
            self.label.config(text=f"Грейс {minutes:02d}:{secs:02d}", fg="#ffd43b")
        elif event_type == "lock":
            self.label.config(text=f"До блокировки {hours:02d}:{minutes:02d}:{secs:02d}", fg="#ff6b6b")
        else:
            self.label.config(text=f"До разблокировки {hours:02d}:{minutes:02d}:{secs:02d}", fg="#51cf66")
    def start_updates(self):
        """Start periodic timer updates."""
        self._preview_mode = False
        self._do_update()

    def start_preview(self):
        """Show a movable preview without requiring protection to be enabled."""
        self._preview_mode = True
        self.update_time(10 * 60, "grace")

    def _do_update(self):
        """Perform timer update and schedule next."""
        if self._preview_mode:
            return

        from config.manager import ConfigManager

        cfg = ConfigManager(read_only=True)
        seconds, event_type = cfg.get_next_event()

        self.update_time(seconds, event_type)

        # Schedule next update in 1 second
        self._update_id = self.parent.after(1000, self._do_update)


def run_timer_overlay():
    """Run the timer overlay as a standalone process."""
    from config.manager import ConfigManager
    from config.paths import AGENT_PID

    cfg = ConfigManager(read_only=True)
    username = os.environ.get("USERNAME", "")
    if not cfg.is_enabled() or not cfg.show_timer() or not cfg.is_controlled_user(username):
        return

    root = tk.Tk()
    root.withdraw()

    try:
        AGENT_PID.parent.mkdir(parents=True, exist_ok=True)
        AGENT_PID.write_text(str(os.getpid()), encoding="utf-8")
    except Exception:
        pass

    overlay = TimerOverlay(root, cfg)
    overlay.create()
    overlay.show()
    overlay.start_updates()

    def monitor_config():
        current = ConfigManager(read_only=True)
        if (not current.is_enabled() or not current.show_timer()
                or not current.is_controlled_user(os.environ.get("USERNAME", ""))):
            root.quit()
            return
        root.after(1000, monitor_config)

    root.after(1000, monitor_config)

    try:
        root.mainloop()
    finally:
        overlay.destroy()
        try:
            if AGENT_PID.exists():
                AGENT_PID.unlink()
        except Exception:
            pass
