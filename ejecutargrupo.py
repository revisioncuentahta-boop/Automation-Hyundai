import os
import sys
import json
import asyncio
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from playwright.async_api import async_playwright
import google.generativeai as genai
import firebase_admin
from firebase_admin import credentials, firestore

# Global DB para actualizar monitoreo
db = None

def obtener_cuentas(num_grupo):
    global db
    try:
        if not firebase_admin._apps:
            if "FIREBASE_CREDENTIALS" in os.environ:
                cred_json = json.loads(os.environ["FIREBASE_CREDENTIALS"])
                cred = credentials.Certificate(cred_json)
            else:
                cred = credentials.Certificate("firebase_key.json")
            firebase_admin.initialize_app(cred)

        db = firestore.client()
        docs = db.collection("tecnicos")\
                 .where("grupo", "==", str(num_grupo))\
                 .where("activo", "==", True).stream()

        usuarios = []
        for idx, doc in enumerate(docs, start=1):
            data = doc.to_dict()
            usuarios.append({
                "id": doc.id,
                "usuario": data["usuario"],
                "password": data["password"]
            })
        if usuarios:
            print(f"✅ Se cargaron {len(usuarios)} usuarios desde Firebase Firestore para el Grupo {num_grupo}.")
            return usuarios
    except Exception as e:
        print(f"⚠️ No se pudo conectar a Firebase ({e}). Leyendo archivo respaldo cuentas.json...")

    with open("cuentas.json", "r", encoding="utf-8") as archivo:
        todas = json.load(archivo)
    
    GRUPOS_LOCAL = {
        "1": todas[0:28], "2": todas[28:56], "3": todas[56:84],
        "4": todas[84:112], "5": todas[112:141]
    }
    return GRUPOS_LOCAL.get(str(num_grupo), GRUPOS_LOCAL["1"])

def actualizar_monitoreo(en_proceso, usuario_actual="", progreso="", total=0, completado=False, fallos_count=0):
    global db
    if db:
        try:
            db.collection("monitoreo").document("estado").set({
                "en_proceso": en_proceso,
                "usuario_actual": usuario_actual,
                "progreso": progreso,
                "total": total,
                "completado": completado,
                "fallos_count": fallos_count,
                "ultima_actualizacion": firestore.SERVER_TIMESTAMP
            })
        except Exception as e:
            print(f"⚠️ Error actualizando estado de monitoreo: {e}")

def enviar_correo_alerta(asunto, cuerpo_html):
    remitente = "revisioncuentahta@gmail.com"
    password = os.environ.get("EMAIL_PASSWORD")
    destinatario = "revisioncuentahta@gmail.com"

    if not password:
        print("❌ Error: No se encontró la variable EMAIL_PASSWORD.")
        return

    msg = MIMEMultipart()
    msg['From'] = remitente
    msg['To'] = destinatario
    msg['Subject'] = asunto
    msg.attach(MIMEText(cuerpo_html, 'html'))

    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(remitente, password)
        server.sendmail(remitente, destinatario, msg.as_string())
        server.quit()
        print("📧 Correo de alerta enviado exitosamente.")
    except Exception as e:
        print(f"❌ Error al enviar el correo: {e}")

async def probar_usuario(page, cuenta):
    usuario = cuenta["usuario"]
    password = cuenta["password"]
    
    try:
        await page.goto("https://hta.hyundai.com/", timeout=60000)
        await page.fill("#userId", usuario)
        await page.fill("#userPwd", password)
        await page.click("#btnLogin")
        await page.wait_for_timeout(3000)

        if await page.is_visible(".alert-danger") or "incorrect" in await page.content():
            return {"usuario": usuario, "estado": "FALLO", "motivo": "Credenciales incorrectas o cuenta bloqueada"}
        
        return {"usuario": usuario, "estado": "OK", "motivo": "Login exitoso"}
    except Exception as e:
        return {"usuario": usuario, "estado": "ERROR", "motivo": f"Error de tiempo de espera/red: {str(e)[:100]}"}

async def main():
    num_grupo = sys.argv[1] if len(sys.argv) > 1 else "1"
    print(f"🚀 Iniciando revisión del GRUPO {num_grupo}...")

    cuentas = obtener_cuentas(num_grupo)
    total_cuentas = len(cuentas)
    fallos = []

    actualizar_monitoreo(en_proceso=True, usuario_actual="Iniciando...", progreso=f"0/{total_cuentas}", total=total_cuentas)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        for idx, cuenta in enumerate(cuentas, start=1):
            actualizar_monitoreo(
                en_proceso=True, 
                usuario_actual=cuenta["usuario"], 
                progreso=f"{idx}/{total_cuentas}", 
                total=total_cuentas,
                fallos_count=len(fallos)
            )
            resultado = await probar_usuario(page, cuenta)
            print(f"[{resultado['estado']}] {resultado['usuario']} - {resultado['motivo']}")
            if resultado["estado"] != "OK":
                fallos.append(resultado)

        await browser.close()

    actualizar_monitoreo(en_proceso=False, usuario_actual="Finalizado", progreso=f"{total_cuentas}/{total_cuentas}", total=total_cuentas, completado=True, fallos_count=len(fallos))

    if fallos:
        print(f"⚠️ Se detectaron {len(fallos)} cuentas con problemas. Generando reporte...")
        gemini_api_key = os.environ.get("GEMINI_API_KEY")
        resumen_ia = ""
        if gemini_api_key:
            try:
                genai.configure(api_key=gemini_api_key)
                model = genai.GenerativeModel("gemini-1.5-flash")
                prompt = f"Analiza estos fallos de inicio de sesión en Hyundai HTA y genera un informe ejecutivo breve en HTML:\n{json.dumps(fallos, indent=2)}"
                response = model.generate_content(prompt)
                resumen_ia = response.text
            except Exception as e:
                resumen_ia = f"<p>Error al generar resumen IA: {e}</p>"

        cuerpo_email = f"""
        <h2>⚠️ Alerta de Inconvenientes - Hyundai HTA (Grupo {num_grupo})</h2>
        <p>Se encontraron <b>{len(fallos)}</b> cuentas con problemas durante la revisión automática:</p>
        <div>{resumen_ia}</div>
        <hr>
        <h3>Detalle de Cuentas Afectadas:</h3>
        <ul>
            {"".join([f"<li><b>{f['usuario']}</b>: {f['motivo']}</li>" for f in fallos])}
        </ul>
        """
        enviar_correo_alerta(f"🚨 Hyundai HTA: {len(fallos)} Cuentas con Fallos (Grupo {num_grupo})", cuerpo_email)
    else:
        print("✅ Todas las cuentas del grupo iniciaron sesión correctamente. No se envió correo.")

if __name__ == "__main__":
    asyncio.run(main())
