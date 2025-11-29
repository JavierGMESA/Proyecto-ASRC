import json
import requests
import time
import binascii
import math
import numpy as np
import os
from datetime import datetime

import matplotlib.pyplot as plt  # pip install matplotlib


NODE_URL = "http://localhost:14265"
TAG = "sensor.glucose"
TAG_HEX = "0x" + TAG.encode("utf-8").hex()

processed = set()

# Almacenamos todas las lecturas aquí
records = []  # cada elemento: {"ts": datetime, "noisy": float, "est": float}

# Carpeta de salida para PNG
OUTPUT_DIR = "reports"
os.makedirs(OUTPUT_DIR, exist_ok=True)


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
    s = (b - a) / epsilon
    xs = np.arange(a, b + step, step)

    log_weights = -np.abs(y - xs) / s
    log_weights -= np.max(log_weights)
    weights = np.exp(log_weights)
    weights /= np.sum(weights)

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

        noisy_value = float(reading.get("value"))
        ts_str = reading.get("ts", None)

        # Timestamp: si viene en ISO, lo convertimos; si no, usamos now()
        if ts_str:
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        else:
            ts = datetime.utcnow()

        epsilon = 3.0
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
            f"est_bayes≈{est:.2f} mg/dL @ {ts.isoformat()}"
        )

        # Guardar registro para gráficas
        records.append({
            "ts": ts,
            "noisy": noisy_value,
            "est": est
        })

    except Exception as e:
        print(f"Error decodificando data: {e}")


def generate_plots():
    if not records:
        print("No hay datos para generar gráficas todavía.")
        return

    # Ordenar por tiempo
    ordered = sorted(records, key=lambda r: r["ts"])
    ts = [r["ts"] for r in ordered]
    noisy_vals = [r["noisy"] for r in ordered]
    est_vals = [r["est"] for r in ordered]

    # --- Gráfica 1: tiempo vs glucosa (noisy vs estimado) ---
    plt.figure(figsize=(10, 5))
    plt.plot(ts, noisy_vals, label="Noisy", marker="o", linestyle="-", alpha=0.7)
    plt.plot(ts, est_vals, label="Est. Bayes", marker="x", linestyle="--", alpha=0.7)

    plt.xlabel("Tiempo")
    plt.ylabel("Glucosa (mg/dL)")
    plt.title("Glucosa ruidosa vs estimada (LDP)")
    plt.legend()
    plt.grid(True)
    plt.tight_layout()

    line_path = os.path.join(OUTPUT_DIR, "glucose_noisy_vs_estimated.png")
    plt.savefig(line_path)
    plt.close()
    print(f"Gráfica de líneas guardada en {line_path}")

    # --- Gráfica 2: histogramas de noisy y est ---
    plt.figure(figsize=(8, 5))
    bins = np.linspace(70, 180, 25)

    plt.hist(noisy_vals, bins=bins, alpha=0.6, label="Noisy", edgecolor="black")
    plt.hist(est_vals, bins=bins, alpha=0.6, label="Est. Bayes", edgecolor="black")

    plt.xlabel("Glucosa (mg/dL)")
    plt.ylabel("Frecuencia")
    plt.title("Distribución de glucosa (noisy vs estimado)")
    plt.legend()
    plt.tight_layout()

    hist_path = os.path.join(OUTPUT_DIR, "glucose_histogram.png")
    plt.savefig(hist_path)
    plt.close()
    print(f"Histograma guardado en {hist_path}")


def main():
    print("Servidor: escuchando bloques con el tag objetivo")
    last_report = time.time()
    REPORT_INTERVAL = 300  # segundos entre generación de gráficas

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

            now = time.time()
            if now - last_report >= REPORT_INTERVAL:
                print("\n=== Generando gráficas ===")
                generate_plots()
                last_report = now

            time.sleep(2)
        except KeyboardInterrupt:
            print("Saliendo...")
            break
        except Exception as e:
            print(f"Error en loop: {e}")
            time.sleep(1)


if __name__ == "__main__":
    main()
