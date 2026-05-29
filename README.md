# 🚁 Tello Object Finder

Sistema autónomo de búsqueda de objetos con un drone DJI Tello / RoboMaster TT. El usuario selecciona un objeto del mundo real mediante la cámara del portátil, el drone despega y lo busca de forma completamente autónoma hasta encontrarlo y aterrizar.

---

## Demostración del flujo

```
Usuario señala objeto  →  Drone despega  →  Exploración autónoma  →  Objeto encontrado  →  Aterrizaje
     (portátil)              (altura config.)     (serpentina + ToF)       (YOLOv8)
```

---

## Características

- **Selección de objeto por cámara** — confirmación por 50 frames consecutivos para evitar falsos positivos
- **Exploración autónoma en serpentina** — avance, detección de pared por sensor ToF, maniobra lateral y giro de 180°
- **Giro preciso por yaw** — el giro no usa timer ciego, sino lectura del sensor del drone hasta alcanzar el ángulo objetivo
- **Tres hilos concurrentes** — vídeo, movimiento y sensor ToF corren en paralelo sin bloqueos
- **Grabación opcional** — guarda la misión en vídeo `.mp4` con timestamp
- **Interfaz gráfica** — panel de control completo con log en tiempo real y estado de batería

---

## Estructura del proyecto

```
.
├── main.py          # Interfaz gráfica (Tkinter) y coordinación general
├── detection.py     # Detección de objeto con cámara del portátil (previa a la misión)
├── mission_v2.py    # Lógica de vuelo autónomo y detección con cámara del drone
└── display.py       # Control del display LED del drone
```

---

## Requisitos

### Hardware
- DJI Tello o RoboMaster TT
- Portátil con cámara integrada
- Conexión WiFi al drone

### Software

**Python 3.8+**

```bash
pip install djitellopy ultralytics opencv-python
```

| Dependencia | Uso |
|---|---|
| `djitellopy` | SDK de control del Tello |
| `ultralytics` | YOLOv8 para detección de objetos |
| `opencv-python` | Procesamiento de vídeo |
| `tkinter` | Interfaz gráfica (incluido en Python estándar) |

El modelo `yolov8n.pt` se descarga automáticamente en el primer arranque.

---

## Uso

### 1. Conectar al drone

Enciende el Tello y conéctate a su red WiFi desde el portátil. Luego lanza la aplicación:

```bash
python main.py
```

### 2. Secuencia en la interfaz

1. **CONECTAR DRONE** — establece conexión y muestra nivel de batería
2. Configura la **altura de despegue** (en cm, por defecto 100cm)
3. **ESCOGER OBJETO** — abre la cámara del portátil; apunta al objeto durante ~2 segundos hasta confirmar
4. **INICIAR MISIÓN** — el drone despega y comienza la búsqueda autónoma
5. (Opcional) **REC** — activa la grabación antes de iniciar la misión

### 3. Durante la misión

- El drone muestra el vídeo con las detecciones en tiempo real
- Pulsa `q` para abortar la misión en cualquier momento
- Al encontrar el objeto, el drone aterriza automáticamente

---

## Parámetros configurables

En `mission_v2.py`:

```python
CONFIDENCE_THRESHOLD = 0.5    # Confianza mínima para considerar una detección válida
WALL_THRESHOLD       = 100    # Distancia (cm) a la que se considera que hay una pared
FORWARD_SPEED        = 45     # Velocidad de avance (0-100)
LATERAL_DISPLACEMENT = 30     # Distancia (cm) del desplazamiento lateral al esquivar
LATERAL_SPEED        = 40     # Velocidad lateral (negativo=izq, positivo=der)
YAW_SPEED            = 50     # Velocidad de giro en °/s aproximados
YAW_TURN             = 180    # Ángulo de giro al cambiar de dirección
```

En `detection.py`:

```python
CONFIRMATION_FRAMES  = 50     # Frames consecutivos necesarios para confirmar objeto (~2s a 30fps)
CONFIDENCE_THRESHOLD = 0.6    # Umbral de confianza en la fase de selección (más estricto)
EXCLUDED_CLASSES     = {"person"}  # Clases ignoradas durante la selección
```

---

## Arquitectura y lógica

### Fase 1 — Selección del objeto (`detection.py`)

La detección previa usa la cámara del portátil con un mecanismo de confirmación por frames para eliminar falsos positivos. El objeto debe aparecer de forma estable durante `CONFIRMATION_FRAMES` frames consecutivos. Si desaparece aunque sea un frame, el contador se resetea a cero.

### Fase 2 — Misión autónoma (`mission_v2.py`)

La misión corre con tres hilos concurrentes:

```
┌─────────────────────────────────────────────────────────┐
│  Hilo ToF         │  Consulta EXT tof? continuamente    │
│                   │  Actualiza front_tof_cm (cm)         │
├─────────────────────────────────────────────────────────┤
│  Hilo movimiento  │  Avanza si dist > WALL_THRESHOLD     │
│                   │  Al detectar pared: frena → lateral  │
│                   │             → giro 180° por yaw      │
├─────────────────────────────────────────────────────────┤
│  Hilo vídeo       │  Procesa frames con YOLOv8           │
│  (principal)      │  Si detecta objeto_id → aterriza     │
└─────────────────────────────────────────────────────────┘
```

Los accesos al SDK del drone están protegidos por `sdk_lock` (sensor) y `rc_lock` (movimiento) para evitar condiciones de carrera.

### Algoritmo de exploración

```
AVANZAR
   │
   ▼
¿dist < WALL_THRESHOLD?
   │ Sí
   ▼
Freno activo (0.4s)
   │
   ▼
Desplazamiento lateral
   │
   ▼
Giro 180° (control por yaw)
   │
   ▼
AVANZAR  ←────────────────────────────────────────────────
```

---

## Vídeos grabados

Las grabaciones se guardan en la carpeta `records/` con el formato:

```
records/mission_20240315-143022.mp4
```

---

## Limitaciones conocidas

- El algoritmo de exploración es determinista (no tiene memoria de zonas visitadas)
- Solo detecta objetos que aparecen en la cámara frontal
- El drone no construye ningún mapa del entorno
- Se usa YOLOv8n (el más ligero), con menor precisión en condiciones difíciles

---

## Posibles mejoras

- Exploración frontier-based para no repetir zonas ya visitadas
- Integrar la cámara inferior del Tello para detectar objetos en el suelo
- Subir a YOLOv8s o YOLOv8m para mayor precisión
- Odometría simple para construir un mapa de ocupación de la sala

---

## Licencia

MIT
