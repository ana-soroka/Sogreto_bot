"""
Адаптер клавиатур: practices.json кнопки → VK Keyboard JSON.
"""
import json


def create_vk_inline_keyboard(buttons_data: list) -> str:
    """
    Конвертировать кнопки из practices.json в VK inline keyboard JSON.

    Input: [{"text": "Текст кнопки", "action": "callback_data"}, ...]
    Output: VK Keyboard JSON string
    """
    buttons = []
    for btn in buttons_data:
        buttons.append([{
            "action": {
                "type": "callback",
                "label": btn.get("text", "Продолжить")[:40],  # VK лимит 40 символов
                "payload": json.dumps({"action": btn.get("action", "unknown")})
            }
        }])

    keyboard = {
        "inline": True,
        "buttons": buttons
    }
    return json.dumps(keyboard, ensure_ascii=False)


def create_vk_menu_keyboard() -> str:
    """Создать постоянную клавиатуру с кнопкой Меню (аналог ReplyKeyboardMarkup)."""
    keyboard = {
        "one_time": False,
        "buttons": [[{
            "action": {
                "type": "text",
                "label": "Меню"
            },
            "color": "primary"
        }]]
    }
    return json.dumps(keyboard, ensure_ascii=False)


def create_vk_callback_keyboard(buttons: list) -> str:
    """
    Создать inline-клавиатуру из списка кортежей (text, action).

    Input: [("Текст", "callback_data"), ...]
    """
    kb_buttons = []
    for text, action in buttons:
        kb_buttons.append([{
            "action": {
                "type": "callback",
                "label": text[:40],
                "payload": json.dumps({"action": action})
            }
        }])

    keyboard = {
        "inline": True,
        "buttons": kb_buttons
    }
    return json.dumps(keyboard, ensure_ascii=False)
