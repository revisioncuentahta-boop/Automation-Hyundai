import os
import json
import firebase_admin
from firebase_admin import credentials, firestore

def obtener_cuentas_firebase(num_grupo):
    """Carga los usuarios desde Firebase Firestore."""
    try:
        if not firebase_admin._apps:
            if "FIREBASE_CREDENTIALS" in os.environ:
                cred_json = json.loads(os.environ["FIREBASE_CREDENTIALS"])
                cred = credentials.Certificate(cred_json)
            else:
                cred = credentials.Certificate("firebase_key.json")
            firebase_admin.initialize_app(cred)

        db = firestore.client()
        docs = db.collection("tecnicos").where("grupo", "==", str(num_grupo)).where("activo", "==", True).stream()

        usuarios = []
        for idx, doc in enumerate(docs, start=1):
            data = doc.to_dict()
            usuarios.append({
                "id": f"Usuario_{idx}",
                "usuario": data["usuario"],
                "password": data["password"]
            })
        if usuarios:
            return usuarios
    except Exception as e:
        print(f"⚠️ No se pudo conectar a Firebase ({e}). Leyendo cuentas.json local...")

    # Respaldo local si no conecta
    with open("cuentas.json", "r", encoding="utf-8") as archivo:
        todas = json.load(archivo)
    GRUPOS_LOCAL = {
        "1": todas[0:28], "2": todas[28:56], "3": todas[56:84],
        "4": todas[84:112], "5": todas[112:141]
    }
    return GRUPOS_LOCAL.get(str(num_grupo), GRUPOS_LOCAL["1"])
