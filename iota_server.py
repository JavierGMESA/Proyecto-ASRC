import json
import requests
import time
import binascii
import math
import numpy as np
import os
from datetime import datetime
import matplotlib.pyplot as plt


# URL del nodo Hornet/IOTA del que se leerán los bloques
NODE_URL = "http://localhost:14265"
# Tag que se utiliza para filtrar solo los bloques relevantes de glucosa
TAG = "sensor.glucose"
TAG_HEX = "0x" + TAG.encode("utf-8").hex()

REPORT_INTERVAL = 45  # segundos entre generación de gráficas

# Conjunto de IDs de bloque ya procesados para no repetir trabajo
processed = set()

# Almacenamos todas las lecturas aquí
# cada elemento: {"ts": datetime, "noisy": float, "est": float}
records = []

# Historial de medias por lote
batch_means = []  # cada elemento: {"ts": datetime, "mean": float}

# Último índice procesado (para separar los lotes)
last_index_for_means = 0

# Carpeta de salida para PNG
OUTPUT_DIR = "reports"
os.makedirs(OUTPUT_DIR, exist_ok=True)


def get_tips():
    # Solicita al nodo la lista de tips actuales
    r = requests.get(f"{NODE_URL}/api/core/v2/tips", timeout=5)
    r.raise_for_status()
    # Devuelve la lista de IDs de bloque en el campo "tips"
    return r.json().get("tips", [])


def bayes_estimate_from_laplace(y: float, epsilon: float, a: float, b: float, step: float = 0.5) -> float:
    """
    Estima x a partir de y sabiendo que y = x + Laplace(0, s),
    con x en [a, b] y prior uniforme.
    Devuelve la media a posteriori E[x|y].
    """
    # Escala del ruido Laplace (mismo diseño que en el cliente)
    s = (b - a) / epsilon
    # Discretización del rango [a, b] en pasos de tamaño 'step'
    xs = np.arange(a, b + step, step)

    # Log-pesos proporcionales a la densidad Laplace: exp(-|y - x| / s)
    log_weights = -np.abs(y - xs) / s
    # Normalización numérica para evitar overflow/underflow
    log_weights -= np.max(log_weights)
    weights = np.exp(log_weights)
    # Normalizar para que los pesos sumen 1
    weights /= np.sum(weights)

    # Media posterior estimada como suma(x * peso)
    est = float(np.sum(xs * weights))
    return est


def get_block(block_id: str):
    # Recupera un bloque concreto por su ID usando el endpoint REST
    r = requests.get(f"{NODE_URL}/api/core/v2/blocks/{block_id}", timeout=10)
    if r.status_code == 200:
        return r.json()
    return None


def decode_hex0x(s: str) -> bytes:
    # Decodifica una cadena en formato "0x..." a bytes binarios
    if not s or not s.startswith("0x"):
        return b""
    return binascii.unhexlify(s[2:])


def process_block(block_json):
    # Extrae el payload principal del bloque
    payload = block_json.get("payload", {})
    # Solo nos interesan los Tagged Data Payload (type == 5)
    if payload.get("type") != 5:
        return
    tag = payload.get("tag")
    data = payload.get("data")
    # Filtrar por el tag lógico esperado
    if tag != TAG_HEX:
        return

    try:
        # Decodificar el campo data (hex → bytes → UTF-8)
        msg = decode_hex0x(data).decode("utf-8")
        # Interpretar el contenido como JSON
        reading = json.loads(msg)

        # Extraer el valor ruidoso y el timestamp de la lectura
        noisy_value = float(reading.get("value"))
        ts_str = reading.get("ts", None)

        # Timestamp: si viene en ISO, lo convertimos; si no, usamos la hora actual
        if ts_str:
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        else:
            ts = datetime.utcnow()

        # Parámetros del modelo de LDP que usamos para reconstruir (aprox.) el valor real
        epsilon = 3.0
        min_glucose = 70.0
        max_glucose = 180.0

        # Estimar el valor "verdadero" a partir del ruidoso usando el estimador bayesiano
        est = bayes_estimate_from_laplace(
            noisy_value,
            epsilon=epsilon,
            a=min_glucose,
            b=max_glucose,
            step=0.5
        )

        # Mostrar por consola el valor ruidoso y el estimado junto con el timestamp
        print(
            f"noisy={noisy_value:.2f} mg/dL | "
            f"est_bayes≈{est:.2f} mg/dL @ {ts.isoformat()}"
        )

        # Guardar registro para su posterior análisis y generación de gráficas
        records.append({
            "ts": ts,
            "noisy": noisy_value,
            "est": est
        })

    except Exception as e:
        # Cualquier problema de decodificación/parsing se reporta por consola
        print(f"Error decodificando data: {e}")

def generate_plots():
    global last_index_for_means, batch_means
    MAX_POINTS = 200
    # Si aún no hay datos, no generamos nada
    if not records:
        print("No hay datos para generar gráficas todavía.")
        return

    # Ordenar las lecturas por tiempo para que las series temporales tengan sentido
    ordered = sorted(records, key=lambda r: r["ts"])
    ordered = ordered[-MAX_POINTS:]
    ts = [r["ts"] for r in ordered]
    noisy_vals = [r["noisy"] for r in ordered]
    est_vals = [r["est"] for r in ordered]

    # --- Gráfica 1: tiempo vs glucosa (noisy vs estimado) ---
    plt.figure(figsize=(10, 5))
    # Serie temporal con los valores ruidosos
    plt.plot(ts, noisy_vals, label="Noisy", marker="o", linestyle="-", alpha=0.7)
    # Serie temporal con los valores estimados bayesianamente
    plt.plot(ts, est_vals, label="Est. Bayes", marker="x", linestyle="--", alpha=0.7)

    plt.xlabel("Tiempo")
    plt.ylabel("Glucosa (mg/dL)")
    plt.title("Glucosa ruidosa vs estimada (LDP)")
    plt.legend()
    plt.grid(True)
    plt.tight_layout()

    # Guardar la figura como PNG en la carpeta reports
    line_path = os.path.join(OUTPUT_DIR, "glucose_noisy_vs_estimated.png")
    plt.savefig(line_path)
    plt.close()
    print(f"Gráfica de líneas guardada en {line_path}")

    # --- Gráfica 2: histogramas de noisy y est ---
    plt.figure(figsize=(8, 5))
    # Definimos bins en el rango fisiológico esperado
    bins = np.linspace(70, 180, 25)  # 24 intervalos iguales en [70, 180]

    # Histograma de valores ruidosos
    plt.hist(noisy_vals, bins=bins, alpha=0.6, label="Noisy", edgecolor="black")
    # Histograma de valores estimados
    plt.hist(est_vals, bins=bins, alpha=0.6, label="Est. Bayes", edgecolor="black")

    plt.xlabel("Glucosa (mg/dL)")
    plt.ylabel("Frecuencia")
    plt.title("Distribución de glucosa (noisy vs estimado)")
    plt.legend()
    plt.tight_layout()

    # Guardar la figura como PNG
    hist_path = os.path.join(OUTPUT_DIR, "glucose_histogram.png")
    plt.savefig(hist_path)
    plt.close()
    print(f"Histograma guardado en {hist_path}")

    # --- Gráfica 3: medias acumuladas en el tiempo ---
    # Calculamos la media 
    new_data = ordered[last_index_for_means:]
    if new_data:
        # Calcular media del lote nuevo usando los estimados bayesianos
        mean_value = np.mean([r["est"] for r in new_data])
        last_ts = new_data[-1]["ts"]

        # Guardarlo como punto en la serie de medias
        batch_means.append({"ts": last_ts, "mean": mean_value})

        # Limitar a las últimas 10 medias
        if len(batch_means) > 10:
            batch_means = batch_means[-10:]
        
        print(f"Nueva media de lote: {mean_value:.2f} mg/dL @ {last_ts}")

        # Actualizar índice global
        last_index_for_means = len(ordered)

    # Crear gráfica de evolución de medias por lote
    plt.figure(figsize=(8, 4))
    plt.plot(
        [m["ts"] for m in batch_means],
        [m["mean"] for m in batch_means],
        marker="o",
        linestyle="-",
        label="Media por lote"
    )

    plt.xlabel("Tiempo (último valor del lote)")
    plt.ylabel("Media glucosa (mg/dL)")
    plt.title("Evolución de la media de glucosa por lotes")
    plt.grid(True)
    plt.tight_layout()

    mean_path = os.path.join(OUTPUT_DIR, "glucose_batch_means.png")
    plt.savefig(mean_path)
    plt.close()
    print(f"Gráfica de medias por lote guardada en {mean_path}")


def main():
    print("Servidor: escuchando bloques con el tag objetivo")
    # Timestamp del último momento en que se generaron gráficas
    last_report = time.time()

    # Bucle principal: leer tips, recuperar bloques, procesarlos y periódicamente graficar
    while True:
        try:
            # Obtener tips actuales del nodo
            tips = get_tips()
            for tip in tips:
                # Evitar reprocesar bloques ya vistos
                if tip in processed:
                    continue
                # Descargar el bloque asociado al tip
                blk = get_block(tip)
                if blk:
                    # Procesar contenido (si coincide el tag y formato)
                    process_block(blk)
                    processed.add(tip)

            # Comprobar si ha pasado suficiente tiempo como para generar nuevas gráficas
            now = time.time()
            if now - last_report >= REPORT_INTERVAL:
                print("\n=== Generando gráficas ===")
                generate_plots()
                last_report = now

            # Pausa corta para no saturar el nodo con peticiones
            time.sleep(2)
        except KeyboardInterrupt:
            # Permite salir limpiamente con Ctrl+C
            print("Saliendo...")
            break
        except Exception as e:
            # Ante cualquier error inesperado, registrar y esperar un poco
            print(f"Error en loop: {e}")
            time.sleep(1)


if __name__ == "__main__":
    # Punto de entrada cuando se ejecuta el script directamente
    main()

