#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
بوت تلجرام احترافي لتفعيل أرقام واتساب خليجية
يستخدم API من موقع SMS-Activate.org
"""

import os
import logging
from typing import Dict
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

# إعداد نظام السجلات
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# جلب المتغيرات البيئية
BOT_TOKEN = os.getenv('BOT_TOKEN')
SMS_API_KEY = os.getenv('SMS_API_KEY')

# التحقق من وجود المتغيرات
if not BOT_TOKEN or not SMS_API_KEY:
    raise ValueError("❌ يجب تعيين BOT_TOKEN و SMS_API_KEY في متغيرات البيئة")

# إعدادات API
SMS_ACTIVATE_BASE_URL = "https://api.sms-activate.org/stubs/handler_api.php"
SERVICE_CODE = "wa"  # كود خدمة الواتساب

# معلومات الدول الخليجية
GULF_COUNTRIES = {
    'saudi': {'name': 'السعودية 🇸🇦', 'id': 2},
    'uae': {'name': 'الإمارات 🇦🇪', 'id': 95},
    'kuwait': {'name': 'الكويت 🇰🇼', 'id': 48},
    'qatar': {'name': 'قطر 🇶🇦', 'id': 110},
}

# تخزين مؤقت لبيانات المستخدمين (في بيئة الإنتاج استخدم قاعدة بيانات)
user_data: Dict[int, dict] = {}


class SMSActivateAPI:
    """كلاس للتعامل مع API موقع SMS-Activate"""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = SMS_ACTIVATE_BASE_URL
    
    def _make_request(self, params: dict) -> str:
        """إجراء طلب API مع معالجة الأخطاء"""
        try:
            params['api_key'] = self.api_key
            response = requests.get(self.base_url, params=params, timeout=10)
            response.raise_for_status()
            return response.text
        except requests.exceptions.RequestException as e:
            logger.error(f"خطأ في الاتصال بـ API: {e}")
            return f"ERROR:CONNECTION_FAILED"
    
    def get_balance(self) -> float:
        """الحصول على الرصيد الحالي"""
        result = self._make_request({'action': 'getBalance'})
        if result.startswith('ACCESS_BALANCE:'):
            return float(result.split(':')[1])
        return 0.0
    
    def get_number(self, country_id: int, service: str = SERVICE_CODE) -> dict:
        """حجز رقم جديد"""
        params = {
            'action': 'getNumber',
            'service': service,
            'country': country_id,
        }
        result = self._make_request(params)
        
        if result.startswith('ACCESS_NUMBER:'):
            parts = result.split(':')
            return {
                'success': True,
                'activation_id': parts[1],
                'phone_number': parts[2]
            }
        elif result == 'NO_NUMBERS':
            return {'success': False, 'error': 'لا توجد أرقام متاحة حالياً'}
        elif result == 'NO_BALANCE':
            return {'success': False, 'error': 'رصيد غير كافٍ'}
        elif result.startswith('BAD_'):
            return {'success': False, 'error': f'خطأ في الطلب: {result}'}
        else:
            return {'success': False, 'error': f'خطأ غير متوقع: {result}'}
    
    def get_status(self, activation_id: str) -> dict:
        """الحصول على حالة الرقم والكود"""
        params = {
            'action': 'getStatus',
            'id': activation_id,
        }
        result = self._make_request(params)
        
        if result.startswith('STATUS_OK:'):
            code = result.split(':')[1]
            return {'success': True, 'status': 'received', 'code': code}
        elif result == 'STATUS_WAIT_CODE':
            return {'success': True, 'status': 'waiting'}
        elif result == 'STATUS_CANCEL':
            return {'success': True, 'status': 'cancelled'}
        else:
            return {'success': False, 'error': result}
    
    def set_status(self, activation_id: str, status: int) -> bool:
        """تغيير حالة التفعيل (1=تم الاستلام، 8=إلغاء)"""
        params = {
            'action': 'setStatus',
            'id': activation_id,
            'status': status,
        }
        result = self._make_request(params)
        return result == 'ACCESS_ACTIVATION' or result == 'ACCESS_CANCEL'


# إنشاء كائن API
sms_api = SMSActivateAPI(SMS_API_KEY)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """معالج أمر /start - عرض قائمة الدول"""
    user = update.effective_user
    logger.info(f"المستخدم {user.id} ({user.username}) بدأ البوت")
    
    # إنشاء أزرار الدول
    keyboard = [
        [
            InlineKeyboardButton(GULF_COUNTRIES['saudi']['name'], callback_data='country_saudi'),
            InlineKeyboardButton(GULF_COUNTRIES['uae']['name'], callback_data='country_uae'),
        ],
        [
            InlineKeyboardButton(GULF_COUNTRIES['kuwait']['name'], callback_data='country_kuwait'),
            InlineKeyboardButton(GULF_COUNTRIES['qatar']['name'], callback_data='country_qatar'),
        ],
        [
            InlineKeyboardButton("💰 عرض الرصيد", callback_data='check_balance'),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    welcome_text = (
        f"مرحباً {user.first_name}! 👋\n\n"
        "🔢 بوت تفعيل أرقام واتساب خليجية\n\n"
        "اختر الدولة التي تريد الحصول على رقم منها:"
    )
    
    await update.message.reply_text(welcome_text, reply_markup=reply_markup)


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """معالج نقرات الأزرار"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    data = query.data
    
    # التعامل مع اختيار الدولة
    if data.startswith('country_'):
        country_key = data.replace('country_', '')
        await handle_country_selection(query, user_id, country_key)
    
    # التعامل مع تحديث الكود
    elif data.startswith('refresh_'):
        activation_id = data.replace('refresh_', '')
        await handle_refresh_code(query, user_id, activation_id)
    
    # التعامل مع إلغاء الرقم
    elif data.startswith('cancel_'):
        activation_id = data.replace('cancel_', '')
        await handle_cancel_number(query, user_id, activation_id)
    
    # عرض الرصيد
    elif data == 'check_balance':
        await handle_check_balance(query)
    
    # العودة للقائمة الرئيسية
    elif data == 'back_to_menu':
        await show_main_menu(query)


async def handle_country_selection(query, user_id: int, country_key: str) -> None:
    """معالجة اختيار الدولة وحجز الرقم"""
    country = GULF_COUNTRIES.get(country_key)
    if not country:
        await query.edit_message_text("❌ خطأ: دولة غير صحيحة")
        return
    
    await query.edit_message_text(
        f"⏳ جاري البحث عن رقم من {country['name']}...\n"
        "الرجاء الانتظار..."
    )
    
    # حجز الرقم
    result = sms_api.get_number(country['id'])
    
    if not result['success']:
        error_msg = (
            f"❌ فشل الحصول على رقم من {country['name']}\n\n"
            f"السبب: {result['error']}\n\n"
            "يرجى المحاولة مرة أخرى أو اختيار دولة أخرى."
        )
        keyboard = [[InlineKeyboardButton("🔙 العودة للقائمة", callback_data='back_to_menu')]]
        await query.edit_message_text(error_msg, reply_markup=InlineKeyboardMarkup(keyboard))
        return
    
    # حفظ بيانات المستخدم
    activation_id = result['activation_id']
    phone_number = result['phone_number']
    
    user_data[user_id] = {
        'activation_id': activation_id,
        'phone_number': phone_number,
        'country': country['name']
    }
    
    # عرض معلومات الرقم
    success_msg = (
        f"✅ تم حجز رقم من {country['name']}\n\n"
        f"📱 الرقم: `+{phone_number}`\n"
        f"🆔 معرف العملية: `{activation_id}`\n\n"
        f"⏰ انتظر وصول كود الواتساب (حتى 20 دقيقة)\n"
        f"ثم اضغط على زر التحديث للحصول على الكود"
    )
    
    keyboard = [
        [InlineKeyboardButton("🔄 تحديث - جلب الكود", callback_data=f'refresh_{activation_id}')],
        [InlineKeyboardButton("❌ إلغاء الرقم", callback_data=f'cancel_{activation_id}')],
        [InlineKeyboardButton("🔙 العودة للقائمة", callback_data='back_to_menu')],
    ]
    
    await query.edit_message_text(
        success_msg,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )


async def handle_refresh_code(query, user_id: int, activation_id: str) -> None:
    """معالجة طلب تحديث الكود"""
    await query.answer("⏳ جاري البحث عن الكود...")
    
    # الحصول على حالة الرقم
    status_result = sms_api.get_status(activation_id)
    
    if not status_result['success']:
        await query.answer(f"❌ خطأ: {status_result['error']}", show_alert=True)
        return
    
    if status_result['status'] == 'received':
        code = status_result['code']
        
        # تحديث حالة التفعيل (تم الاستلام)
        sms_api.set_status(activation_id, 1)
        
        user_info = user_data.get(user_id, {})
        success_msg = (
            f"🎉 تم استلام الكود بنجاح!\n\n"
            f"📱 الرقم: `+{user_info.get('phone_number', 'غير معروف')}`\n"
            f"🔐 كود التفعيل: `{code}`\n\n"
            f"استخدم الكود لتفعيل الواتساب الآن"
        )
        
        keyboard = [[InlineKeyboardButton("🔙 العودة للقائمة", callback_data='back_to_menu')]]
        
        await query.edit_message_text(
            success_msg,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    
    elif status_result['status'] == 'waiting':
        await query.answer(
            "⏰ لم يصل الكود بعد، يرجى الانتظار والمحاولة مرة أخرى",
            show_alert=True
        )
    
    elif status_result['status'] == 'cancelled':
        await query.answer("❌ تم إلغاء هذا الرقم", show_alert=True)
        await show_main_menu(query)


async def handle_cancel_number(query, user_id: int, activation_id: str) -> None:
    """معالجة إلغاء الرقم"""
    await query.answer("⏳ جاري إلغاء الرقم...")
    
    # إلغاء التفعيل (استرجاع الرصيد)
    success = sms_api.set_status(activation_id, 8)
    
    if success:
        # حذف بيانات المستخدم
        if user_id in user_data:
            del user_data[user_id]
        
        cancel_msg = (
            "✅ تم إلغاء الرقم بنجاح\n"
            "💰 تم استرجاع الرصيد\n\n"
            "يمكنك طلب رقم جديد الآن"
        )
        
        await query.answer("✅ تم الإلغاء بنجاح", show_alert=True)
        await show_main_menu(query, cancel_msg)
    else:
        await query.answer("❌ فشل إلغاء الرقم، حاول مرة أخرى", show_alert=True)


async def handle_check_balance(query) -> None:
    """عرض الرصيد الحالي"""
    balance = sms_api.get_balance()
    
    balance_msg = (
        f"💰 الرصيد الحالي: {balance:.2f} روبل\n\n"
        f"يمكنك شحن الرصيد من موقع SMS-Activate.org"
    )
    
    keyboard = [[InlineKeyboardButton("🔙 العودة للقائمة", callback_data='back_to_menu')]]
    
    await query.edit_message_text(
        balance_msg,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def show_main_menu(query, message: str = None) -> None:
    """عرض القائمة الرئيسية"""
    keyboard = [
        [
            InlineKeyboardButton(GULF_COUNTRIES['saudi']['name'], callback_data='country_saudi'),
            InlineKeyboardButton(GULF_COUNTRIES['uae']['name'], callback_data='country_uae'),
        ],
        [
            InlineKeyboardButton(GULF_COUNTRIES['kuwait']['name'], callback_data='country_kuwait'),
            InlineKeyboardButton(GULF_COUNTRIES['qatar']['name'], callback_data='country_qatar'),
        ],
        [
            InlineKeyboardButton("💰 عرض الرصيد", callback_data='check_balance'),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = message if message else "اختر الدولة التي تريد الحصول على رقم منها:"
    
    await query.edit_message_text(text, reply_markup=reply_markup)


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """معالج الأخطاء العام"""
    logger.error(f"حدث خطأ: {context.error}")
    
    if update and update.effective_message:
        await update.effective_message.reply_text(
            "❌ حدث خطأ غير متوقع\n"
            "يرجى المحاولة مرة أخرى أو التواصل مع المطور"
        )


def main() -> None:
    """نقطة البداية الرئيسية للبوت"""
    logger.info("🚀 بدء تشغيل البوت...")
    
    # إنشاء التطبيق
    application = Application.builder().token(BOT_TOKEN).build()
    
    # إضافة المعالجات
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CallbackQueryHandler(button_callback))
    
    # معالج الأخطاء
    application.add_error_handler(error_handler)
    
    # بدء البوت
    logger.info("✅ البوت يعمل الآن...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
