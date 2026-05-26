from djitellopy import Tello
import tkinter as tk
from tkinter import font as tkfont
import threading
import time
import mission_v2
import detection
# ─────────────────────────────────────────────
#  Estado global
# ─────────────────────────────────────────────
tello = None
camera_running = [False]
camera_thread = None
selected_class_id = None
battery_poll_thread = None
battery_poll_running = False
record_enabled = False

# ─────────────────────────────────────────────
#  Paleta de colores
# ─────────────────────────────────────────────
BG        = "#0d0f14"
PANEL     = "#13161e"
ACCENT    = "#00e5ff"
ACCENT2   = "#ff4c4c"
TEXT      = "#e8eaf0"
TEXT_DIM  = "#4a5060"
SUCCESS   = "#00e676"
WARNING   = "#ffab00"
BORDER    = "#1e2330"

# ─────────────────────────────────────────────
#  Helpers UI.
# ─────────────────────────────────────────────
def set_status(msg, color=TEXT):
    status_var.set(msg)
    status_label.config(fg=color)

def set_log(msg):
    log_text.config(state="normal")
    timestamp = time.strftime("%H:%M:%S")
    log_text.insert("end", f"[{timestamp}]  {msg}\n")
    log_text.see("end")
    log_text.config(state="disabled")

def update_battery_display(value):
    pct = int(value)
    battery_var.set(f"{pct}%")
    if pct > 50:
        battery_label.config(fg=SUCCESS)
    elif pct > 20:
        battery_label.config(fg=WARNING)
    else:
        battery_label.config(fg=ACCENT2)
    # Actualizar barra
    battery_canvas.delete("bar")
    w = int((pct / 100) * 180)
    color = SUCCESS if pct > 50 else (WARNING if pct > 20 else ACCENT2)
    battery_canvas.create_rectangle(0, 0, w, 14, fill=color, outline="", tags="bar")

def set_object_label(class_id):
    if class_id is not None:
        name = detection.model.names[class_id]
        object_var.set(f"TARGET  ›  {name.upper()}  (id={class_id})")
        object_label.config(fg=ACCENT)
    else:
        object_var.set("TARGET  ›  sin seleccionar")
        object_label.config(fg=TEXT_DIM)

def btn_style(state="normal"):
    """Devuelve kwargs de color según estado."""
    if state == "active":
        return dict(bg=ACCENT, fg=BG, activebackground=ACCENT, activeforeground=BG)
    if state == "danger":
        return dict(bg=ACCENT2, fg=TEXT, activebackground="#cc3333", activeforeground=TEXT)
    return dict(bg=PANEL, fg=ACCENT, activebackground=BORDER, activeforeground=ACCENT)

def make_button(parent, text, command, state="normal", width=18):
    cfg = btn_style(state)
    b = tk.Button(
        parent, text=text, command=command,
        relief="flat", bd=0, padx=12, pady=8,
        font=mono_bold, cursor="hand2", width=width,
        **cfg
    )
    b.bind("<Enter>", lambda e: b.config(bg=ACCENT if state == "active" else BORDER))
    b.bind("<Leave>", lambda e: b.config(bg=cfg["bg"]))
    return b

def make_separator(parent):
    f = tk.Frame(parent, bg=BORDER, height=1)
    f.pack(fill="x", pady=8)

# ─────────────────────────────────────────────
#  Lógica de la aplicación
# ─────────────────────────────────────────────
def poll_battery():
    """Hilo que refresca la batería cada 10 s."""
    global battery_poll_running
    while battery_poll_running and tello:
        try:
            batt = tello.get_battery()
            window.after(0, update_battery_display, batt)
        except Exception:
            pass
        time.sleep(10)

def connect_click():
    global tello, battery_poll_running, battery_poll_thread
    set_status("Conectando…", WARNING)
    set_log("Intentando conectar con el Tello…")
    try:
        tello = Tello()
        tello.connect()
        batt = tello.get_battery()
        tello.streamon()
        update_battery_display(batt)
        set_status("✓  Conectado", SUCCESS)
        set_log(f"Tello conectado. Batería: {batt}%")
        connect_btn.config(state="disabled", bg=TEXT_DIM, fg=BG)
        takeoff_btn.config(state="normal")
        land_btn.config(state="normal")
        select_btn.config(state="normal")
        # Iniciar polling de batería
        battery_poll_running = True
        battery_poll_thread = threading.Thread(target=poll_battery, daemon=True)
        battery_poll_thread.start()
    except Exception as e:
        set_status("✗  Error de conexión", ACCENT2)
        set_log(f"Error: {e}")


def takeoff_click():
    if not tello:
        return

    try:
        target_height = int(height_var.get())
    except ValueError:
        set_log("Error: Altura no válida")
        return

    def run_takeoff_sequence():
        try:
            set_log(f"Iniciando secuencia: Despegue -> {target_height}cm")
            set_status("↑  En vuelo", ACCENT)

            tello.takeoff()

            # El Tello queda a ~80cm tras despegar
            init_h = 80
            diff = target_height - init_h

            if diff > 10:  # Umbral de 10cm para mayor precisión
                set_log(f"Ajustando altura: +{diff}cm")
                tello.move_up(diff)
            elif diff < -10:
                set_log(f"Ajustando altura: {diff}cm")
                tello.move_down(abs(diff))

            set_log("Altura alcanzada.")
        except Exception as e:
            set_log(f"Error en vuelo: {e}")

    # Ejecutamos toda la secuencia en un hilo para no congelar la UI
    threading.Thread(target=run_takeoff_sequence, daemon=True).start()

def land_click():
    if not tello:
        return
    set_log("Aterrizando…")
    threading.Thread(target=tello.land, daemon=True).start()
    set_status("↓  Aterrizando", WARNING)

def select_object_click():
    global camera_thread, selected_class_id

    if camera_running[0]:
        set_log("La detección ya está en ejecución.")
        return

    camera_running[0] = True
    set_status("⬤  Cámara activa — busca el objeto", ACCENT)
    set_log("Iniciando cámara para selección de objeto…")
    select_btn.config(state="normal", bg=TEXT_DIM)

    def run():
        global selected_class_id
        result = detection.run_object_detection_loop(camera_running)
        selected_class_id = result
        camera_running[0] = False
        window.after(0, on_detection_done, result)

    camera_thread = threading.Thread(target=run, daemon=True)
    camera_thread.start()

def on_detection_done(class_id):
    select_btn.config(state="normal", bg=PANEL)
    if class_id is not None:
        set_object_label(class_id)
        set_status("✓  Objeto seleccionado", SUCCESS)
        set_log(f"Objeto confirmado: {detection.model.names[class_id]} (id={class_id})")
        start_btn.config(state="normal")
    else:
        set_status("—  Selección cancelada", TEXT_DIM)
        set_log("Selección de objeto cancelada.")

def start_mission_click():
    if not tello or selected_class_id is None:
        return
    set_log(f"Misión iniciada. Buscando: {detection.model.names[selected_class_id]}")
    if record_enabled:
        set_log("GRABANDO")
    set_status("⬤  Misión en curso", ACCENT)
    start_btn.config(state="disabled", bg=TEXT_DIM)
    threading.Thread(
        target=mission_v2.mission_loop,
        args=(tello, selected_class_id, record_enabled),
        daemon=True
    ).start()


def on_window_close():
    global battery_poll_running
    battery_poll_running = False
    camera_running[0] = False
    if tello:
        try:
            tello.land()
            tello.streamoff()
        except Exception:
            pass
    window.destroy()


def toggle_record():
    """Cambia el estado de grabación y actualiza la UI del botón."""
    global record_enabled
    record_enabled = not record_enabled
    if record_enabled:
        record_btn.config(text="●  REC ON", bg=ACCENT2, fg=TEXT)
        set_log("Grabación armada para la siguiente misión.")
    else:
        record_btn.config(text="○  REC OFF", bg=PANEL, fg=ACCENT)
        set_log("Grabación desactivada.")
# ─────────────────────────────────────────────
#  Ventana principal
# ─────────────────────────────────────────────
window = tk.Tk()
window.title("TELLO CONTROL CENTER")
window.geometry("520x680")
window.resizable(False, False)
window.configure(bg=BG)

# Fuentes
mono      = tkfont.Font(family="Courier", size=10)
mono_bold = tkfont.Font(family="Courier", size=10, weight="bold")
title_f   = tkfont.Font(family="Courier", size=15, weight="bold")
small_f   = tkfont.Font(family="Courier", size=8)
large_f   = tkfont.Font(family="Courier", size=22, weight="bold")

# ─── Header ───────────────────────────────────
header = tk.Frame(window, bg=BG)
header.pack(fill="x", padx=24, pady=(22, 4))

tk.Label(header, text="TELLO", font=title_f, bg=BG, fg=ACCENT).pack(side="left")
tk.Label(header, text=" CONTROL CENTER", font=title_f, bg=BG, fg=TEXT).pack(side="left")

status_var = tk.StringVar(value="—  Sin conectar")
status_label = tk.Label(window, textvariable=status_var, font=small_f, bg=BG, fg=TEXT_DIM, anchor="w")
status_label.pack(fill="x", padx=24)

tk.Frame(window, bg=ACCENT, height=2).pack(fill="x", padx=24, pady=(6, 16))

# ─── Panel batería ────────────────────────────
batt_frame = tk.Frame(window, bg=PANEL, bd=0, relief="flat")
batt_frame.pack(fill="x", padx=24, pady=(0, 12))
tk.Frame(batt_frame, bg=ACCENT, width=4).pack(side="left", fill="y")

batt_inner = tk.Frame(batt_frame, bg=PANEL, padx=14, pady=12)
batt_inner.pack(side="left", fill="both", expand=True)

tk.Label(batt_inner, text="BATERÍA", font=small_f, bg=PANEL, fg=TEXT_DIM).pack(anchor="w")
battery_var = tk.StringVar(value="—")
battery_label = tk.Label(batt_inner, textvariable=battery_var, font=large_f, bg=PANEL, fg=TEXT_DIM)
battery_label.pack(anchor="w")

battery_canvas = tk.Canvas(batt_inner, width=180, height=14, bg=BORDER, highlightthickness=0)
battery_canvas.pack(anchor="w", pady=(4, 0))

# ─── Sección conexión ─────────────────────────
section_frame = tk.Frame(window, bg=BG)
section_frame.pack(fill="x", padx=24)

tk.Label(section_frame, text="CONEXIÓN", font=small_f, bg=BG, fg=TEXT_DIM).pack(anchor="w", pady=(0, 6))

connect_btn = make_button(section_frame, "⬡  CONECTAR DRONE", connect_click, state="active", width=24)
connect_btn.pack(anchor="w")

make_separator(section_frame)

# ─── Sección vuelo ────────────────────────────
tk.Label(section_frame, text="VUELO", font=small_f, bg=BG, fg=TEXT_DIM).pack(anchor="w", pady=(0, 6))

height_input = tk.Frame(section_frame, bg=BG)
height_input.pack(fill="x", padx=24, pady=(0, 10))

tk.Label(height_input, text="Altura despegue (cm)",font=small_f, bg=BG, fg=TEXT).pack(side="left")
height_var = tk.StringVar(value="100") # Valor por defecto
height_entry = tk.Entry(
    height_input, textvariable=height_var, width=5,
    bg=BORDER, fg=ACCENT, insertbackground=ACCENT,
    relief="flat", font=mono_bold, justify="center")
height_entry.pack(side="left", padx=10)

flight_row = tk.Frame(section_frame, bg=BG)
flight_row.pack(anchor="w")

takeoff_btn = make_button(flight_row, "↑  DESPEGAR", takeoff_click, state="active", width=14)
takeoff_btn.pack(side="left", padx=(0, 8))
takeoff_btn.config(state="disabled", bg=TEXT_DIM, activebackground=TEXT_DIM)

land_btn = make_button(flight_row, "↓  ATERRIZAR", land_click, state="danger", width=14)
land_btn.pack(side="left")
land_btn.config(state="disabled", bg=TEXT_DIM, activebackground=TEXT_DIM)

make_separator(section_frame)

# ─── Sección detección ────────────────────────
tk.Label(section_frame, text="DETECCIÓN", font=small_f, bg=BG, fg=TEXT_DIM).pack(anchor="w", pady=(0, 6))

object_var = tk.StringVar(value="TARGET  ›  sin seleccionar")
object_label = tk.Label(section_frame, textvariable=object_var, font=mono_bold, bg=BG, fg=TEXT_DIM, anchor="w")
object_label.pack(anchor="w", pady=(0, 8))

select_btn = make_button(section_frame, "⬤  ESCOGER OBJETO", select_object_click, width=24)
select_btn.pack(anchor="w", pady=(0, 8))

start_btn = make_button(section_frame, "▶  INICIAR MISIÓN", start_mission_click, state="active", width=24)
start_btn.pack(anchor="w")
start_btn.config(state="disabled", bg=TEXT_DIM, activebackground=TEXT_DIM)

record_btn = make_button(section_frame, "○  REC OFF", toggle_record, width=24)
record_btn.pack(anchor="w", pady=(0, 8))

make_separator(section_frame)

# ─── Log ──────────────────────────────────────
tk.Label(section_frame, text="LOG", font=small_f, bg=BG, fg=TEXT_DIM).pack(anchor="w", pady=(0, 6))

log_frame = tk.Frame(section_frame, bg=PANEL, pady=0)
log_frame.pack(fill="both", expand=True)

log_text = tk.Text(
    log_frame, height=8, bg=PANEL, fg=TEXT_DIM,
    font=small_f, relief="flat", bd=0,
    insertbackground=ACCENT, state="disabled",
    wrap="word", padx=10, pady=8
)
log_text.pack(fill="both", expand=True)

scrollbar = tk.Scrollbar(log_frame, command=log_text.yview, bg=BORDER, troughcolor=PANEL, width=6)
scrollbar.pack(side="right", fill="y")
log_text.config(yscrollcommand=scrollbar.set)

# ─── Footer ───────────────────────────────────
tk.Label(window, text="RoboMaster TT  ·  YOLOv5  ·  OpenCV",
         font=small_f, bg=BG, fg=TEXT_DIM).pack(pady=(10, 6))

# ─── Arranque ─────────────────────────────────
set_log("Sistema listo.")
window.protocol("WM_DELETE_WINDOW", on_window_close)
window.mainloop()