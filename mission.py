import time
import threading
import cv2 as cv
from detection import analyze_frame

class MissionState:
    def __init__(self):
        self.searching   = False
        self.approaching = False
        self.evading     = False
        self.lost        = False
        self.completed   = False

# ── PARÁMETROS ────────────────────────────────────────────────
SEARCH_ROTATION      = 30
SEARCH_MAX_ROTATIONS = 12      # 12 x 30° = 360°
SEARCH_FORWARD       = 50      # cm al completar una vuelta sin target

FRAME_W, FRAME_H     = 960, 720
APPROACH_KP_YAW      = 0.1
APPROACH_KP_THROTTLE = 0.08
APPROACH_KP_PITCH    = 0.05
APPROACH_BBOX_TARGET = 0.20    # fracción del frame = "llegado"


# ── INFERENCIA EN HILO SEPARADO ───────────────────────────────
class YoloWorker:
    """
    Mantiene siempre la detección del último frame disponible.
    El hilo principal deposita frames; este hilo los procesa.
    La UI nunca espera a YOLO.
    """
    def __init__(self):
        self._frame      = None
        self._detections = []
        self._lock       = threading.Lock()
        self._new_frame  = threading.Event()
        self._running    = True
        self._thread     = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def push_frame(self, frame):
        with self._lock:
            self._frame = frame.copy()
        self._new_frame.set()

    def get_detections(self):
        with self._lock:
            return list(self._detections)

    def stop(self):
        self._running = False
        self._new_frame.set()  # desbloquea el wait

    def _run(self):
        while self._running:
            self._new_frame.wait()
            self._new_frame.clear()
            with self._lock:
                frame = self._frame
            if frame is None:
                continue
            result = analyze_frame(frame)
            with self._lock:
                self._detections = result


# ── LÓGICA DE ESTADOS ─────────────────────────────────────────
def search(tello, rotation_count):
    tello.rotate_clockwise(SEARCH_ROTATION)
    rotation_count += 1
    if rotation_count >= SEARCH_MAX_ROTATIONS:
        tello.move_forward(SEARCH_FORWARD)
        rotation_count = 0
    return rotation_count


def approach(tello, target):
    x1, y1, x2, y2 = target["bbox"]

    cx = (x1 + x2) / 2
    cy = (y1 + y2) / 2

    error_x   = cx - (FRAME_W / 2)
    error_y   = cy - (FRAME_H / 2)

    bbox_area_ratio = ((x2 - x1) * (y2 - y1)) / (FRAME_W * FRAME_H)
    error_dist      = APPROACH_BBOX_TARGET - bbox_area_ratio

    vel_yaw      = int(max(-30, min(30, APPROACH_KP_YAW      * error_x)))
    vel_throttle = int(max(-30, min(30, APPROACH_KP_THROTTLE * (-error_y))))
    vel_pitch    = int(max(-30, min(30, APPROACH_KP_PITCH    * error_dist * 1000)))

    tello.send_rc_control(0, vel_pitch, vel_throttle, vel_yaw)
    return bbox_area_ratio >= APPROACH_BBOX_TARGET


# ── BUCLE PRINCIPAL ───────────────────────────────────────────
def mission_loop(tello, object_id):
    mission_state           = MissionState()
    mission_state.searching = True
    rotation_count          = 0

    frame_read  = tello.get_frame_read()
    yolo_worker = YoloWorker()

    # Rate limiting: no mandar comandos a cada frame
    last_command_time = 0.0
    COMMAND_INTERVAL  = 0.15   # segundos entre comandos (~6 Hz)

    try:
        while not mission_state.completed:
            frame = frame_read.frame
            if frame is None:
                continue

            # 1. Enviar frame al hilo YOLO (no bloqueante)
            yolo_worker.push_frame(frame)

            # 2. Recoger últimas detecciones (del frame anterior)
            detections = yolo_worker.get_detections()
            target     = next((d for d in detections if d["class_id"] == object_id), None)

            # 3. Mostrar vídeo fluido con bbox superpuesto
            frame_display = cv.resize(frame, (360, 240))
            scale_x = 360 / FRAME_W
            scale_y = 240 / FRAME_H

            for d in detections:
                x1, y1, x2, y2 = d["bbox"]
                color = (0, 255, 0) if d["class_id"] == object_id else (0, 100, 255)
                cv.rectangle(frame_display,
                             (int(x1*scale_x), int(y1*scale_y)),
                             (int(x2*scale_x), int(y2*scale_y)),
                             color, 2)

            # HUD de estado
            state_text = (
                "BUSCANDO"    if mission_state.searching   else
                "APROXIMANDO" if mission_state.approaching else
                "EVADIENDO"   if mission_state.evading     else
                "PERDIDO"     if mission_state.lost        else "—"
            )
            cv.putText(frame_display, f"Estado: {state_text}",
                       (8, 20), cv.FONT_HERSHEY_SIMPLEX, 0.5, (0, 230, 255), 1)

            cv.imshow("Tello - Camara", frame_display)

            # 4. Lógica de navegación con rate limiting
            now = time.time()
            if now - last_command_time >= COMMAND_INTERVAL:
                last_command_time = now

                if mission_state.searching:
                    if target:
                        print("Target encontrado → APPROACHING")
                        mission_state.searching   = False
                        mission_state.approaching = True
                        rotation_count = 0
                    else:
                        rotation_count = search(tello, rotation_count)

                elif mission_state.approaching:
                    if not target:
                        print("Target perdido → SEARCHING")
                        tello.send_rc_control(0, 0, 0, 0)
                        mission_state.approaching = False
                        mission_state.searching   = True
                    else:
                        arrived = approach(tello, target)
                        if arrived:
                            print("¡Target alcanzado! → COMPLETADO")
                            tello.send_rc_control(0, 0, 0, 0)
                            mission_state.completed = True

                elif mission_state.evading:
                    pass

                elif mission_state.lost:
                    pass

            # 5. Salida con Q
            if cv.waitKey(1) & 0xFF == ord('q'):
                tello.send_rc_control(0, 0, 0, 0)
                break

    finally:
        yolo_worker.stop()
        cv.destroyAllWindows()