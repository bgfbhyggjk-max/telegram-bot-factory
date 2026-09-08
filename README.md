# Telegram Bot Factory

مصنع بوتات تيليجرام بـ Python + aiogram 3.

## الوظائف

### لوحة المصنع
- إنشاء بوت بواسطة Token.
- تحديد Telegram ID لمالك البوت المصنوع.
- قائمة البوتات.
- تشغيل / إيقاف / حذف.
- معلومات وحالة كل بوت.
- استعادة البوتات المفعلة بعد إعادة تشغيل السيرفر.

### لوحة مالك البوت
- 📣 إذاعة.
- اختيار مكان النشر: **الخاص فقط / المجموعات والقنوات / الكل**.
- عند اختيار المجموعات والقنوات: إدخال Chat IDs المحفوظة أو اختيار «الكل».
- 📊 إحصائيات.
- ✏️ رسالة الترحيب.
- إضافة/حذف مجموعات وقنوات.

## التخزين الدائم

كل البيانات المهمة محفوظة في:

`data/factory.db`

وقاعدة البيانات تحفظ:
- البوتات وTokens الخاصة بها.
- مالك كل بوت.
- حالة التشغيل.
- مستخدمي الخاص الذين بدأوا البوت.
- Chat IDs للمجموعات والقنوات.
- إعدادات البوت.

**نقل الاستضافة:** انسخ المشروع ومعه `data/factory.db` إلى السيرفر الجديد. لا تحذف ملف قاعدة البيانات. عند تشغيل المشروع سيقرأ نفس البيانات ويعيد تشغيل البوتات التي كانت مفعلة.

لا ترفع `data/factory.db` أو `.env` إلى GitHub لأنهما يحتويان على أسرار وبيانات تشغيل.

## التشغيل

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
nano .env
python3 -m app.main
```

## تشغيل دائم عبر systemd

```ini
[Unit]
Description=Telegram Bot Factory
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/opt/bot_factory
ExecStart=/opt/bot_factory/.venv/bin/python -m app.main
Restart=always
RestartSec=5
EnvironmentFile=/opt/bot_factory/.env

[Install]
WantedBy=multi-user.target
```

ثم:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now bot-factory
sudo systemctl status bot-factory
```

## ملاحظة Telegram

البوت يرسل في الخاص فقط للمستخدمين الذين بدأوا المحادثة معه، ويرسل للمجموعات/القنوات التي أضيف إليها ولديه صلاحية الإرسال. Chat IDs للمجموعات والقنوات يتم حفظها في `data/factory.db`.

## أمان

أي Token تم نشره أو إرساله في مكان عام يجب تدويره من BotFather. استخدم Token جديداً في `.env` ولا تضعه في الكود أو GitHub.
