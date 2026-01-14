"""
Обработчики команд контента:
/examples, /recipes, /manifesto, /contact
"""
import logging
from telegram import Update
from telegram.ext import ContextTypes
from utils import error_handler, practices_manager

logger = logging.getLogger(__name__)


@error_handler
async def examples_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /examples - примеры желаний"""
    examples = practices_manager.get_examples_menu()

    message = "**Примеры желаний** 🎯\n\n"

    for category_key, category_data in examples.items():
        if isinstance(category_data, dict) and 'title' in category_data:
            message += f"**{category_data['title']}**\n"
            items = category_data.get('items', [])
            for item in items:
                message += f"• {item}\n"
            message += "\n"

    message += "Используй эти примеры как вдохновение для своих практик! 💡"

    await update.message.reply_text(message)


@error_handler
async def recipes_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /recipes - рецепты"""
    recipes = practices_manager.get_recipes()

    message = "**Рецепты с микрозеленью** 🥗\n\n"

    recipes_list = recipes.get('recipes_list', [])
    for i, recipe in enumerate(recipes_list, 1):
        message += f"**{i}. {recipe.get('name', 'Рецепт')}**\n"
        message += f"{recipe.get('description', '')}\n\n"

    message += "Приятного аппетита! 🌿"

    await update.message.reply_text(message)


@error_handler
async def manifesto_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /manifesto - манифест"""
    manifesto = practices_manager.get_manifesto()

    message = "**Манифест предвкушения** ✨\n\n"

    intro = manifesto.get('intro', '')
    if intro:
        message += f"{intro}\n\n"

    principles = manifesto.get('principles', [])
    for i, principle in enumerate(principles, 1):
        message += f"{i}. {principle}\n\n"

    outro = manifesto.get('outro', '')
    if outro:
        message += f"{outro}\n"

    await update.message.reply_text(message)


@error_handler
async def contact_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /contact"""
    contact_message = (
        "**Поддержка Sogreto Bot** 💚\n\n"
        "По всем вопросам пишите:\n"
        "📧 Email: support@sogreto.com\n"
        "💬 Telegram: @sogreto_support\n\n"
        "Мы ответим в течение 24 часов."
    )

    await update.message.reply_text(contact_message)
