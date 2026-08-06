from aiogram.fsm.state import State, StatesGroup


class RedeemStates(StatesGroup):
    awaiting_amount = State()


class SettingsStates(StatesGroup):
    awaiting_name = State()
