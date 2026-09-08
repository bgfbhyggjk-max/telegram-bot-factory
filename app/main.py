import asyncio
import logging
from contextlib import suppress

from aiogram import Bot, Dispatcher, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from app.config import load_settings
from app.db import Database
from app.keyboards import factory_main
from app.services.bot_manager import BotManager
from app.states import FactoryCreate, FactorySelectBot

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)

log = logging.getLogger("factory")

settings = load_settings()
db = Database(settings.database_path)
manager = BotManager(db, settings.broadcast_delay)

factory_bot = Bot(
    settings.factory_bot_token,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)

dp = Dispatcher()
router = Router()
dp.include_router(router)


def is_owner(user_id: int) -> bool:
    return user_id == settings.factory_owner_id


def allowed(event) -> bool:
    return bool(event.from_user and is_owner(event.from_user.id))


@router.message(CommandStart())
async def start(message: Message):
    if not is_owner(message.from_user.id):
        return await message.answer(
            "❌ غير مصرح لك باستخدام مصنع البوتات."
        )

    await message.answer(
        "🏭 <b>مصنع البوتات</b>\n\n"
        "اختر من لوحة التحكم:",
        reply_markup=factory_main()
    )


@router.callback_query(lambda c: c.data == "f:create")
async def create_start(call: CallbackQuery, state: FSMContext):
    if not allowed(call):
        return await call.answer("غير مصرح", show_alert=True)

    await state.set_state(FactoryCreate.token)

    await call.message.answer(
        "🤖 أرسل Token البوت من BotFather:"
    )

    await call.answer()


@router.message(FactoryCreate.token)
async def create_token(message: Message, state: FSMContext):
    if not is_owner(message.from_user.id):
        return

    token = (message.text or "").strip()

    if ":" not in token or len(token) < 20:
        return await message.answer(
            "❌ صيغة Token غير صحيحة."
        )

    test_bot = None

    try:
        test_bot = Bot(token)
        me = await test_bot.get_me()

    except Exception as e:
        return await message.answer(
            f"❌ لم أستطع التحقق من Token:\n{e}"
        )

    finally:
        if test_bot:
            with suppress(Exception):
                await test_bot.session.close()

    if await db.get_bot(me.id):
        return await message.answer(
            "⚠️ هذا البوت موجود بالفعل."
        )

    await state.update_data(
        token=token,
        bot_id=me.id,
        username=me.username,
        first_name=me.first_name
    )

    await state.set_state(FactoryCreate.owner_id)

    await message.answer(
        f"✅ تم التحقق من @{me.username or me.first_name}.\n\n"
        "أرسل Telegram ID لمالك البوت المصنوع:"
    )


@router.message(FactoryCreate.owner_id)
async def create_owner(message: Message, state: FSMContext):
    if not is_owner(message.from_user.id):
        return

    try:
        owner_id = int((message.text or "").strip())

    except ValueError:
        return await message.answer(
            "❌ Telegram ID يجب أن يكون رقماً."
        )

    data = await state.get_data()

    try:
        await db.add_bot(
            data["token"],
            data["bot_id"],
            data.get("username"),
            owner_id,
            data.get("first_name")
        )

        await state.clear()

        await manager.start_bot(data["bot_id"])

        await message.answer(
            f"🎉 تم إنشاء البوت بنجاح.\n"
            f"🤖 @{data.get('username') or data.get('first_name')}\n"
            f"👤 المالك: <code>{owner_id}</code>\n"
            "🟢 تم تشغيله.",
            reply_markup=factory_main()
        )

        with suppress(Exception):
            await factory_bot.send_message(
                owner_id,
                "🎉 تم تجهيز بوتك. "
                "أرسل /start للبوت لفتح لوحة التحكم الخاصة بك."
            )

    except Exception as e:
        await state.clear()

        await message.answer(
            f"❌ تعذر إنشاء البوت: {e}"
        )


async def select_bot(
    call: CallbackQuery,
    state: FSMContext,
    action: str
):
    if not allowed(call):
        return await call.answer(
            "غير مصرح",
            show_alert=True
        )

    rows = await db.get_bots()

    if not rows:
        return await call.answer(
            "لا توجد بوتات.",
            show_alert=True
        )

    await state.set_state(
        FactorySelectBot.bot_id
    )

    await state.update_data(
        action=action
    )

    await call.message.answer(
        "أرسل Bot ID:\n\n"
        + "\n".join(
            f"• {r['bot_id']} — "
            f"@{r['username'] or r['first_name']}"
            for r in rows
        )
    )

    await call.answer()


for action, callback in (
    ("start", "f:start"),
    ("stop", "f:stop"),
    ("delete", "f:delete"),
    ("info", "f:info")
):

    async def handler(
        call: CallbackQuery,
        state: FSMContext,
        _action=action
    ):
        await select_bot(
            call,
            state,
            _action
        )

    router.callback_query(
        lambda c, cb=callback:
        c.data == cb
    )(handler)


@router.callback_query(
    lambda c: c.data == "f:list"
)
async def bot_list(call: CallbackQuery):
    if not allowed(call):
        return await call.answer(
            "غير مصرح",
            show_alert=True
        )

    rows = await db.get_bots()

    if not rows:
        text = "🤖 لا توجد بوتات مصنوعة."

    else:
        text = (
            "🤖 <b>البوتات المصنوعة</b>\n\n"
            + "\n".join(
                f"{'🟢' if manager.is_running(r['bot_id']) else '🔴'} "
                f"@{r['username'] or r['first_name']} "
                f"— المالك {r['owner_id']}"
                for r in rows
            )
        )

    await call.message.edit_text(
        text,
        reply_markup=factory_main()
    )

    await call.answer()


@router.message(
    FactorySelectBot.bot_id
)
async def selected_bot(
    message: Message,
    state: FSMContext
):
    if not is_owner(message.from_user.id):
        return

    try:
        bot_id = int(
            (message.text or "").strip()
        )

    except ValueError:
        return await message.answer(
            "❌ Bot ID غير صحيح."
        )

    data = await state.get_data()
    action = data.get("action")

    await state.clear()

    row = await db.get_bot(bot_id)

    if not row:
        return await message.answer(
            "❌ البوت غير موجود."
        )

    if action == "start":
        await manager.start_bot(bot_id)
        text = "🟢 تم تشغيل البوت."

    elif action == "stop":
        await manager.stop_bot(bot_id)
        text = "🔴 تم إيقاف البوت."

    elif action == "delete":
        await manager.stop_bot(bot_id)
        await db.delete_bot(bot_id)
        text = "🗑 تم حذف البوت."

    else:
        status = (
            "🟢 يعمل"
            if manager.is_running(bot_id)
            else "🔴 متوقف"
        )

        text = (
            f"ℹ️ ID: <code>{row['bot_id']}</code>\n"
            f"Username: @{row['username'] or '-'}\n"
            f"المالك: <code>{row['owner_id']}</code>\n"
            f"الحالة: {status}\n"
            f"تاريخ الإضافة: {row['created_at']}"
        )

    await message.answer(
        text,
        reply_markup=factory_main()
    )


@router.callback_query(
    lambda c: c.data == "f:refresh"
)
async def refresh(call: CallbackQuery):
    if not allowed(call):
        return await call.answer(
            "غير مصرح",
            show_alert=True
        )

    started = 0

    for r in await db.get_bots():

        if (
            r["enabled"]
            and not manager.is_running(r["bot_id"])
        ):

            try:
                await manager.start_bot(
                    r["bot_id"]
                )

                started += 1

            except Exception:
                log.exception(
                    "Could not start bot %s",
                    r["bot_id"]
                )

    await call.answer(
        f"تم تشغيل {started} بوت.",
        show_alert=True
    )


async def main():

    await db.init()

    for r in await db.get_bots():

        if r["enabled"]:

            try:
                await manager.start_bot(
                    r["bot_id"]
                )

            except Exception:
                log.exception(
                    "Failed to restore bot %s",
                    r["bot_id"]
                )

    try:

        await factory_bot.delete_webhook(
            drop_pending_updates=False
        )

        await dp.start_polling(
            factory_bot
        )

    finally:

        await manager.stop_all()

        await factory_bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
