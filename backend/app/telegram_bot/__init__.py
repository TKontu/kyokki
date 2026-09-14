"""Private Telegram bot: share receipt files from the phone into Kyokki (MVP-T1).

Run with ``python -m app.telegram_bot``. The bot long-polls the Bot API, so the homelab needs
no open port. Only chats listed in ``TELEGRAM_ALLOWED_CHAT_IDS`` are served.
"""
