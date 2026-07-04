from aiogram.fsm.state import State, StatesGroup


class GroupCreation(StatesGroup):
    waiting_usernames = State()


class MediaProposal(StatesGroup):
    waiting_title = State()


class AddMember(StatesGroup):
    waiting_username = State()
