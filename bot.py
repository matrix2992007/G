import telebot
from telebot import types
import sqlite3
import threading
import time

# --- الإعدادات الأساسية ---
TOKEN = "8802141344:AAEaAn4rH3QPMYqN8MYZ_2Cj70yA1NotMoE"
bot = telebot.TeleBot(TOKEN)

# معرفات التحكم (IDs) - المالك والمدير متساويان في الإدارة ولكن ميزة التحليل للمالك فقط
OWNER_ID = 7253092491    # المالك (@VIR_XT)
MANAGER_ID = 6525167572  # المدير (@Omar_7874)

ADMINS = [OWNER_ID, MANAGER_ID]

# أسماء اليوزرات للمرجع
OWNER_USER = "@VIR_XT"
MANAGER_USER = "@Omar_7874"

# قناة إثباتات الثقة والاشتراك الإجباري
TRUST_CHANNEL = "@Barq_G" 

# --- إعداد قاعدة البيانات ---
def init_db():
    conn = sqlite3.connect("barq_bot.db")
    cursor = conn.cursor()
    try:
        # جدول المستخدمين
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                points REAL DEFAULT 0.0,
                warnings INTEGER DEFAULT 0,
                status TEXT DEFAULT 'active',
                last_daily_claim TEXT DEFAULT NULL
            )
        ''')
        # جدول الأسماء المقترحة للجيميلات
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS gmail_names (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE,
                used_by INTEGER DEFAULT NULL
            )
        ''')
        # جدول المهام المعلقة والمقبولة والمرفوضة
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS submissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                accounts_data TEXT,
                num_accounts INTEGER,
                status TEXT DEFAULT 'pending'
            )
        ''')
        # جدول التذاكر
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tickets (
                ticket_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                message TEXT,
                status TEXT DEFAULT 'open'
            )
        ''')
        # إعدادات النظام
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        ''')
        # قيم افتراضية للإعدادات
        cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('point_price', '1')") 
        cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('required_password', 'Barq@2026')")
        
        conn.commit()
    except Exception as e:
        print(f"Error during database initialization: {e}")
    finally:
        conn.close()

init_db()

# --- دوال مساعدة لقاعدة البيانات والأمن ---
def get_db_connection():
    return sqlite3.connect("barq_bot.db")

def is_admin(user_id):
    return user_id in ADMINS

# إرسال إشعار لكافة المسؤولين
def notify_admins(text, parse_mode="Markdown"):
    for admin in ADMINS:
        try:
            bot.send_message(admin, text, parse_mode=parse_mode)
        except Exception:
            pass

# التحقق من الاشتراك الإجباري في القناة
def check_forced_subscription(user_id):
    if is_admin(user_id):
        return True
    try:
        member = bot.get_chat_member(TRUST_CHANNEL, user_id)
        if member.status in ['member', 'administrator', 'creator']:
            return True
        return False
    except Exception as e:
        print(f"Forced sub check error: {e}")
        return True

# رسالة طلب الاشتراك الإجباري
def send_subscription_alert(chat_id):
    markup = types.InlineKeyboardMarkup()
    channel_link = f"https://t.me/{TRUST_CHANNEL.replace('@', '')}"
    markup.add(types.InlineKeyboardButton("📢 اشترك في القناة من هنا", url=channel_link))
    markup.add(types.InlineKeyboardButton("✅ تحقق من الاشتراك", callback_data="check_sub"))
    
    alert_text = (
        f"⚠️ **تنبيه هام:**\n\n"
        f"عذرًا، للاستفادة من خدمات البوت والبدء في جني الأرباح وسحبها، "
        f"يجب عليك الاشتراك أولاً في قناتنا الرسمية لإثباتات الثقة والأخبار:\n\n"
        f"👉 {TRUST_CHANNEL}\n\n"
        f"اشترك الآن ثم اضغط على زر التحقق بالأسفل 👇"
    )
    bot.send_message(chat_id, alert_text, reply_markup=markup, parse_mode="Markdown")

# دالة إلغاء الخطوات إذا أرسل المستخدم أمراً
def check_for_command(message):
    if message.text and message.text.startswith('/'):
        bot.clear_step_handler_by_chat_id(message.chat.id)
        cmd = message.text.split()[0]
        if cmd == '/start':
            start_cmd(message)
        elif cmd == '/panel':
            admin_panel(message)
        return True
    return False

# --- كيبوردات مخصصة (Keyboards) ---

# 1. كيبورد المستخدم الرئيسي
def user_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("⚡️ بدء عمل جيميلات", "👤 حسابي ونقاطي")
    markup.row("💸 سحب الأرباح", "🎁 مكافأة يومية")
    markup.row("🏆 المتصدرين", "📞 تذكرة دعم فني")
    markup.row("ℹ️ نصائح تخطي الآي بي")
    return markup

# 2. لوحة تحكم الإدارة الموحدة (تتغير ديناميكياً بناءً على كون المستخدم هو المالك أم لا)
def admin_menu(is_owner=False):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("➕ إضافة أسماء جيميلات", "🔑 تغيير كلمة السر")
    markup.row("⚙️ سعر النقطة", "📢 الإذاعة")
    markup.row("📥 طلبات مراجعة الجيميلات", "📩 التذاكر المفتوحة")
    
    if is_owner:
        # زر خاص بمالك البوت فقط للاطلاع على تحليل البيانات
        markup.row("📊 الإحصائيات", "📈 تحليل البيانات المالي")
    else:
        markup.row("📊 الإحصائيات")
        
    markup.row("🔙 القائمة الرئيسية")
    return markup


# --- استقبال الأوامر الترحيبية ---

@bot.message_handler(commands=['start'])
def start_cmd(message):
    user_id = message.from_user.id
    username = message.from_user.username or "بلا يوزر"
    
    conn = get_db_connection()
    cursor = conn.cursor()
    is_new = False
    try:
        cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
        exists = cursor.fetchone()
        if not exists:
            cursor.execute("INSERT INTO users (user_id, username) VALUES (?, ?)", (user_id, username))
            conn.commit()
            is_new = True
    except Exception as e:
        print(f"Error saving user: {e}")
    finally:
        conn.close()

    if is_new:
        notify_admins(
            f"🔔 **عضو جديد دخل البوت الآن!**\n\n"
            f"👤 اليوزر: @{username}\n"
            f"🆔 الآيدي: `{user_id}`\n"
            f"⚙️ تم تسجيله بنجاح في قاعدة البيانات."
        )

    if not check_forced_subscription(user_id):
        send_subscription_alert(message.chat.id)
        return

    welcome_text = (
        f"⚡️ **أهلاً بك في بوت برق للجيميلات | Barq G-Bot** ⚡️\n\n"
        f"المنصة الأسهل والأسرع لكسب الكاش عبر إنشاء حسابات الجيميل وتجميع النقاط! 🚀\n\n"
        f"🛡️ **شروط وقواعد العمل الأساسية:**\n"
        f"• نقبل الحسابات المنشأة بالأسماء التي نوفرها لك فقط.\n"
        f"• يجب تعيين كلمة السر الموحدة المطلوبة عند التسليم.\n"
        f"• ⏱️ **مدة تنفيذ ومعالجة طلبات السحب:** تستغرق من **8 إلى 24 ساعة كحد أقصى** لضمان فحص ووصول الكاش إليك بأمان.\n\n"
        f"👑 **الإدارة والدعم:** {OWNER_USER} & {MANAGER_USER}\n"
        f"📢 **قناة الإثباتات والثقة:** {TRUST_CHANNEL}\n\n"
        f"استخدم أزرار التحكم بالأسفل للبدء فوراً وتجميع الأرباح 👇"
    )
    
    bot.send_message(message.chat.id, welcome_text, reply_markup=user_menu(), parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data == "check_sub")
def check_subscription_callback(call):
    user_id = call.from_user.id
    if check_forced_subscription(user_id):
        bot.answer_callback_query(call.id, "✅ تم تأكيد الاشتراك بنجاح! أهلاً بك.")
        welcome_text = (
            f"⚡️ **أهلاً بك في بوت برق للجيميلات | Barq G-Bot** ⚡️\n\n"
            f"تم تفعيل الحساب بنجاح بعد التحقق من اشتراكك بالقناة! 🚀\n\n"
            f"⏱️ **تنويه هام:** عمليات تحويل المبالغ والسحب المستحق تصلك في فترة تتراوح بين **8 إلى 24 ساعة** بعد المراجعة.\n\n"
            f"ابدأ الآن بتصفح الخيارات بالأسفل وتجميع نقاطك 👇"
        )
        bot.send_message(call.message.chat.id, welcome_text, reply_markup=user_menu(), parse_mode="Markdown")
    else:
        bot.answer_callback_query(call.id, "❌ لم تشترك في القناة بعد! اشترك أولاً ثم اضغط تحقق.", show_alert=True)

@bot.message_handler(commands=['panel'])
def admin_panel(message):
    user_id = message.from_user.id
    if is_admin(user_id):
        is_owner = (user_id == OWNER_ID)
        bot.send_message(message.chat.id, "🔐 مرحبًا بك في لوحة تحكم الإدارة الكاملة الموحدة:", reply_markup=admin_menu(is_owner=is_owner))
    else:
        bot.send_message(message.chat.id, "❌ عذرًا، هذا الأمر مخصص للإدارة فقط.")

# تفويض فحص الاشتراك الإجباري على جميع الأزرار لحماية العمليات
@bot.message_handler(func=lambda msg: msg.text in ["⚡️ بدء عمل جيميلات", "👤 حسابي ونقاطي", "💸 سحب الأرباح", "🎁 مكافأة يومية", "🏆 المتصدرين", "📞 تذكرة دعم فني", "ℹ️ نصائح تخطي الآي بي"])
def handle_user_buttons_with_sub_check(message):
    if not check_forced_subscription(message.from_user.id):
        send_subscription_alert(message.chat.id)
        return
    
    if message.text == "⚡️ بدء عمل جيميلات":
        start_work(message)
    elif message.text == "👤 حسابي ونقاطي":
        check_balance(message)
    elif message.text == "💸 سحب الأرباح":
        withdraw_start(message)
    elif message.text == "🎁 مكافأة يومية":
        claim_daily_reward(message)
    elif message.text == "🏆 المتصدرين":
        leaderboards(message)
    elif message.text == "📞 تذكرة دعم فني":
        open_ticket_start(message)
    elif message.text == "ℹ️ نصائح تخطي الآي بي":
        ip_tips(message)

# --- الرجوع للقائمة الرئيسية ---
@bot.message_handler(func=lambda msg: msg.text == "🔙 القائمة الرئيسية")
def back_to_main(message):
    bot.send_message(message.chat.id, "🔙 تم الرجوع للقائمة الرئيسية للتصفح:", reply_markup=user_menu())


# ==========================================
# أولاً: عمليات لوحة التحكم (إضافة، تعديل رصيد، إلخ)
# ==========================================

# 1. إضافة الأسماء
@bot.message_handler(func=lambda msg: msg.text == "➕ إضافة أسماء جيميلات")
def add_names_start(message):
    if not is_admin(message.from_user.id):
        return
    msg_sent = bot.send_message(message.chat.id, "ارسل الآن الأسماء التي تريد إضافتها للبوت.\n(يمكنك إرسال كل اسم في سطر منفصل):")
    bot.register_next_step_handler(msg_sent, save_gmail_names)

def save_gmail_names(message):
    if check_for_command(message): return
    names = message.text.split("\n")
    conn = get_db_connection()
    cursor = conn.cursor()
    added_count = 0
    try:
        for name in names:
            name = name.strip()
            if name:
                try:
                    cursor.execute("INSERT INTO gmail_names (name) VALUES (?)", (name,))
                    added_count += 1
                except sqlite3.IntegrityError:
                    pass
        conn.commit()
        bot.send_message(message.chat.id, f"✅ تم حفظ {added_count} اسم بنجاح في قاعدة البيانات وجاهزة للمستخدمين!")
    except Exception as e:
         bot.send_message(message.chat.id, f"❌ حدث خطأ أثناء الحفظ: {e}")
    finally:
        conn.close()

# 2. تعديل رصيد مستخدم يدويًا
@bot.message_handler(commands=['points'])
def manual_modify_points(message):
    if not is_admin(message.from_user.id):
        return
    try:
        parts = message.text.split()
        if len(parts) < 3:
            raise ValueError
        
        target_user = int(parts[1])
        points_change = float(parts[2])
    except (IndexError, ValueError):
        bot.reply_to(message, "❌ **الاستخدام الخاطئ للأمر!**\nالصيغة الصحيحة هي:\n`/points [معرف_المستخدم] [النقاط]`\n\n💡 *مثال للإضافة:* `/points 7253092491 15`\n💡 *مثال للخصم:* `/points 7253092491 -10`", parse_mode="Markdown")
        return

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT points, username FROM users WHERE user_id = ?", (target_user,))
        user_row = cursor.fetchone()
        
        if not user_row:
            bot.reply_to(message, "❌ هذا العضو غير مسجل في قاعدة بيانات البوت حالياً.")
            return
            
        current_points = user_row[0]
        user_name = user_row[1] or "بدون يوزر"
        new_points = current_points + points_change
        
        if new_points < 0:
            new_points = 0.0
            
        cursor.execute("UPDATE users SET points = ? WHERE user_id = ?", (new_points, target_user))
        conn.commit()
        
        bot.reply_to(message, f"✅ تم تعديل رصيد العميل `@{user_name}` ({target_user}) بنجاح.\n\n💰 رصيده السابق: {current_points} نقطة.\n➕ التعديل: {points_change:+} نقطة.\n✨ رصيده الحالي: {new_points} نقطة.", parse_mode="Markdown")
        
        try:
            bot.send_message(target_user, f"🔔 **إشعار من الإدارة:**\nتم تعديل رصيد نقاطك بواسطة الإدارة بـ ({points_change:+}) نقطة.\n💰 رصيدك الحالي أصبح: *{new_points}* نقطة.", parse_mode="Markdown")
        except Exception:
            pass
            
    except Exception as e:
        bot.reply_to(message, f"❌ حدث خطأ أثناء تعديل النقاط: {e}")
    finally:
        conn.close()

# 3. تغيير سعر النقطة
@bot.message_handler(func=lambda msg: msg.text == "⚙️ سعر النقطة")
def set_point_price_start(message):
    if not is_admin(message.from_user.id):
        return
    conn = get_db_connection()
    cursor = conn.cursor()
    current_price = cursor.execute("SELECT value FROM settings WHERE key='point_price'").fetchone()[0]
    conn.close()
    
    msg = bot.send_message(message.chat.id, f"💵 السعر الحالي للنقطة الواحدة هو: `{current_price}` جنيه كاش.\n\nأرسل الآن السعر الجديد (رقم فقط، مثل 1.5 أو 2):", parse_mode="Markdown")
    bot.register_next_step_handler(msg, save_point_price)

def save_point_price(message):
    if check_for_command(message): return
    try:
        new_price = float(message.text.strip())
        if new_price <= 0:
            raise ValueError
    except ValueError:
        bot.send_message(message.chat.id, "❌ يرجى إدخال قيمة مالية صحيحة أكبر من الصفر.")
        return
        
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE settings SET value = ? WHERE key = 'point_price'", (str(new_price),))
        conn.commit()
        bot.send_message(message.chat.id, f"✅ تم تحديث سعر النقطة بنجاح إلى: `{new_price}` جنيه كاش.", parse_mode="Markdown")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ خطأ في حفظ السعر: {e}")
    finally:
        conn.close()

# 4. تغيير كلمة السر الخاصة بالجيميلات
@bot.message_handler(func=lambda msg: msg.text == "🔑 تغيير كلمة السر")
def set_password_start(message):
    if not is_admin(message.from_user.id):
        return
    
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        current_pass = cursor.execute("SELECT value FROM settings WHERE key='required_password'").fetchone()[0]
    except Exception:
        current_pass = "Barq@2026"
    finally:
        conn.close()
    
    msg = bot.send_message(message.chat.id, f"🔑 كلمة السر الحالية المطلوبة من المستخدمين هي: `{current_pass}`\n\nأرسل الآن كلمة السر الجديدة التي تريد فرضها عليهم عند التسليم:", parse_mode="Markdown")
    bot.register_next_step_handler(msg, save_new_password)

def save_new_password(message):
    if check_for_command(message): return
    new_pass = message.text.strip()
    if not new_pass:
        bot.send_message(message.chat.id, "❌ لا يمكن تعيين كلمة سر فارغة.")
        return
        
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE settings SET value = ? WHERE key = 'required_password'", (new_pass,))
        conn.commit()
        bot.send_message(message.chat.id, f"✅ تم تحديث كلمة السر المطلوبة بنجاح إلى: `{new_pass}`", parse_mode="Markdown")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ حدث خطأ أثناء تحديث كلمة السر: {e}")
    finally:
        conn.close()

# 5. قسم الإذاعة الآمن مع Threading
@bot.message_handler(func=lambda msg: msg.text == "📢 الإذاعة")
def start_broadcast(message):
    if not is_admin(message.from_user.id):
        return
    msg = bot.send_message(message.chat.id, "📢 أرسل الآن الرسالة التي تريد إذاعتها لجميع مستخدمي البوت.\n(يمكنك إرسال نص عادي، أو صورة مرفقة بنص):")
    bot.register_next_step_handler(msg, trigger_broadcast_thread)

def trigger_broadcast_thread(message):
    if check_for_command(message): return
    threading.Thread(target=send_broadcast_to_all, args=(message,), daemon=True).start()

def send_broadcast_to_all(message):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        users = cursor.execute("SELECT user_id FROM users").fetchall()
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ فشل جلب المستخدمين: {e}")
        return
    finally:
        conn.close()
    
    if not users:
        bot.send_message(message.chat.id, "⚠️ لا يوجد مستخدمين مسجلين في البوت حالياً.")
        return
        
    bot.send_message(message.chat.id, f"⚡️ جاري بدء الإذاعة لعدد {len(users)} مستخدم في الخلفية... يرجى الانتظار.")
    
    success_count = 0
    fail_count = 0
    
    for row in users:
        u_id = row[0]
        try:
            if message.content_type == 'text':
                bot.send_message(u_id, message.text, parse_mode="Markdown")
            elif message.content_type == 'photo':
                photo_id = message.photo[-1].file_id
                bot.send_photo(u_id, photo_id, caption=message.caption, parse_mode="Markdown")
            success_count += 1
            time.sleep(0.05)
        except Exception:
            fail_count += 1
            
    bot.send_message(message.chat.id, f"📢 **تم الانتهاء من الإذاعة بنجاح!**\n\n✅ تم الإرسال بنجاح إلى: {success_count} مستخدم.\n❌ فشل الإرسال (حظر للبوت): {fail_count} مستخدم.")

# 6. قسم الإحصائيات الشامل للسيستم
@bot.message_handler(func=lambda msg: msg.text == "📊 الإحصائيات")
def show_statistics(message):
    if not is_admin(message.from_user.id):
        return
        
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        total_users = cursor.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        available_names = cursor.execute("SELECT COUNT(*) FROM gmail_names WHERE used_by IS NULL").fetchone()[0]
        used_names = cursor.execute("SELECT COUNT(*) FROM gmail_names WHERE used_by IS NOT NULL").fetchone()[0]
        pending_submissions = cursor.execute("SELECT COUNT(*) FROM submissions WHERE status='pending'").fetchone()[0]
        open_tickets = cursor.execute("SELECT COUNT(*) FROM tickets WHERE status='open'").fetchone()[0]
        current_pass = cursor.execute("SELECT value FROM settings WHERE key='required_password'").fetchone()[0]
        
        stats_text = (
            f"📊 **إحصائيات وتحليلات بوت برق للجيميلات:**\n\n"
            f"👥 إجمالي المستخدمين المسجلين: `{total_users}` عضو\n"
            f"🔑 كلمة السر الحالية المفروضة: `{current_pass}`\n\n"
            f"🌐 **جيميلات الأسماء:**\n"
            f"🔹 أسماء جاهزة ومتاحة للعمل: `{available_names}` اسم\n"
            f"🔸 أسماء تم حجزها وبدأ العمل عليها: `{used_names}` اسم\n\n"
            f"📥 **العمليات المعلقة والمراجعة:**\n"
            f"⏳ حسابات بانتظار فحص المدير: `{pending_submissions}` طلب تسليم\n"
            f"🎫 تذاكر دعم فني مفتوحة حالياً: `{open_tickets}` تذكرة"
        )
        bot.send_message(message.chat.id, stats_text, parse_mode="Markdown")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ حدث خطأ أثناء جلب الإحصائيات: {e}")
    finally:
        conn.close()


# ==========================================
# ميزة المالك الحصرية: تحليل البيانات المالي
# ==========================================

@bot.message_handler(func=lambda msg: msg.text == "📈 تحليل البيانات المالي")
def owner_financial_analysis(message):
    user_id = message.from_user.id
    
    # حظر وموثوقية: للمالك فقط
    if user_id != OWNER_ID:
        bot.send_message(message.chat.id, "❌ عذرًا، هذا القسم مخصص لمالك البوت الأساسي فقط ولا يمكن لغير المالك الوصول إليه.")
        return
        
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # إحصائيات تسليم الحسابات
        cursor.execute("SELECT COUNT(*) FROM submissions WHERE status='approved'")
        approved_submissions = cursor.fetchone()[0] or 0
        
        cursor.execute("SELECT COUNT(*) FROM submissions WHERE status='rejected'")
        rejected_submissions = cursor.fetchone()[0] or 0
        
        cursor.execute("SELECT COUNT(*) FROM submissions WHERE status='pending'")
        pending_submissions = cursor.fetchone()[0] or 0
        
        # إجمالي الجيميلات التي تم العمل عليها
        cursor.execute("SELECT COUNT(*) FROM gmail_names WHERE used_by IS NOT NULL")
        total_worked_gmails = cursor.fetchone()[0] or 0

        # جلب الإعدادات المالية الحالية
        point_price = float(cursor.execute("SELECT value FROM settings WHERE key='point_price'").fetchone()[0])
        
        # حساب إجمالي النقاط والمبالغ الكلية المعلقة والمسحوبة
        cursor.execute("SELECT SUM(points) FROM users")
        total_users_points = cursor.fetchone()[0] or 0.0
        potential_payout = total_users_points * point_price

        analysis_text = (
            f"👑 **مرحباً بك يا مالك البوت في قسم التحليل المالي والبيانات:**\n"
            f"📈 _تقرير شامل وفوري لحالة الحسابات والتدفقات المالية:_\n\n"
            f"📊 **أولاً: تحليل جيميلات النظام:**\n"
            f"🔹 إجمالي الجيميلات التي بدأ العمل عليها: `{total_worked_gmails}` حساب\n"
            f"✅ طلبات تسليم تم قبولها وصرف نقاطها: `{approved_submissions}` طلب\n"
            f"❌ طلبات تسليم تم رفضها كلياً: `{rejected_submissions}` طلب\n"
            f"⏳ طلبات تسليم معلقة وبانتظار الفحص: `{pending_submissions}` طلب\n\n"
            f"💰 **ثانياً: التحليل المالي والأرباح:**\n"
            f"💵 سعر النقطة الحالي بالسيستم: `{point_price} جنيه`\n"
            f"🪙 إجمالي النقاط المتواجدة بحسابات الأعضاء حالياً: `{total_users_points:.2f}` نقطة\n"
            f"💸 إجمالي الالتزامات المالية المستحقة حالياً: *{potential_payout:.2f} جنيه مصري*\n\n"
            f"💡 *ملاحظة:* يتم تحديث هذه البيانات ديناميكياً بناءً على العمليات وتأكيدات السحب في قاعدة البيانات."
        )
        
        bot.send_message(message.chat.id, analysis_text, parse_mode="Markdown")
        
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ حدث خطأ أثناء إعداد التقرير المالي: {e}")
    finally:
        conn.close()


# ==========================================
# ثانياً: واجهة وعمليات المستخدم (User Process)
# ==========================================

# 1. مكافأة يومية للمستخدمين
def claim_daily_reward(message):
    user_id = message.from_user.id
    current_date = time.strftime("%Y-%m-%d")
    
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT last_daily_claim, points FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        
        if row:
            last_claim = row[0]
            current_points = row[1] or 0.0
            
            if last_claim == current_date:
                bot.send_message(message.chat.id, "❌ **لقد حصلت على مكافأتك اليومية بالفعل!**\nعد مجدداً غداً للحصول عليها.", parse_mode="Markdown")
            else:
                reward = 0.1
                new_points = current_points + reward
                cursor.execute("UPDATE users SET points = ?, last_daily_claim = ? WHERE user_id = ?", (new_points, current_date, user_id))
                conn.commit()
                bot.send_message(message.chat.id, f"🎁 **تهانينا!** لقد حصلت على هدية اليوم بمقدار `{reward}` نقطة مجاناً.\n💰 رصيدك الحالي: {new_points} نقطة.", parse_mode="Markdown")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ حدث خطأ: {e}")
    finally:
        conn.close()

# 2. قائمة المتصدرين
def leaderboards(message):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT username, points, user_id FROM users WHERE points > 0 ORDER BY points DESC LIMIT 10")
        rows = cursor.fetchall()
        
        if not rows:
            bot.send_message(message.chat.id, "🏆 قائمة المتصدرين فارغة حالياً. ابدأ بالعمل لتكون الأول!")
            return
            
        leaderboard_text = "🏆 **قائمة متصدري تجميع النقاط في بوت برق:**\n\n"
        for i, row in enumerate(rows):
            user_display = f"@{row[0]}" if row[0] and row[0] != "بلا يوزر" else f"المستخدم ({row[2]})"
            leaderboard_text += f"{i+1}. 👤 {user_display} ➔ 🪙 `{row[1]}` نقطة\n"
            
        bot.send_message(message.chat.id, leaderboard_text, parse_mode="Markdown")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ خطأ: {e}")
    finally:
        conn.close()

# 3. بدء عمل الحسابات
def start_work(message):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        available_count = cursor.execute("SELECT COUNT(*) FROM gmail_names WHERE used_by IS NULL").fetchone()[0]
        if available_count == 0:
            bot.send_message(message.chat.id, "⚠️ لا تتوفر أسماء جيميلات جديدة حالياً للعمل عليها. يرجى مراجعة الدعم الفني أو المحاولة لاحقاً.")
            return
            
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("تحديد عدد الجيميلات المطلوب عملها 🔢", callback_data="select_amount"))
        bot.send_message(message.chat.id, f"⚡️ متاح حالياً {available_count} اسم للعمل عليها.\nاضغط بالأسفل لتحديد العدد والبدء فوراً:", reply_markup=markup)
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ خطأ غير متوقع: {e}")
    finally:
        conn.close()

@bot.callback_query_handler(func=lambda call: call.data == "select_amount")
def select_amount_callback(call):
    if not check_forced_subscription(call.from_user.id):
        send_subscription_alert(call.message.chat.id)
        return
    msg = bot.send_message(call.message.chat.id, "يرجى كتابة عدد الجيميلات التي تريد القيام بعملها (مثال: 3):")
    bot.register_next_step_handler(msg, provide_names_one_by_one)

def provide_names_one_by_one(message):
    if check_for_command(message): return
    try:
        amount = int(message.text)
        if amount <= 0:
            raise ValueError
    except ValueError:
        bot.send_message(message.chat.id, "❌ يرجى إدخال رقم صحيح أكبر من صفر.")
        return

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id, name FROM gmail_names WHERE used_by IS NULL LIMIT ?", (amount,))
        rows = cursor.fetchall()
        
        required_pass = cursor.execute("SELECT value FROM settings WHERE key='required_password'").fetchone()[0]
        
        if len(rows) < amount:
            bot.send_message(message.chat.id, f"⚠️ المتاح حالياً أقل من طلبك، المتاح فقط: {len(rows)} اسم.")
            return

        assigned_names = []
        for row in rows:
            cursor.execute("UPDATE gmail_names SET used_by = ? WHERE id = ?", (message.from_user.id, row[0]))
            assigned_names.append(row[1])
        conn.commit()

        names_list_str = "\n".join([f"🔹 الاسم {i+1}: `{name}`" for i, name in enumerate(assigned_names)])
        
        response_msg = (
            f"📋 **الأسماء المطلوبة منك لعمل حسابات الجيميل:**\n\n"
            f"{names_list_str}\n\n"
            f"⚠️ **مهم جداً:** يجب تعيين كلمة السر التالية لجميع الحسابات أعلاه:\n"
            f"🔑 كلمة السر المطلوبة: `{required_pass}`\n\n"
            f"بمجرد الانتهاء، اضغط على زر **حفظ وتسليم** أدناه لتقديم البيانات لجهة المراجعة."
        )
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("💾 حفظ وتسليم الحسابات", callback_data=f"submit_work:{amount}"))
        bot.send_message(message.chat.id, response_msg, reply_markup=markup, parse_mode="Markdown")
    except Exception as e:
         bot.send_message(message.chat.id, f"❌ حدث خطأ تقني: {e}")
    finally:
        conn.close()

@bot.callback_query_handler(func=lambda call: call.data.startswith("submit_work"))
def submit_work_callback(call):
    if not check_forced_subscription(call.from_user.id):
        send_subscription_alert(call.message.chat.id)
        return
    amount = call.data.split(":")[1]
    msg = bot.send_message(call.message.chat.id, 
        f"📥 **واجهة تسليم الجيميلات المعمولة:**\n\n"
        f"يرجى إرسال الحسابات الـ {amount} التي قمت بإنشائها بصيغة (الإيميل:الباسوورد) كالتالي:\n"
        f"1. الإيميل الأول:الباسوورد\n"
        f"2. الإيميل الثاني:الباسوورد\n\n"
        f"اكتبهم دفعة واحدة الآن وأرسل الرسالة:"
    )
    bot.register_next_step_handler(msg, save_submission_to_manager, amount)

def save_submission_to_manager(message, amount):
    if check_for_command(message): return
    user_id = message.from_user.id
    accounts_data = message.text
    
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO submissions (user_id, accounts_data, num_accounts) VALUES (?, ?, ?)", (user_id, accounts_data, amount))
        submission_id = cursor.lastrowid
        conn.commit()
        
        admin_alert = (
            f"📥 **طلب مراجعة حسابات جديد #{submission_id}!**\n"
            f"👤 المستخدم: @{message.from_user.username or user_id}\n"
            f"🔢 العدد المطلوب: {amount}\n"
            f"📝 كود التسليم:\n`{accounts_data}`\n\n"
            f"المراجعة من لوحة تحكم الإدارة بالضغط على زر /panel"
        )
        notify_admins(admin_alert)
        
        bot.send_message(message.chat.id, "✅ تم حفظ وتسليم الجيميلات لجهة المراجعة بنجاح! سيتم فحصها فوراً وإضافة النقاط لحسابك.")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ حدث خطأ في معالجة طلب التسليم: {e}")
    finally:
        conn.close()

# 4. معلومات الرصيد والحساب
def check_balance(message):
    user_id = message.from_user.id
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT points FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        points = row[0] if row else 0.0
        bot.send_message(message.chat.id, f"👤 **معلومات حسابك:**\n\n💰 إجمالي نقاطك الحالية: *{points} نقطة*", parse_mode="Markdown")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ خطأ في جلب بيانات الحساب: {e}")
    finally:
        conn.close()

# 5. سحب الأرباح
def withdraw_start(message):
    user_id = message.from_user.id
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT points FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        points = row[0] if row else 0.0
        
        point_price = float(cursor.execute("SELECT value FROM settings WHERE key='point_price'").fetchone()[0])
        
        if points < 5.0:
            bot.send_message(message.chat.id, f"❌ الحد الأدنى للسحب هو **5 نقاط**.\nنقاطك الحالية: {points} نقطة. قم بعمل المزيد من المهام لتصل للحد الأدنى!")
            return
            
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("طلب سحب كاش 💸", callback_data="withdraw_cash"))
        
        withdraw_text = (
            f"💰 رصيدك الحالي {points} نقطة جاهزة للسحب.\n"
            f"💵 (النقطة الواحدة تعادل {point_price} جنيه كاش).\n\n"
            f"⚠️ **ملاحظة هامة جداً:**\n"
            f"يصل السحب الخاص بك في مدة تتراوح من **8 ساعات إلى 24 ساعة كحد أقصى** من وقت تقديم الطلب ومراجعته.\n\n"
            f"اضغط بالأسفل لبدء عملية السحب فوراً:"
        )
        bot.send_message(message.chat.id, withdraw_text, reply_markup=markup, parse_mode="Markdown")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ خطأ أثناء فتح واجهة السحب: {e}")
    finally:
        conn.close()

@bot.callback_query_handler(func=lambda call: call.data == "withdraw_cash")
def withdraw_cash_process(call):
    if not check_forced_subscription(call.from_user.id):
        send_subscription_alert(call.message.chat.id)
        return
    msg = bot.send_message(call.message.chat.id, "اكتب عدد النقاط التي تريد سحبها بالظبط (مثال: 5):")
    bot.register_next_step_handler(msg, ask_for_cash_number)

def ask_for_cash_number(message):
    if check_for_command(message): return
    try:
        points_to_draw = float(message.text)
        if points_to_draw < 5.0:
            bot.send_message(message.chat.id, "❌ يجب أن يكون طلب السحب 5 نقاط كحد أدنى.")
            return
    except ValueError:
        bot.send_message(message.chat.id, "❌ يرجى إدخال رقم نقاط صحيح.")
        return

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT points FROM users WHERE user_id = ?", (message.from_user.id,))
        user_points = cursor.fetchone()[0]
        point_price = float(cursor.execute("SELECT value FROM settings WHERE key='point_price'").fetchone()[0])
        
        if points_to_draw > user_points:
            bot.send_message(message.chat.id, f"❌ رصيد نقاطك غير كافٍ. الحد الأقصى المتاح لك لسحبه هو {user_points} نقطة.")
            return

        cash_amount = points_to_draw * point_price
        msg = bot.send_message(message.chat.id, f"💵 قيمة السحب الخاص بك: *{cash_amount} جنيه كاش*\n\nيرجى كتابة وإرسال رقم محفظة الكاش الخاصة بك (فودافون كاش، اتصالات، إلخ):", parse_mode="Markdown")
        bot.register_next_step_handler(msg, send_withdraw_to_admin, points_to_draw, cash_amount)
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ حدث خطأ أثناء المعالجة: {e}")
    finally:
        conn.close()

def send_withdraw_to_admin(message, points, money_amount):
    if check_for_command(message): return
    wallet_number = message.text
    user_id = message.from_user.id
    
    withdraw_alert = (
        f"💳 **طلب سحب رصيد جديد معلق!**\n\n"
        f"👤 المستخدم: @{message.from_user.username or user_id}\n"
        f"🪙 عدد النقاط المطلوب سحبها: {points} نقطة\n"
        f"💰 المبلغ المطلوب بالكاش: *{money_amount} جنيه مصرى*\n"
        f"📱 رقم المحفظة المستلمة: `{wallet_number}`\n\n"
        f"قم بتحويل المبلغ المالي ثم استخدم كود التأكيد وإرسال الإثبات كالتالي:\n"
        f"`/confirm {user_id} {points} {money_amount}` (مع إرفاق صورة التحويل في رسالة واحدة)"
    )
    notify_admins(withdraw_alert)
    bot.send_message(message.chat.id, "✅ تم إرسال طلب السحب الخاص بك بنجاح! جاري معالجة الطلب وتحويل الأموال إليك من قبل الإدارة في خلال (8 - 24) ساعة.")

# 6. تذكرة الدعم الفني
def open_ticket_start(message):
    msg = bot.send_message(message.chat.id, "اكتب رسالتك أو مشكلتك هنا بالتفصيل، وسيقوم أحد المسؤولين بالرد عليك داخل البوت فوراً:")
    bot.register_next_step_handler(msg, submit_ticket)

def submit_ticket(message):
    if check_for_command(message): return
    user_id = message.from_user.id
    msg_text = message.text
    
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO tickets (user_id, message) VALUES (?, ?)", (user_id, msg_text))
        ticket_id = cursor.lastrowid
        conn.commit()
        
        admin_alert = (
            f"🎫 **تذكرة دعم فني جديدة #{ticket_id}**\n"
            f"👤 من: @{message.from_user.username or user_id}\n"
            f"💬 الرسالة: {msg_text}\n\n"
            f"للرد على هذه التذكرة أرسل الأمر التالي:\n`/reply {ticket_id} نص الرد هنا`"
        )
        notify_admins(admin_alert)
        bot.send_message(message.chat.id, "✅ تم إرسال تذكرتك بنجاح، ستتلقى الرد هنا فور قيام الإدارة بمراجعتها.")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ حدث خطأ أثناء فتح التذكرة: {e}")
    finally:
        conn.close()


# ==========================================
# ثالثاً: عمليات الإدارة (تأكيد السحب والرد المباشر)
# ==========================================

@bot.message_handler(commands=['confirm'], content_types=['photo'])
def confirm_and_trust(message):
    if not is_admin(message.from_user.id):
        return
    try:
        caption = message.caption
        if not caption:
            raise ValueError
        parts = caption.split()
        if len(parts) < 4:
            raise ValueError
            
        target_user = int(parts[1])
        points = float(parts[2])
        money = float(parts[3])
    except (AttributeError, IndexError, ValueError):
        bot.reply_to(message, "❌ **الاستخدام الصحيح:** أرفق لقطة الشاشة مع الأمر التالي في الـ Caption:\n`/confirm [معرف_المستخدم] [النقاط] [المبلغ]`")
        return

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # خصم النقاط من رصيد المستخدم
        cursor.execute("UPDATE users SET points = points - ? WHERE user_id = ?", (points, target_user))
        
        # تغيير حالة آخر تسليم للمستخدم إلى approved (مقبول) لأغراض الإحصاء المالي للمالك
        cursor.execute("""
            UPDATE submissions 
            SET status = 'approved' 
            WHERE id = (SELECT id FROM submissions WHERE user_id = ? ORDER BY id DESC LIMIT 1)
        """, (target_user,))
        
        conn.commit()
        
        photo_id = message.photo[-1].file_id
        bot.send_photo(target_user, photo_id, caption=f"💵 تم تحويل مبلغ *{money} جنيه* بنجاح إلى حسابك!\nيرجى كتابة وإرسال 'كلمة ثقة' بخصوص هذه المعاملة لنشرها كإثبات بالجروب والقناة الخاصة بنا ❤️", parse_mode="Markdown")
        
        bot.register_next_step_handler_by_chat_id(target_user, forward_trust_to_channel, photo_id, money, target_user)
        bot.reply_to(message, f"✅ تم تأكيد الدفع وخصم {points} نقطة وتحديث حالة الطلب إلى (مقبول ✅) بنجاح.")
    except Exception as e:
        bot.reply_to(message, f"❌ حدث خطأ أثناء تنفيذ التأكيد: {e}")
    finally:
        conn.close()

def forward_trust_to_channel(message, photo_id, money, user_id):
    if check_for_command(message): return
    trust_word = message.text
    username = f"@{message.from_user.username}" if message.from_user.username else f"المستخدم {user_id}"
    
    channel_post = (
        f"🤝 **إثبات تحويل ثقة جديد من بوت برق!** ⚡️\n\n"
        f"👤 العميل المحترم: {username}\n"
        f"💰 القيمة المحولة: *{money} جنيه كاش*\n"
        f"💬 رأي العميل وثقته:\n« {trust_word} »\n\n"
        f"🛒 اعمل جيميلات واكسب فلوسك كاش فوراً عبر: @Barq_GBot"
    )
    
    try:
        bot.send_photo(TRUST_CHANNEL, photo_id, caption=channel_post, parse_mode="Markdown")
        bot.send_message(user_id, "❤️ شكراً لثقتك ودعمك المستمر! تم نشر رأيك بنجاح في القناة لإثبات مصداقيتنا.")
    except Exception as e:
        notify_admins(f"⚠️ حدث خطأ أثناء إرسال إثبات الثقة إلى القناة {TRUST_CHANNEL}. تأكد من رفع البوت أدمن بها أولاً.\nالسبب: {e}")

# الرد على التذاكر
@bot.message_handler(commands=['reply'])
def reply_to_ticket(message):
    if not is_admin(message.from_user.id):
        return
    try:
        parts = message.text.split(" ", 2)
        ticket_id = int(parts[1])
        reply_msg = parts[2]
    except (IndexError, ValueError):
        bot.reply_to(message, "❌ الاستخدام الصحيح للأمر: /reply [رقم_التذكرة] [نص_الرد]")
        return
        
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT user_id FROM tickets WHERE ticket_id = ?", (ticket_id,))
        row = cursor.fetchone()
        if row:
            target_user = row[0]
            cursor.execute("UPDATE tickets SET status = 'replied' WHERE ticket_id = ?", (ticket_id,))
            conn.commit()
            
            bot.send_message(target_user, f"💬 **رد الإدارة على تذكرتك #{ticket_id}:**\n\n{reply_msg}", parse_mode="Markdown")
            bot.reply_to(message, f"✅ تم إرسال الرد للمستخدم بنجاح وإغلاق التذكرة.")
        else:
            bot.reply_to(message, "❌ لم يتم العثور على تذكرة بهذا الرقم.")
    except Exception as e:
        bot.reply_to(message, f"❌ حدث خطأ أثناء معالجة الرد: {e}")
    finally:
        conn.close()

# دليل تخطي الأي بي
def ip_tips(message):
    tips_text = (
        f"📱 **نصائح ذهبية لإنشاء حسابات جيميل بدون رقم هاتف:**\n\n"
        f"1. **وضع الطيران:** قبل عمل كل حساب، قم بتفعيل وضع الطيران لمدة 10 ثوانٍ ثم اغلقه ليقوم هاتفك بتغيير الـ IP تلقائياً.\n"
        f"2. **التصفح الخفي:** استخدم دائماً نافذة تصفح متخفية (Incognito Mode) لإنشاء الحساب.\n"
        f"3. **مسح الكاش:** امسح ذاكرة التخزين المؤقت لمتصفحك دورياً لتفادي كشف جوجل لجهازك.\n"
        f"4. **بيانات الهاتف:** لا تستخدم شبكة الواي فاي المنزلية مطلقاً، اعتمد بالكامل على بيانات الهاتف (4G/5G)."
    )
    bot.send_message(message.chat.id, tips_text)

# --- تشغيل البوت بسلاسة ---
if __name__ == "__main__":
    print("⚡️ بوت برق للجيميلات يعمل الآن بكفاءة قصوى وبأمان تام... ⚡️")
    bot.infinity_polling()
