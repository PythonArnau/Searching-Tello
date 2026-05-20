import cv2
from ultralytics import YOLO
from djitellopy import Tello
import threading
import time, datetime
import random
import os

# PARAMETERS
CONFIDENCE_THRESHOLD = 0.5
WALL_THRESHOLD = 80
FORWARD_SPEED = 30
LATERAL_DISPLACEMENT = 30
LATERAL_SPEED = 40         #Negativo: izq, Positivo:der
LATERAL_TIME = abs(LATERAL_DISPLACEMENT/LATERAL_SPEED)
YAW_SPEED = 50              # Velocidad de giro (°/s aproximado)
YAW_TURN = 180
TURN_TIME = abs(YAW_TURN/YAW_SPEED)             # Segundos para girar ~180° a YAW_SPEED=50
colors = {}
RECORDS_DIR = "records"
record_writer = None

sdk_lock = threading.Lock()
front_tof_cm = -1.0
tof_thread_active = False

rc_lock = threading.Lock()


def search(tello, stop_searching):
    while not stop_searching.is_set():
        dist = front_tof_cm
        print(f"Distancia: {dist}")

        if dist < 0:
            # Fuera de rango fiable: seguir avanzando
            with rc_lock:
                tello.send_rc_control(0, FORWARD_SPEED, 0, 0)
            time.sleep(0.1)

        elif dist > WALL_THRESHOLD:
            with rc_lock:
                tello.send_rc_control(0, FORWARD_SPEED, 0, 0)
            time.sleep(0.1)

        else:

            print("Pared detectada. Frenando...")

            # Freno activo: empuja hacia atrás para contrarrestar inercia
            t_brake = time.time()
            while time.time() - t_brake < 0.4 and not stop_searching.is_set():
                with rc_lock:
                    tello.send_rc_control(0, -60, 0, 0)
                time.sleep(0.05)

            with rc_lock:
                tello.send_rc_control(0, 0, 0, 0)
            time.sleep(0.5)  # esperar a que el dron esté estable

            print("Iniciando maniobra lateral...")
            t_start = time.time()
            while time.time() - t_start < LATERAL_TIME and not stop_searching.is_set():
                with rc_lock:
                    tello.send_rc_control(LATERAL_SPEED, 0, 0, 0)
                time.sleep(0.05)

            with rc_lock:
                tello.send_rc_control(0, 0, 0, 0)
            time.sleep(0.5)

            rotate_180_rc(tello, stop_searching)
            time.sleep(0.5)

    with rc_lock:
        tello.send_rc_control(0, 0, 0, 0)

def rotate_180_rc(tello, stop_event):
    start_yaw = tello.get_yaw()
    target_yaw = (start_yaw + 180) % 360

    t_start = time.time()
    while not stop_event.is_set():
        current_yaw = tello.get_yaw()
        diff = (target_yaw - current_yaw + 360) % 360

        # Si estamos a menos de 10° del objetivo, paramos
        if diff < 10 or diff > 350:
            break

        with rc_lock:
            tello.send_rc_control(0, 0, 0, YAW_SPEED)
        time.sleep(0.05)

    with rc_lock:
        tello.send_rc_control(0, 0, 0, 0)
    time.sleep(0.3)

def tof_loop(tello):
    global front_tof_cm
    while tof_thread_active:
        try:
            with sdk_lock:
                raw = tello.send_command_with_return("EXT tof?")
            if raw and raw.strip().startswith("tof "):
                dist_mm = int(raw.strip().split()[1])
                front_tof_cm = -1.0 if dist_mm >= 8190 else dist_mm / 10.0
        except Exception:
            pass


def mission_loop(tello, object_id, rec):
    # Cargar modelo
    model = YOLO("yolov8n.pt")
    frame_read = tello.get_frame_read()

    # Variables de control
    global tof_thread_active, rc_lock
    stop_mission = threading.Event()
    target_detected = [False]
    tof_thread_active = True
    tof_t = threading.Thread(target=tof_loop, args=(tello,), daemon=True)
    tof_t.start()

    rc_lock = threading.Lock()

    #Grabacion de video
    video_writer = None
    if rec:
        if not os.path.exists(RECORDS_DIR):
            os.makedirs(RECORDS_DIR)
        timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        filename = os.path.join(RECORDS_DIR, f"mission_{timestamp}.mp4")

        # Definir codec y crear objeto VideoWriter (960x720 es el nativo de Tello)
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        video_writer = cv2.VideoWriter(filename, fourcc, 30.0, (960, 720))
        print(f"Grabación armada en: {filename}")

    def movement_thread():
        """Hilo secundario: Controla el movimiento sin bloquear el video"""

        try:
            search(tello, stop_mission)
        except Exception as e:
            print(f"Error en hilo de movimiento: {e}")

    # Iniciar el hilo de movimiento
    mover = threading.Thread(target=movement_thread, daemon=True)
    mover.start()

    print("Bucle de video iniciado...")
    try:
        while not stop_mission.is_set():
            frame = frame_read.frame
            if frame is None:
                continue

            # Procesamiento de imagen
            frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
            results = model(frame_bgr, verbose=False)

            found_in_this_frame = False

            for box in results[0].boxes:
                confidence = float(box.conf[0])
                class_id = int(box.cls[0])

                if confidence < CONFIDENCE_THRESHOLD:
                    continue

                x1, y1, x2, y2 = map(int, box.xyxy[0])

                # Dibujado de cajas
                if class_id not in colors:
                    random.seed(class_id)
                    colors[class_id] = (random.randint(50, 255), random.randint(50, 255), random.randint(50, 255))

                cv2.rectangle(frame_bgr, (x1, y1), (x2, y2), colors[class_id], 2)
                cv2.putText(frame_bgr, f"ID:{class_id} {confidence:.2f}", (x1, y1 - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, colors[class_id], 2)

                # Lógica de detección del objetivo
                if class_id == object_id:
                    found_in_this_frame = True
                    target_detected[0] = True
                    print(f"¡OBJETIVO {class_id} ENCONTRADO! Aterrizando...")
                    stop_mission.set()  # Detiene el hilo de movimiento
                    with rc_lock:
                        tello.send_rc_control(0, 0, 0, 0)
                    tello.land()
                    break

            # Si lo perdemos de vista, permitimos que el hilo de movimiento siga buscando
            if not found_in_this_frame:
                target_detected[0] = False

            if rec and video_writer is not None:
                video_writer.write(frame_bgr)


            # Mostrar video (Siempre fluido)
            cv2.imshow("Tello Detection (Hilo Fluido)", frame_bgr)

            #Grabar Video

            if cv2.waitKey(1) & 0xFF == ord('q'):
                stop_mission.set()
                break
    finally:
        tof_thread_active = False
        if video_writer is not None:
            video_writer.release()

    cv2.destroyAllWindows()