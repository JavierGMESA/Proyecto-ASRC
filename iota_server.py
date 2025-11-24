import json
import requests
import time
import binascii
import math
import numpy as np

NODE_URL = "http://localhost:14265"
TAG = "sensor.glucose"
TAG_HEX = "0x" + TAG.encode("utf-8").hex()

processed = set()

def get_tips():
    r = requests.get(f"{NODE_URL}/api/core/v2/tips", timeout=5)
    r.raise_for_status()
    return r.json().get("tips", [])

def bayes_estimate_from_laplace(y: float, epsilon: float, a: float, b: float, step: float = 0.5) -> float:
    """
    Estima x a partir de y sabiendo que y = x + Laplace(0, s),
    con x en [a, b] y prior uniforme.
    Devuelve la media a posteriori E[x|y].
    """
    # escala del ruido (mismo diseño que en el cliente)
    s = (b - a) / epsilon

    # grid de posibles valores reales x
    xs = np.arange(a, b + step, step)

    # densidad (no normalizada) del posterior ~ exp(-|y - x| / s)
    log_weights = -np.abs(y - xs) / s
    # para estabilidad numérica
    log_weights -= np.max(log_weights)
    weights = np.exp(log_weights)

    # normalizar
    weights /= np.sum(weights)

    # media posterior
    est = float(np.sum(xs * weights))
    return est

def get_block(block_id: str):
    r = requests.get(f"{NODE_URL}/api/core/v2/blocks/{block_id}", timeout=10)
    if r.status_code == 200:
        return r.json()
    return None

def decode_hex0x(s: str) -> bytes:
    if not s or not s.startswith("0x"):
        return b""
    return binascii.unhexlify(s[2:])

#def process_block(block_json):
#    payload = block_json.get("payload", {})
#    if payload.get("type") != 5:
#        return
#    tag = payload.get("tag")
#    data = payload.get("data")
#    if tag != TAG_HEX:
#        return
#    try:
#        msg = decode_hex0x(data).decode("utf-8")
#        print(f"✓ Mensaje recibido con tag '{TAG}': {msg}")
#    except Exception as e:
#        print(f"Error decodificando data: {e}")

def process_block(block_json):
    payload = block_json.get("payload", {})
    if payload.get("type") != 5:
        return
    tag = payload.get("tag")
    data = payload.get("data")
    if tag != TAG_HEX:
        return

    try:
        msg = decode_hex0x(data).decode("utf-8")
        reading = json.loads(msg)
        noisy_value = reading.get("value")

        epsilon = 0.5
        min_glucose = 70.0
        max_glucose = 180.0

        est = bayes_estimate_from_laplace(
            noisy_value,
            epsilon=epsilon,
            a=min_glucose,
            b=max_glucose,
            step=0.5
        )

        print(
            f"noisy={noisy_value:.2f} mg/dL | "
            f"est_bayes≈{est:.2f} mg/dL"
        )

    except Exception as e:
        print(f"Error decodificando data: {e}")


def main():
    print("Servidor: escuchando bloques con el tag objetivo")
    while True:
        try:
            tips = get_tips()
            for tip in tips:
                if tip in processed:
                    continue
                blk = get_block(tip)
                if blk:
                    process_block(blk)
                    processed.add(tip)
            # sleep pequeño para no sobrecargar el nodo
            time.sleep(2)
        except KeyboardInterrupt:
            print("Saliendo...")
            break
        except Exception as e:
            print(f"Error en loop: {e}")
            time.sleep(5)

if __name__ == "__main__":
    main()
