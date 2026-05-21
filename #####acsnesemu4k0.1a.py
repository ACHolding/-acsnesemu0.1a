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
ROM_EXTENSIONS = (".sfc", ".smc", ".fig", ".swc")
BOOT_ROM_NAMES = ("boot.sfc", "boot.smc", "game.sfc", "game.smc", "rom.sfc", "rom.smc")


def discover_rom_paths(directory):
    """Find commercial SNES ROM files in a folder."""
    found = []
    try:
        names = os.listdir(directory)
    except OSError:
        return found
    for name in sorted(names, key=str.lower):
        if name.startswith("."):
            continue
        lower = name.lower()
        if not lower.endswith(ROM_EXTENSIONS):
            continue
        path = os.path.join(directory, name)
        if os.path.isfile(path) and os.path.getsize(path) >= 32768:
            found.append(path)
    return found


def build_boot_candidates():
    """Ordered list of ROM paths to try on startup."""
    seen = set()
    candidates = []

    def add(path):
        if not path:
            return
        path = os.path.abspath(path)
        if path in seen or not os.path.isfile(path):
            return
        seen.add(path)
        candidates.append(path)

    if len(sys.argv) > 1:
        add(sys.argv[1])
    for name in BOOT_ROM_NAMES:
        add(os.path.join(SCRIPT_DIR, name))
    for path in discover_rom_paths(SCRIPT_DIR):
        add(path)
    return candidates


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
        self.current_rom_path = None

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
            text="SYSTEM READY\n\nSCANNING FOR COMMERCIAL ROMs...",
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
            "Place any .sfc / .smc ROM in this folder — it auto-boots on launch.\n"
            "Or pass a ROM path: python3 acsnesemu4k0.1.1.py game.sfc"
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
        """Boot first valid commercial ROM: argv, boot.*, then any .sfc/.smc in folder."""
        candidates = build_boot_candidates()
        errors = []

        self.status_text.set(f"Scanning {len(candidates)} commercial ROM candidate(s)...")
        self.root.update_idletasks()

        for rom_path in candidates:
            try:
                self.load_rom(rom_path, auto_start=True, show_error_dialog=False)
                return
            except (OSError, ValueError) as exc:
                errors.append(f"{os.path.basename(rom_path)}: {exc}")

        found = discover_rom_paths(SCRIPT_DIR)
        if found:
            listing = "\n".join(os.path.basename(p) for p in found[:8])
            extra = f"\n(+{len(found) - 8} more)" if len(found) > 8 else ""
            self.screen_canvas.config(
                text=f"ROM BOOT FAILED\n\nFound in folder:\n{listing}{extra}\n\nFILE → LOAD ROM"
            )
            self.status_text.set(
                f"No ROM booted ({len(found)} file(s) found). Use File → Load ROM."
            )
        else:
            self.screen_canvas.config(
                text="NO COMMERCIAL ROM FOUND\n\nAdd .sfc or .smc to:\n"
                f"{SCRIPT_DIR}\n\nFILE → LOAD ROM"
            )
            self.status_text.set("No .sfc/.smc ROMs in folder. Use File → Load ROM.")

        if errors and len(errors) <= 3:
            self.status_text.set(self.status_text.get() + " | " + errors[-1][:60])

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
            self.load_rom(file_path, auto_start=True)

    def quit_app(self):
        self.is_running = False
        self.root.quit()

    def load_rom(self, file_path, auto_start=True, show_error_dialog=True):
        """Load a commercial ROM and show it in the 256x224 window."""
        if self.is_running:
            self.is_running = False

        try:
            with open(file_path, "rb") as rom_file:
                rom_data = rom_file.read()

            if len(rom_data) < 32768:
                raise ValueError(
                    f"File too small ({len(rom_data)} bytes). Need a commercial SNES ROM."
                )

            core_msg = self.core.load_rom_bytes(rom_data)
            self.rom_loaded = True
            self.current_rom_path = file_path

            rom_name = os.path.basename(file_path)
            self.header.config(
                text=f"--- {rom_name.upper()} | SNES CYTHON CORE ---"
            )
            self.status_text.set(f"Booted: {rom_name} — {core_msg}")
            self.root.title(f"{APP_NAME} {APP_VERSION} — {rom_name}")

            self._present_framebuffer()
            self.screen_canvas.config(image=self._photo, text="")
            self.run_btn.config(state=tk.NORMAL)
            self._set_play_label("Play Game", enabled=True)

            if auto_start:
                if not self.is_running:
                    self.toggle_emulation()
                else:
                    self.emulation_loop()

        except (OSError, ValueError) as exc:
            self.rom_loaded = False
            self.status_text.set(f"Error booting ROM: {exc}")
            self.screen_canvas.config(text=f"ROM BOOT ERROR\n\n{exc}")
            if show_error_dialog:
                messagebox.showerror("Load ROM", str(exc))
            raise

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
