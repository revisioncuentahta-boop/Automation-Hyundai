import os
import sys
import json
import time
import pandas as pd
from datetime import datetime
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

# Identificador del mes actual (Ejemplo: "2026-10")
mes_actual_str = datetime.now().strftime("%Y-%m")

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

# B) Consultar si existe una orden de ejecución manual enviada desde Firebase
manual_doc_ref = db.collection("config").document("ejecucion_manual")
manual_doc = manual_doc_ref.get()

if manual_doc.exists:
    datos_manuales = manual_doc.to_dict()
    if datos_manuales.get("solicitado") is True:
        grupo_a_ejecutar = str(datos_manuales.get("grupo", "1")).strip()
        print(f"🤖 Solicitud manual detectada desde Firebase para el Grupo: {grupo_a_ejecutar}")
        
        # Limpiar la bandera para evitar ejecuciones repetidas involuntarias
        manual_doc_ref.update({"solicitado": False})

if not grupo_a_ejecutar:
    grupo_a_ejecutar = "1"
    print(f"ℹ️ No se especificó grupo. Ejecutando por defecto el Grupo {grupo_a_ejecutar}")

print(f"🚀 Iniciando proceso de automatización para el GRUPO {grupo_a_ejecutar}")

# ---------------------------------------------------------
# 4. ACTUALIZAR ESTADO INICIAL EN MONITOREO
# ---------------------------------------------------------
db.collection("monitoreo").document("estado").set({
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
    db.collection("monitoreo").document("estado").set({
        "en_proceso": False,
        "usuario_actual": "---",
        "progreso": "Completado (0 técnicos)",
        "ultima_actualizacion": firestore.SERVER_TIMESTAMP
    }, merge=True)
    sys.exit(0)

# ---------------------------------------------------------
# 6. LÓGICA DE AUTOMATIZACIÓN PLAYWRIGHT & CONTEO DE ACCESOS
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
        db.collection("monitoreo").document("estado").set({
            "en_proceso": True,
            "usuario_actual": email,
            "progreso": f"{idx}/{total_tecnicos}",
            "fallos_count": fallos_acumulados,
            "ultima_actualizacion": firestore.SERVER_TIMESTAMP
        }, merge=True)

        try:
            # Flujo de interacción con Playwright
            time.sleep(2)  # Simulación de proceso de login/navegación en HTA

            # --- REGISTRO Y SUMA DE ACCESOS MENSUALES EN FIREBASE ---
            tec_doc_ref = db.collection("tecnicos").document(email)
            doc_snap = tec_doc_ref.get()

            if doc_snap.exists:
                datos_tec = doc_snap.to_dict()
                
                # Verificar si la última actualización corresponde al mes actual
                if datos_tec.get("mes_acceso") == mes_actual_str:
                    nuevos_accesos = (datos_tec.get("accesos_mes") or 0) + 1
                else:
                    # Nuevo mes detectado: se reinicia el contador a 1
                    nuevos_accesos = 1

                tec_doc_ref.update({
                    "accesos_mes": nuevos_accesos,
                    "mes_acceso": mes_actual_str,
                    "ultimo_acceso_exitoso": firestore.SERVER_TIMESTAMP
                })

            print(f"✅ Procesado con éxito: {email} | Accesos del mes ({mes_actual_str}): {nuevos_accesos}")

        except Exception as e:
            print(f"❌ Error al procesar a {email}: {e}")
            fallos_acumulados += 1
            db.collection("monitoreo").document("estado").set({
                "fallos_count": fallos_acumulados
            }, merge=True)

    browser.close()

# ---------------------------------------------------------
# 7. FINALIZACIÓN Y RESTABLECIMIENTO DE ESTADO
# ---------------------------------------------------------
db.collection("monitoreo").document("estado").set({
    "en_proceso": False,
    "usuario_actual": "---",
    "progreso": f"Finalizado ({total_tecnicos}/{total_tecnicos})",
    "ultima_actualizacion": firestore.SERVER_TIMESTAMP
}, merge=True)

print("🎉 Proceso finalizado correctamente para todos los usuarios.")
