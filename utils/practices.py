"""
Утилиты для работы с practices.json
"""
import json
import os
import logging
from typing import Optional, Dict, List

logger = logging.getLogger(__name__)

PRACTICES_FILE = 'practices.json'


class PracticesManager:
    """Менеджер для работы с практиками"""

    def __init__(self, practices_file: str = PRACTICES_FILE):
        self.practices_file = practices_file
        self.data = None
        self.load_practices()

    def load_practices(self):
        """Загрузить practices.json"""
        try:
            with open(self.practices_file, 'r', encoding='utf-8') as f:
                self.data = json.load(f)
            logger.info(f"Практики загружены из {self.practices_file}")
        except FileNotFoundError:
            logger.error(f"Файл {self.practices_file} не найден!")
            raise
        except json.JSONDecodeError as e:
            logger.error(f"Ошибка парсинга JSON: {e}")
            raise

    def get_stage(self, stage_id: int) -> Optional[Dict]:
        """
        Получить этап по ID

        Args:
            stage_id: ID этапа (1-6)

        Returns:
            Dict с данными этапа или None
        """
        stages = self.data.get('practice_structure', {}).get('stages', [])
        for stage in stages:
            if stage.get('stage_id') == stage_id:
                return stage
        return None

    def get_step(self, stage_id: int, step_id: int) -> Optional[Dict]:
        """
        Получить конкретный шаг практики

        Args:
            stage_id: ID этапа
            step_id: ID шага

        Returns:
            Dict с данными шага или None
        """
        stage = self.get_stage(stage_id)
        if not stage:
            return None

        steps = stage.get('steps', [])
        for step in steps:
            if step.get('step_id') == step_id:
                return step
        return None

    def get_next_step(self, current_stage: int, current_step: int) -> Optional[Dict]:
        """
        Получить следующий шаг

        Args:
            current_stage: Текущий этап
            current_step: Текущий шаг

        Returns:
            Dict: {'stage_id': int, 'step_id': int, 'step_data': Dict} или None если практики закончились
        """
        stage = self.get_stage(current_stage)
        if not stage:
            return None

        steps = stage.get('steps', [])

        # Найти текущий шаг и взять следующий
        for i, step in enumerate(steps):
            if step.get('step_id') == current_step:
                # Если есть следующий шаг в текущем этапе
                if i + 1 < len(steps):
                    next_step = steps[i + 1]
                    return {
                        'stage_id': current_stage,
                        'step_id': next_step['step_id'],
                        'step_data': next_step
                    }
                else:
                    # Перейти к следующему этапу
                    next_stage = self.get_stage(current_stage + 1)
                    if next_stage and next_stage.get('steps'):
                        first_step = next_stage['steps'][0]
                        return {
                            'stage_id': current_stage + 1,
                            'step_id': first_step['step_id'],
                            'step_data': first_step
                        }

        return None

    def get_examples_menu(self) -> Dict:
        """Получить меню с примерами желаний"""
        return self.data.get('examples_menu', {})

    def get_recipes(self) -> Dict:
        """Получить рецепты"""
        return self.data.get('recipes', {})

    def get_manifesto(self) -> Dict:
        """Получить манифест"""
        return self.data.get('manifesto', {})

    def get_schedule(self) -> Dict:
        """Получить информацию о расписании"""
        return self.data.get('schedule', {})

    def get_replant_scenario(self) -> Optional[Dict]:
        """Получить сценарий 'Салат не взошёл'"""
        return self.data.get('replant_scenario')

    def get_mold_scenario(self) -> Optional[Dict]:
        """Получить сценарий 'Плесень'"""
        return self.data.get('mold_scenario')

    def get_mold_sprouts_scenario(self) -> Optional[Dict]:
        """Получить сценарий 'Плесень' для ростков на воздухе"""
        return self.data.get('mold_scenario_sprouts')

    def get_all_dead_scenario(self) -> Optional[Dict]:
        """Получить сценарий 'Всё погибло'"""
        return self.data.get('all_dead_scenario')

    def get_total_stages(self) -> int:
        """Получить общее количество этапов"""
        stages = self.data.get('practice_structure', {}).get('stages', [])
        return len(stages)

    def get_stage_day(self, stage_id: int) -> Optional[int]:
        """
        Получить день, в который выполняется этап

        Args:
            stage_id: ID этапа

        Returns:
            int: День или None
        """
        stage = self.get_stage(stage_id)
        if stage:
            return stage.get('day')
        return None

    def format_step_message(self, step_data: Dict) -> str:
        """
        Отформатировать сообщение шага для отправки пользователю

        Args:
            step_data: Данные шага

        Returns:
            str: Отформатированное сообщение
        """
        message = step_data.get('message', '')
        title = step_data.get('title')

        if title:
            return f"**{title}**\n\n{message}"
        return message

    def get_step_buttons(self, step_data: Dict) -> List[Dict]:
        """
        Получить кнопки для шага

        Args:
            step_data: Данные шага

        Returns:
            List[Dict]: Список кнопок с полями 'text' и 'action'
        """
        return step_data.get('buttons', [])


# Глобальный экземпляр менеджера практик
practices_manager = PracticesManager()
