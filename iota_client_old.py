import requests
import json
import time
from datetime import datetime
import random
import math
import random

NODE_URL = "http://localhost:14265"
TAG = "sensor.glucose"  # cambia por sensor.hum / sensor.press según el tipo

def get_tips():
    r = requests.get(f"{NODE_URL}/api/core/v2/tips", timeout=5)
    r.raise_for_status()
    return r.json().get("tips", [])

def laplace_noise(scale: float) -> float:
    """
    Genera ruido Laplace(0, scale) usando la transformada inversa.
    """
    # U ~ Uniform(-0.5, 0.5)
    u = random.random() - 0.5
    return -scale * math.copysign(1.0, u) * math.log(1 - 2 * abs(u))

def privatize_value(value: float,
                    epsilon: float = 1.0,
                    min_val: float = 70.0,
                    max_val: float = 180.0) -> float:
    """
    Aplica Local Differential Privacy al valor numérico mediante
    el mecanismo Laplace.
    - epsilon: controla privacidad (↓epsilon = ↑ruido = ↑privacidad)
    - min_val, max_val: rango esperado del sensor
    """
    # 1) Recortar al rango permitido
    clipped = max(min_val, min(max_val, value))

    # 2) Sensibilidad: rango máximo posible
    sensitivity = max_val - min_val

    # 3) Escala b = sensibilidad / epsilon
    scale = sensitivity / epsilon

    # 4) Ruido Laplace
    noise = laplace_noise(scale)

    noisy = clipped + noise

    # 5) Volver a recortar para evitar valores físicamente imposibles
    noisy_clipped = max(min_val, min(max_val, noisy))
    return noisy_clipped

def send_tagged_block(tag: str, payload_obj: dict) -> str | None:
    tag_hex = tag.encode("utf-8").hex()
    data_hex = json.dumps(payload_obj).encode("utf-8").hex()

    parents = get_tips()
    if not parents:
        print("✗ No hay tips disponibles")
        return None

    block = {
        "protocolVersion": 2,
        "parents": parents,
        "payload": {
            "type": 5,
            "tag": f"0x{tag_hex}",
            "data": f"0x{data_hex}"
        }
        # sin nonce: si tu nodo hace PoW remoto funcionará; si no, habilítalo en Hornet
    }

    r = requests.post(f"{NODE_URL}/api/core/v2/blocks",
                      headers={"Content-Type": "application/json"},
                      json=block, timeout=60)
    if r.status_code == 201:
        return r.json().get("blockId")
    print(f"✗ Error HTTP {r.status_code}: {r.text}")
    return None

def simulate():
    return round(random.uniform(70.0, 180.0), 2)

def main():
    print("Cliente de sensor: enviando lecturas a IOTA (con LDP)")
    epsilon = 3.0         # ajusta este valor según el nivel de privacidad
    min_glucose = 70.0
    max_glucose = 180.0

    while True:
        true_value = simulate()  # valor "real" simulado

        noisy_value = privatize_value(
            true_value,
            epsilon=epsilon,
            min_val=min_glucose,
            max_val=max_glucose
        )

        reading = {
            "sensor_id": "TEMP_001",
            "type": "glucose",
            "true_value": round(true_value, 2),   # opcional, solo para debug local
            "value": round(noisy_value, 2),       # ESTE es el que viaja por IOTA
            "unit": "mg/dL",
            "ts": datetime.utcnow().isoformat() + "Z"
        }

        block_id = send_tagged_block(TAG, reading)
        if block_id:
            print(
                f"✓ Enviado: real={reading['true_value']} mg/dL, "
                f"noisy={reading['value']} mg/dL | BlockID={block_id}"
            )
        time.sleep(3)


if __name__ == "__main__":
    main()
