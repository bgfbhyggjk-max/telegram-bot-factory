import asyncio
import logging
from contextlib import suppress

from aiogram import Bot, Dispatcher, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode, ChatType
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from app.keyboards import bot_panel, settings_panel, broadcast_targets
from app.states import BotBroadcast, BotWelcome, BotAllowedChat

log = logging.getLogger(__name__)


class ManagedBot:
    def __init__(self, manager, row):
        self.manager = manager
        self.row = row
        self.bot_id = row['bot_id']
        self.owner_id = row['owner_id']
        self.bot = Bot(
            row['token'],
            default=DefaultBotProperties(parse_mode=ParseMode.HTML)
        )
        self.dp = Dispatcher()
        self.router = Router()
        self.dp.include_router(self.router)
        self._register_handlers()

    def _owner(self, user_id):
        return user_id == self.owner_id

    async def _finish_broadcast(
        self,
        message: Message,
        state: FSMContext,
        target: str,
        chat_ids
    ):
        if not self._owner(message.from_user.id):
            return

        await state.clear()
        destinations = []

        if target in ('private', 'all'):
            destinations.extend(
                ('private', chat_id)
                for chat_id in await self.manager.db.get_subscribers(self.bot_id)
            )

        if target in ('chats', 'all'):
            destinations.extend(
                ('chat', chat_id)
                for chat_id in chat_ids
            )

        seen = set()
        unique = []

        for item in destinations:
            if item not in seen:
                seen.add(item)
                unique.append(item)

        sent = failed = 0

        status = await message.answer(
            f'📣 بدأت الإذاعة...\n'
            f'🎯 عدد الوجهات: <b>{len(unique)}</b>'
        )

        for kind, chat_id in unique:
            try:
                await self.bot.copy_message(
                    chat_id=chat_id,
                    from_chat_id=message.chat.id,
                    message_id=message.message_id,
                )
                sent += 1

            except Exception as exc:
                failed += 1

                log.warning(
                    'Broadcast failed bot=%s chat=%s kind=%s error=%s',
                    self.bot_id,
                    chat_id,
                    kind,
                    exc
                )

                if kind == 'private':
                    await self.manager.db.remove_subscriber(
                        self.bot_id,
                        chat_id
                    )

            await asyncio.sleep(self.manager.delay)

        await status.edit_text(
            f'✅ <b>انتهت الإذاعة</b>\n\n'
            f'📨 نجح: <b>{sent}</b>\n'
            f'❌ فشل: <b>{failed}</b>\n'
            f'🎯 الإجمالي: <b>{len(unique)}</b>',
            reply_markup=bot_panel(),
        )

    def _register_handlers(self):
        router = self.router

        @router.message(CommandStart())
        async def start(message: Message):
            if message.chat.type == ChatType.PRIVATE and message.from_user:
                await self.manager.db.add_subscriber(
                    self.bot_id,
                    message.from_user.id
                )

            if message.from_user and self._owner(message.from_user.id):
                setting = await self.manager.db.get_setting(self.bot_id)

                welcome = (
                    setting['welcome_text']
                    if setting
                    else 'مرحباً بك يا مالك البوت!'
                )

                await message.answer(
                    welcome,
                    reply_markup=bot_panel()
                )

            else:
                await message.answer('مرحباً بك 👋')

        @router.message(lambda m: m.chat.type == ChatType.PRIVATE)
        async def track_user(message: Message):
            if message.from_user:
                await self.manager.db.add_subscriber(
                    self.bot_id,
                    message.from_user.id
                )

        @router.callback_query(lambda c: c.data == 'b:stats')
        async def stats(call: CallbackQuery):
            if not self._owner(call.from_user.id):
                return await call.answer(
                    'غير مصرح',
                    show_alert=True
                )

            count = await self.manager.db.subscriber_count(
                self.bot_id
            )

            chats = await self.manager.db.get_allowed_chats(
                self.bot_id
            )

            await call.message.edit_text(
                f'📊 <b>الإحصائيات</b>\n\n'
                f'👥 المستخدمون في الخاص: <b>{count}</b>\n'
                f'💬 المجموعات والقنوات المحفوظة: <b>{len(chats)}</b>',
                reply_markup=bot_panel(),
            )

            await call.answer()

        @router.callback_query(lambda c: c.data == 'b:settings')
        async def settings(call: CallbackQuery):
            if not self._owner(call.from_user.id):
                return await call.answer(
                    'غير مصرح',
                    show_alert=True
                )

            await call.message.edit_text(
                '⚙️ اختر من الإعدادات:',
                reply_markup=settings_panel()
            )

            await call.answer()

        @router.callback_query(lambda c: c.data == 'bs:back')
        async def back(call: CallbackQuery):
            if not self._owner(call.from_user.id):
                return await call.answer(
                    'غير مصرح',
                    show_alert=True
                )

            await call.message.edit_text(
                'لوحة التحكم الرئيسية:',
                reply_markup=bot_panel()
            )

            await call.answer()

        @router.callback_query(lambda c: c.data == 'bs:welcome')
        async def welcome_start(
            call: CallbackQuery,
            state: FSMContext
        ):
            if not self._owner(call.from_user.id):
                return await call.answer(
                    'غير مصرح',
                    show_alert=True
                )

            await state.set_state(BotWelcome.content)

            await call.message.answer(
                'أرسل رسالة الترحيب الجديدة:'
            )

            await call.answer()

        @router.message(BotWelcome.content)
        async def welcome_save(
            message: Message,
            state: FSMContext
        ):
            if not self._owner(message.from_user.id):
                return

            text = message.text or message.caption

            if not text:
                return await message.answer(
                    '❌ أرسل نصاً لرسالة الترحيب.'
                )

            await self.manager.db.set_welcome(
                self.bot_id,
                text
            )

            await state.clear()

            await message.answer(
                '✅ تم حفظ رسالة الترحيب.',
                reply_markup=bot_panel()
            )

        @router.callback_query(lambda c: c.data == 'b:broadcast')
        async def broadcast_start(
            call: CallbackQuery,
            state: FSMContext
        ):
            if not self._owner(call.from_user.id):
                return await call.answer(
                    'غير مصرح',
                    show_alert=True
                )

            await state.set_state(BotBroadcast.target)

            await call.message.answer(
                '📣 <b>اختر مكان نشر المنشور:</b>',
                reply_markup=broadcast_targets()
            )

            await call.answer()

        @router.callback_query(
            lambda c: c.data in {
                'bt:private',
                'bt:chats',
                'bt:all'
            }
        )
        async def broadcast_target(
            call: CallbackQuery,
            state: FSMContext
        ):
            if not self._owner(call.from_user.id):
                return await call.answer(
                    'غير مصرح',
                    show_alert=True
                )

            target = call.data.split(':', 1)[1]

            await state.update_data(
                target=target
            )

            if target == 'private':
                await state.set_state(
                    BotBroadcast.content
                )

                await call.message.answer(
                    '👤 أرسل المنشور الآن.\n'
                    'سيتم إرساله للمستخدمين الذين بدأوا البوت فقط.'
                )

            else:
                await state.set_state(
                    BotBroadcast.chats
                )

                await call.message.answer(
                    '👥 أرسل Chat IDs للمجموعات والقنوات المطلوبة، '
                    'مفصولة بفواصل.\n'
                    'مثال: '
                    '<code>-1001234567890,-1009876543210</code>\n\n'
                    'أو اكتب <code>الكل</code> لاستخدام كل المجموعات '
                    'والقنوات المحفوظة.'
                )

            await call.answer()

        @router.message(BotBroadcast.chats)
        async def broadcast_chats(
            message: Message,
            state: FSMContext
        ):
            if not self._owner(message.from_user.id):
                return

            data = await state.get_data()

            target = data.get('target')

            saved = await self.manager.db.get_allowed_chats(
                self.bot_id
            )

            saved_ids = [
                int(row['chat_id'])
                for row in saved
            ]

            raw = (message.text or '').strip()

            if raw == 'الكل' or raw.lower() == 'all':
                chat_ids = saved_ids

            else:
                try:
                    parts = [
                        p.strip()
                        for p in raw.replace('،', ',').split(',')
                        if p.strip()
                    ]

                    chat_ids = list(
                        dict.fromkeys(
                            int(p)
                            for p in parts
                        )
                    )

                except ValueError:
                    return await message.answer(
                        '❌ أرسل IDs مفصولة بفواصل '
                        'أو اكتب «الكل».'
                    )

                unauthorized = [
                    x
                    for x in chat_ids
                    if x not in saved_ids
                ]

                if unauthorized:
                    return await message.answer(
                        '❌ هذه الـ IDs غير محفوظة في إعدادات البوت:\n'
                        +
                        '\n'.join(
                            f'• <code>{x}</code>'
                            for x in unauthorized
                        )
                        +
                        '\n\nأضفها أولاً من الإعدادات.'
                    )

            if target == 'chats' and not chat_ids:
                return await message.answer(
                    '❌ لم يتم تحديد أي مجموعة أو قناة.'
                )

            await state.update_data(
                chat_ids=chat_ids
            )

            await state.set_state(
                BotBroadcast.content
            )

            await message.answer(
                f'✅ تم تحديد <b>{len(chat_ids)}</b> مجموعة/قناة.\n'
                'الآن أرسل المنشور نفسه '
                '(نص/صورة/فيديو/ملف...).'
            )

        @router.message(BotBroadcast.content)
        async def broadcast_send(
            message: Message,
            state: FSMContext
        ):
            if not self._owner(message.from_user.id):
                return

            data = await state.get_data()

            await self._finish_broadcast(
                message,
                state,
                data.get('target', 'private'),
                data.get('chat_ids', [])
            )

        @router.callback_query(lambda c: c.data == 'bs:addchat')
        async def addchat_start(
            call: CallbackQuery,
            state: FSMContext
        ):
            if not self._owner(call.from_user.id):
                return await call.answer(
                    'غير مصرح',
                    show_alert=True
                )

            await state.set_state(
                BotAllowedChat.add_chat_id
            )

            await call.message.answer(
                '➕ أرسل Chat ID للمجموعة أو القناة.\n'
                'يجب أن يكون البوت مضافاً إليها '
                'ولديه صلاحية الإرسال.\n'
                'مثال: <code>-1001234567890</code>'
            )

            await call.answer()

        @router.message(BotAllowedChat.add_chat_id)
        async def addchat_save(
            message: Message,
            state: FSMContext
        ):
            if not self._owner(message.from_user.id):
                return

            try:
                chat_id = int(
                    (message.text or '').strip()
                )

            except ValueError:
                return await message.answer(
                    '❌ أرسل Chat ID رقمي صحيح.'
                )

            try:
                chat = await self.bot.get_chat(
                    chat_id
                )

                if chat.type not in {
                    ChatType.GROUP,
                    ChatType.SUPERGROUP,
                    ChatType.CHANNEL
                }:
                    return await message.answer(
                        '❌ هذا الـ Chat ليس مجموعة أو قناة.'
                    )

                await self.manager.db.add_allowed_chat(
                    self.bot_id,
                    chat.id,
                    chat.title or str(chat.id),
                    chat.type
                )

                await state.clear()

                await message.answer(
                    f'✅ تم حفظ '
                    f'<b>{chat.title or chat.id}</b> بشكل دائم.\n'
                    f'🆔 <code>{chat.id}</code>',
                    reply_markup=bot_panel()
                )

            except Exception as exc:
                await message.answer(
                    '❌ لم أستطع الوصول إلى المجموعة/القناة. '
                    'تأكد من إضافة البوت والصلاحيات وChat ID.\n\n'
                    f'<code>{exc}</code>'
                )

        @router.callback_query(lambda c: c.data == 'bs:delchat')
        async def delchat_start(
            call: CallbackQuery,
            state: FSMContext
        ):
            if not self._owner(call.from_user.id):
                return await call.answer(
                    'غير مصرح',
                    show_alert=True
                )

            await state.set_state(
                BotAllowedChat.delete_chat_id
            )

            await call.message.answer(
                'أرسل Chat ID لحذفه من قائمة '
                'المجموعات والقنوات المحفوظة.'
            )

            await call.answer()

        @router.message(BotAllowedChat.delete_chat_id)
        async def delchat_save(
            message: Message,
            state: FSMContext
        ):
            if not self._owner(message.from_user.id):
                return

            try:
                chat_id = int(
                    (message.text or '').strip()
                )

            except ValueError:
                return await message.answer(
                    '❌ أرسل Chat ID رقمي صحيح.'
                )

            await self.manager.db.remove_allowed_chat(
                self.bot_id,
                chat_id
            )

            await state.clear()

            await message.answer(
                '✅ تم حذف المجموعة/القناة.',
                reply_markup=bot_panel()
            )

        @router.callback_query(lambda c: c.data == 'b:mandatory')
        async def mandatory(call: CallbackQuery):
            if not self._owner(call.from_user.id):
                return await call.answer(
                    'غير مصرح',
                    show_alert=True
                )

            await call.message.answer(
                '🔒 الاشتراك الإجباري متروك للتوسعة التالية، '
                'ويستخدم فقط مع قنوات يديرها صاحب البوت.'
            )

            await call.answer()

        @router.callback_query(lambda c: c.data == 'b:auto')
        async def auto(call: CallbackQuery):
            if not self._owner(call.from_user.id):
                return await call.answer(
                    'غير مصرح',
                    show_alert=True
                )

            chats = await self.manager.db.get_allowed_chats(
                self.bot_id
            )

            text = (
                '📢 <b>المجموعات والقنوات المحفوظة</b>\n\n'
            )

            text += (
                '\n'.join(
                    f"• {r['title']} — "
                    f"<code>{r['chat_id']}</code>"
                    for r in chats
                )
                if chats
                else 'لا توجد مجموعات/قنوات محفوظة.'
            )

            await call.message.answer(text)

            await call.answer()

    async def run(self):
        await self.bot.delete_webhook(
            drop_pending_updates=False
        )

        me = await self.bot.get_me()

        log.info(
            'Starting managed bot @%s (%s)',
            me.username,
            me.id
        )

        await self.dp.start_polling(
            self.bot,
            handle_signals=False
        )

    async def close(self):
        with suppress(Exception):
            await self.bot.session.close()


class BotManager:
    def __init__(self, db, delay=0.08):
        self.db = db
        self.delay = delay
        self.running = {}
        self.instances = {}

    async def start_bot(self, bot_id):
        if (
            bot_id in self.running
            and not self.running[bot_id].done()
        ):
            return False

        row = await self.db.get_bot(
            bot_id
        )

        if not row:
            raise ValueError(
                'البوت غير موجود'
            )

        managed = ManagedBot(
            self,
            row
        )

        task = asyncio.create_task(
            managed.run(),
            name=f'bot-{bot_id}'
        )

        self.running[bot_id] = task
        self.instances[bot_id] = managed

        await self.db.set_enabled(
            bot_id,
            True
        )

        def cleanup(done_task):
            if self.running.get(bot_id) is done_task:
                self.running.pop(
                    bot_id,
                    None
                )

        task.add_done_callback(
            cleanup
        )

        return True

    async def stop_bot(self, bot_id):
        task = self.running.pop(
            bot_id,
            None
        )

        if task and not task.done():
            task.cancel()

            with suppress(asyncio.CancelledError):
                await task

        instance = self.instances.pop(
            bot_id,
            None
        )

        if instance:
            await instance.close()

        await self.db.set_enabled(
            bot_id,
            False
        )

    async def stop_all(self):
        for bot_id in list(self.running):
            await self.stop_bot(
                bot_id
            )

    def is_running(self, bot_id):
        task = self.running.get(
            bot_id
        )

        return bool(
            task
            and not task.done()
              )
