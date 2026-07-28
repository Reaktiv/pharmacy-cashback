"""Builds a per-tenant aiogram Bot instance (CLAUDE.md §7a multibot: one
process, many tokens). Never construct aiogram.Bot with a raw token
elsewhere — always go through here so decryption stays in one place."""

from aiogram import Bot as AiogramBot

from apps.tenants.models import Bot as BotRow


def build_client(bot_row: BotRow) -> AiogramBot:
    return AiogramBot(token=bot_row.get_token())
