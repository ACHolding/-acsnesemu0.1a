import os
import sys
import tkinter as tk
from tkinter import filedialog, messagebox

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SCREEN_W = 256
SCREEN_H = 224

BG_COLOR = "#000000"
TEXT_COLOR = "#3399FF"
PANEL_BG = "#050515"
ACCENT_COLOR = "#0055FF"

# Targeting ~60 frames per second (1000ms / 60 frames = ~16.67ms per frame)
FPS_TARGET_MS = 16

APP_VERSION = "0.1a"
APP_NAME = "ac's snes emu"


def _load_cython_core():
    if SCRIPT_DIR not in sys.path:
        sys.path.insert(0, SCRIPT_DIR)
    build_dir = os.path.join(SCRIPT_DIR, ".pyxbld")
    os.makedirs(build_dir, exist_ok=True)
    try:
        import pyximport

        # Python 3.14 target: standard build flags ensure backward compatibility
        pyximport.install(
            build_dir=build_dir,
            setup_args={"include_dirs": []},
            language_level=3,
        )
        import snes_cython_core

        return snes_cython_core
    except Exception as exc:
        print("Error compiling Cython core. Install Cython and a C compiler (clang/gcc).")
        print(f"Details: {exc}")
        sys.exit(1)


snes_cython_core = _load_cython_core()


class SNESEmulatorGUI:

    def __init__(self, root):
        self.root = root
        self.root.title(f"{APP_NAME} {APP_VERSION} (AUTO-BOOT / 60 FPS)")
        self.root.geometry("600x480")
        self.root.configure(bg=BG_COLOR)

        self.core = snes_cython_core.SNESCore()
        self.rom_loaded = False
        self.is_running = False

        self._photo = None
        self._ppm_header = f"P6 {SCREEN_W} {SCREEN_H} 255 ".encode("ascii")

        self.build_ui()

        # Trigger auto-boot sequence shortly after UI initializes
        self.root.after(200, self.auto_boot)

    def build_ui(self):
        # ---- menubar (black + electric blue, cat style) ----
        menu_opts = dict(
            bg=BG_COLOR,
            fg=TEXT_COLOR,
            activebackground=ACCENT_COLOR,
            activeforeground=BG_COLOR,
            borderwidth=0,
        )
        menubar = tk.Menu(self.root, **menu_opts)

        # File menu: Load ROM, Play Game, Exit
        filemenu = tk.Menu(menubar, tearoff=0, **menu_opts)
        filemenu.add_command(
            label="Load ROM…",
            accelerator="Ctrl+O",
            command=self.open_rom_dialog,
        )
        self.play_menu_index = 1  # remember position for label updates
        filemenu.add_command(
            label="Play Game",
            accelerator="Space",
            command=self.toggle_emulation,
            state=tk.DISABLED,
        )
        filemenu.add_separator()
        filemenu.add_command(
            label="Exit",
            accelerator="Ctrl+Q",
            command=self.quit_app,
        )
        menubar.add_cascade(label="File", menu=filemenu)
        self.filemenu = filemenu

        # Help menu: Help, About
        helpmenu = tk.Menu(menubar, tearoff=0, **menu_opts)
        helpmenu.add_command(label="Help", accelerator="F1", command=self.show_help)
        helpmenu.add_separator()
        helpmenu.add_command(label="About", command=self.show_about)
        menubar.add_cascade(label="Help", menu=helpmenu)

        self.root.config(menu=menubar)

        # ---- hotkeys ----
        self.root.bind_all("<Control-o>", lambda _e: self.open_rom_dialog())
        self.root.bind_all("<Control-q>", lambda _e: self.quit_app())
        self.root.bind_all("<space>", lambda _e: self.toggle_emulation())
        self.root.bind_all("<F1>", lambda _e: self.show_help())

        # ---- main frame ----
        frame = tk.Frame(self.root, bg=BG_COLOR)
        frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)

        self.header = tk.Label(
            frame,
            text="--- SNES CYTHON CORE (60 FPS LOOP) ---",
            font=("Courier", 14, "bold"),
            bg=BG_COLOR,
            fg=TEXT_COLOR,
        )
        self.header.pack(pady=5)

        self.display_screen = tk.Frame(
            frame,
            width=SCREEN_W,
            height=SCREEN_H,
            bg=PANEL_BG,
            highlightbackground=ACCENT_COLOR,
            highlightthickness=2,
        )
        self.display_screen.pack(pady=15)
        self.display_screen.pack_propagate(False)

        self.screen_canvas = tk.Label(
            self.display_screen,
            bg=PANEL_BG,
            fg=TEXT_COLOR,
            font=("Courier", 9),
            text="SYSTEM READY\n\nSEARCHING FOR BOOT ROM...",
        )
        self.screen_canvas.pack(expand=True)

        self.run_btn = tk.Button(
            frame,
            text="START EMULATION",
            command=self.toggle_emulation,
            state=tk.DISABLED,
            bg=PANEL_BG,
            fg=TEXT_COLOR,
            activebackground=ACCENT_COLOR,
            activeforeground=BG_COLOR,
        )
        self.run_btn.pack(pady=5)

        self.status_text = tk.StringVar(
            value="Status: Cython core ready. Python 3.14 target."
        )
        status_bar = tk.Label(
            self.root,
            textvariable=self.status_text,
            bd=1,
            relief=tk.SUNKEN,
            anchor=tk.W,
            bg=PANEL_BG,
            fg=TEXT_COLOR,
            font=("Courier", 9),
        )
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)

    # ---- menu actions ----

    def show_help(self):
        msg = (
            "Controls\n"
            "────────\n"
            "  Ctrl+O   Load ROM\n"
            "  Space    Play / Pause\n"
            "  F1       Help\n"
            "  Ctrl+Q   Exit\n\n"
            "Supports commercial .sfc / .smc / .fig / .swc dumps.\n"
            "LoROM, HiROM, and ExHiROM headers are detected automatically.\n\n"
            "Drop boot.sfc in this folder or pass a ROM path as argv[1]."
        )
        messagebox.showinfo("Help — ac's snes emu", msg)

    def show_about(self):
        msg = (
            f"{APP_NAME} {APP_VERSION}\n"
            "────────────────────────────\n"
            "SNES Cython core • 60 FPS loop\n"
            "Python 3.14 target • Tkinter UI\n\n"
            "Team Flames / Samsoft\n"
            "made with 🐾 by catsan"
        )
        messagebox.showinfo("About", msg)

    def _set_play_label(self, label, enabled=True):
        """Update the File → Play Game entry label/state."""
        try:
            self.filemenu.entryconfig(
                self.play_menu_index,
                label=label,
                state=tk.NORMAL if enabled else tk.DISABLED,
            )
        except tk.TclError:
            pass

    # ---- boot / rom handling ----

    def auto_boot(self):
        """Automatically load a ROM from sys.argv or default 'boot.sfc'."""
        rom_path = None

        if len(sys.argv) > 1 and os.path.isfile(sys.argv[1]):
            rom_path = sys.argv[1]
        else:
            default_rom = os.path.join(SCRIPT_DIR, "boot.sfc")
            if os.path.isfile(default_rom):
                rom_path = default_rom

        if rom_path:
            self.load_rom(rom_path)
        else:
            self.status_text.set("No ROM found. Use File → Load ROM or add boot.sfc.")
            self.screen_canvas.config(text="NO ROM FOUND\n\nFILE → LOAD ROM")

    def open_rom_dialog(self):
        file_path = filedialog.askopenfilename(
            initialdir=SCRIPT_DIR,
            title="Load SNES ROM",
            filetypes=[
                ("SNES ROMs", "*.sfc *.smc *.fig *.swc"),
                ("Super Famicom ROM", "*.sfc"),
                ("Super NES ROM", "*.smc"),
                ("All Files", "*.*"),
            ],
        )
        if file_path:
            was_running = self.is_running
            if was_running:
                self.is_running = False
            self.load_rom(file_path, auto_start=was_running)

    def quit_app(self):
        self.is_running = False
        self.root.quit()

    def load_rom(self, file_path, auto_start=True):
        """Headless ROM loading."""
        try:
            with open(file_path, "rb") as rom_file:
                rom_data = rom_file.read()

            core_msg = self.core.load_rom_bytes(rom_data)
            self.rom_loaded = True

            rom_name = os.path.basename(file_path)
            self.status_text.set(f"Loaded: {rom_name} — {core_msg}")

            self._present_framebuffer()
            self.screen_canvas.config(image=self._photo, text="")
            self.run_btn.config(state=tk.NORMAL)
            self._set_play_label("Play Game", enabled=True)

            if auto_start and not self.is_running:
                self.toggle_emulation()

        except (OSError, ValueError) as exc:
            self.status_text.set(f"Error booting ROM: {exc}")
            self.screen_canvas.config(text="ROM LOAD ERROR")
            messagebox.showerror("Load ROM", str(exc))

    def _present_framebuffer(self):
        try:
            rgb = self.core.get_framebuffer()
            self._photo = tk.PhotoImage(
                master=self.root,
                width=SCREEN_W,
                height=SCREEN_H,
                data=self._ppm_header + rgb,
                format="PPM",
            )
        except tk.TclError as e:
            self.status_text.set(f"Framebuffer error: {e}")

    def toggle_emulation(self):
        if not self.rom_loaded:
            return

        if self.is_running:
            self.is_running = False
            self.run_btn.config(text="RESUME EMULATION")
            self._set_play_label("Play Game", enabled=True)
            self.status_text.set("Status: Paused.")
        else:
            self.is_running = True
            self.run_btn.config(text="PAUSE EMULATION")
            self._set_play_label("Pause Game", enabled=True)
            self.status_text.set("Status: Running at 60 FPS...")
            self.emulation_loop()

    def emulation_loop(self):
        """Asynchronous execution loop targeting 60 FPS."""
        if not self.is_running or not self.rom_loaded:
            return

        self.core.step_frame()
        self._present_framebuffer()

        # Tkinter loop scheduling callback (~16.6ms)
        self.root.after(FPS_TARGET_MS, self.emulation_loop)


if __name__ == "__main__":
    root = tk.Tk()
    app = SNESEmulatorGUI(root)
    root.mainloop()
