import random
import cv2
from ultralytics import YOLO

model = YOLO("yolov8n.pt")

cap = None

EXCLUDED_CLASSES = {"person"}
CONFIRMATION_FRAMES = 50  # ~2 segundos a 30fps

def run_object_detection_loop(camera_running):
    global cap

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("No se pudo abrir la camara del portatil.")
        camera_running = False
        return None

    print("Camara abierta. Pulsa 'q' o ESC para cerrar.")

    CONFIDENCE_THRESHOLD = 0.6
    colors = {}

    # Contador de frames consecutivos por class_id
    frame_counts = {}  # {class_id: int}
    result_class_id = None

    try:
        while camera_running and cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                print("No se pudo leer frame de la camara.")
                break

            results = model(frame, verbose=False)

            detected_ids_this_frame = set()

            # results[0].boxes contiene las detecciones
            for box in results[0].boxes:
                confidence = float(box.conf[0])
                class_id = int(box.cls[0])
                class_name = model.names[class_id]

                if confidence < CONFIDENCE_THRESHOLD:
                    continue
                if class_name in EXCLUDED_CLASSES:
                    continue

                detected_ids_this_frame.add(class_id)

                # Coordenadas [x1, y1, x2, y2]
                x1, y1, x2, y2 = map(int, box.xyxy[0])

                # Generar color único por clase
                if class_id not in colors:
                    random.seed(class_id)
                    colors[class_id] = (
                        random.randint(50, 255),
                        random.randint(50, 255),
                        random.randint(50, 255),
                    )
                color = colors[class_id]

                # Dibujar bounding box
                cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

                # Etiqueta con progreso
                count = frame_counts.get(class_id, 0)
                progress = min(count, CONFIRMATION_FRAMES)
                label = f"{class_name} {confidence:.2f} [{progress}/{CONFIRMATION_FRAMES}]"
                label_y = y1 - 10 if y1 - 10 > 10 else y1 + 20
                cv2.putText(
                    frame, label,
                    (x1, label_y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2
                )

            # Actualizar contadores
            for cid in detected_ids_this_frame:
                frame_counts[cid] = frame_counts.get(cid, 0) + 1

            for cid in list(frame_counts):
                if cid not in detected_ids_this_frame:
                    frame_counts[cid] = 0

                    # Comprobar confirmación
            confirmed = [cid for cid, cnt in frame_counts.items() if cnt >= CONFIRMATION_FRAMES]
            if confirmed:
                result_class_id = confirmed[0]
                print(f"Objeto confirmado: {model.names[result_class_id]} (id={result_class_id})")
                break

            cv2.imshow("Deteccion YOLOv8", frame)
            key = cv2.waitKey(1) & 0xFF
            if key == ord("q") or key == 27:
                camera_running = False
                break

    finally:
        if cap is not None:
            cap.release()
            cap = None
        cv2.destroyAllWindows()
        print("Camara cerrada.")

    return result_class_id


def analyze_frame(frame):
    if frame is None:
        return []

    # Inferencia simple
    results = model(frame, verbose=False)
    detections = []

    for box in results[0].boxes:
        class_id = int(box.cls[0])
        conf_val = float(box.conf[0])

        if conf_val > 0.4:
            x1, y1, x2, y2 = map(int, box.xyxy[0])

            detections.append({
                "class_id": class_id,
                "confidence": conf_val,
                "bbox": (x1, y1, x2, y2)
            })

            # Dibujo visual
            label = f"ID:{class_id} {conf_val:.2f}"
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
            cv2.putText(frame, label, (x1, y1 - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

    return detections