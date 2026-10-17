import os
import sys
import json
import time
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import pandas as pd
import firebase_admin
from firebase_admin import credentials, firestore
import google.generativeai as genai
from playwright.sync_api import sync_playwright

# ---------------------------------------------------------
# CONFIGURACIÓN DE CORREO DE NOTIFICACIÓN Y REPORTES
# ---------------------------------------------------------
EMAIL_REMITENTE = "esteban.fernandez@automotor.com.py"  # Correo remitente (usa la contraseña en EMAIL_PASSWORD)
EMAIL_DESTINATARIO = "revisioncuentahta@gmail.com"     # Correo destinatario final de reportes y alertas

def enviar_correo_inicio(grupo, tipo_ejecucion):
    """Envía un correo de notificación al iniciar la automatización."""
    email_pass = os.environ.get("EMAIL_PASSWORD")
    if not email_pass:
        print("⚠️ No se encontró EMAIL_PASSWORD. Omitiendo notificación de inicio.")
        return

    asunto = f"🚀 [INICIO] Automatización Hyundai HTA - Grupo {grupo}"
    hora_actual = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    
    cuerpo_html = f"""
    <html>
      <body style="font-family: Arial, sans-serif; color: #333; line-height: 1.6;">
        <div style="max-width: 550px; margin: 0 auto; border: 1px solid #e0e0e0; border-radius: 10px; padding: 20px; background-color: #f9f9f9;">
          <h2 style="color: #2563eb; text-align: center;">🏎️ Hyundai Monitor HTA</h2>
          <hr style="border: 0; border-top: 1px solid #e0e0e0;">
          <p>Se ha iniciado una nueva ejecución del robot de automatización.</p>
          <ul>
            <li><strong>Grupo Ejecutado:</strong> Grupo {grupo}</li>
            <li><strong>Modo:</strong> {tipo_ejecucion}</li>
            <li><strong>Fecha y Hora:</strong> {hora_actual}</li>
            <li><strong>Estado:</strong> 🟢 En Proceso</li>
          </ul>
        </div>
      </body>
    </html>
    """

    msg = MIMEMultipart("alternative")
    msg["Subject"] = asunto
    msg["From"] = EMAIL_REMITENTE
    msg["To"] = EMAIL_DESTINATARIO
    msg.attach(MIMEText(cuerpo_html, "html"))

    try:
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(EMAIL_REMITENTE, email_pass)
        server.sendmail(EMAIL_REMITENTE, EMAIL_DESTINATARIO, msg.as_string())
        server.quit()
        print(f"📧 Correo de notificación de inicio enviado a {EMAIL_DESTINATARIO}")
    except Exception as e:
        print(f"❌ Error al enviar correo de inicio: {e}")

def enviar_reporte_final(grupo, tipo_ejecucion, exitosos, fallidos):
    """Envía un reporte detallado con los usuarios que ingresaron y los que fallaron con su motivo."""
    email_pass = os.environ.get("EMAIL_PASSWORD")
    if not email_pass:
        print("⚠️ No se encontró EMAIL_PASSWORD. Omitiendo reporte final.")
        return

    hora_actual = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    total_procesados = len(exitosos) + len(fallidos)
    
    asunto = f"📊 [REPORTE FINAL] Grupo {grupo} - {len(exitosos)}/{total_procesados} Correctos - Hyundai HTA"

    # Construir filas de usuarios exitosos
    filas_exitosos = ""
    for u in exitosos:
        filas_exitosos += f"""
        <tr>
            <td style="padding: 8px; border-bottom: 1px solid #eee;">{u['email']}</td>
            <td style="padding: 8px; border-bottom: 1px solid #eee; color: #16a34a; font-weight: bold;">✅ Éxito ({u['accesos']}º acceso del mes)</td>
        </tr>
        """
    if not exitosos:
        filas_exitosos = "<tr><td colspan='2' style='padding: 8px; color: #777;'>Ningún usuario ingresó exitosamente.</td></tr>"

    # Construir filas de usuarios fallidos
    filas_fallidos = ""
    for u in fallidos:
        filas_fallidos += f"""
        <tr>
            <td style="padding: 8px; border-bottom: 1px solid #eee;">{u['email']}</td>
            <td style="padding: 8px; border-bottom: 1px solid #eee; color: #dc2626;">❌ {u['motivo']}</td>
        </tr>
        """
    if not fallidos:
        filas_fallidos = "<tr><td colspan='2' style='padding: 8px; color: #16a34a; font-weight: bold;'>🎉 ¡Genial! No hubo fallas en ningún usuario.</td></tr>"

    cuerpo_html = f"""
    <html>
      <body style="font-family: Arial, sans-serif; color: #333; line-height: 1.6;">
        <div style="max-width: 600px; margin: 0 auto; border: 1px solid #e0e0e0; border-radius: 10px; padding: 20px; background-color: #ffffff;">
          <h2 style="color: #1e293b; text-align: center;">📊 Reporte Final de Automatización HTA</h2>
          <p style="text-align: center; color: #64748b; font-size: 13px;">Grupo {grupo} | Modo: {tipo_ejecucion} | {hora_actual}</p>
          <hr style="border: 0; border-top: 1px solid #e0e0e0; margin-bottom: 20px;">

          <!-- Resumen Numérico -->
          <table style="width: 100%; margin-bottom: 20px; text-align: center;">
            <tr>
              <td style="background-color: #f1f5f9; padding: 12px; border-radius: 8px; width: 30%;">
                <span style="font-size: 11px; color: #64748b; font-weight: bold; display: block;">PROCESADOS</span>
                <span style="font-size: 18px; font-weight: bold; color: #0f172a;">{total_procesados}</span>
              </td>
              <td style="background-color: #dcfce7; padding: 12px; border-radius: 8px; width: 30%;">
                <span style="font-size: 11px; color: #15803d; font-weight: bold; display: block;">EXITOSOS</span>
                <span style="font-size: 18px; font-weight: bold; color: #166534;">{len(exitosos)}</span>
              </td>
              <td style="background-color: #fee2e2; padding: 12px; border-radius: 8px; width: 30%;">
                <span style="font-size: 11px; color: #b91c1c; font-weight: bold; display: block;">FALLIDOS</span>
                <span style="font-size: 18px; font-weight: bold; color: #991b1b;">{len(fallos_acumulados)}</span>
              </td>
            </tr>
          </table>

          <!-- Tabla de Fallidos -->
          <h3 style="color: #dc2626; font-size: 14px; margin-bottom: 8px;">⚠️ Usuarios con Errores ({len(fallidos)})</h3>
          <table style="width: 100%; border-collapse: collapse; font-size: 12px; margin-bottom: 25px;">
            <thead>
              <tr style="background-color: #fee2e2; text-align: left;">
                <th style="padding: 8px; border-bottom: 2px solid #fca5a5;">Técnico / Usuario</th>
                <th style="padding: 8px; border-bottom: 2px solid #fca5a5;">Motivo del Error</th>
              </tr>
            </thead>
            <tbody>
              {filas_fallidos}
            </tbody>
          </table>

          <!-- Tabla de Exitosos -->
          <h3 style="color: #16a34a; font-size: 14px; margin-bottom: 8px;">✅ Usuarios Procesados Correctamente ({len(exitosos)})</h3>
          <table style="width: 100%; border-collapse: collapse; font-size: 12px;">
            <thead>
              <tr style="background-color: #f0fdf4; text-align: left;">
                <th style="padding: 8px; border-bottom: 2px solid #86efac;">Técnico / Usuario</th>
                <th style="padding: 8px; border-bottom: 2px solid #86efac;">Estado / Conteo</th>
              </tr>
            </thead>
            <tbody>
              {filas_exitosos}
            </tbody>
          </table>

          <p style="text-align: center; font-size: 11px; color: #94a3b8; margin-top: 25px;">
            Notificación automática enviada a {EMAIL_DESTINATARIO} desde el servidor en la nube.
          </p>
        </div>
      </body>
    </html>
    """

    msg = MIMEMultipart("alternative")
    msg["Subject"] = asunto
    msg["From"] = EMAIL_REMITENTE
    msg["To"] = EMAIL_DESTINATARIO
    msg.attach(MIMEText(cuerpo_html, "html"))

    try:
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(EMAIL_REMITENTE, email_pass)
        server.sendmail(EMAIL_REMITENTE, EMAIL_DESTINATARIO, msg.as_string())
        server.quit()
        print(f"📧 Reporte final enviado exitosamente a {EMAIL_DESTINATARIO}")
    except Exception as e:
        print(f"❌ Error al enviar el reporte final: {e}")

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
mes_actual_str = datetime.now().strftime("%Y-%m")

# ---------------------------------------------------------
# 2. CONFIGURACIÓN DE GEMINI API
# ---------------------------------------------------------
gemini_api_key = os.environ.get("GEMINI_API_KEY")
if gemini_api_key:
    genai.configure(api_key=gemini_api_key)

# ---------------------------------------------------------
# 3. DETERMINAR EL GRUPO A EJECUTAR (CLI o Firebase)
# ---------------------------------------------------------
grupo_a_ejecutar = None
tipo_ejecucion = "Automática (Programada 08:00 AM)"

if len(sys.argv) > 1:
    grupo_a_ejecutar = str(sys.argv[1]).strip()
    tipo_ejecucion = "Manual (Desde GitHub Actions)"
    print(f"📌 Grupo recibido por argumento CLI: {grupo_a_ejecutar}")

manual_doc_ref = db.collection("config").document("ejecucion_manual")
manual_doc = manual_doc_ref.get()

if manual_doc.exists:
    datos_manuales = manual_doc.to_dict()
    if datos_manuales.get("solicitado") is True:
        grupo_a_ejecutar = str(datos_manuales.get("grupo", "1")).strip()
        tipo_ejecucion = "Manual (Desde App Web)"
        print(f"🤖 Solicitud manual detectada desde Firebase para Grupo {grupo_a_ejecutar}")
        manual_doc_ref.update({"solicitado": False})

if not grupo_a_ejecutar:
    grupo_a_ejecutar = "1"
    print(f"ℹ️ No se especificó grupo. Ejecutando Grupo {grupo_a_ejecutar} por defecto.")

print(f"🚀 Iniciando automatización para GRUPO {grupo_a_ejecutar} [{tipo_ejecucion}]")

# Enviar correo de inicio
enviar_correo_inicio(grupo_a_ejecutar, tipo_ejecucion)

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
    lista_tecnicos.append(doc.to_dict())

total_tecnicos = len(lista_tecnicos)
print(f"📋 Se encontraron {total_tecnicos} técnicos activos en el Grupo {grupo_a_ejecutar}.")

if total_tecnicos == 0:
    print("⚠️ No hay técnicos activos registrados. Finalizando tarea.")
    db.collection("monitoreo").document("estado").set({
        "en_proceso": False,
        "usuario_actual": "---",
        "progreso": "Completado (0 técnicos)",
        "ultima_actualizacion": firestore.SERVER_TIMESTAMP
    }, merge=True)
    sys.exit(0)

# ---------------------------------------------------------
# 6. LÓGICA DE AUTOMATIZACIÓN PLAYWRIGHT & REPORTES
# ---------------------------------------------------------
usuarios_exitosos = []
usuarios
