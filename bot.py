import os
import logging
import sqlite3
import random
import string
from datetime import datetime, timedelta

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# =========================
# CONFIG
# =========================
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 6359828846
CHANNEL_ID = -1003738953503
DB_NAME = "suscripciones.db"

# =========================
# LOGGING
# =========================
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# =========================
# DATABASE
# =========================
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS codes (
            code TEXT PRIMARY KEY,
            duration_days INTEGER NOT NULL,
            max_uses INTEGER NOT NULL,
            current_uses INTEGER NOT NULL DEFAULT 0
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            expire_date TEXT NOT NULL,
            code_used TEXT
        )
    """)

    conn.commit()
    conn.close()


def execute(query, params=(), fetchone=False, fetchall=False):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(query, params)

    data = None
    if fetchone:
        data = cursor.fetchone()
    if fetchall:
        data = cursor.fetchall()

    conn.commit()
    conn.close()
    return data


# =========================
# ADMIN CHECK
# =========================
def is_admin(user_id):
    return user_id == ADMIN_ID


# =========================
# ADMIN COMMANDS
# =========================
async def crear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    try:
        code = context.args[0]
        days = int(context.args[1])
        uses = int(context.args[2])
    except:
        await update.message.reply_text("Uso: /crear CODIGO DIAS USOS")
        return

    try:
        execute(
            "INSERT INTO codes (code, duration_days, max_uses) VALUES (?, ?, ?)",
            (code, days, uses),
        )
        await update.message.reply_text(f"✅ Código {code} creado.")
    except sqlite3.IntegrityError:
        await update.message.reply_text("❌ Ese código ya existe.")


async def crear_auto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    try:
        days = int(context.args[0])
        uses = int(context.args[1])
    except:
        await update.message.reply_text("Uso: /crear_auto DIAS USOS")
        return

    code = "".join(random.choices(string.ascii_uppercase + string.digits, k=8))

    execute(
        "INSERT INTO codes (code, duration_days, max_uses) VALUES (?, ?, ?)",
        (code, days, uses),
    )

    await update.message.reply_text(f"✅ Código generado: {code}")


async def codigos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    rows = execute("SELECT * FROM codes", fetchall=True)

    if not rows:
        await update.message.reply_text("No hay códigos.")
        return

    text = "📦 CÓDIGOS:\n\n"
    for row in rows:
        text += f"{row[0]} → {row[3]}/{row[2]} usos | {row[1]} días\n"

    await update.message.reply_text(text)


async def usuarios(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    rows = execute("SELECT * FROM users", fetchall=True)

    if not rows:
        await update.message.reply_text("No hay usuarios activos.")
        return

    text = "👥 USUARIOS ACTIVOS:\n\n"
    for row in rows:
        text += f"ID: {row[0]} | Expira: {row[1]}\n"

    await update.message.reply_text(text)


async def eliminar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    try:
        user_id = int(context.args[0])
    except:
        await update.message.reply_text("Uso: /eliminar USER_ID")
        return

    try:
        await context.bot.ban_chat_member(CHANNEL_ID, user_id)
        await context.bot.unban_chat_member(CHANNEL_ID, user_id)
    except Exception as e:
        logger.error(e)

    execute("DELETE FROM users WHERE user_id = ?", (user_id,))
    await update.message.reply_text("Usuario eliminado.")


# =========================
# USER COMMANDS
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Bienvenido.\nEnvíame tu código de acceso.")


async def handle_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    code = update.message.text.strip().upper()

    existing = execute(
        "SELECT * FROM users WHERE user_id = ?",
        (user_id,),
        fetchone=True,
    )

    if existing:
        await update.message.reply_text("❌ Ya tienes una suscripción activa.")
        return

    code_data = execute(
        "SELECT * FROM codes WHERE code = ?",
        (code,),
        fetchone=True,
    )

    if not code_data:
        await update.message.reply_text("❌ Código inválido o agotado.")
        return

    if code_data[3] >= code_data[2]:
        await update.message.reply_text("❌ Código agotado.")
        return

    expire_date = datetime.utcnow() + timedelta(days=code_data[1])

    execute(
        "INSERT INTO users (user_id, expire_date, code_used) VALUES (?, ?, ?)",
        (user_id, expire_date.isoformat(), code),
    )

    execute(
        "UPDATE codes SET current_uses = current_uses + 1 WHERE code = ?",
        (code,),
    )

    try:
        invite = await context.bot.create_chat_invite_link(
            chat_id=CHANNEL_ID,
            member_limit=1,
        )
        await update.message.reply_text(
            f"✅ Acceso concedido.\nExpira: {expire_date}\n\nEnlace:\n{invite.invite_link}"
        )
    except Exception as e:
        logger.error(e)
        await update.message.reply_text("Error generando enlace.")


# =====================
