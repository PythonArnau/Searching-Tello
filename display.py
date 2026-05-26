from djitellopy import Tello
import time

#Definir formas para mostrar en el display

def arrived(tello):
    tello.send_control_command("EXT mled g pppppppppbbbbbbppbrrrrbppbrpprbppbrpprbppbrrrrbppbbbbbbppppppppp")

