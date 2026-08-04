import os
import psycopg2
from psycopg2 import pool
from psycopg2.extras import DictCursor
import logging
import asyncio
import re
from telegram import ReplyKeyboardMarkup, Update, InputMediaPhoto, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
Application,
CommandHandler,
MessageHandler,
CallbackQueryHandler,
filters,
ContextTypes
)

================== الإعدادات العامة ==================
TOKEN = '8419808024:AAH-O_C_1Y96H1ciGL4TE5emAPjI3DhLUqk' # ⚠️ توكن البوت
ADMIN_ID = 6451215097 # معرف المشرف الرئيسي

رابط الاتصال بقاعدة البيانات (سيتم جلبه من إعدادات PandaStack)
DATABASE_URL = os.environ.get("DATABASE_URL")

إعدادات الاشتراك الإجباري
CHANNEL_USERNAME = '@KATA_SYS' # معرف القناة
CHANNEL_LINK = 'https://t.me/KATA_SYS' # رابط القناة

logging.basicConfig(
format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
level=logging.INFO
)
logger = logging.getLogger(name)

================== إعداد تجمع اتصالات قاعدة البيانات ==================
استخدام Connection Pool مهم جداً للبيئات السحابية لمنع أخطاء الاتصال المتزامنة
try:
db_pool = psycopg2.pool.SimpleConnectionPool(1, 20, DATABASE_URL)
if db_pool:
logger.info("Connection pool created successfully")
except Exception as e:
logger.error(f"Error creating connection pool: {e}")
db_pool = None

def get_db_connection():
if not db_pool:
raise Exception("Database connection pool is not initialized.")
return db_pool.getconn()

def release_db_connection(conn):
if db_pool and conn:
db_pool.putconn(conn)

================== تزيين الأزرار والبيانات ==================
COLLEGE_EMOJI = "🏛️ "
SPEC_EMOJI = "📘 "
LEVEL_EMOJI = "📊 "
SEM_EMOJI = "📅 "
MATERIAL_EMOJI = "📖 "
BACK_EMOJI = "🔙 رجوع"
MAIN_MENU_BTN = "🏠 القائمة الرئيسية"
TIMETABLE_BTN = "🗓 الجدول الدراسي"
MATERIALS_BTN = "📚 المواد"

================== قاعدة البيانات ==================
def init_db():
"""إنشاء الهيكل الأساسي لقاعدة البيانات وتأسيس الجداول المترابطة."""
conn = get_db_connection()
c = conn.cursor()
try:
# في PostgreSQL، يتم استخدام SERIAL بدلاً من AUTOINCREMENT
c.execute('''CREATE TABLE IF NOT EXISTS colleges (
id SERIAL PRIMARY KEY,
name TEXT UNIQUE NOT NULL
)''')

c.execute('''CREATE TABLE IF NOT EXISTS specializations (
id SERIAL PRIMARY KEY,
college_id INTEGER NOT NULL,
name TEXT NOT NULL,
levels_count INTEGER DEFAULT 4,
UNIQUE(college_id, name),
FOREIGN KEY(college_id) REFERENCES colleges(id) ON DELETE CASCADE
)''')

c.execute('''CREATE TABLE IF NOT EXISTS levels (
id SERIAL PRIMARY KEY,
name TEXT UNIQUE NOT NULL
)''')

c.execute('''CREATE TABLE IF NOT EXISTS semesters (
id SERIAL PRIMARY KEY,
name TEXT UNIQUE NOT NULL
)''')

c.execute('''CREATE TABLE IF NOT EXISTS materials (
id SERIAL PRIMARY KEY,
specialization_id INTEGER NOT NULL,
level_id INTEGER NOT NULL,
semester_id INTEGER NOT NULL,
name TEXT NOT NULL,
UNIQUE(specialization_id, level_id, semester_id, name),
FOREIGN KEY(specialization_id) REFERENCES specializations(id) ON DELETE CASCADE,
FOREIGN KEY(level_id) REFERENCES levels(id) ON DELETE CASCADE,
FOREIGN KEY(semester_id) REFERENCES semesters(id) ON DELETE CASCADE
)''')

c.execute('''CREATE TABLE IF NOT EXISTS files (
id SERIAL PRIMARY KEY,
material_id INTEGER NOT NULL,
file_id TEXT NOT NULL,
file_name TEXT,
description TEXT,
file_type TEXT NOT NULL DEFAULT 'pdf',
FOREIGN KEY(material_id) REFERENCES materials(id) ON DELETE CASCADE
)''')

c.execute('''CREATE TABLE IF NOT EXISTS exam_models (
id SERIAL PRIMARY KEY,
material_id INTEGER NOT NULL,
file_id TEXT NOT NULL,
file_name TEXT,
file_type TEXT NOT NULL DEFAULT 'pdf',
FOREIGN KEY(material_id) REFERENCES materials(id) ON DELETE CASCADE
)''')

c.execute('''CREATE TABLE IF NOT EXISTS links (
id SERIAL PRIMARY KEY,
material_id INTEGER NOT NULL,
url TEXT NOT NULL,
description TEXT,
FOREIGN KEY(material_id) REFERENCES materials(id) ON DELETE CASCADE
)''')

c.execute('''CREATE TABLE IF NOT EXISTS timetable (
id SERIAL PRIMARY KEY,
specialization_id INTEGER NOT NULL UNIQUE,
file_id TEXT NOT NULL,
FOREIGN KEY(specialization_id) REFERENCES specializations(id) ON DELETE CASCADE
)''')

c.execute('''CREATE TABLE IF NOT EXISTS sub_admins (
id SERIAL PRIMARY KEY,
user_id BIGINT NOT NULL,
specialization_id INTEGER NOT NULL,
level_id INTEGER NOT NULL,
granted_by BIGINT,
granted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
UNIQUE(user_id, specialization_id, level_id)
)''')

c.execute('''CREATE TABLE IF NOT EXISTS users (
user_id BIGINT PRIMARY KEY,
username TEXT,
first_name TEXT,
last_name TEXT,
is_banned INTEGER DEFAULT 0,
registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)''')

c.execute('''CREATE TABLE IF NOT EXISTS bot_settings (
key TEXT PRIMARY KEY,
value TEXT
)''')

# إدخال البيانات الافتراضية
c.execute("INSERT INTO bot_settings (key, value) VALUES ('welcome_message', 'مرحباً بك في بوت الملخصات الجامعية!') ON CONFLICT (key) DO NOTHING")

for level in ["المستوى الأول", "المستوى الثاني", "المستوى الثالث", "المستوى الرابع", "المستوى الخامس"]:
c.execute("INSERT INTO levels (name) VALUES (%s) ON CONFLICT (name) DO NOTHING", (level,))
for sem in ["الترم الأول", "الترم الثاني"]:
c.execute("INSERT INTO semesters (name) VALUES (%s) ON CONFLICT (name) DO NOTHING", (sem,))

conn.commit()
except Exception as e:
logger.error(f"Database Initialization Error: {e}")
conn.rollback()
finally:
c.close()
release_db_connection(conn)

================== دوال استعلامات قاعدة البيانات ==================
تم تغيير علامة الاستفهام (?) في استعلامات SQL إلى (%s) لتتوافق مع PostgreSQL

def get_colleges():
conn = get_db_connection()
c = conn.cursor()
try:
c.execute("SELECT name FROM colleges ORDER BY id")
return [row[0] for row in c.fetchall()]
finally:
c.close()
release_db_connection(conn)

def get_specializations(college_name):
conn = get_db_connection()
c = conn.cursor()
try:
c.execute("""SELECT s.name FROM specializations s
JOIN colleges c ON s.college_id=c.id
WHERE c.name=%s ORDER BY s.id""", (college_name,))
return [row[0] for row in c.fetchall()]
finally:
c.close()
release_db_connection(conn)

def get_spec_levels_count(spec_name):
conn = get_db_connection()
c = conn.cursor()
try:
c.execute("SELECT levels_count FROM specializations WHERE name=%s", (spec_name,))
row = c.fetchone()
return row[0] if row else 4
finally:
c.close()
release_db_connection(conn)

def get_levels(limit=4):
conn = get_db_connection()
c = conn.cursor()
try:
c.execute("SELECT name FROM levels ORDER BY id LIMIT %s", (limit,))
return [row[0] for row in c.fetchall()]
finally:
c.close()
release_db_connection(conn)

def get_semesters():
conn = get_db_connection()
c = conn.cursor()
try:
c.execute("SELECT name FROM semesters ORDER BY id")
return [row[0] for row in c.fetchall()]
finally:
c.close()
release_db_connection(conn)

def get_materials(spec_name, level_name, sem_name):
conn = get_db_connection()
c = conn.cursor()
try:
c.execute("""SELECT m.name FROM materials m
JOIN specializations s ON m.specialization_id=s.id
JOIN levels l ON m.level_id=l.id
JOIN semesters sem ON m.semester_id=sem.id
WHERE s.name=%s AND l.name=%s AND sem.name=%s ORDER BY m.id""",
(spec_name, level_name, sem_name))
return [row[0] for row in c.fetchall()]
finally:
c.close()
release_db_connection(conn)

def get_material_id(spec_name, level_name, sem_name, mat_name):
conn = get_db_connection()
c = conn.cursor()
try:
c.execute("""SELECT m.id FROM materials m
JOIN specializations s ON m.specialization_id=s.id
JOIN levels l ON m.level_id=l.id
JOIN semesters sem ON m.semester_id=sem.id
WHERE s.name=%s AND l.name=%s AND sem.name=%s AND m.name=%s""",
(spec_name, level_name, sem_name, mat_name))
row = c.fetchone()
return row[0] if row else None
finally:
c.close()
release_db_connection(conn)

def get_files(material_id, file_type=None):
conn = get_db_connection()
c = conn.cursor()
try:
if file_type:
c.execute("SELECT id, file_id, file_name, description, file_type FROM files WHERE material_id=%s AND file_type=%s",
(material_id, file_type))
else:
c.execute("SELECT id, file_id, file_name, description, file_type FROM files WHERE material_id=%s", (material_id,))
return c.fetchall()
finally:
c.close()
release_db_connection(conn)

def add_file(material_id, file_id, file_name, file_type, description=""):
conn = get_db_connection()
c = conn.cursor()
try:
c.execute("INSERT INTO files (material_id, file_id, file_name, description, file_type) VALUES (%s,%s,%s,%s,%s)",
(material_id, file_id, file_name, description, file_type))
conn.commit()
finally:
c.close()
release_db_connection(conn)

def delete_file(file_id):
conn = get_db_connection()
c = conn.cursor()
try:
c.execute("DELETE FROM files WHERE id=%s", (file_id,))
conn.commit()
return c.rowcount > 0
finally:
c.close()
release_db_connection(conn)

def add_exam_model(material_id, file_id, file_name, file_type):
conn = get_db_connection()
c = conn.cursor()
try:
c.execute("INSERT INTO exam_models (material_id, file_id, file_name, file_type) VALUES (%s,%s,%s,%s)",
(material_id, file_id, file_name, file_type))
conn.commit()
finally:
c.close()
release_db_connection(conn)

def get_exam_models(material_id):
conn = get_db_connection()
c = conn.cursor()
try:
c.execute("SELECT id, file_id, file_name, file_type FROM exam_models WHERE material_id=%s", (material_id,))
return c.fetchall()
finally:
c.close()
release_db_connection(conn)

def delete_exam_model(exam_id):
conn = get_db_connection()
c = conn.cursor()
try:
c.execute("DELETE FROM exam_models WHERE id=%s", (exam_id,))
conn.commit()
return c.rowcount > 0
finally:
c.close()
release_db_connection(conn)

def add_link(material_id, url, description):
conn = get_db_connection()
c = conn.cursor()
try:
c.execute("INSERT INTO links (material_id, url, description) VALUES (%s,%s,%s)", (material_id, url, description))
conn.commit()
finally:
c.close()
release_db_connection(conn)

def get_links(material_id):
conn = get_db_connection()
c = conn.cursor()
try:
c.execute("SELECT id, url, description FROM links WHERE material_id=%s", (material_id,))
return c.fetchall()
finally:
c.close()
release_db_connection(conn)

def delete_link(link_id):
conn = get_db_connection()
c = conn.cursor()
try:
c.execute("DELETE FROM links WHERE id=%s", (link_id,))
conn.commit()
return c.rowcount > 0
finally:
c.close()
release_db_connection(conn)

def add_material_db(spec_name, level_name, sem_name, mat_name):
conn = get_db_connection()
c = conn.cursor()
try:
c.execute("SELECT id FROM specializations WHERE name=%s", (spec_name,))
spec_row = c.fetchone()
if not spec_row: return False, "التخصص غير موجود."
spec_id = spec_row[0]

c.execute("SELECT id FROM levels WHERE name=%s", (level_name,))
level_row = c.fetchone()
if not level_row: return False, "المستوى غير موجود."
level_id = level_row[0]

c.execute("SELECT id FROM semesters WHERE name=%s", (sem_name,))
sem_row = c.fetchone()
if not sem_row: return False, "الترم غير موجود."
sem_id = sem_row[0]

c.execute("INSERT INTO materials (specialization_id, level_id, semester_id, name) VALUES (%s,%s,%s,%s)",
(spec_id, level_id, sem_id, mat_name))
conn.commit()
return True, "تمت إضافة المادة بنجاح."
except psycopg2.IntegrityError:
conn.rollback()
return False, "المادة موجودة مسبقاً."
finally:
c.close()
release_db_connection(conn)

def delete_material_db(mat_id):
conn = get_db_connection()
c = conn.cursor()
try:
c.execute("DELETE FROM materials WHERE id=%s", (mat_id,))
conn.commit()
return c.rowcount > 0
finally:
c.close()
release_db_connection(conn)

def update_material_name_db(mat_id, new_name):
conn = get_db_connection()
c = conn.cursor()
try:
c.execute("UPDATE materials SET name=%s WHERE id=%s", (new_name, mat_id))
conn.commit()
return c.rowcount > 0
except psycopg2.IntegrityError:
conn.rollback()
return False
finally:
c.close()
release_db_connection(conn)

def add_college_db(name):
conn = get_db_connection()
c = conn.cursor()
try:
c.execute("INSERT INTO colleges (name) VALUES (%s)", (name,))
conn.commit()
return True, "تمت إضافة الكلية."
except psycopg2.IntegrityError:
conn.rollback()
return False, "الكلية موجودة مسبقاً."
finally:
c.close()
release_db_connection(conn)

def delete_college_db(college_name):
conn = get_db_connection()
c = conn.cursor()
try:
c.execute("DELETE FROM colleges WHERE name=%s", (college_name,))
conn.commit()
return c.rowcount > 0
finally:
c.close()
release_db_connection(conn)

def update_college_name_db(old_name, new_name):
conn = get_db_connection()
c = conn.cursor()
try:
c.execute("UPDATE colleges SET name=%s WHERE name=%s", (new_name, old_name))
conn.commit()
return c.rowcount > 0
except psycopg2.IntegrityError:
conn.rollback()
return False
finally:
c.close()
release_db_connection(conn)

def add_specialization_db(college_name, spec_name, levels_count):
conn = get_db_connection()
c = conn.cursor()
try:
c.execute("SELECT id FROM colleges WHERE name=%s", (college_name,))
college_row = c.fetchone()
if not college_row:
return False, "الكلية غير موجودة."
college_id = college_row[0]

c.execute("INSERT INTO specializations (college_id, name, levels_count) VALUES (%s,%s,%s)", (college_id, spec_name, levels_count))
conn.commit()
return True, "تمت إضافة التخصص بنجاح."
except psycopg2.IntegrityError:
conn.rollback()
return False, "التخصص موجود مسبقاً في هذه الكلية."
finally:
c.close()
release_db_connection(conn)

def delete_specialization_db(college_name, spec_name):
conn = get_db_connection()
c = conn.cursor()
try:
c.execute("""DELETE FROM specializations
WHERE name=%s AND college_id=(SELECT id FROM colleges WHERE name=%s)""",
(spec_name, college_name))
conn.commit()
return c.rowcount > 0
finally:
c.close()
release_db_connection(conn)

def update_specialization_name_db(college_name, old_spec, new_spec):
conn = get_db_connection()
c = conn.cursor()
try:
c.execute("SELECT id FROM colleges WHERE name=%s", (college_name,))
college_row = c.fetchone()
if not college_row:
return False
college_id = college_row[0]

c.execute("UPDATE specializations SET name=%s WHERE name=%s AND college_id=%s",
(new_spec, old_spec, college_id))
conn.commit()
return c.rowcount > 0
except psycopg2.IntegrityError:
conn.rollback()
return False
finally:
c.close()
release_db_connection(conn)

def add_sub_admin(user_id, spec_id, level_id):
conn = get_db_connection()
c = conn.cursor()
try:
c.execute("INSERT INTO sub_admins (user_id, specialization_id, level_id, granted_by) VALUES (%s,%s,%s,%s)",
(user_id, spec_id, level_id, ADMIN_ID))
conn.commit()
return True
except psycopg2.IntegrityError:
conn.rollback()
return False
finally:
c.close()
release_db_connection(conn)

def remove_sub_admin(user_id, spec_id, level_id):
conn = get_db_connection()
c = conn.cursor()
try:
c.execute("DELETE FROM sub_admins WHERE user_id=%s AND specialization_id=%s AND level_id=%s",
(user_id, spec_id, level_id))
conn.commit()
return c.rowcount > 0
finally:
c.close()
release_db_connection(conn)

def get_sub_admins():
conn = get_db_connection()
c = conn.cursor()
try:
c.execute("""SELECT sa.id, sa.user_id, s.name, l.name, sa.granted_at
FROM sub_admins sa
JOIN specializations s ON sa.specialization_id = s.id
JOIN levels l ON sa.level_id = l.id
ORDER BY sa.id""")
return c.fetchall()
finally:
c.close()
release_db_connection(conn)

def get_sub_admin_by_user(user_id):
conn = get_db_connection()
c = conn.cursor()
try:
c.execute("""SELECT sa.id, sa.user_id, s.name, l.name, sa.specialization_id, sa.level_id
FROM sub_admins sa
JOIN specializations s ON sa.specialization_id = s.id
JOIN levels l ON sa.level_id = l.id
WHERE sa.user_id = %s""", (user_id,))
return c.fetchall()
finally:
c.close()
release_db_connection(conn)

def check_sub_admin(user_id, spec_id, level_id):
conn = get_db_connection()
c = conn.cursor()
try:
c.execute("SELECT 1 FROM sub_admins WHERE user_id=%s AND specialization_id=%s AND level_id=%s", (user_id, spec_id, level_id))
return c.fetchone() is not None
finally:
c.close()
release_db_connection(conn)

def is_sub_admin_for(user_id, spec_name, level_name):
conn = get_db_connection()
c = conn.cursor()
try:
c.execute("SELECT id FROM specializations WHERE name=%s", (spec_name,))
spec_id = c.fetchone()
c.execute("SELECT id FROM levels WHERE name=%s", (level_name,))
level_id = c.fetchone()
if not spec_id or not level_id:
return False
return check_sub_admin(user_id, spec_id[0], level_id[0])
finally:
c.close()
release_db_connection(conn)

def has_file_permission(update, spec_id, level_id):
user_id = update.effective_user.id
if user_id == ADMIN_ID:
return True
return check_sub_admin(user_id, spec_id, level_id)

def get_subadmin_permissions(user_id):
rows = get_sub_admin_by_user(user_id)
return [(row[2], row[3], row[4], row[5]) for row in rows]

def set_timetable(spec_name, file_id):
conn = get_db_connection()
c = conn.cursor()
try:
c.execute("SELECT id FROM specializations WHERE name=%s", (spec_name,))
row = c.fetchone()
if not row:
return
spec_id = row[0]
c.execute("INSERT INTO timetable (specialization_id, file_id) VALUES (%s,%s) ON CONFLICT (specialization_id) DO UPDATE SET file_id=EXCLUDED.file_id", (spec_id, file_id))
conn.commit()
finally:
c.close()
release_db_connection(conn)

def get_timetable(spec_name):
conn = get_db_connection()
c = conn.cursor()
try:
c.execute("SELECT t.file_id FROM timetable t JOIN specializations s ON t.specialization_id=s.id WHERE s.name=%s", (spec_name,))
row = c.fetchone()
return row[0] if row else None
finally:
c.close()
release_db_connection(conn)

def delete_timetable(spec_name):
conn = get_db_connection()
c = conn.cursor()
try:
c.execute("DELETE FROM timetable WHERE specialization_id=(SELECT id FROM specializations WHERE name=%s)", (spec_name,))
conn.commit()
return c.rowcount > 0
finally:
c.close()
release_db_connection(conn)

def register_user(update: Update):
user = update.effective_user
user_id = user.id
username = user.username or ""
first_name = user.first_name or ""
last_name = user.last_name or ""
conn = get_db_connection()
c = conn.cursor()
try:
c.execute("INSERT INTO users (user_id, username, first_name, last_name) VALUES (%s,%s,%s,%s) ON CONFLICT (user_id) DO NOTHING",
(user_id, username, first_name, last_name))
conn.commit()
return c.rowcount > 0
except Exception as e:
logger.error(f"Error registering user {user_id}: {e}")
conn.rollback()
return False
finally:
c.close()
release_db_connection(conn)

def is_user_banned(user_id):
conn = get_db_connection()
c = conn.cursor()
try:
c.execute("SELECT is_banned FROM users WHERE user_id=%s", (user_id,))
row = c.fetchone()
return row and row[0] == 1
finally:
c.close()
release_db_connection(conn)

def ban_user(user_id):
conn = get_db_connection()
c = conn.cursor()
try:
c.execute("UPDATE users SET is_banned=1 WHERE user_id=%s", (user_id,))
conn.commit()
return c.rowcount > 0
finally:
c.close()
release_db_connection(conn)

def unban_user(user_id):
conn = get_db_connection()
c = conn.cursor()
try:
c.execute("UPDATE users SET is_banned=0 WHERE user_id=%s", (user_id,))
conn.commit()
return c.rowcount > 0
finally:
c.close()
release_db_connection(conn)

def get_welcome_message():
conn = get_db_connection()
c = conn.cursor()
try:
c.execute("SELECT value FROM bot_settings WHERE key='welcome_message'")
row = c.fetchone()
return row[0] if row else "مرحباً بك في البوت!"
finally:
c.close()
release_db_connection(conn)

def set_welcome_message(msg):
conn = get_db_connection()
c = conn.cursor()
try:
c.execute("UPDATE bot_settings SET value=%s WHERE key='welcome_message'", (msg,))
conn.commit()
finally:
c.close()
release_db_connection(conn)

def get_all_users():
conn = get_db_connection()
c = conn.cursor()
try:
c.execute("SELECT user_id, username, first_name, last_name, is_banned, registered_at FROM users ORDER BY registered_at DESC")
return c.fetchall()
finally:
c.close()
release_db_connection(conn)

def get_users_count():
conn = get_db_connection()
c = conn.cursor()
try:
c.execute("SELECT COUNT(*) FROM users")
return c.fetchone()[0]
finally:
c.close()
release_db_connection(conn)

================== الاشتراك الإجباري التفاعلي ==================
async def check_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
user_id = update.effective_user.id
if user_id == ADMIN_ID:
return True

try:
member = await context.bot.get_chat_member(chat_id=CHANNEL_USERNAME, user_id=user_id)
return member.status in ['member', 'creator', 'administrator']
except Exception as e:
logger.warning(f"Subscription check error for {user_id}: {e}")
return False

async def send_subscription_message(update: Update):
keyboard = [
[InlineKeyboardButton("📢 اضغط هنا للاشتراك في القناة", url=CHANNEL_LINK)],
[InlineKeyboardButton("🔄 تحقق من الاشتراك الان", callback_data="check_sub")]
]
reply_markup = InlineKeyboardMarkup(keyboard)
text = (
"عذراً، لا يمكنك استخدام البوت إلا بعد الاشتراك في القناة الرسمية.\n\n"
"👇 يرجى الاشتراك في القناة من خلال الزر أدناه، ثم اضغط على زر التحقق من الاشتراك."
)
if update.callback_query:
await update.callback_query.answer("⚠️ لا تزال غير مشترك في القناة، يرجى الاشتراك أولاً!", show_alert=True)
else:
await update.message.reply_text(text, reply_markup=reply_markup)

async def check_sub_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
query = update.callback_query
if await check_subscription(update, context):
await query.answer("✅ تم التاكد من اشتراكك بنجاح!")
await query.message.delete()
await start(update, context)
else:
await query.answer("❌ لم تنضم إلى القناة بعد، يرجى الانضمام أولاً.", show_alert=True)

================== التنسيق والمساعدة ==================
def decorate_colleges():
return [f"{COLLEGE_EMOJI}{c}" for c in get_colleges()]

def decorate_specs(college_name):
return [f"{SPEC_EMOJI}{s}" for s in get_specializations(college_name)]

def decorate_levels_for_spec(spec_name):
count = get_spec_levels_count(spec_name)
return [f"{LEVEL_EMOJI}{l}" for l in get_levels(limit=count)]

def decorate_semesters():
return [f"{SEM_EMOJI}{s}" for s in get_semesters()]

def decorate_materials(spec, level, sem):
return [f"{MATERIAL_EMOJI}{m}" for m in get_materials(spec, level, sem)]

def extract_name(decorated, prefix):
return decorated[len(prefix):] if decorated.startswith(prefix) else decorated

def extract_id_from_text(text):
match = re.search(r'((\d+))$`', text.strip())
return int(match.group(1)) if match else None

def clean_admin_temp_data(context):
keys_to_remove = [k for k in context.user_data.keys() if k.startswith('admin_') or k.startswith('broadcast_') or k in ['temp_spec_name', 'old_college', 'spec_to_delete', 'old_spec', 'sub_user_id', 'college_to_delete', 'link_url']]
for k in keys_to_remove:
context.user_data.pop(k, None)

================== واجهات التحكم والقوائم ==================
async def show_admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
clean_admin_temp_data(context)
keyboard = [
["📂 تصفح المواد"],
["🏛 إدارة الكليات", "📘 إدارة التخصصات"],
["👥 إدارة المشرفين الفرعيين"],
["📊 إحصائيات", "📢 رسالة جماعية"],
["⚙️ إعدادات أخرى"]
]
reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
await update.message.reply_text("🛡 لوحة تحكم المشرف الرئيسي:", reply_markup=reply_markup)
context.user_data['state'] = 'admin_panel'

async def show_admin_colleges_menu(update, context):
clean_admin_temp_data(context)
context.user_data['state'] = 'admin_colleges'
keyboard = [["➕ إضافة كلية", "➖ حذف كلية"], ["✏️ تعديل كلية", MAIN_MENU_BTN]]
reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
await update.message.reply_text("خيارات إدارة الكليات:", reply_markup=reply_markup)

async def show_admin_specs_menu(update, context):
clean_admin_temp_data(context)
context.user_data['state'] = 'admin_specs'
keyboard = [["➕ إضافة تخصص", "➖ حذف تخصص"], ["✏️ تعديل تخصص", MAIN_MENU_BTN]]
reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
await update.message.reply_text("خيارات إدارة التخصصات:", reply_markup=reply_markup)

async def show_admin_subadmins_menu(update, context):
clean_admin_temp_data(context)
context.user_data['state'] = 'admin_subadmins'
keyboard = [["➕ إضافة مشرف", "➖ حذف مشرف"], ["📋 عرض المشرفين", MAIN_MENU_BTN]]
reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
await update.message.reply_text("خيارات إدارة المشرفين الفرعيين:", reply_markup=reply_markup)

async def show_subadmin_panel(update, context):
user_id = update.effective_user.id
spec = context.user_data.get('specialization', '')
level = context.user_data.get('level', '')
sem = context.user_data.get('semester', '')
clean_admin_temp_data(context)

keyboard = [
["➕ إضافة مادة", "✏️ تعديل مادة"],
["📎 إضافة ملف", "🗑 حذف ملف"],
["➕ إضافة نموذج", "🗑 حذف نموذج"],
["➕ إضافة رابط", "🗑 حذف رابط"],
]
if user_id == ADMIN_ID:
keyboard.append(["🗑 حذف مادة"])
keyboard.append([BACK_EMOJI, MAIN_MENU_BTN])
reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
await update.message.reply_text(f"🛠 إدارة: {spec} - {level} - {sem}", reply_markup=reply_markup)
context.user_data['state'] = 'subadmin_panel'

async def show_specialization_menu(update, context, college):
specs = decorate_specs(college)
keyboard = [[s] for s in specs]
keyboard.append([BACK_EMOJI, MAIN_MENU_BTN])
reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
await update.message.reply_text(f"اختر تخصص في {COLLEGE_EMOJI}{college}:", reply_markup=reply_markup)
context.user_data['state'] = 'specialization'

async def show_material_or_manage_keyboard(update, context):
user_id = update.effective_user.id
spec = context.user_data.get('specialization')
level = context.user_data.get('level')

if not spec or not level:
await start(update, context)
return

is_sub = (user_id == ADMIN_ID) or is_sub_admin_for(user_id, spec, level)
keyboard = [[MATERIALS_BTN]]
if is_sub:
keyboard.append(["🛠 إدارة"])
keyboard.append([BACK_EMOJI, MAIN_MENU_BTN])
reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
await update.message.reply_text("اختر:", reply_markup=reply_markup)
context.user_data['state'] = 'material_or_manage'

================== أوامر واستجابات المستخدم ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
if not await check_subscription(update, context):
await send_subscription_message(update)
return

user_id = update.effective_user.id
register_user(update)
if is_user_banned(user_id):
await update.message.reply_text("⛔ تم حظرك من استخدام هذا البوت.")
return

if user_id == ADMIN_ID:
context.user_data.clear()
await show_admin_panel(update, context)
return

context.user_data.clear()
context.user_data['state'] = 'college'
welcome = get_welcome_message()
cols = decorate_colleges()
if not cols:
await update.message.reply_text("⚠️ لا توجد كليات مسجلة. تواصل مع المشرف.")
return
keyboard = [[c] for c in cols] + [[MAIN_MENU_BTN]]
reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
await update.message.reply_text(f"{welcome}\n\nيرجى اختيار الكلية للبدء:", reply_markup=reply_markup)

async def show_materials(update, context):
spec = context.user_data.get('specialization')
level = context.user_data.get('level')
sem = context.user_data.get('semester')

if not spec or not level or not sem:
await start(update, context)
return

mats = decorate_materials(spec, level, sem)
if not mats:
await update.message.reply_text("لا توجد مواد مسجلة.")
await show_material_or_manage_keyboard(update, context)
return
keyboard = [[m] for m in mats] + [[BACK_EMOJI, MAIN_MENU_BTN]]
reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
await update.message.reply_text(f'مواد {SEM_EMOJI}{sem} - {SPEC_EMOJI}{spec} ({LEVEL_EMOJI}{level}):', reply_markup=reply_markup)
context.user_data['state'] = 'material'

async def show_file_types(update, context):
keyboard = [
['📄 PDF', '🎵 صوتيات', '🖼 صور'],
['📝 نماذج اختبارات', '🔗 روابط'],
[BACK_EMOJI, MAIN_MENU_BTN]
]
reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
mat_name = context.user_data.get('material_name', 'مادة')
await update.message.reply_text(f'اختر نوع المحتوى لمادة {MATERIAL_EMOJI}{mat_name}:', reply_markup=reply_markup)
context.user_data['state'] = 'file_type'

async def show_exam_models(update, context):
spec = context.user_data.get('specialization')
level = context.user_data.get('level')
sem = context.user_data.get('semester')
mat_name = context.user_data.get('material_name')

mat_id = get_material_id(spec, level, sem, mat_name)
if not mat_id:
await update.message.reply_text("حدث خطأ، لا يمكن العثور على المادة.")
return

exams = get_exam_models(mat_id)
keyboard = []

if exams:
for exam in exams:
keyboard.append([f"{exam[2]}"])
else:
await update.message.reply_text("لا توجد نماذج اختبارات مضافة حالياً.")

keyboard.append([BACK_EMOJI, MAIN_MENU_BTN])
reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
await update.message.reply_text("نماذج الاختبارات المتاحة للعرض:", reply_markup=reply_markup)
context.user_data['state'] = 'exam_models'
context.user_data['current_exams'] = exams

async def show_links(update, context):
spec = context.user_data.get('specialization')
level = context.user_data.get('level')
sem = context.user_data.get('semester')
mat_name = context.user_data.get('material_name')

mat_id = get_material_id(spec, level, sem, mat_name)
if not mat_id:
await update.message.reply_text("حدث خطأ في استدعاء المادة.")
return

links = get_links(mat_id)
keyboard = []

if links:
for link in links:
keyboard.append([link[2]])
else:
await update.message.reply_text("لا توجد روابط مضافة حالياً.")

keyboard.append([BACK_EMOJI, MAIN_MENU_BTN])
reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
await update.message.reply_text("الروابط المتاحة للعرض:", reply_markup=reply_markup)
context.user_data['state'] = 'links'
context.user_data['current_links'] = links

async def show_file_list(update, context):
material_name = context.user_data.get('material_name')
spec = context.user_data.get('specialization')
level = context.user_data.get('level')
sem = context.user_data.get('semester')
file_type = context.user_data.get('file_type')

mat_id = get_material_id(spec, level, sem, material_name)
if not mat_id:
await update.message.reply_text("خطأ في جلب بيانات المادة.")
return

files = get_files(mat_id, file_type)
if not files:
await update.message.reply_text(f"لا توجد ملفات {file_type} لهذه المادة.")
await show_file_types(update, context)
return

keyboard = []
if len(files) > 1:
keyboard.append(["الكل"])

for f in files:
keyboard.append([f[2]])
keyboard.append([BACK_EMOJI, MAIN_MENU_BTN])

reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
await update.message.reply_text(f'اختر ملف {file_type} (أو "الكل"):', reply_markup=reply_markup)
context.user_data['current_files'] = files
context.user_data['state'] = 'file_selection'

async def send_single_file(update, context, file_row):
file_id, file_name, file_type = file_row[1], file_row[2] or "بدون اسم", file_row[4]
caption = file_name[:1000]
try:
if file_type == 'image':
await update.message.reply_photo(photo=file_id, caption=caption)
elif file_type == 'audio':
await update.message.reply_audio(audio=file_id, title=caption)
else:
await update.message.reply_document(document=file_id, caption=caption)
except Exception as e:
logger.error(f"Send error: {e}", exc_info=True)
await update.message.reply_text(f"تعذر إرسال {caption}.")

async def send_all_files(update, context, files):
file_type = files[0][4]
if file_type == 'image':
chunk_size = 10
for i in range(0, len(files), chunk_size):
chunk = files[i:i + chunk_size]
media_group = [InputMediaPhoto(media=f[1], caption=(f[2] or "")[:1000]) for f in chunk]
try:
await update.message.reply_media_group(media_group)
await asyncio.sleep(0.5)
except Exception as e:
logger.error(f"Album error: {e}", exc_info=True)
for f in chunk:
await send_single_file(update, context, f)
else:
for f in files:
await send_single_file(update, context, f)
await asyncio.sleep(0.2)

async def handle_file_selection(update, context):
text = update.message.text
files = context.user_data.get('current_files', [])
if not files:
await start(update, context)
return

if text == 'الكل':
await send_all_files(update, context, files)
elif text in [f[2] for f in files]:
for f in files:
if f[2] == text:
await send_single_file(update, context, f)
break
await show_file_list(update, context)
else:
await update.message.reply_text("الرجاء اختيار ملف من القائمة أو الضغط على رجوع.")

async def show_timetable_for_spec(update, context):
spec = context.user_data.get('specialization')
if not spec:
await update.message.reply_text("حدث خطأ في تحديد التخصص.")
return

file_id = get_timetable(spec)
user_id = update.effective_user.id

if not file_id:
await update.message.reply_text("لا يوجد جدول دراسي لهذا التخصص حالياً.")
if user_id == ADMIN_ID:
keyboard = [["➕ إضافة جدول"], [BACK_EMOJI, MAIN_MENU_BTN]]
reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
await update.message.reply_text("يمكنك إضافة جدول دراسي:", reply_markup=reply_markup)
context.user_data['state'] = 'timetable_manage'
else:
lvls = decorate_levels_for_spec(spec)
keyboard = [[l] for l in lvls] + [[TIMETABLE_BTN], [BACK_EMOJI, MAIN_MENU_BTN]]
reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
await update.message.reply_text('اختر المستوى:', reply_markup=reply_markup)
context.user_data['state'] = 'level'
return

try:
await update.message.reply_document(document=file_id, caption=f"🗓 الجدول الدراسي - {spec}")
except Exception as e:
logger.error(f"Timetable send error: {e}", exc_info=True)
await update.message.reply_text("تعذر إرسال الجدول الدراسي.")

if user_id == ADMIN_ID:
keyboard = [["🗑 حذف الجدول"], [BACK_EMOJI, MAIN_MENU_BTN]]
reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
await update.message.reply_text("إدارة الجدول:", reply_markup=reply_markup)
context.user_data['state'] = 'timetable_manage'
else:
lvls = decorate_levels_for_spec(spec)
keyboard = [[l] for l in lvls] + [[TIMETABLE_BTN], [BACK_EMOJI, MAIN_MENU_BTN]]
reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
await update.message.reply_text('اختر المستوى:', reply_markup=reply_markup)
context.user_data['state'] = 'level'

================== معالج النصوص الموحد ==================
async def unified_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
if not await check_subscription(update, context):
await send_subscription_message(update)
return

user_id = update.effective_user.id
text = update.message.text
if not text: return

# إلغاء البث الجماعي
if text in ["إلغاء", "/cancel"] and context.user_data.get('broadcast_step'):
clean_admin_temp_data(context)
await update.message.reply_text("✅ تم إلغاء عملية البث الجماعي بنجاح.")
await show_admin_panel(update, context)
return

broadcast_step = context.user_data.get('broadcast_step')
if broadcast_step == 'waiting_text':
context.user_data['broadcast_text'] = text
context.user_data['broadcast_step'] = 'waiting_media'
await update.message.reply_text("✓ تم حفظ النص بنجاح. يمكنك الآن إرسال صورة/فيديو (اختياري) أو الضغط على /send للإرسال فوراً.\n\n(للإلغاء أرسل: إلغاء)")
return
if broadcast_step == 'waiting_media':
await update.message.reply_text("الرجاء إرسال وسائط (صورة أو فيديو) أو /send للإرسال بدون وسائط.\n\n(للإلغاء أرسل: إلغاء)")
return

# زر القائمة الرئيسية
if text == MAIN_MENU_BTN:
if user_id == ADMIN_ID:
await show_admin_panel(update, context)
else:
context.user_data.clear()
await start(update, context)
return

# أزرار لوحة المشرف الرئيسي
if user_id == ADMIN_ID:
if text == "📂 تصفح المواد":
clean_admin_temp_data(context)
context.user_data['state'] = 'college'
cols = decorate_colleges()
if not cols:
await update.message.reply_text("لا توجد كليات مسجلة بعد."); return
keyboard = [[c] for c in cols] + [[MAIN_MENU_BTN]]
reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
await update.message.reply_text("اختر الكلية لتصفح موادها:", reply_markup=reply_markup)
return
elif text == "🏛 إدارة الكليات":
await show_admin_colleges_menu(update, context)
return
elif text == "📘 إدارة التخصصات":
await show_admin_specs_menu(update, context)
return
elif text == "👥 إدارة المشرفين الفرعيين":
await show_admin_subadmins_menu(update, context)
return
elif text == "📊 إحصائيات":
await update.message.reply_text(f"📊 إجمالي عدد المستخدمين المسجلين: {get_users_count()}")
return
elif text == "📢 رسالة جماعية":
context.user_data['broadcast_step'] = 'waiting_text'
await update.message.reply_text("قم بإرسال النص الذي تريد بثه لجميع المستخدمين (يمكنك إرفاق صورة/فيديو في الخطوة التالية).\n\n(للإلغاء أرسل: إلغاء)")
return
elif text == "⚙️ إعدادات أخرى":
await update.message.reply_text("هذا القسم قيد التطوير...")
return

elif text == "➕ إضافة كلية":
context.user_data['admin_action'] = 'add_college'
context.user_data['admin_state'] = 'enter_college_name'
context.user_data['state'] = 'admin_action'
await update.message.reply_text("قم بإرسال اسم الكلية الجديدة:")
return
elif text == "➖ حذف كلية":
cols = decorate_colleges()
if not cols:
await update.message.reply_text("لا توجد كليات مسجلة."); return
context.user_data['admin_action'] = 'delete_college'
context.user_data['admin_state'] = 'choose_college'
context.user_data['state'] = 'admin_action'
keyboard = [[c] for c in cols] + [[MAIN_MENU_BTN]]
reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
await update.message.reply_text("اختر الكلية التي ترغب في حذفها:", reply_markup=reply_markup)
return
elif text == "✏️ تعديل كلية":
cols = decorate_colleges()
if not cols:
await update.message.reply_text("لا توجد كليات مسجلة."); return
context.user_data['admin_action'] = 'edit_college'
context.user_data['admin_state'] = 'choose_college_to_edit'
context.user_data['state'] = 'admin_action'
keyboard = [[c] for c in cols] + [[MAIN_MENU_BTN]]
reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
await update.message.reply_text("اختر الكلية التي تريد تعديل اسمها:", reply_markup=reply_markup)
return

elif text == "➕ إضافة تخصص":
cols = decorate_colleges()
if not cols:
await update.message.reply_text("لا توجد كليات مسجلة."); return
context.user_data['admin_action'] = 'add_spec'
context.user_data['admin_state'] = 'choose_college_for_spec'
context.user_data['state'] = 'admin_action'
keyboard = [[c] for c in cols] + [[MAIN_MENU_BTN]]
reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
await update.message.reply_text("اختر الكلية لإضافة التخصص إليها:", reply_markup=reply_markup)
return
elif text == "➖ حذف تخصص":
cols = decorate_colleges()
if not cols:
await update.message.reply_text("لا توجد كليات مسجلة."); return
context.user_data['admin_action'] = 'delete_spec'
context.user_data['admin_state'] = 'choose_college_for_spec_del'
context.user_data['state'] = 'admin_action'
keyboard = [[c] for c in cols] + [[MAIN_MENU_BTN]]
reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
await update.message.reply_text("اختر الكلية التابع لها التخصص المراد حذفه:", reply_markup=reply_markup)
return
elif text == "✏️ تعديل تخصص":
cols = decorate_colleges()
if not cols:
await update.message.reply_text("لا توجد كليات مسجلة."); return
context.user_data['admin_action'] = 'edit_spec'
context.user_data['admin_state'] = 'choose_college_for_spec_edit'
context.user_data['state'] = 'admin_action'
keyboard = [[c] for c in cols] + [[MAIN_MENU_BTN]]
reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
await update.message.reply_text("اختر الكلية التابع لها التخصص المراد تعديله:", reply_markup=reply_markup)
return

elif text == "➕ إضافة مشرف":
context.user_data['admin_action'] = 'add_subadmin'
context.user_data['admin_state'] = 'enter_user_id'
context.user_data['state'] = 'admin_action'
await update.message.reply_text("أرسل معرف المستخدم (User ID) من تيليجرام لمنحه صلاحية الإشراف الفرعي:")
return
elif text == "➖ حذف مشرف":
sub_admins = get_sub_admins()
if not sub_admins:
await update.message.reply_text("لا يوجد مشرفين فرعيين مسجلين حالياً."); return
context.user_data['admin_action'] = 'remove_subadmin'
context.user_data['admin_state'] = 'choose_subadmin_to_remove'
context.user_data['state'] = 'admin_action'
keyboard = [[f"{sa[1]} | {sa[2]} | {sa[3]}"] for sa in sub_admins] + [[MAIN_MENU_BTN]]
reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
await update.message.reply_text("اختر صلاحية المشرف الفرعي التي تريد إزالتها بدقة:", reply_markup=reply_markup)
return
elif text == "📋 عرض المشرفين":
sub_admins = get_sub_admins()
if not sub_admins:
await update.message.reply_text("لا يوجد مشرفين فرعيين."); return
msg = "قائمة المشرفين الفرعيين والصلاحيات:\n\n"
for sa in sub_admins:
line = f"🆔 {sa[1]} | تخصص: {sa[2]} | مستوى: {sa[3]}\n"
if len(msg) + len(line) > 4000:
await update.message.reply_text(msg)
msg = ""
msg += line
if msg:
await update.message.reply_text(msg)
return

await handle_message(update, context)

================== معالجات التنقل وإدخال البيانات ==================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
user_id = update.effective_user.id
if is_user_banned(user_id):
await update.message.reply_text("⛔ محظور.")
return

text = update.message.text
if not text: return

state = context.user_data.get('state', 'college')

if state != 'admin_action':
cols = decorate_colleges()
if text in cols:
college = extract_name(text, COLLEGE_EMOJI)
context.user_data['college'] = college
context.user_data['state'] = 'specialization'
await show_specialization_menu(update, context, college)
return

subadmin_actions = ["➕ إضافة مادة", "📎 إضافة ملف", "🗑 حذف ملف", "➕ إضافة نموذج", "🗑 حذف نموذج", "➕ إضافة رابط", "🗑 حذف رابط", "✏️ تعديل مادة", "🗑 حذف مادة"]
if text in subadmin_actions:
spec = context.user_data.get('specialization')
if not spec:
await update.message.reply_text("⚠️ عذراً، تم مسح الذاكرة اللحظية. يرجى إعادة تصفح المادة من جديد للقيام بهذه العملية.")
if user_id == ADMIN_ID:
await show_admin_panel(update, context)
else:
await start(update, context)
return
state = 'subadmin_panel'
context.user_data['state'] = 'subadmin_panel'

# زر الرجوع التكيفي
if text == BACK_EMOJI and state != 'admin_action':
if state == 'file_selection':
context.user_data['state'] = 'file_type'
await show_file_types(update, context)
elif state in ['exam_models', 'links']:
context.user_data['state'] = 'file_type'
await show_file_types(update, context)
elif state == 'file_type':
context.user_data['state'] = 'material'
await show_materials(update, context)
elif state == 'material':
await show_material_or_manage_keyboard(update, context)
elif state == 'material_or_manage':
context.user_data['state'] = 'semester'
sems = decorate_semesters()
keyboard = [[s] for s in sems] + [[BACK_EMOJI, MAIN_MENU_BTN]]
reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
await update.message.reply_text('اختر الترم:', reply_markup=reply_markup)
elif state == 'semester':
context.user_data['state'] = 'level'
spec = context.user_data.get('specialization')
lvls = decorate_levels_for_spec(spec)
keyboard = [[l] for l in lvls] + [[TIMETABLE_BTN], [BACK_EMOJI, MAIN_MENU_BTN]]
reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
await update.message.reply_text('اختر المستوى:', reply_markup=reply_markup)
elif state == 'level':
college = context.user_data.get('college')
if college:
context.user_data['state'] = 'specialization'
await show_specialization_menu(update, context, college)
else:
await start(update, context)
elif state == 'specialization':
context.user_data['state'] = 'college'
cols = decorate_colleges()
keyboard = [[c] for c in cols] + [[MAIN_MENU_BTN]]
reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
await update.message.reply_text('اختر الكلية:', reply_markup=reply_markup)
elif state == 'timetable_manage':
spec = context.user_data.get('specialization')
if spec:
lvls = decorate_levels_for_spec(spec)
keyboard = [[l] for l in lvls] + [[TIMETABLE_BTN], [BACK_EMOJI, MAIN_MENU_BTN]]
reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
await update.message.reply_text('اختر المستوى:', reply_markup=reply_markup)
context.user_data['state'] = 'level'
else:
await start(update, context)
elif state == 'subadmin_panel':
await show_material_or_manage_keyboard(update, context)
else:
await start(update, context)
return

# معالجة القوائم والتنقل المتسلسل
if state == 'college':
cols = decorate_colleges()
if text not in cols:
await update.message.reply_text('اختر كلية من القائمة.')

elif state == 'specialization':
college = context.user_data.get('college')
specs = decorate_specs(college)
if text in specs:
spec = extract_name(text, SPEC_EMOJI)
context.user_data['specialization'] = spec
context.user_data['state'] = 'level'
lvls = decorate_levels_for_spec(spec)
keyboard = [[l] for l in lvls] + [[TIMETABLE_BTN], [BACK_EMOJI, MAIN_MENU_BTN]]
reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
await update.message.reply_text(f'اختر المستوى في {text}:', reply_markup=reply_markup)
else:
await update.message.reply_text('اختر تخصصاً من القائمة.')

elif state == 'level':
spec = context.user_data.get('specialization')
lvls = decorate_levels_for_spec(spec)
if text in lvls:
level = extract_name(text, LEVEL_EMOJI)
context.user_data['level'] = level
context.user_data['state'] = 'semester'
sems = decorate_semesters()
keyboard = [[s] for s in sems] + [[BACK_EMOJI, MAIN_MENU_BTN]]
reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
await update.message.reply_text('اختر الترم:', reply_markup=reply_markup)
elif text == TIMETABLE_BTN:
await show_timetable_for_spec(update, context)
else:
await update.message.reply_text('اختر مستوى من القائمة.')

elif state == 'semester':
sems = decorate_semesters()
if text in sems:
sem = extract_name(text, SEM_EMOJI)
context.user_data['semester'] = sem
await show_material_or_manage_keyboard(update, context)
else:
await update.message.reply_text('اختر ترماً من القائمة.')

elif state == 'material_or_manage':
if text == MATERIALS_BTN:
context.user_data['state'] = 'material'
await show_materials(update, context)
elif text == "🛠 إدارة":
await show_subadmin_panel(update, context)
else:
await update.message.reply_text("الرجاء اختيار خيار من القائمة.")

elif state == 'material':
spec = context.user_data.get('specialization')
level = context.user_data.get('level')
sem = context.user_data.get('semester')
mats = decorate_materials(spec, level, sem)
if text in mats:
mat_name = extract_name(text, MATERIAL_EMOJI)
context.user_data['material_name'] = mat_name
await show_file_types(update, context)
else:
await update.message.reply_text('اختر مادة من القائمة.')

elif state == 'file_type':
if text in ['📄 PDF', '🎵 صوتيات', '🖼 صور']:
type_map = {'📄 PDF': 'pdf', '🎵 صوتيات': 'audio', '🖼 صور': 'image'}
context.user_data['file_type'] = type_map[text]
await show_file_list(update, context)
elif text == '📝 نماذج اختبارات':
await show_exam_models(update, context)
elif text == '🔗 روابط':
await show_links(update, context)
else:
await update.message.reply_text('الرجاء اختيار نوع المحتوى من الأزرار.')

elif state == 'exam_models':
exams = context.user_data.get('current_exams', [])
if text in [e[2] for e in exams]:
for e in exams:
if text == e[2]:
await send_single_file(update, context, (e[0], e[1], e[2], None, e[3]))
break
else:
await update.message.reply_text("الرجاء اختيار نموذج من القائمة.")

elif state == 'links':
links = context.user_data.get('current_links', [])
if text in [l[2] for l in links]:
for l in links:
if text == l[2]:
await update.message.reply_text(f"{l[2]}\n{l[1]}")
break
else:
await update.message.reply_text("الرجاء اختيار خيار صحيح من القائمة.")

elif state == 'file_selection':
await handle_file_selection(update, context)

elif state == 'timetable_manage':
if text == "➕ إضافة جدول" and user_id == ADMIN_ID:
context.user_data['admin_action'] = 'add_timetable'
context.user_data['admin_state'] = 'wait_timetable_upload'
context.user_data['state'] = 'admin_action'
await update.message.reply_text("أرسل ملف PDF الخاص بالجدول الدراسي الآن:")
elif text == "🗑 حذف الجدول" and user_id == ADMIN_ID:
spec = context.user_data.get('specialization')
if delete_timetable(spec):
await update.message.reply_text("✅ تم حذف الجدول الدراسي بنجاح.")
else:
await update.message.reply_text("لا يوجد جدول دراسي مسجل لحذفه.")

lvls = decorate_levels_for_spec(spec)
keyboard = [[l] for l in lvls] + [[TIMETABLE_BTN], [BACK_EMOJI, MAIN_MENU_BTN]]
reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
await update.message.reply_text('اختر المستوى:', reply_markup=reply_markup)
context.user_data['state'] = 'level'
else:
await update.message.reply_text("الرجاء اختيار عملية صحيحة.")

elif state == 'subadmin_panel':
spec = context.user_data.get('specialization')
level = context.user_data.get('level')
sem = context.user_data.get('semester')

if text == "➕ إضافة مادة":
context.user_data['admin_action'] = 'add_material'
context.user_data['admin_state'] = 'enter_material_name'
context.user_data['state'] = 'admin_action'
await update.message.reply_text("أرسل اسم المادة الجديدة بدقة:")
return

action_map = {
"📎 إضافة ملف": ('add_file', "اختر المادة التي تود إضافة ملف إليها:"),
"🗑 حذف ملف": ('delete_file', "اختر المادة لحذف ملف منها:"),
"➕ إضافة نموذج": ('add_exam_model', "اختر المادة لإضافة نموذج اختبار:"),
"🗑 حذف نموذج": ('delete_exam_model', "اختر المادة لحذف نموذج اختبار منها:"),
"➕ إضافة رابط": ('add_link', "اختر المادة لإضافة رابط:"),
"🗑 حذف رابط": ('delete_link', "اختر المادة لحذف رابط منها:"),
"✏️ تعديل مادة": ('edit_material', "اختر المادة لتعديل اسمها:"),
"🗑 حذف مادة": ('delete_material', "اختر المادة التي تريد حذفها:")
}

if text in action_map:
if text == "🗑 حذف مادة" and user_id != ADMIN_ID:
await update.message.reply_text("⛔ المشرف الرئيسي فقط يمتلك صلاحية حذف المواد.")
return

mats = get_materials(spec, level, sem)
if not mats:
await update.message.reply_text("لا توجد مواد مسجلة في هذا التخصص والمستوى.")
return

act_key, msg = action_map[text]
context.user_data['admin_action'] = act_key
context.user_data['admin_state'] = 'choose_material'
context.user_data['state'] = 'admin_action'
context.user_data['admin_mats'] = [f"{MATERIAL_EMOJI}{m}" for m in mats]

keyboard = [[f"{MATERIAL_EMOJI}{m}"] for m in mats] + [[BACK_EMOJI, MAIN_MENU_BTN]]
reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
await update.message.reply_text(msg, reply_markup=reply_markup)
else:
await update.message.reply_text("خيار غير متاح أو ليس لديك الصلاحية الكافية.")

elif state == 'admin_action':
handled = await admin_text_handler(update, context)
if not handled:
await update.message.reply_text("خطأ في إتمام العملية.")

elif user_id != ADMIN_ID:
await start(update, context)

================== المعالج الإداري للأعمال ==================
async def admin_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
user_id = update.effective_user.id
action = context.user_data.get('admin_action')

if not action:
return False

text = update.message.text

if text == BACK_EMOJI:
if action in ['add_college', 'delete_college', 'edit_college']:
await show_admin_colleges_menu(update, context)
elif action in ['add_spec', 'delete_spec', 'edit_spec']:
await show_admin_specs_menu(update, context)
elif action in ['add_subadmin', 'remove_subadmin']:
await show_admin_subadmins_menu(update, context)
elif action in ['add_timetable']:
spec = context.user_data.get('specialization')
if spec:
lvls = decorate_levels_for_spec(spec)
keyboard = [[l] for l in lvls] + [[TIMETABLE_BTN], [BACK_EMOJI, MAIN_MENU_BTN]]
reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
await update.message.reply_text('اختر المستوى:', reply_markup=reply_markup)
context.user_data['state'] = 'level'
else:
await start(update, context)
elif action in ['add_material', 'delete_material', 'edit_material', 'add_file', 'delete_file', 'add_exam_model', 'delete_exam_model', 'add_link', 'delete_link']:
await show_subadmin_panel(update, context)
else:
if user_id != ADMIN_ID:
await start(update, context)
return True

state = context.user_data.get('admin_state')

if action == 'add_timetable':
await update.message.reply_text("الرجاء إرسال ملف PDF فقط، أو اضغط رجوع للإلغاء.")
return True

if action == 'add_college':
if state == 'enter_college_name':
success, msg = add_college_db(text)
await update.message.reply_text(msg)
await show_admin_colleges_menu(update, context)
return True

if action == 'delete_college':
if state == 'choose_college':
cols = decorate_colleges()
if text in cols:
college = extract_name(text, COLLEGE_EMOJI)
context.user_data['college_to_delete'] = college
context.user_data['admin_state'] = 'confirm_delete_college'
keyboard = [['نعم', 'لا']]
reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
await update.message.reply_text(f"تحذير هام: سيؤدي حذف كلية '{college}' إلى حذف جميع تخصصاتها وموادها وملفاتها بشكل نهائي.\n\nهل أنت متأكد من الحذف؟", reply_markup=reply_markup)
else:
await update.message.reply_text("اسم الكلية غير صحيح، اختر من الأزرار المتاحة.")
elif state == 'confirm_delete_college':
if text == 'نعم':
if delete_college_db(context.user_data['college_to_delete']):
await update.message.reply_text("✅ تم حذف الكلية وجميع توابعها بنجاح.")
else:
await update.message.reply_text("❌ فشل عملية الحذف.")
else:
await update.message.reply_text("تم إلغاء عملية الحذف.")
await show_admin_colleges_menu(update, context)
return True

if action == 'edit_college':
if state == 'choose_college_to_edit':
cols = decorate_colleges()
if text in cols:
old = extract_name(text, COLLEGE_EMOJI)
context.user_data['old_college'] = old
context.user_data['admin_state'] = 'enter_new_college_name'
await update.message.reply_text(f"أرسل الاسم الجديد لكلية '{old}':")
else:
await update.message.reply_text("اسم الكلية غير صحيح.")
elif state == 'enter_new_college_name':
old = context.user_data['old_college']
if update_college_name_db(old, text):
await update.message.reply_text(f"✅ تم تغيير اسم الكلية من '{old}' إلى '{text}'.")
else:
await update.message.reply_text("❌ فشل التعديل، ربما الاسم موجود مسبقاً.")
await show_admin_colleges_menu(update, context)
return True

if action == 'add_spec':
if state == 'choose_college_for_spec':
cols = decorate_colleges()
if text in cols:
college = extract_name(text, COLLEGE_EMOJI)
context.user_data['admin_college'] = college
context.user_data['admin_state'] = 'enter_spec_name'
await update.message.reply_text(f"أرسل اسم التخصص الجديد الخاص بكلية '{college}':")
else:
await update.message.reply_text("اسم الكلية غير صحيح.")
elif state == 'enter_spec_name':
context.user_data['temp_spec_name'] = text
context.user_data['admin_state'] = 'choose_levels_count'
keyboard = [["4 مستويات", "5 مستويات"], [MAIN_MENU_BTN]]
reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
await update.message.reply_text("هل هذا التخصص يتكون من 4 أو 5 مستويات؟", reply_markup=reply_markup)
elif state == 'choose_levels_count':
if text in ["4 مستويات", "5 مستويات"]:
levels_count = 5 if text == "5 مستويات" else 4
college = context.user_data['admin_college']
spec_name = context.user_data['temp_spec_name']
success, msg = add_specialization_db(college, spec_name, levels_count)
await update.message.reply_text(msg)
await show_admin_specs_menu(update, context)
else:
await update.message.reply_text("الرجاء اختيار عدد المستويات من الأزرار فقط.")
return True

if action == 'delete_spec':
if state == 'choose_college_for_spec_del':
cols = decorate_colleges()
if text in cols:
college = extract_name(text, COLLEGE_EMOJI)
context.user_data['admin_college'] = college
specs = decorate_specs(college)
if not specs:
await update.message.reply_text("لا توجد تخصصات مسجلة بهذه الكلية.");
await show_admin_specs_menu(update, context)
return True
context.user_data['admin_state'] = 'choose_spec_to_delete'
keyboard = [[s] for s in specs] + [[MAIN_MENU_BTN]]
reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
await update.message.reply_text("اختر التخصص الذي ترغب في حذفه:", reply_markup=reply_markup)
else:
await update.message.reply_text("اسم الكلية غير صحيح.")
elif state == 'choose_spec_to_delete':
college = context.user_data['admin_college']
specs = decorate_specs(college)
if text in specs:
spec = extract_name(text, SPEC_EMOJI)
context.user_data['spec_to_delete'] = spec
context.user_data['admin_state'] = 'confirm_delete_spec'
keyboard = [['نعم', 'لا']]
reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
await update.message.reply_text(f"تحذير: حذف تخصص '{spec}' سيؤدي لحذف جميع مواده وملفاته نهائياً.\nهل أنت متأكد؟", reply_markup=reply_markup)
else:
await update.message.reply_text("التخصص المختار غير صحيح.")
elif state == 'confirm_delete_spec':
if text == 'نعم':
college = context.user_data['admin_college']
spec = context.user_data['spec_to_delete']
if delete_specialization_db(college, spec):
await update.message.reply_text(f"✅ تم حذف تخصص '{spec}' بنجاح.")
else:
await update.message.reply_text("❌ فشل عملية الحذف.")
else:
await update.message.reply_text("تم إلغاء عملية الحذف.")
await show_admin_specs_menu(update, context)
return True

if action == 'edit_spec':
if state == 'choose_college_for_spec_edit':
cols = decorate_colleges()
if text in cols:
college = extract_name(text, COLLEGE_EMOJI)
context.user_data['admin_college'] = college
specs = decorate_specs(college)
if not specs:
await update.message.reply_text("لا توجد تخصصات بهذه الكلية.");
await show_admin_specs_menu(update, context)
return True
context.user_data['admin_state'] = 'choose_spec_to_edit'
keyboard = [[s] for s in specs] + [[MAIN_MENU_BTN]]
reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
await update.message.reply_text("اختر التخصص المراد تعديل اسمه:", reply_markup=reply_markup)
else:
await update.message.reply_text("اسم الكلية غير موجود.")
elif state == 'choose_spec_to_edit':
college = context.user_data['admin_college']
specs = decorate_specs(college)
if text in specs:
old = extract_name(text, SPEC_EMOJI)
context.user_data['old_spec'] = old
context.user_data['admin_state'] = 'enter_new_spec_name'
await update.message.reply_text(f"أرسل الاسم الجديد للتخصص '{old}':")
else:
await update.message.reply_text("التخصص المختار غير صحيح.")
elif state == 'enter_new_spec_name':
college = context.user_data['admin_college']
old = context.user_data['old_spec']
if update_specialization_name_db(college, old, text):
await update.message.reply_text(f"✅ تم تغيير التخصص من '{old}' إلى '{text}'.")
else:
await update.message.reply_text("❌ فشل التعديل، تأكد من صحة البيانات.")
await show_admin_specs_menu(update, context)
return True

if action == 'add_subadmin':
if state == 'enter_user_id':
try:
sub_id = int(text)
context.user_data['sub_user_id'] = sub_id
context.user_data['admin_state'] = 'choose_college_sub'
cols = decorate_colleges()
if not cols:
await update.message.reply_text("لا توجد كليات مسجلة.");
await show_admin_subadmins_menu(update, context)
return True
keyboard = [[c] for c in cols] + [[MAIN_MENU_BTN]]
reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
await update.message.reply_text("اختر الكلية الصلاحية:", reply_markup=reply_markup)
except ValueError:
await update.message.reply_text("يرجى إدخال أرقام صحيحة فقط.")
elif state == 'choose_college_sub':
cols = decorate_colleges()
if text in cols:
college = extract_name(text, COLLEGE_EMOJI)
context.user_data['admin_college'] = college
specs = decorate_specs(college)
if not specs:
await update.message.reply_text("لا توجد تخصصات مسجلة في هذه الكلية.");
await show_admin_subadmins_menu(update, context)
return True
context.user_data['admin_state'] = 'choose_spec_sub'
keyboard = [[s] for s in specs] + [[MAIN_MENU_BTN]]
reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
await update.message.reply_text("اختر التخصص الذي سُيشرف عليه:", reply_markup=reply_markup)
else:
await update.message.reply_text("اسم الكلية غير صحيح.")
elif state == 'choose_spec_sub':
college = context.user_data['admin_college']
specs = decorate_specs(college)
if text in specs:
spec = extract_name(text, SPEC_EMOJI)
context.user_data['admin_spec'] = spec
context.user_data['admin_state'] = 'choose_level_sub'
lvls = decorate_levels_for_spec(spec)
keyboard = [[l] for l in lvls] + [[MAIN_MENU_BTN]]
reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
await update.message.reply_text("اختر المستوى الدراسي الذي سيشرف عليه:", reply_markup=reply_markup)
else:
await update.message.reply_text("اسم التخصص غير صحيح.")
elif state == 'choose_level_sub':
spec_name = context.user_data['admin_spec']
lvls = decorate_levels_for_spec(spec_name)
if text in lvls:
level = extract_name(text, LEVEL_EMOJI)
conn = get_db_connection()
c = conn.cursor()
try:
c.execute("SELECT id FROM specializations WHERE name=%s", (spec_name,))
spec_row = c.fetchone()
c.execute("SELECT id FROM levels WHERE name=%s", (level,))
level_row = c.fetchone()
finally:
c.close()
release_db_connection(conn)

if not spec_row or not level_row:
await update.message.reply_text("حدث خطأ في جلب بيانات التخصص أو المستوى.");
await show_admin_subadmins_menu(update, context)
return True

if add_sub_admin(context.user_data['sub_user_id'], spec_row[0], level_row[0]):
await update.message.reply_text(f"✅ تم منح صلاحية الإشراف للمستخدم ID: {context.user_data['sub_user_id']}.")
else:
await update.message.reply_text("❌ فشل منح الصلاحية (ربما لديه هذه الصلاحية مسبقاً).")

await show_admin_subadmins_menu(update, context)
else:
await update.message.reply_text("المستوى المختار غير صحيح.")
return True

if action == 'remove_subadmin':
if state == 'choose_subadmin_to_remove':
try:
parts = [p.strip() for p in text.split('|')]
if len(parts) != 3:
await update.message.reply_text("تنسيق الاختيار غير صحيح، الرجاء اختيار زر من القائمة.");
return True

uid_str, spec, level = parts
conn = get_db_connection()
c = conn.cursor()
try:
c.execute("SELECT s.id, l.id FROM specializations s, levels l WHERE s.name=%s AND l.name=%s", (spec, level))
row = c.fetchone()
finally:
c.close()
release_db_connection(conn)

if not row:
await update.message.reply_text("حدث خطأ في التحقق من التخصص والمستوى.");
return True

if remove_sub_admin(int(uid_str.replace('🆔', '').strip()), row[0], row[1]):
await update.message.reply_text("✅ تم سحب الصلاحية بنجاح.")
else:
await update.message.reply_text("❌ فشلت عملية سحب الصلاحية.")

await show_admin_subadmins_menu(update, context)
except Exception as e:
logger.error(f"Remove subadmin error: {e}", exc_info=True)
await update.message.reply_text("حدث خطأ أثناء معالجة الطلب.")
return True

if action in ('add_material', 'delete_material', 'edit_material', 'add_file', 'delete_file',
'add_exam_model', 'delete_exam_model', 'add_link', 'delete_link'):

spec = context.user_data.get('specialization')
level = context.user_data.get('level')
sem = context.user_data.get('semester')

if state == 'enter_material_name':
if not all([spec, level, sem]):
await update.message.reply_text("بيانات غير مكتملة. الرجاء البدء من جديد.");
return True

if user_id != ADMIN_ID:
perms = get_subadmin_permissions(user_id)
if not any(p[0]==spec and p[1]==level for p in perms):
await update.message.reply_text("⛔ عذراً، ليس لديك صلاحية في هذا القسم.");
await show_subadmin_panel(update, context)
return True

success, msg = add_material_db(spec, level, sem, text)
await update.message.reply_text(msg)
await show_subadmin_panel(update, context)
return True

elif state == 'choose_material':
mats = context.user_data.get('admin_mats', [])
if text in mats:
mat_name = extract_name(text, MATERIAL_EMOJI)
mat_id = get_material_id(spec, level, sem, mat_name)

if not mat_id:
await update.message.reply_text("حدث خطأ غير متوقع في جلب هوية المادة.");
return True

if user_id != ADMIN_ID:
conn = get_db_connection()
c = conn.cursor()
try:
c.execute("SELECT specialization_id, level_id FROM materials WHERE id=%s", (mat_id,))
row = c.fetchone()
finally:
c.close()
release_db_connection(conn)

if not row or not has_file_permission(update, row[0], row[1]):
await update.message.reply_text("⛔ عذراً، ليس لديك صلاحية لإدارة هذه المادة.");
await show_subadmin_panel(update, context)
return True

context.user_data['admin_mat_id'] = mat_id
context.user_data['admin_mat_name'] = mat_name

if action == 'delete_material':
context.user_data['admin_state'] = 'confirm_delete_mat'
keyboard = [['نعم', 'لا']]
reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
await update.message.reply_text(f"هل أنت متأكد تماماً من رغبتك بحذف مادة '{mat_name}' وكافة ملفاتها؟", reply_markup=reply_markup)

elif action == 'edit_material':
context.user_data['admin_state'] = 'enter_new_mat_name'
await update.message.reply_text(f"قم بإرسال الاسم الجديد لمادة '{mat_name}':")

elif action == 'add_file':
context.user_data['admin_state'] = 'wait_file_upload'
await update.message.reply_text("قم برفع وإرسال الملفات الآن (مستند PDF، صورة، مقطع صوتي). \nعند الانتهاء أرسل الأمر /done.")

elif action == 'delete_file':
files = get_files(mat_id)
if not files:
await update.message.reply_text("المادة فارغة، لا توجد ملفات لحذفها.");
await show_subadmin_panel(update, context)
return True

context.user_data['admin_state'] = 'choose_file_to_delete'
keyboard = [[f"[{f[4]}] {f[2]} ({f[0]})"] for f in files] + [[BACK_EMOJI, MAIN_MENU_BTN]]
reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
await update.message.reply_text("الرجاء اختيار الملف الذي ترغب بحذفه من القائمة:", reply_markup=reply_markup)

elif action == 'add_exam_model':
context.user_data['admin_state'] = 'wait_exam_upload'
await update.message.reply_text("أرسل ملف النموذج (صورة أو PDF) المخصص لهذه المادة:")

elif action == 'delete_exam_model':
exams = get_exam_models(mat_id)
if not exams:
await update.message.reply_text("لا توجد نماذج مسجلة في هذه المادة.")
await show_subadmin_panel(update, context)
return True
context.user_data['admin_state'] = 'choose_exam_to_delete'
keyboard = [[f"{e[2]} ({e[0]})"] for e in exams] + [[BACK_EMOJI, MAIN_MENU_BTN]]
reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
await update.message.reply_text("اختر النموذج لحذفه:", reply_markup=reply_markup)

elif action == 'add_link':
context.user_data['admin_state'] = 'enter_link_url'
await update.message.reply_text("قم بإرسال رابط URL:")

elif action == 'delete_link':
links = get_links(mat_id)
if not links:
await update.message.reply_text("لا توجد روابط مسجلة لهذه المادة.")
await show_subadmin_panel(update, context)
return True
context.user_data['admin_state'] = 'choose_link_to_delete'
keyboard = [[f"{l[2]} ({l[0]})"] for l in links] + [[BACK_EMOJI, MAIN_MENU_BTN]]
reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
await update.message.reply_text("اختر الرابط لحذفه (بناءً على الوصف):", reply_markup=reply_markup)
else:
await update.message.reply_text("الرجاء اختيار مادة صحيحة من القائمة.")
return True

elif state == 'confirm_delete_mat':
if text == 'نعم':
if delete_material_db(context.user_data['admin_mat_id']):
await update.message.reply_text("✅ تم حذف المادة وكافة الملحقات.")
else:
await update.message.reply_text("❌ حدث فشل في عملية الحذف.")
else:
await update.message.reply_text("تم إلغاء عملية الحذف.")
await show_subadmin_panel(update, context)
return True

elif state == 'enter_new_mat_name':
if update_material_name_db(context.user_data['admin_mat_id'], text):
await update.message.reply_text("✅ تم تعديل اسم المادة بنجاح.")
else:
await update.message.reply_text("❌ فشل التعديل، قد يكون الاسم محجوزاً لمادة أخرى.")
await show_subadmin_panel(update, context)
return True

elif state == 'choose_file_to_delete':
fid = extract_id_from_text(text)
if fid:
try:
if delete_file(fid):
await update.message.reply_text("✅ تم حذف الملف نهائياً.")
else:
await update.message.reply_text("❌ فشل الحذف.")
except Exception as e:
logger.error(f"File delete error: {e}", exc_info=True)
await update.message.reply_text("حدث خطأ في النظام الداخلي.")
else:
await update.message.reply_text("تنسيق اسم الملف غير مقروء، يرجى الاستعانة بالأزرار.")
await show_subadmin_panel(update, context)
return True

elif action == 'add_exam_model' and state == 'wait_exam_upload':
await update.message.reply_text("عذراً، يجب إرسال ملف (صورة أو PDF) وليس نصاً مكتوباً.")
return True

elif state == 'choose_exam_to_delete':
eid = extract_id_from_text(text)
if eid:
if delete_exam_model(eid):
await update.message.reply_text("✅ تم حذف نموذج الاختبار بنجاح.")
else:
await update.message.reply_text("❌ تعذر حذف النموذج.")
else:
await update.message.reply_text("الرجاء استخدام الأزرار المتاحة للاختيار.")
await show_subadmin_panel(update, context)
return True

elif state == 'enter_link_url':
context.user_data['link_url'] = text
context.user_data['admin_state'] = 'enter_link_desc'
await update.message.reply_text("أرسل وصفاً نصياً للرابط:")
return True

elif state == 'enter_link_desc':
mat_id = context.user_data.get('admin_mat_id')
if not mat_id: return True

add_link(mat_id, context.user_data['link_url'], text)
await update.message.reply_text("✅ تمت إضافة الرابط بنجاح في قاعدة البيانات.")
await show_subadmin_panel(update, context)
return True

elif state == 'choose_link_to_delete':
lid = extract_id_from_text(text)
if lid:
if delete_link(lid):
await update.message.reply_text("✅ تم إزالة الرابط.")
else:
await update.message.reply_text("❌ تعذرت إزالة الرابط.")
else:
await update.message.reply_text("استخدم الأزرار للاختيار.")
await show_subadmin_panel(update, context)
return True

return False

================== معالج الوسائط ==================
async def media_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
if not await check_subscription(update, context):
await send_subscription_message(update)
return

user_id = update.effective_user.id

if is_admin(update) and context.user_data.get('broadcast_step') == 'waiting_media':
if update.message.photo:
context.user_data['broadcast_media'] = ('photo', update.message.photo[-1].file_id)
elif update.message.video:
context.user_data['broadcast_media'] = ('video', update.message.video.file_id)
else:
await update.message.reply_text("نوع الوسائط غير مدعوم للبث. يرجى إرسال صورة أو فيديو، أو أمر /cancel للإلغاء.");
return

context.user_data['broadcast_step'] = 'ready'
await update.message.reply_text("✓ تم استلام الميديا. أرسل الأمر /send لتنفيذ البث الجماعي الآن.")
return

if context.user_data.get('admin_action') == 'add_file' and context.user_data.get('admin_state') == 'wait_file_upload':
mat_id = context.user_data.get('admin_mat_id')
if not mat_id:
await update.message.reply_text("حدث خطأ في ربط البيانات.");
return

file_id = None; file_name = "unknown"; file_type = 'pdf'
if update.message.photo:
file_id = update.message.photo[-1].file_id; file_name = update.message.caption or "صورة"; file_type = 'image'
elif update.message.audio:
file_id = update.message.audio.file_id; file_name = update.message.audio.file_name or "صوت"; file_type = 'audio'
elif update.message.voice:
file_id = update.message.voice.file_id; file_name = "رسالة صوتية"; file_type = 'audio'
elif update.message.document:
doc = update.message.document
if doc.mime_type and doc.mime_type.startswith('audio/'): file_type='audio'; file_name=doc.file_name or "ملف صوتي"
elif doc.mime_type and doc.mime_type.startswith('image/'): file_type='image'; file_name=doc.file_name or "صورة"
else: file_type='pdf'; file_name=doc.file_name or "ملف PDF"
file_id = doc.file_id
else:
await update.message.reply_text("نوع الملف المرفوع غير مدعوم في الوقت الحالي.");
return

conn = get_db_connection()
c = conn.cursor()
try:
c.execute("SELECT specialization_id, level_id FROM materials WHERE id=%s", (mat_id,))
row = c.fetchone()
finally:
c.close()
release_db_connection(conn)

if not row:
await update.message.reply_text("المادة المراد الإضافة لها غير موجودة بالقاعدة.");
return

spec_id, level_id = row
if not has_file_permission(update, spec_id, level_id):
await update.message.reply_text("⛔ عذراً، لا تمتلك الأذونات والصلاحيات الكافية.");
return

safe_name = file_name[:250] if file_name else "ملف غير مسمى"

add_file(mat_id, file_id, safe_name, file_type)
await update.message.reply_text("✅ تم حفظ الملف بنجاح. أرسل المزيد أو اضغط /done للانتهاء.")
return

if context.user_data.get('admin_action') == 'add_exam_model' and context.user_data.get('admin_state') == 'wait_exam_upload':
mat_id = context.user_data.get('admin_mat_id')
if not mat_id:
await update.message.reply_text("حدث خطأ في استخراج هوية المادة.");
return

file_id = None; file_name = "unknown"; file_type = 'pdf'
if update.message.photo:
file_id = update.message.photo[-1].file_id; file_name = update.message.caption or "صورة نموذج"; file_type = 'image'
elif update.message.document:
doc = update.message.document
if doc.mime_type and doc.mime_type.startswith('image/'): file_type='image'; file_name=doc.file_name or "صورة نموذج"
else: file_type='pdf'; file_name=doc.file_name or "ملف PDF لنموذج"
file_id = doc.file_id
else:
await update.message.reply_text("يرجى إرسال صور أو ملفات مستندات PDF فقط.");
return

conn = get_db_connection()
c = conn.cursor()
try:
c.execute("SELECT specialization_id, level_id FROM materials WHERE id=%s", (mat_id,))
row = c.fetchone()
finally:
c.close()
release_db_connection(conn)

if not row:
await update.message.reply_text("حدث خطأ داخلي، المادة مفقودة.");
return

spec_id, level_id = row
if not has_file_permission(update, spec_id, level_id):
await update.message.reply_text("⛔ لا توجد لديك صلاحيات لذلك.");
return

safe_name = file_name[:250] if file_name else "نموذج اختبار"
add_exam_model(mat_id, file_id, safe_name, file_type)

await update.message.reply_text("✅ تمت إضافة نموذج الاختبار للمادة بنجاح.")
await show_subadmin_panel(update, context)
return

if context.user_data.get('admin_action') == 'add_timetable' and context.user_data.get('admin_state') == 'wait_timetable_upload':
if user_id != ADMIN_ID:
await update.message.reply_text("⛔ المشرف الرئيسي هو الوحيد المخول برفع الجداول الدراسية.")
return

if update.message.document:
doc = update.message.document
file_name = doc.file_name or ""
if file_name.lower().endswith('.pdf') or (doc.mime_type and 'pdf' in doc.mime_type.lower()):
file_id = doc.file_id
spec = context.user_data.get('specialization')
if not spec:
await update.message.reply_text("لم يتم التعرف على التخصص المطلوب.")
return
set_timetable(spec, file_id)
await update.message.reply_text("✅ تم تحديث ورفع الجدول الدراسي بنجاح.")

lvls = decorate_levels_for_spec(spec)
keyboard = [[l] for l in lvls] + [[TIMETABLE_BTN], [BACK_EMOJI, MAIN_MENU_BTN]]
reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
await update.message.reply_text('اختر المستوى:', reply_markup=reply_markup)
context.user_data['state'] = 'level'
return
else:
await update.message.reply_text("الملف المرفوع غير مدعوم، يرجى إرفاق بصيغة PDF حصراً.")
return
else:
await update.message.reply_text("الرجاء إرسال ملف مستند (Document) من نوع PDF فقط.")
return

def is_admin(update: Update):
return update.effective_user.id == ADMIN_ID

================== الأوامر الإدارية ==================
async def set_welcome_cmd(update, context):
if not is_admin(update): return
if not context.args:
await update.message.reply_text("الاستخدام الصحيح: /setwelcome رسالة الترحيب الجديدة");
return
set_welcome_message(' '.join(context.args))
await update.message.reply_text("✅ تم تحديث رسالة الترحيب الخاصة بالبوت بنجاح.")

async def ban_cmd(update, context):
if not is_admin(update): return
try:
uid = int(context.args[0])
await update.message.reply_text(f"✅ تم حظر المستخدم {uid}" if ban_user(uid) else "❌ فشل حظر المستخدم (قد لا يكون مسجلاً).")
except ValueError:
await update.message.reply_text("معرف المستخدم غير صحيح (أرقام فقط).")
except IndexError:
await update.message.reply_text("الاستخدام: /ban User_ID")

async def unban_cmd(update, context):
if not is_admin(update): return
try:
uid = int(context.args[0])
await update.message.reply_text("✅ تم رفع الحظر" if unban_user(uid) else "❌ فشل رفع الحظر.")
except ValueError:
await update.message.reply_text("معرف المستخدم غير صحيح (أرقام فقط).")
except IndexError:
await update.message.reply_text("الاستخدام: /unban User_ID")

async def broadcast_cmd(update, context):
if not is_admin(update): return
context.user_data['broadcast_step'] = 'waiting_text'
await update.message.reply_text("قم بكتابة وإرسال نص رسالة البث الجماعي، أو أرسل الأمر /cancel للإلغاء.")

async def broadcast_send(update, context):
if not is_admin(update): return
text = context.user_data.get('broadcast_text')
if not text:
await update.message.reply_text("رسالة البث فارغة، يجب كتابة نص قبل إرسال هذا الأمر.");
return

media = context.user_data.get('broadcast_media')
users = get_all_users()
sent, failed = 0, 0

await update.message.reply_text("⏳ جارٍ إرسال البث لجميع المستخدمين، يرجى الانتظار...")

for u in users:
if is_user_banned(u[0]): continue
try:
if media:
if media[0] == 'photo':
await context.bot.send_photo(u[0], media[1], caption=text)
else:
await context.bot.send_video(u[0], media[1], caption=text)
else:
await context.bot.send_message(u[0], text)
sent += 1
await asyncio.sleep(0.05)
except Exception:
failed += 1

await update.message.reply_text(f"✅ تمت عملية البث.\n\nاستلمها بنجاح: {sent}\nفشل الإرسال: {failed}")
context.user_data.pop('broadcast_step', None)
context.user_data.pop('broadcast_text', None)
context.user_data.pop('broadcast_media', None)

async def users_list_cmd(update, context):
if not is_admin(update): return
users = get_all_users()
if not users:
await update.message.reply_text("لا يوجد مستخدمين بعد.")
return

msg = "\n".join([f"ID: {u[0]} | {'🚫 محظور' if u[4] else '✅ نشط'}" for u in users])
if len(msg) > 4000:
msg = msg[:4000] + "\n... (تم اقتطاع القائمة للطول)"
await update.message.reply_text(msg)

async def stats_cmd(update, context):
if not is_admin(update): return
await update.message.reply_text(f"📊 الإحصائيات العامة للبوت:\n\nعدد الأعضاء المسجلين: {get_users_count()}")

async def cancel_admin_cmd(update, context):
if not is_admin(update): return
clean_admin_temp_data(context)
await update.message.reply_text("✅ تم إلغاء العمليات الإدارية النشطة.")
await show_admin_panel(update, context)

async def done_cmd(update, context):
if not await check_subscription(update, context):
await send_subscription_message(update)
return

user_id = update.effective_user.id
if user_id != ADMIN_ID and not get_sub_admin_by_user(user_id): return

clean_admin_temp_data(context)
await show_subadmin_panel(update, context)
await update.message.reply_text("✅ تم إنهاء الرفع والتخزين بنجاح والعودة لقائمة الإدارة.")

================== تشغيل البوت ==================
def main():
if not DATABASE_URL:
logger.error("DATABASE_URL is not set. Please set it in your environment variables.")
return

init_db()
app = Application.builder().token(TOKEN).build()

# معالجات الأوامر الرئيسية
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("setwelcome", set_welcome_cmd))
app.add_handler(CommandHandler("ban", ban_cmd))
app.add_handler(CommandHandler("unban", unban_cmd))
app.add_handler(CommandHandler("broadcast", broadcast_cmd))
app.add_handler(CommandHandler("send", broadcast_send))
app.add_handler(CommandHandler("users", users_list_cmd))
app.add_handler(CommandHandler("stats", stats_cmd))
app.add_handler(CommandHandler("cancel", cancel_admin_cmd))
app.add_handler(CommandHandler("done", done_cmd))

# معالج أزرار callback الخاصة بالاشتراك
app.add_handler(CallbackQueryHandler(check_sub_callback, pattern="^check_sub`$"))

# معالجات الوسائط والنصوص
app.add_handler(MessageHandler(filters.PHOTO | filters.VIDEO | filters.AUDIO | filters.VOICE | filters.Document.ALL, media_handler))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, unified_text_handler))

app.run_polling()

if name == 'main':
main()