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
from playwright.sync_api import sync_playwright

# ---------------------------------------------------------
# ZONA HORARIA Y HORA LOCAL (PARAGUAY UTC-3)
# ---------------------------------------------------------
def obtener_hora_paraguay():
    try:
        tz = zoneinfo.ZoneInfo("America/Asuncion")
        return datetime.now(tz).strftime("%d/%m/%Y %H:%M:%S")
    except Exception:
        return datetime.now().strftime("%d/%m/%Y %H:%M:%S")

# ---------------------------------------------------------
# CONFIGURACIÓN DE CORREO SMTP
# ---------------------------------------------------------
EMAIL_REMITENTE = "revisioncuentahta@gmail.com"
EMAIL_DESTINATARIO = "revisioncuentahta@gmail.com"

def enviar_correo_smtp(asunto, cuerpo_html):
    email_pass = os.environ.get("EMAIL_PASSWORD")
    if not email_pass:
        print("⚠️ No se encontró EMAIL_PASSWORD en Secrets. Omitiendo envío.")
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

def enviar_correo_inicio(detalle_ejecucion, tipo_ejecucion):
    asunto = f"🚀 [INICIO] Automatización Hyundai HTA - {detalle_ejecucion}"
    hora_actual = obtener_hora_paraguay()
    cuerpo_html = f"""
    <html>
      <body style="font-family: Arial, sans-serif; color: #333; line-height: 1.6;">
        <div style="max-width: 550px; margin: 0 auto; border: 1px solid #e0e0e0; border-radius: 10px; padding: 20px; background-color: #f9f9f9;">
          <h2 style="color: #2563eb; text-align: center;">🏎️ Hyundai Monitor HTA</h2>
          <hr style="border: 0; border-top: 1px solid #e0e0e0;">
          <p>Se ha iniciado la ejecución del robot de producción.</p>
          <ul>
            <li><strong>Modo / Objetivo:</strong> {detalle_ejecucion}</li>
            <li><strong>Origen:</strong> {tipo_ejecucion}</li>
            <li><strong>Fecha y Hora:</strong> {hora_actual} (Paraguay)</li>
            <li><strong>Estado:</strong> 🟢 En Proceso</li>
          </ul>
        </div>
      </body>
    </html>
    """
    enviar_correo_smtp(asunto, cuerpo_html)

def enviar_reporte_final(detalle_ejecucion, tipo_ejecucion, exitosos, fallidos):
    hora_actual = obtener_hora_paraguay()
    total = len(exitosos) + len(fallidos)
    asunto = f"📊 [REPORTE FINAL] {detalle_ejecucion} - {len(exitosos)}/{total} Correctos"

    filas_exitosos = "".join([f"<tr><td style='padding:8px; border-bottom:1px solid #eee;'>{u['email']}</td><td style='padding:8px; border-bottom:1px solid #eee; color:#16a34a; font-weight:bold;'>✅ Login HTA Verificado ({u['accesos']}º acceso registrado)</td></tr>" for u in exitosos])
    if not exitosos:
        filas_exitosos = "<tr><td colspan='2' style='padding:8px; color:#777;'>Ningún usuario ingresó exitosamente.</td></tr>"

    filas_fallidos = "".join([f"<tr><td style='padding:8px; border-bottom:1px solid #eee;'>{u['email']}</td><td style='padding:8px; border-bottom:1px solid #eee; color:#dc2626;'>❌ {u['motivo']}</td></tr>" for u in fallidos])
    if not fallidos:
        filas_fallidos = "<tr><td colspan='2' style='padding:8px; color:#16a34a; font-weight:bold;'>🎉 ¡Todos los accesos procesados fueron exitosos!</td></tr>"

    cuerpo_html = f"""
    <html>
      <body style="font-family: Arial, sans-serif; color: #333; line-height: 1.6;">
        <div style="max-width: 600px; margin: 0 auto; border: 1px solid #e0e0e0; border-radius: 10px; padding: 20px; background-color: #ffffff;">
          <h2 style="color: #1e293b; text-align: center;">📊 Reporte Final de Automatización HTA</h2>
          <p style="text-align: center; color: #64748b; font-size: 13px;">{detalle_ejecucion} | Modo: {tipo_ejecucion} | {hora_actual}</p>
          <hr style="border: 0; border-top: 1px solid #e0e0e0; margin-bottom: 20px;">

          <h3 style="color: #16a34a; font-size: 14px; margin-bottom: 8px;">✅ Logins Verificados Correctamente ({len(exitosos)})</h3>
          <table style="width: 100%; border-collapse: collapse; font-size: 12px; margin-bottom: 25px;">
            <thead>
              <tr style="background-color: #f0fdf4; text-align: left;">
                <th style="padding: 8px; border-bottom: 2px solid #86efac;">Técnico / Usuario</th>
                <th style="padding: 8px; border-bottom: 2px solid #86efac;">Estado / Conteo</th>
              </tr>
            </thead>
            <tbody>{filas_exitosos}</tbody>
          </table>

          <h3 style="color: #dc2626; font-size: 14px; margin-bottom: 8px;">⚠️ Errores de Login o Contraseña Incorrecta ({len(fallidos)})</h3>
          <table style="width: 100%; border-collapse: collapse; font-size: 12px;">
            <thead>
              <tr style="background-color: #fee2e2; text-align: left;">
                <th style="padding: 8px; border-bottom: 2px solid #fca5a5;">Técnico / Usuario</th>
                <th style="padding: 8px; border-bottom: 2px solid #fca5a5;">Motivo del Error</th>
              </tr>
            </thead>
            <tbody>{filas_fallidos}</tbody>
          </table>
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
    print("❌ ERROR: La variable FIREBASE_CREDENTIALS no está configurada.")
    sys.exit(1)

cred_dict = json.loads(firebase_creds_json)
cred = credentials.Certificate(cred_dict)

if not firebase_admin._apps:
    firebase_admin.initialize_app(cred)

db = firestore.client()

# ---------------------------------------------------------
# 2. DETERMINAR MODO DE EJECUCIÓN
# ---------------------------------------------------------
grupo_a_ejecutar = "1"
tipo_ejecucion = "Automática (Programada 08:00 AM)"
usuario_individual = None

if len(sys.argv) > 1:
    grupo_a_ejecutar = str(sys.argv[1]).strip()
    tipo_ejecucion = "Manual (GitHub Actions)"

manual_doc_ref = db.collection("config").document("ejecucion_manual")
manual_doc = manual_doc_ref.get()

if manual_doc.exists:
    datos_manuales = manual_doc.to_dict()
    if datos_manuales.get("solicitado") is True:
        usuario_individual = datos_manuales.get("usuario_individual")
        grupo_a_ejecutar = str(datos_manuales.get("grupo", "1")).strip()
        tipo_ejecucion = "Manual (App Web)"
        manual_doc_ref.update({"solicitado": False, "usuario_individual": None})

if usuario_individual:
    detalle_ejecucion = f"Reintento Individual ({usuario_individual})"
    tarea_texto = f"Reintento Individual de {usuario_individual}"
else:
    detalle_ejecucion = f"Grupo {grupo_a_ejecutar}"
    tarea_texto = f"Automatización de Grupo {grupo_a_ejecutar}"

print(f"🚀 Iniciando: {detalle_ejecucion} [{tipo_ejecucion}]")
enviar_correo_inicio(detalle_ejecucion, tipo_ejecucion)

# ---------------------------------------------------------
# 3. OBTENER TÉCNICOS A PROCESAR
# ---------------------------------------------------------
tecnicos_ref = db.collection("tecnicos")
lista_tecnicos = []

if usuario_individual:
    doc_single = tecnicos_ref.document(usuario_individual).get()
    if doc_single.exists:
        d = doc_single.to_dict()
        d["_doc_id"] = doc_single.id
        lista_tecnicos.append(d)
    else:
        q_single = tecnicos_ref.where(filter=FieldFilter("usuario", "==", usuario_individual)).limit(1).stream()
        for doc in q_single:
            d = doc.to_dict()
            d["_doc_id"] = doc.id
            lista_tecnicos.append(d)
else:
    query = tecnicos_ref.where(filter=FieldFilter("grupo", "==", str(grupo_a_ejecutar))).where(filter=FieldFilter("activo", "==", True))
    docs = query.stream()
    for doc in docs:
        d = doc.to_dict()
        d["_doc_id"] = doc.id
        lista_tecnicos.append(d)

total_tecnicos = len(lista_tecnicos)
print(f"📋 Se encontraron {total_tecnicos} técnico(s) para procesar.")

if total_tecnicos == 0:
    db.collection("monitoreo").document("estado").set({
        "en_proceso": False,
        "tarea": "Sin tareas activas",
        "usuario_actual": "---",
        "progreso": "Completado (0 técnicos)",
        "porcentaje": 100,
        "eta_segundos": 0,
        "ultima_actualizacion": firestore.SERVER_TIMESTAMP
    }, merge=True)
    sys.exit(0)

# ---------------------------------------------------------
# 4. AUTOMATIZACIÓN CON RETRY Y ETA
# ---------------------------------------------------------
usuarios_exitosos = []
usuarios_fallidos = []
URL_HTA = "https://hta.hyundai.com/"

tiempo_promedio_por_usuario = 12  # Segundos promedio por login

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)

    for idx, tec in enumerate(lista_tecnicos, start=1):
        doc_id = tec.get("_doc_id")
        email = tec.get("usuario", doc_id)
        clave = tec.get("password", "Automotor*2026")

        porcentaje_actual = int(((idx - 1) / total_tecnicos) * 100)
        eta_segundos = (total_tecnicos - idx + 1) * tiempo_promedio_por_usuario

        print(f"[{idx}/{total_tecnicos}] ({porcentaje_actual}%) Procesando: {email} | ETA: {eta_segundos}s")

        db.collection("monitoreo").document("estado").set({
            "en_proceso": True,
            "tarea": tarea_texto,
            "usuario_actual": email,
            "progreso": f"{idx}/{total_tecnicos}",
            "porcentaje": porcentaje_actual,
            "eta_segundos": eta_segundos,
            "fallos_count": len(usuarios_fallidos),
            "ultima_actualizacion": firestore.SERVER_TIMESTAMP
        }, merge=True)

        login_exitoso = False
        ultimo_error = ""

        # SISTEMA DE AUTO-REINTENTO (Máximo 2 intentos por usuario)
        for intento in range(1, 3):
            context = browser.new_context(viewport={"width": 1920, "height": 1080})
            page = context.new_page()
            page.set_default_timeout(35000)

            try:
                page.goto(URL_HTA, wait_until="domcontentloaded", timeout=40000)
                page.wait_for_timeout(2000)

                if page.is_visible("input[type='email']"):
                    page.fill("input[type='email']", email)
                elif page.is_visible("input[name='username']"):
                    page.fill("input[name='username']", email)
                elif page.is_visible("input[id*='user']"):
                    page.fill("input[id*='user']", email)
                else:
                    page.fill("input[type='text']", email)

                if page.is_visible("input[type='password']"):
                    page.fill("input[type='password']", clave)

                if page.is_visible("button[type='submit']"):
                    page.click("button[type='submit']")
                elif page.is_visible("input[type='submit']"):
                    page.click("input[type='submit']")
                elif page.is_visible(".btn-login"):
                    page.click(".btn-login")
                else:
                    page.keyboard.press("Enter")

                page.wait_for_timeout(5000)

                html_pagina = page.content().lower()
                if "login" in page.url.lower() and ("incorrect" in html_pagina or "invalid" in html_pagina or "error" in html_pagina or "fallo" in html_pagina):
                    raise Exception("Credenciales o contraseña rechazada por el portal HTA")

                # ÉXITO
                tec_ref = db.collection("tecnicos").document(doc_id)
                tec_ref.set({
                    "accesos_mes": firestore.Increment(1),
                    "ultimo_acceso": firestore.SERVER_TIMESTAMP
                }, merge=True)

                snap_actualizado = tec_ref.get()
                conteo_nuevo = snap_actualizado.to_dict().get("accesos_mes", 1) if snap_actualizado.exists else 1

                usuarios_exitosos.append({
                    "email": email,
                    "accesos": conteo_nuevo
                })
                print(f"✅ Login verificado en HTA: {email} | Accesos: {conteo_nuevo}")
                login_exitoso = True
                context.close()
                break

            except Exception as e:
                ultimo_error = str(e)
                context.close()
                if intento == 1:
                    print(f"⚠️ Intento 1 falló para {email}. Reintentando automáticamente en 2s...")
                    time.sleep(2)

        if not login_exitoso:
            if "Timeout" in ultimo_error:
                motivo = "El servidor HTA no respondió a tiempo (Timeout)"
            elif "rechazada" in ultimo_error:
                motivo = "Usuario o clave rechazada por el portal HTA"
            else:
                motivo = f"Error en el flujo de ingreso: {ultimo_error[:80]}"

            print(f"❌ Falló definitivamente {email}: {motivo}")
            usuarios_fallidos.append({
                "email": email,
                "motivo": motivo
            })
            db.collection("monitoreo").document("estado").set({"fallos_count": len(usuarios_fallidos)}, merge=True)

    browser.close()

# ---------------------------------------------------------
# 5. FINALIZACIÓN Y REPORTE
# ---------------------------------------------------------
db.collection("monitoreo").document("estado").set({
    "en_proceso": False,
    "tarea": f"Completado: {tarea_texto}",
    "usuario_actual": "---",
    "progreso": f"Finalizado ({total_tecnicos}/{total_tecnicos})",
    "porcentaje": 100,
    "eta_segundos": 0,
    "ultima_actualizacion": firestore.SERVER_TIMESTAMP
}, merge=True)

print("🎉 Proceso finalizado. Enviando reporte...")
enviar_reporte_final(detalle_ejecucion, tipo_ejecucion, usuarios_exitosos, usuarios_fallidos)
print("🏁 Completado con éxito.")
