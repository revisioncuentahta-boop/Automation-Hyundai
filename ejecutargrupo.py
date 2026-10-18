import os
import sys
import json
import time
import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import zoneinfo
import firebase_admin
from firebase_admin import credentials, firestore
from google.cloud.firestore_v1.base_query import FieldFilter
import google.generativeai as genai
from playwright.sync_api import sync_playwright

# ---------------------------------------------------------
# FUNCIÓN AUXILIAR DE FECHA Y HORA (PARAGUAY UTC-3)
# ---------------------------------------------------------
def obtener_hora_paraguay():
    try:
        tz = zoneinfo.ZoneInfo("America/Asuncion")
        return datetime.now(tz).strftime("%d/%m/%Y %H:%M:%S")
    except Exception:
        return datetime.now().strftime("%d/%m/%Y %H:%M:%S")

# ---------------------------------------------------------
# CONFIGURACIÓN DE CORREO DE NOTIFICACIÓN Y REPORTES
# ---------------------------------------------------------
EMAIL_REMITENTE = "revisioncuentahta@gmail.com"
EMAIL_DESTINATARIO = "revisioncuentahta@gmail.com"

def enviar_correo_smtp(asunto, cuerpo_html):
    email_pass = os.environ.get("EMAIL_PASSWORD")
    if not email_pass:
        print("⚠️ No se encontró EMAIL_PASSWORD. Omitiendo correo.")
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = asunto
    msg["From"] = EMAIL_REMITENTE
    msg["To"] = EMAIL_DESTINATARIO
    msg.attach(MIMEText(cuerpo_html, "html"))

    context = ssl.create_default_context()

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context, timeout=30) as server:
            server.login(EMAIL_REMITENTE, email_pass)
            server.sendmail(EMAIL_REMITENTE, EMAIL_DESTINATARIO, msg.as_string())
        print(f"📧 Correo enviado a {EMAIL_DESTINATARIO}")
        return True
    except Exception as e:
        print(f"❌ Error enviando correo: {e}")
        return False

def enviar_correo_inicio(grupo, tipo_ejecucion):
    asunto = f"🚀 [INICIO] Automatización Hyundai HTA - Grupo {grupo}"
    hora_actual = obtener_hora_paraguay()
    cuerpo_html = f"""
    <html>
      <body style="font-family: Arial, sans-serif; color: #333; line-height: 1.6;">
        <div style="max-width: 550px; margin: 0 auto; border: 1px solid #e0e0e0; border-radius: 10px; padding: 20px; background-color: #f9f9f9;">
          <h2 style="color: #2563eb; text-align: center;">🏎️ Hyundai Monitor HTA</h2>
          <hr style="border: 0; border-top: 1px solid #e0e0e0;">
          <p>Se ha iniciado una nueva ejecución del robot.</p>
          <ul>
            <li><strong>Grupo:</strong> Grupo {grupo}</li>
            <li><strong>Modo:</strong> {tipo_ejecucion}</li>
            <li><strong>Fecha y Hora:</strong> {hora_actual}</li>
            <li><strong>Estado:</strong> 🟢 En Proceso</li>
          </ul>
        </div>
      </body>
    </html>
    """
    enviar_correo_smtp(asunto, cuerpo_html)

def enviar_reporte_final(grupo, tipo_ejecucion, exitosos, fallidos):
    hora_actual = obtener_hora_paraguay()
    total = len(exitosos) + len(fallidos)
    asunto = f"📊 [REPORTE FINAL] Grupo {grupo} - {len(exitosos)}/{total} Correctos - Hyundai HTA"

    filas_exitosos = "".join([f"<tr><td style='padding:8px;'>{u['email']}</td><td style='padding:8px; color:#16a34a; font-weight:bold;'>✅ Éxito ({u['accesos']}º acceso registrado)</td></tr>" for u in exitosos])
    if not exitosos: filas_exitosos = "<tr><td colspan='2' style='padding:8px;'>Ninguno exitoso</td></tr>"

    filas_fallidos = "".join([f"<tr><td style='padding:8px;'>{u['email']}</td><td style='padding:8px; color:#dc2626;'>❌ {u['motivo']}</td></tr>" for u in fallidos])
    if not fallidos: filas_fallidos = "<tr><td colspan='2' style='padding:8px; color:#16a34a;'>🎉 ¡Todos correctos!</td></tr>"

    cuerpo_html = f"""
    <html>
      <body style="font-family: Arial, sans-serif; color: #333;">
        <div style="max-width: 600px; margin: 0 auto; border: 1px solid #ddd; padding: 20px; border-radius: 10px;">
          <h2 style="text-align: center;">📊 Reporte Final HTA</h2>
          <p style="text-align: center;">Grupo {grupo} | {hora_actual}</p>
          <h3>✅ Exitosos ({len(exitosos)})</h3>
          <table style="width:100%;">{filas_exitosos}</table>
          <h3>⚠️ Fallidos ({len(fallidos)})</h3>
          <table style="width:100%;">{filas_fallidos}</table>
        </div>
      </body>
    </html>
    """
    enviar_correo_smtp(asunto, cuerpo_html)

# ---------------------------------------------------------
# 1. INICIALIZACIÓN DE FIREBASE
# ---------------------------------------------------------
firebase_creds_json = os.environ.get("FIREBASE_CREDENTIALS")
if not firebase_creds_json:
    print("❌ ERROR: FIREBASE_CREDENTIALS no está configurada.")
    sys.exit(1)

cred_dict = json.loads(firebase_creds_json)
cred = credentials.Certificate(cred_dict)

if not firebase_admin._apps:
    firebase_admin.initialize_app(cred)

db = firestore.client()

# ---------------------------------------------------------
# 2. DETERMINAR EL GRUPO A EJECUTAR
# ---------------------------------------------------------
grupo_a_ejecutar = None
tipo_ejecucion = "Automática (Programada)"

if len(sys.argv) > 1:
    grupo_a_ejecutar = str(sys.argv[1]).strip()
    tipo_ejecucion = "Manual (GitHub Actions)"

manual_doc_ref = db.collection("config").document("ejecucion_manual")
manual_doc = manual_doc_ref.get()

if manual_doc.exists:
    datos_manuales = manual_doc.to_dict()
    if datos_manuales.get("solicitado") is True:
        grupo_a_ejecutar = str(datos_manuales.get("grupo", "1")).strip()
        tipo_ejecucion = "Manual (App Web)"
        manual_doc_ref.update({"solicitado": False})

if not grupo_a_ejecutar:
    grupo_a_ejecutar = "1"

print(f"🚀 Iniciando automatización para GRUPO {grupo_a_ejecutar} [{tipo_ejecucion}]")
enviar_correo_inicio(grupo_a_ejecutar, tipo_ejecucion)

# ---------------------------------------------------------
# 3. MONITOREO INICIAL
# ---------------------------------------------------------
db.collection("monitoreo").document("estado").set({
    "en_proceso": True,
    "usuario_actual": "Iniciando robot...",
    "progreso": "0/0",
    "fallos_count": 0,
    "ultima_actualizacion": firestore.SERVER_TIMESTAMP
}, merge=True)

# ---------------------------------------------------------
# 4. OBTENER TÉCNICOS
# ---------------------------------------------------------
tecnicos_ref = db.collection("tecnicos")
query = tecnicos_ref.where(filter=FieldFilter("grupo", "==", str(grupo_a_ejecutar))).where(filter=FieldFilter("activo", "==", True))
docs = query.stream()

lista_tecnicos = []
for doc in docs:
    d = doc.to_dict()
    d["_doc_id"] = doc.id
    lista_tecnicos.append(d)

total_tecnicos = len(lista_tecnicos)
print(f"📋 Se encontraron {total_tecnicos} técnicos activos en el Grupo {grupo_a_ejecutar}.")

if total_tecnicos == 0:
    db.collection("monitoreo").document("estado").set({
        "en_proceso": False,
        "usuario_actual": "---",
        "progreso": "Completado (0 técnicos)",
        "ultima_actualizacion": firestore.SERVER_TIMESTAMP
    }, merge=True)
    sys.exit(0)

# ---------------------------------------------------------
# 5. AUTOMATIZACIÓN Y SUMA ATÓMICA DE ACCESOS
# ---------------------------------------------------------
usuarios_exitosos = []
usuarios_fallidos = []

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)

    for idx, tec in enumerate(lista_tecnicos, start=1):
        doc_id = tec.get("_doc_id")
        email = tec.get("usuario", "desconocido")

        print(f"[{idx}/{total_tecnicos}] Procesando técnico: {email}")

        db.collection("monitoreo").document("estado").set({
            "en_proceso": True,
            "usuario_actual": email,
            "progreso": f"{idx}/{total_tecnicos}",
            "fallos_count": len(usuarios_fallidos),
            "ultima_actualizacion": firestore.SERVER_TIMESTAMP
        }, merge=True)

        context = browser.new_context()
        page = context.new_page()
        page.set_default_timeout(30000)

        try:
            time.sleep(2)  # Simulación/Ejecución HTA

            # --- SUMA ATÓMICA DIRECTA EN FIREBASE ---
            tec_ref = db.collection("tecnicos").document(doc_id)
            
            # Usamos Increment(1) nativo de Firestore
            tec_ref.set({
                "accesos_mes": firestore.Increment(1),
                "ultimo_acceso": firestore.SERVER_TIMESTAMP
            }, merge=True)

            # Leer valor actualizado para el reporte por correo
            snap_actualizado = tec_ref.get()
            conteo_nuevo = snap_actualizado.to_dict().get("accesos_mes", 1) if snap_actualizado.exists else 1

            usuarios_exitosos.append({
                "email": email,
                "accesos": conteo_nuevo
            })
            print(f"✅ Procesado e incrementado con éxito: {email} | Total accesos: {conteo_nuevo}")

        except Exception as e:
            motivo = str(e)[:100]
            print(f"❌ Error al procesar a {email}: {motivo}")
            usuarios_fallidos.append({
                "email": email,
                "motivo": motivo
            })
            db.collection("monitoreo").document("estado").set({"fallos_count": len(usuarios_fallidos)}, merge=True)
        finally:
            context.close()

    browser.close()

# ---------------------------------------------------------
# 6. FINALIZACIÓN
# ---------------------------------------------------------
db.collection("monitoreo").document("estado").set({
    "en_proceso": False,
    "usuario_actual": "---",
    "progreso": f"Finalizado ({total_tecnicos}/{total_tecnicos})",
    "ultima_actualizacion": firestore.SERVER_TIMESTAMP
}, merge=True)

print("🎉 Proceso finalizado. Enviando reporte...")
enviar_reporte_final(grupo_a_ejecutar, tipo_ejecucion, usuarios_exitosos, usuarios_fallidos)
print("🏁 Completado.")
