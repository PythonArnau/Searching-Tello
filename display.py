from djitellopy import Tello
import time

def hum_hum(tello):
    tello.send_control_command("EXT mled g 000bb00000bbbb00bbbbbbbb0bbbbbb00bbbbbb0bbbbbbbb00bbbb00000bb000")


tello = Tello()
tello.connect()
hum_hum(tello)
