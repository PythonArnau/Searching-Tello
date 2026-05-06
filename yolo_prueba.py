import cv2
from ultralytics import YOLO
from djitellopy import Tello

tello = Tello()
tello.connect()
print(tello.get_battery())
tello.streamon()

model = YOLO("yolov8n.pt")

frame_read = tello.get_frame_read()
while True:
    frame = frame_read.frame
    if frame is not None:
        frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
        results = model(frame_bgr, verbose=False)
        annotated_frame = results[0].plot()
        cv2.imshow("Tello YOLO Detection", annotated_frame)
    if cv2.waitKey(1) & 0xFF == ord("q"):
        break

tello.streamoff()
tello.end()             # Ends the tello object (lands tello, turns off stream, stops BackgroundFrameRead)
cv2.destroyAllWindows() # Destroys any open windows, such as the streaming window.
