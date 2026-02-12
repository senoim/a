import os
import logging
import requests
import json
import asyncio
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# إعداد السجلات (Logging)
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# جلب متغيرات البيئة
BOT_TOKEN = os.getenv("BOT_TOKEN")
SMS_API_KEY = os.getenv("SMS_API_KEY")
API_BASE_URL = "https://api.sms-man.com/stubs/handler_api.php"

# تخزين مؤقت للبيانات لتقليل طلبات API
cache = {
    "countries": [],
    "services": [],
    "last_update": 0
}

async def get_balance():
    params = {"action": "getBalance", "api_key": SMS_API_KEY}
    try:
        response = requests.get(API_BASE_URL, params=params)
        if "ACCESS_BALANCE" in response.text:
            return response.text.split(":")[1]
        return "0"
    except Exception as e:
        logger.error(f"Error getting balance: {e}")
        return "Error"

async def get_countries():
    if cache["countries"]:
        return cache["countries"]
    params = {"action": "getCountries", "api_key": SMS_API_KEY}
    try:
        response = requests.get(API_BASE_URL, params=params)
        data = response.json()
        # تحويل القاموس إلى قائمة إذا لزم الأمر
        countries = []
        if isinstance(data, dict):
            for cid, cinfo in data.items():
                countries.append({"id": cid, "name": cinfo.get("name_en", cinfo.get("name", "Unknown"))})
        elif isinstance(data, list):
            countries = data
        cache["countries"] = countries
        return countries
    except Exception as e:
        logger.error(f"Error getting countries: {e}")
        return []

async def get_services():
    if cache["services"]:
        return cache["services"]
    params = {"action": "getServices", "api_key": SMS_API_KEY}
    try:
        response = requests.get(API_BASE_URL, params=params)
        data = response.json()
        services = []
        if isinstance(data, dict):
            for sid, sinfo in data.items():
                services.append({"id": sid, "name": sinfo.get("name", "Unknown")})
        elif isinstance(data, list):
            services = data
        cache["services"] = services
        return services
    except Exception as e:
        logger.error(f"Error getting services: {e}")
        return []

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    balance = await get_balance()
    user_name = update.effective_user.first_name
    welcome_text = (
        f"مرحباً بك يا {user_name} في بوت تفعيل الأرقام الاحترافي 🤖\n\n"
        f"💰 رصيدك الحالي: {balance} USD\n\n"
        "يمكنك البدء باختيار الدولة ثم الخدمة المطلوبة."
    )
    keyboard = [
        [InlineKeyboardButton("🌍 اختيار الدولة", callback_query_data="list_countries")],
        [InlineKeyboardButton("💰 تحديث الرصيد", callback_query_data="update_balance")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    if update.message:
        await update.message.reply_text(welcome_text, reply_markup=reply_markup)
    else:
        await update.callback_query.edit_message_text(welcome_text, reply_markup=reply_markup)

async def list_countries(update: Update, context: ContextTypes.DEFAULT_TYPE, page=0):
    query = update.callback_query
    countries = await get_countries()
    
    # تقسيم الدول لصفحات (10 في كل صفحة)
    per_page = 10
    start_idx = page * per_page
    end_idx = start_idx + per_page
    current_countries = countries[start_idx:end_idx]
    
    keyboard = []
    for country in current_countries:
        c_name = country.get("name_en", country.get("name", "Unknown"))
        c_id = country.get("id")
        keyboard.append([InlineKeyboardButton(f"🏳️ {c_name}", callback_query_data=f"select_country:{c_id}")])
    
    # أزرار التنقل
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ السابق", callback_query_data=f"page_country:{page-1}"))
    if end_idx < len(countries):
        nav_buttons.append(InlineKeyboardButton("التالي ➡️", callback_query_data=f"page_country:{page+1}"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    keyboard.append([InlineKeyboardButton("🔍 بحث عن دولة", callback_query_data="search_country")])
    keyboard.append([InlineKeyboardButton("🏠 العودة للرئيسية", callback_query_data="back_home")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("الرجاء اختيار الدولة من القائمة أدناه:", reply_markup=reply_markup)

async def list_services(update: Update, context: ContextTypes.DEFAULT_TYPE, country_id, page=0):
    query = update.callback_query
    services = await get_services()
    
    per_page = 10
    start_idx = page * per_page
    end_idx = start_idx + per_page
    current_services = services[start_idx:end_idx]
    
    keyboard = []
    for service in current_services:
        s_name = service.get("name", "Unknown")
        s_id = service.get("id")
        keyboard.append([InlineKeyboardButton(f"📲 {s_name}", callback_query_data=f"buy:{country_id}:{s_id}")])
    
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ السابق", callback_query_data=f"page_service:{country_id}:{page-1}"))
    if end_idx < len(services):
        nav_buttons.append(InlineKeyboardButton("التالي ➡️", callback_query_data=f"page_service:{country_id}:{page+1}"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
        
    keyboard.append([InlineKeyboardButton("🔍 بحث عن خدمة", callback_query_data=f"search_service:{country_id}")])
    keyboard.append([InlineKeyboardButton("🌍 تغيير الدولة", callback_query_data="list_countries")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(f"اختر الخدمة المطلوبة للدولة المختارة:", reply_markup=reply_markup)

async def buy_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    _, country_id, service_id = query.data.split(":")
    
    params = {
        "action": "getNumber",
        "api_key": SMS_API_KEY,
        "country": country_id,
        "service": service_id
    }
    
    try:
        response = requests.get(API_BASE_URL, params=params)
        res_text = response.text
        
        if "ACCESS_NUMBER" in res_text:
            # ACCESS_NUMBER:id:number
            _, activation_id, number = res_text.split(":")
            msg = (
                f"✅ تم حجز الرقم بنجاح!\n\n"
                f"📞 الرقم: `{number}`\n"
                f"🆔 معرف العملية: `{activation_id}`\n\n"
                "الرجاء طلب الكود في التطبيق ثم الضغط على زر التحديث."
            )
            keyboard = [
                [InlineKeyboardButton("🔄 جلب الكود", callback_query_data=f"get_code:{activation_id}")],
                [InlineKeyboardButton("❌ إلغاء الرقم", callback_query_data=f"cancel:{activation_id}")]
            ]
            await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        elif "NO_NUMBERS" in res_text:
            await query.answer("❌ عذراً، لا تتوفر أرقام حالياً لهذه الخدمة في هذه الدولة.", show_alert=True)
        elif "NO_BALANCE" in res_text:
            await query.answer("❌ رصيدك غير كافٍ لإتمام العملية.", show_alert=True)
        else:
            await query.answer(f"❌ حدث خطأ: {res_text}", show_alert=True)
            
    except Exception as e:
        logger.error(f"Error buying number: {e}")
        await query.answer("❌ حدث خطأ تقني أثناء طلب الرقم.", show_alert=True)

async def get_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    activation_id = query.data.split(":")[1]
    
    params = {"action": "getStatus", "api_key": SMS_API_KEY, "id": activation_id}
    
    try:
        response = requests.get(API_BASE_URL, params=params)
        res_text = response.text
        
        if "STATUS_OK" in res_text:
            code = res_text.split(":")[1]
            await query.edit_message_text(f"✅ الكود الواصل: `{code}`", parse_mode="Markdown")
        elif "STATUS_WAIT_CODE" in res_text:
            await query.answer("⏳ لم يصل الكود بعد، يرجى الانتظار والمحاولة مرة أخرى.", show_alert=True)
        elif "STATUS_CANCEL" in res_text:
            await query.edit_message_text("❌ تم إلغاء هذه العملية.")
        else:
            await query.answer(f"ℹ️ الحالة الحالية: {res_text}", show_alert=True)
    except Exception as e:
        logger.error(f"Error getting status: {e}")
        await query.answer("❌ خطأ في جلب الحالة.", show_alert=True)

async def cancel_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    activation_id = query.data.split(":")[1]
    
    params = {
        "action": "setStatus",
        "api_key": SMS_API_KEY,
        "id": activation_id,
        "status": "-1"
    }
    
    try:
        response = requests.get(API_BASE_URL, params=params)
        if "ACCESS_CANCEL" in response.text:
            await query.edit_message_text("✅ تم إلغاء الرقم بنجاح واستعادة الرصيد.")
        else:
            await query.answer(f"❌ لا يمكن الإلغاء حالياً: {response.text}", show_alert=True)
    except Exception as e:
        logger.error(f"Error cancelling: {e}")
        await query.answer("❌ خطأ في عملية الإلغاء.", show_alert=True)

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    
    if data == "list_countries":
        await list_countries(update, context)
    elif data.startswith("page_country:"):
        page = int(data.split(":")[1])
        await list_countries(update, context, page=page)
    elif data.startswith("select_country:"):
        country_id = data.split(":")[1]
        await list_services(update, context, country_id)
    elif data.startswith("page_service:"):
        _, country_id, page = data.split(":")
        await list_services(update, context, country_id, page=int(page))
    elif data.startswith("buy:"):
        await buy_number(update, context)
    elif data.startswith("get_code:"):
        await get_code(update, context)
    elif data.startswith("cancel:"):
        await cancel_number(update, context)
    elif data == "update_balance":
        balance = await get_balance()
        await query.answer(f"💰 رصيدك الحالي: {balance} USD", show_alert=True)
    elif data == "back_home":
        await start(update, context)
    elif data == "search_country":
        context.user_data["state"] = "search_country"
        await query.edit_message_text("الرجاء إرسال اسم الدولة بالإنجليزية للبحث عنها:")
    elif data.startswith("search_service:"):
        country_id = data.split(":")[1]
        context.user_data["state"] = "search_service"
        context.user_data["search_country_id"] = country_id
        await query.edit_message_text("الرجاء إرسال اسم الخدمة للبحث عنها (مثال: whatsapp):")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = context.user_data.get("state")
    text = update.message.text.lower()
    
    if state == "search_country":
        countries = await get_countries()
        results = [c for c in countries if text in c.get("name_en", "").lower() or text in c.get("name", "").lower()]
        
        if not results:
            await update.message.reply_text("❌ لم يتم العثور على نتائج. حاول مرة أخرى أو ارجع للرئيسية /start")
            return
            
        keyboard = []
        for c in results[:10]: # عرض أول 10 نتائج
            keyboard.append([InlineKeyboardButton(f"🏳️ {c['name']}", callback_query_data=f"select_country:{c['id']}")])
        
        keyboard.append([InlineKeyboardButton("🏠 العودة للرئيسية", callback_query_data="back_home")])
        await update.message.reply_text(f"🔍 نتائج البحث عن '{text}':", reply_markup=InlineKeyboardMarkup(keyboard))
        context.user_data["state"] = None
        
    elif state == "search_service":
        country_id = context.user_data.get("search_country_id")
        services = await get_services()
        results = [s for s in services if text in s.get("name", "").lower() or text in s.get("id", "").lower()]
        
        if not results:
            await update.message.reply_text("❌ لم يتم العثور على خدمات تطابق بحثك.")
            return
            
        keyboard = []
        for s in results[:10]:
            keyboard.append([InlineKeyboardButton(f"📲 {s['name']}", callback_query_data=f"buy:{country_id}:{s['id']}")])
            
        keyboard.append([InlineKeyboardButton("🌍 تغيير الدولة", callback_query_data="list_countries")])
        await update.message.reply_text(f"🔍 نتائج البحث عن '{text}':", reply_markup=InlineKeyboardMarkup(keyboard))
        context.user_data["state"] = None

def main():
    if not BOT_TOKEN or not SMS_API_KEY:
        print("Error: BOT_TOKEN or SMS_API_KEY not set in environment variables.")
        return

    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(handle_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    print("Bot is starting...")
    application.run_polling()

if __name__ == "__main__":
    main()
