#from iota_sdk import Client
#
## Crear cliente
#client = Client(nodes=["http://localhost:14265"])
#
## Construir y enviar mensaje
#message = client.message()
#message = message.with_index("MiIndice").with_data(b"Hola, IOTA!").finish()
#
## Obtener ID del mensaje
#print("Mensaje enviado con ID:", message.id)




#from iota_client import IotaClient
#
## Crear cliente
#client = IotaClient({'nodes': ['http://localhost:14265'], 'local_pow': True})
#
## Construir payload tipo indexation
#payload = {
#    "type": 2,  # 2 = IndexationPayload
#    "index": "MiIndice",
#    "data": "486f6c612c20494f544121"  # Hexadecimal de "Hola, IOTA!"
#}
#
## Enviar mensaje
#message = client.send_message(payload=payload)
#
## Obtener ID del mensaje
#print("Mensaje enviado con ID:", message['message_id'])
