from djitellopy import Tello
import time

# Inicializar el dron
tello = Tello()
def get_tof(tello):
    #Devuelve el ToF en cm
    res = tello.send_read_command("EXT tof?")
    try:
        dist_str = res.replace('tof', '').strip()
        dist = float(dist_str)

        if dist >= 8192:
            return 999.0
        return dist/10
    except:
        return 999.0

try:
    tello.connect()
    print(f"Batería: {tello.get_battery()}%")
    print("--- Probando sensor ToF FRONTAL (vía ESP32) ---")

    while True:
        # Enviamos el comando de lectura específico para el controlador de código abierto
        # El comando 'EXT tof?' devuelve la distancia en milímetros (mm)
        respuesta = get_tof(tello)

        # El manual indica que si se excede el rango de detección, devuelve 8192
        print(f"Respuesta sensor frontal: {respuesta}")

        # Como comparación, el 'tof' estándar del estado del Tello suele ser en cm
        # pero mediante EXT tof? obtenemos la lectura precisa del módulo frontal.

        time.sleep(0.2)

except KeyboardInterrupt:
    print("\nPrueba finalizada por el usuario.")
except Exception as e:
    print(f"Error: {e}")
finally:
    tello.end()