import sys
import json
import time
import smtplib
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import pandas as pd
from google import genai
from google.genai import types
from playwright.sync_api import sync_playwright

# 1. Configuración de API Key de Gemini
GEMINI_API_KEY = "AQ.Ab8RN6LGUlQP786aQPhdruudjXkVSI70GzIdCF2fCzRZ6bbv5Q"
client = genai.Client(api_key=GEMINI_API_KEY)

# 2. Configuración del Correo Electrónico de Notificaciones
EMAIL_REMITENTE = "revisioncuentahta@gmail.com"
PASSWORD_REMITENTE = "ypjphiqcghbvqeuk"  # Contraseña de aplicación de 16 caracteres
EMAIL_DESTINATARIO = "revisioncuentahta@gmail.com"  # Dirección que recibirá los reportes de error

# 3. Cargar cuentas desde cuentas.json
with open("cuentas.json", "r", encoding="utf-8") as archivo:
    todas_las_cuentas = json.load(archivo)

# 4. División de los 141 usuarios en 5 Grupos Diarios
GRUPOS = {
    "1": todas_las_cuentas[0:28],     # Lunes: Usuarios 1 al 28 (28 usuarios)
    "2": todas_las_cuentas[28:56],    # Martes: Usuarios 29 al 56 (28 usuarios)
    "3": todas_las_cuentas[56:84],    # Miércoles: Usuarios 57 al 84 (28 usuarios)
    "4": todas_las_cuentas[84:112],   # Jueves: Usuarios 85 al 112 (28 usuarios)
    "5": todas_las_cuentas[112:141]   # Viernes: Usuarios 113 al 141 (29 usuarios)
}

def enviar_correo_errores(lista_errores, num_grupo):
    """Envía un correo con el reporte detallado únicamente si existen usuarios con error."""
    if not lista_errores:
        print("✉️ No hay errores: Todos los usuarios del grupo ingresaron con éxito.")
        return

    asunto = f"🚨 Reporte de Errores Hyundai HTA - Grupo {num_grupo} ({datetime.now().strftime('%Y-%m-%d')})"
    
    cuerpo_html = f"""
    <h2>Reporte de Usuarios con Fallo - Grupo {num_grupo}</h2>
    <p>Se detectaron <b>{len(lista_errores)}</b> usuario(s) con problemas al ingresar/cerrar sesión:</p>
    <table border="1" cellpadding="8" cellspacing="0" style="border-collapse: collapse; font-family: Arial, sans-serif;">
        <tr style="background-color: #f2f2f2;">
            <th>ID</th>
            <th>Usuario</th>
            <th>Fecha / Hora</th>
            <th>Motivo del Error</th>
        </tr>
    """
    for err in lista_errores:
        cuerpo_html += f"""
        <tr>
            <td><b>{err['ID']}</b></td>
            <td>{err['Usuario']}</td>
            <td>{err['Fecha_Hora']}</td>
            <td style="color: red;">{err['Detalle_o_Motivo']}</td>
        </tr>
        """
    cuerpo_html += "</table><p><i>Mensaje generado automáticamente por el sistema Python.</i></p>"

    try:
        msg = MIMEMultipart()
        msg['From'] = EMAIL_REMITENTE
        msg['To'] = EMAIL_DESTINATARIO
        msg['Subject'] = asunto
        msg.attach(MIMEText(cuerpo_html, 'html'))

        # Servidor SMTP seguro de Gmail
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(EMAIL_REMITENTE, PASSWORD_REMITENTE)
        server.sendmail(EMAIL_REMITENTE, EMAIL_DESTINATARIO, msg.as_string())
        server.quit()
        print(f"📧 Correo de errores enviado exitosamente a {EMAIL_DESTINATARIO}")
    except Exception as e:
        print(f"⚠️ No se pudo enviar el correo de errores: {e}")

def consultar_gemini(captura_bytes, pregunta):
    """Consulta a Gemini Vision para confirmación visual."""
    try:
        imagen_part = types.Part.from_bytes(data=captura_bytes, mime_type="image/png")
        response = client.models.generate_content(
            model="gemini-3.8-flash",
            contents=[pregunta, imagen_part]
        )
        return response.text.strip()
    except Exception as e:
        if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
            return "Límite de API Gemini alcanzado (20 diarias)"
        return f"Error Gemini: {e}"

def procesar_login_logout(page, usuario, password, es_reintento=False):
    """Ejecuta la secuencia de acceso y salida con tiempos de espera configurables."""
    page.goto("https://hta.hyundai.com/gate/user/selectLogin.do", timeout=30000, wait_until="domcontentloaded")
    
    # Pausa de 5 segundos antes de ingresar credenciales
    time.sleep(5.0)

    page.locator("input[type='text'], input[name*='id'], input[id*='id']").first.fill(usuario)
    page.locator("input[type='password']").fill(password)
    page.locator("button[type='submit'], a:has-text('Login'), input[type='submit']").first.click()

    tiempo_espera = 25000 if not es_reintento else 40000
    logout_selector = page.locator("a[href*='selectLogout.do']")
    logout_selector.first.wait_for(state="attached", timeout=tiempo_espera)

    # Paso 4: Espera en el panel principal (10s normal / 15s en reintento)
    espera_paso4 = 10.0 if not es_reintento else 15.0
    time.sleep(espera_paso4)

    # Cierre de sesión por evento DOM JavaScript
    page.evaluate("() => { const link = document.querySelector('a[href*=\"selectLogout.do\"]'); if (link) link.click(); }")

    page.locator("input[type='password']").wait_for(state="visible", timeout=15000)
    
    # Paso 5: Espera tras cerrar sesión (10s normal / 15s en reintento)
    espera_paso5 = 10.0 if not es_reintento else 15.0
    time.sleep(espera_paso5)

    screenshot_bytes = page.screenshot()
    confirmacion = consultar_gemini(
        screenshot_bytes, 
        "¿La pantalla muestra nuevamente la página de inicio de sesión de Hyundai? Responde brevemente."
    )
    return confirmacion

def ejecutar_grupo(num_grupo="1"):
    usuarios = GRUPOS.get(num_grupo, GRUPOS["1"])
    reporte_resultados = []

    print(f"==================================================")
    print(f"🚀 INICIANDO AUTOMATIZACIÓN - GRUPO {num_grupo}")
    print(f"📊 Cantidad de usuarios en este grupo: {len(usuarios)}")
    print(f"==================================================\n")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        for index, u in enumerate(usuarios, start=1):
            print(f"--- Procesando [{index}/{len(usuarios)}] de Grupo {num_grupo}: {u['id']} ({u['usuario']}) ---")
            
            context = browser.new_context(viewport={"width": 1920, "height": 1080})
            page = context.new_page()
            
            mensajes_alerta = []
            page.on("dialog", lambda dialog: (mensajes_alerta.append(dialog.message), dialog.accept()))

            registro = {
                "ID": u["id"],
                "Usuario": u["usuario"],
                "Fecha_Hora": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "Grupo": f"Grupo {num_grupo}",
                "Estado": "Pendiente",
                "Detalle_o_Motivo": "",
                "Validacion_Gemini": "N/A"
            }

            try:
                # --- PRIMER INTENTO ---
                try:
                    confirmacion = procesar_login_logout(page, u["usuario"], u["password"], es_reintento=False)
                    print(f"✅ Login y Logout exitoso para {u['id']}")
                    
                    registro["Estado"] = "Éxito"
                    registro["Detalle_o_Motivo"] = "Ingreso y cierre de sesión completados correctamente"
                    registro["Validacion_Gemini"] = confirmacion

                except Exception as e_primero:
                    if mensajes_alerta:
                        raise Exception(f"Aviso de la web: {mensajes_alerta[-1]}")

                    print(f"\n⚠️  [REINTENTO ACTIVADO] El primer intento falló para {u['id']}.")
                    print(f"🔄 Reintentando ingreso por SEGUNDA VEZ con tiempos extendidos (15s)...")
                    time.sleep(8.0)

                    # --- SEGUNDO INTENTO ---
                    confirmacion = procesar_login_logout(page, u["usuario"], u["password"], es_reintento=True)
                    print(f"✅ Login y Logout exitoso para {u['id']} (en SEGUNDO INTENTO)")

                    registro["Estado"] = "Éxito"
                    registro["Detalle_o_Motivo"] = "Ingreso y cierre de sesión completados correctamente (en 2.º intento)"
                    registro["Validacion_Gemini"] = confirmacion

            except KeyboardInterrupt:
                print("\n🛑 Proceso cancelado manualmente por el usuario.")
                registro["Estado"] = "Cancelado"
                registro["Detalle_o_Motivo"] = "Cancelado manualmente"
                reporte_resultados.append(registro)
                context.close()
                break

            except Exception as e_final:
                error_msg = str(e_final)
                print(f"❌ Error definitivo en {u['id']}: {error_msg}")
                registro["Estado"] = "Fallido"

                if mensajes_alerta:
                    registro["Detalle_o_Motivo"] = f"Aviso de la web: {mensajes_alerta[-1]}"
                elif "Timeout" in error_msg:
                    registro["Detalle_o_Motivo"] = "El servidor no respondió tras 2 intentos. Bloqueo temporal de IP o credencial no válida."
                else:
                    registro["Detalle_o_Motivo"] = f"Error: {error_msg[:120]}"

            finally:
                reporte_resultados.append(registro)
                context.close()
                time.sleep(3.0)

            # Pausa de enfriamiento cada 15 usuarios
            if index % 15 == 0 and index < len(usuarios):
                print(f"\n☕ [Lote de 15 usuarios completado] Pausa de enfriamiento de 40 segundos...")
                time.sleep(40.0)

        browser.close()

    # Guardar Excel del grupo y enviar correo
    if reporte_resultados:
        df = pd.DataFrame(reporte_resultados)
        nombre_archivo = f"Reporte_Grupo_{num_grupo}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        df.to_excel(nombre_archivo, index=False)
        print(f"\n💾 Reporte Excel guardado en: {nombre_archivo}")

        # Filtrar errores y enviar notificación por correo
        errores = [r for r in reporte_resultados if r["Estado"] == "Fallido"]
        enviar_correo_errores(errores, num_grupo)

if __name__ == "__main__":
    grupo_solicitado = sys.argv[1] if len(sys.argv) > 1 else "1"
    ejecutar_grupo(grupo_solicitado)