import os
import sys
import json
import time
import pandas as pd
import firebase_admin
from firebase_admin import credentials, firestore
import google.generativeai as genai
from playwright.sync_api import sync_playwright

# ---------------------------------------------------------
# 1. INICIALIZACIÓN DE FIREBASE
# ---------------------------------------------------------
firebase_creds_json = os.environ.get("FIREBASE_CREDENTIALS")

if not firebase_creds_json:
    print("❌ ERROR: La variable de entorno FIREBASE_CREDENTIALS no está configurada.")
    sys.exit(1)

cred_dict = json.loads(firebase_creds_json)
cred = credentials.Certificate(cred_dict)

if not firebase_admin._apps:
    firebase_admin.initialize_app(cred)

db = firestore.client()

# ---------------------------------------------------------
# 2. CONFIGURACIÓN DE GEMINI API
# ---------------------------------------------------------
gemini_api_key = os.environ.get("GEMINI_API_KEY")
if gemini_api_key:
    genai.configure(api_key=gemini_api_key)

# ---------------------------------------------------------
# 3. DETERMINAR EL GRUPO A EJECUTAR (Argumento CLI o Firebase)
# ---------------------------------------------------------
grupo_a_ejecutar = None

# A) Verificar si se pasó el número de grupo como argumento (vía GitHub Actions workflow_dispatch)
if len(sys.argv) > 1:
    grupo_a_ejecutar = str(sys.argv[1]).strip()
    print(f"📌 Grupo recibido por argumento de línea de comandos: {grupo_a_ejecutar}")

# B) Consultar si existe una orden de ejecución manual enviada desde la App Web
manual_doc_ref = db.collection("config").doc("ejecucion_manual")
manual_doc = manual_doc_ref.get()

if manual_doc.exists:
    datos_manuales = manual_doc.to_dict()
    if datos_manuales.get("solicitado") is True:
        grupo_a_ejecutar = str(datos_manuales.get("grupo", "1")).strip()
        print(f"🤖 Solicitud manual detectada desde la App Web para el Grupo: {grupo_a_ejecutar}")
        
        # Limpiar la bandera para evitar ejecuciones repetidas involuntarias
        manual_doc_ref.update({"solicitado": False})

if not grupo_a_ejecutar:
    grupo_a_ejecutar = "1"
    print(f"ℹ️ No se especificó grupo. Ejecutando por defecto el Grupo {grupo_a_ejecutar}")

print(f"🚀 Iniciando proceso de automatización para el GRUPO {grupo_a_ejecutar}")

# ---------------------------------------------------------
# 4. ACTUALIZAR ESTADO INICIAL EN MONITOREO
# ---------------------------------------------------------
db.collection("monitoreo").doc("estado").set({
    "en_proceso": True,
    "usuario_actual": "Iniciando robot...",
    "progreso": "0/0",
    "fallos_count": 0,
    "ultima_actualizacion": firestore.SERVER_TIMESTAMP
}, merge=True)

# ---------------------------------------------------------
# 5. OBTENER LECTURA DE TÉCNICOS DESDE FIREBASE
# ---------------------------------------------------------
tecnicos_ref = db.collection("tecnicos")
query = tecnicos_ref.where("grupo", "==", str(grupo_a_ejecutar)).where("activo", "==", True)
docs = query.stream()

lista_tecnicos = []
for doc in docs:
    data = doc.to_dict()
    lista_tecnicos.append(data)

total_tecnicos = len(lista_tecnicos)
print(f"📋 Se encontraron {total_tecnicos} técnicos activos pertenecientes al Grupo {grupo_a_ejecutar}.")

if total_tecnicos == 0:
    print("⚠️ No hay técnicos activos registrados para este grupo. Finalizando tarea.")
    db.collection("monitoreo").doc("estado").set({
        "en_proceso": False,
        "usuario_actual": "---",
        "progreso": "Completado (0 técnicos)",
        "ultima_actualizacion": firestore.SERVER_TIMESTAMP
    }, merge=True)
    sys.exit(0)

# ---------------------------------------------------------
# 6. LÓGICA DE AUTOMATIZACIÓN PLAYWRIGHT
# ---------------------------------------------------------
fallos_acumulados = 0

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()

    for idx, tec in enumerate(lista_tecnicos, start=1):
        email = tec.get("usuario", "desconocido")
        clave = tec.get("password", "")

        print(f"[{idx}/{total_tecnicos}] Procesando técnico: {email}")

        # Actualizar monitoreo en tiempo real hacia la App Web
        db.collection("monitoreo").doc("estado").set({
            "en_proceso": True,
            "usuario_actual": email,
            "progreso": f"{idx}/{total_tecnicos}",
            "fallos_count": fallos_acumulados,
            "ultima_actualizacion": firestore.SERVER_TIMESTAMP
        }, merge=True)

        try:
            # Aquí va tu flujo de navegación en HTA con Playwright
            # Ejemplo:
            # page.goto("https://portal.hyundai.com")
            # page.fill("#username", email)
            # page.fill("#password", clave)
            # page.click("#login-btn")
            time.sleep(2)  # Simulación de interacción
            print(f"✅ Procesado con éxito: {email}")

        except Exception as e:
            print(f"❌ Error al procesar a {email}: {e}")
            fallos_acumulados += 1
            db.collection("monitoreo").doc("estado").set({
                "fallos_count": fallos_acumulados
            }, merge=True)

    browser.close()

# ---------------------------------------------------------
# 7. FINALIZACIÓN Y RESTABLECIMIENTO DE ESTADO
# ---------------------------------------------------------
db.collection("monitoreo").doc("estado").set({
    "en_proceso": False,
    "usuario_actual": "---",
    "progreso": f"Finalizado ({total_tecnicos}/{total_tecnicos})",
    "ultima_actualizacion": firestore.SERVER_TIMESTAMP
}, merge=True)

print("🎉 Proceso finalizado correctamente para todos los usuarios.")
