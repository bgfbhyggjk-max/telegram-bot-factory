from aiogram.fsm.state import State, StatesGroup


class FactoryCreate(StatesGroup):
    token = State()
    owner_id = State()


class FactorySelectBot(StatesGroup):
    bot_id = State()


class BotBroadcast(StatesGroup):
    target = State()
    chats = State()
    content = State()


class BotWelcome(StatesGroup):
    content = State()


class BotAllowedChat(StatesGroup):
    add_chat_id = State()
    delete_chat_id = State()
