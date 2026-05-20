import cv2
from ultralytics import YOLO
from djitellopy import Tello
import threading
import time, datetime
import random
import os

# PARAMETERS
SEARCH_ROTATION = 30
SEARCH_FORWARD = 75
CONFIDENCE_THRESHOLD = 0.5
colors = {}
RECORDS_DIR = "records"
record_writer = None

def rotation_iteration(tello):
    #Mirar un lado y volver
    tello.rotate_clockwise(SEARCH_ROTATION)
    tello.rotate_clockwise(SEARCH_ROTATION)
    tello.rotate_counter_clockwise(2*SEARCH_ROTATION)
    #Mirar otro lado y volver
    tello.rotate_counter_clockwise(SEARCH_ROTATION)
    tello.rotate_counter_clockwise(SEARCH_ROTATION)
    tello.rotate_clockwise(2*SEARCH_ROTATION)

    tello.move_forward(SEARCH_FORWARD)

def mission_loop(tello, object_id, rec):
    # Cargar modelo
    model = YOLO("yolov8n.pt")
    frame_read = tello.get_frame_read()

    # Variables de control
    stop_mission = threading.Event()
    target_detected = [False]

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
        rotation_count = 0
        while not stop_mission.is_set():
            # Si NO hemos detectado el objeto, rotamos
            if not target_detected[0]:
                try:
                    rotation_iteration(tello)

                except Exception as e:
                    print(f"Error en movimiento: {e}")

            # Pequeña pausa para no saturar el procesador
            time.sleep(0.5)

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
        if video_writer is not None:
            video_writer.release()

    cv2.destroyAllWindows()