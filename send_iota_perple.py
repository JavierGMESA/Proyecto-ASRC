import requests
import json

def test_node_connection():
    """
    Test 1: Verificar que Hornet está corriendo y responde
    """
    print("=" * 60)
    print("TEST 1: Verificando conexión con Hornet")
    print("=" * 60)
    
    try:
        response = requests.get(
            "http://localhost:14265/api/core/v2/info",
            timeout=5
        )
        
        if response.status_code == 200:
            info = response.json()
            print("✓ Hornet está corriendo correctamente\n")
            print(f"Nombre del nodo: {info.get('name', 'N/A')}")
            print(f"Versión: {info.get('version', 'N/A')}")
            print(f"Protocolo: {info.get('protocol', {}).get('networkName', 'N/A')}")
            print(f"Estado: Healthy = {info.get('status', {}).get('isHealthy', False)}")
            return True
        else:
            print(f"✗ Error: HTTP {response.status_code}")
            return False
            
    except requests.exceptions.ConnectionError:
        print("✗ No se puede conectar a Hornet")
        print("Verifica que Docker esté ejecutando el contenedor")
        return False
    except Exception as e:
        print(f"✗ Error: {e}")
        return False


def get_tips():
    """
    Obtiene los 'tips' (parents) necesarios para crear un bloque
    """
    try:
        response = requests.get(
            "http://localhost:14265/api/core/v2/tips",
            timeout=5
        )
        
        if response.status_code == 200:
            tips_data = response.json()
            # El endpoint devuelve un array de tips
            tips = tips_data.get('tips', [])
            if tips:
                print(f"✓ Tips obtenidos: {len(tips)} tips disponibles")
                return tips
            else:
                print("✗ No se obtuvieron tips")
                return None
        else:
            print(f"✗ Error obteniendo tips: HTTP {response.status_code}")
            return None
            
    except Exception as e:
        print(f"✗ Error obteniendo tips: {e}")
        return None


def test_send_simple_block():
    """
    Test 2: Enviar un bloque simple al Tangle CON PARENTS
    """
    print("\n" + "=" * 60)
    print("TEST 2: Enviando bloque de prueba")
    print("=" * 60)
    
    # Primero obtener los tips (parents)
    print("\nObteniendo tips para usar como parents...")
    tips = get_tips()
    
    if not tips:
        print("✗ No se pueden obtener tips. Abortando envío.")
        return None
    
    # Datos de prueba muy simples
    test_message = "Hola desde Python!"
    tag = "test"
    
    # Convertir a hexadecimal
    tag_hex = tag.encode('utf-8').hex()
    data_hex = test_message.encode('utf-8').hex()
    
    print(f"\nMensaje: {test_message}")
    print(f"Tag: {tag}")
    print(f"Parents: {tips[:2]}")  # Mostrar los primeros 2
    
    # Payload según formato Stardust CON PARENTS
    payload = {
        "protocolVersion": 2,
        "parents": tips,  # ¡IMPORTANTE! Este campo es obligatorio
        "payload": {
            "type": 5,  # Tagged Data Payload
            "tag": f"0x{tag_hex}",
            "data": f"0x{data_hex}"
        },
        "nonce": "0"  # Nonce en 0 porque el PoW está deshabilitado
    }
    
    try:
        response = requests.post(
            "http://localhost:14265/api/core/v2/blocks",
            headers={'Content-Type': 'application/json'},
            json=payload,
            timeout=30
        )
        
        if response.status_code == 201:
            result = response.json()
            block_id = result.get('blockId')
            print(f"\n✓ Bloque enviado exitosamente!")
            print(f"Block ID: {block_id}")
            return block_id
        else:
            print(f"\n✗ Error al enviar: HTTP {response.status_code}")
            print(f"Respuesta: {response.text}")
            return None
            
    except Exception as e:
        print(f"\n✗ Error: {e}")
        return None


def test_retrieve_block(block_id):
    """
    Test 3: Recuperar el bloque enviado
    """
    print("\n" + "=" * 60)
    print("TEST 3: Recuperando bloque del Tangle")
    print("=" * 60)
    
    if not block_id:
        print("✗ No hay Block ID para recuperar")
        return False
    
    try:
        response = requests.get(
            f"http://localhost:14265/api/core/v2/blocks/{block_id}",
            timeout=10
        )
        
        if response.status_code == 200:
            block_data = response.json()
            print("\n✓ Bloque recuperado exitosamente!")
            
            # Extraer y decodificar los datos
            payload = block_data.get('payload', {})
            if payload.get('type') == 5:
                tag_hex = payload.get('tag', '0x').replace('0x', '')
                data_hex = payload.get('data', '0x').replace('0x', '')
                
                tag_decoded = bytes.fromhex(tag_hex).decode('utf-8') if tag_hex else ""
                data_decoded = bytes.fromhex(data_hex).decode('utf-8') if data_hex else ""
                
                print(f"\nTag recuperado: {tag_decoded}")
                print(f"Mensaje recuperado: {data_decoded}")
                print(f"Parents del bloque: {block_data.get('parents', [])}")
                return True
        else:
            print(f"✗ Error: HTTP {response.status_code}")
            return False
            
    except Exception as e:
        print(f"✗ Error: {e}")
        return False


def main():
    print("\n🐝 TEST DE HORNET - VERIFICACIÓN RÁPIDA 🐝\n")
    
    # Test 1: Conexión
    if not test_node_connection():
        print("\n❌ Hornet no está accesible. Abortando tests.")
        return
    
    # Test 2: Enviar bloque (con parents)
    block_id = test_send_simple_block()
    
    # Test 3: Recuperar bloque
    if block_id:
        test_retrieve_block(block_id)
    
    print("\n" + "=" * 60)
    print("TESTS COMPLETADOS")
    print("=" * 60)
    print()


if __name__ == "__main__":
    main()
