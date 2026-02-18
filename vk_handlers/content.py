"""
VK обработчики: примеры, рецепты, манифест, контакты
"""
import logging
from utils import practices_manager
from utils.formatting import markdown_to_plain

logger = logging.getLogger(__name__)


async def vk_examples_command(api, peer_id):
    """Показать примеры желаний"""
    examples = practices_manager.get_examples_menu()

    message = "Примеры желаний 🎯\n\n"

    for category_key, category_data in examples.items():
        if isinstance(category_data, dict) and 'title' in category_data:
            message += f"{category_data['title']}\n"
            items = category_data.get('items', [])
            for item in items:
                message += f"• {item}\n"
            message += "\n"

    message += "Используй эти примеры как вдохновение для своих практик! 💡"

    await api.messages.send(
        peer_id=peer_id,
        message=markdown_to_plain(message),
        random_id=0
    )


async def vk_recipes_command(api, peer_id):
    """Показать рецепты"""
    recipes = practices_manager.get_recipes()

    message = "Рецепты с микрозеленью 🥗\n\n"

    recipes_list = recipes.get('recipes_list', [])
    for i, recipe in enumerate(recipes_list, 1):
        message += f"{i}. {recipe.get('name', 'Рецепт')}\n"
        message += f"{recipe.get('description', '')}\n\n"

    message += "Приятного аппетита! 🌿"

    await api.messages.send(
        peer_id=peer_id,
        message=markdown_to_plain(message),
        random_id=0
    )


async def vk_manifesto_command(api, peer_id):
    """Показать манифест"""
    manifesto = practices_manager.get_manifesto()

    message = "Манифест предвкушения ✨\n\n"

    intro = manifesto.get('intro', '')
    if intro:
        message += f"{intro}\n\n"

    principles = manifesto.get('principles', [])
    for i, principle in enumerate(principles, 1):
        message += f"{i}. {principle}\n\n"

    outro = manifesto.get('outro', '')
    if outro:
        message += f"{outro}\n"

    await api.messages.send(
        peer_id=peer_id,
        message=markdown_to_plain(message),
        random_id=0
    )


async def vk_contact_command(api, peer_id):
    """Показать контакты поддержки"""
    await api.messages.send(
        peer_id=peer_id,
        message=(
            "Поддержка Sogreto Bot 💚\n\n"
            "По всем вопросам пишите:\n"
            "💬 Telegram: @sogreto_support\n\n"
            "Мы ответим в течение 24 часов."
        ),
        random_id=0
    )
