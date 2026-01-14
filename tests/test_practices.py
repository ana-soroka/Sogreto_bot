"""
Тесты для проверки загрузки и валидности практик
"""

import pytest
import json
import os


def test_practices_json_exists():
    """Проверка что файл practices.json существует"""
    practices_path = os.path.join(os.path.dirname(__file__), '..', 'practices.json')
    assert os.path.exists(practices_path), "practices.json не найден"


def test_practices_json_valid():
    """Проверка что practices.json валидный JSON"""
    practices_path = os.path.join(os.path.dirname(__file__), '..', 'practices.json')

    with open(practices_path, 'r', encoding='utf-8') as f:
        try:
            practices = json.load(f)
        except json.JSONDecodeError as e:
            pytest.fail(f"practices.json не валидный JSON: {e}")

    assert practices is not None


def test_practices_structure():
    """Проверка структуры practices.json"""
    practices_path = os.path.join(os.path.dirname(__file__), '..', 'practices.json')

    with open(practices_path, 'r', encoding='utf-8') as f:
        practices = json.load(f)

    # Проверка основных ключей
    assert 'practice_structure' in practices
    assert 'stages' in practices['practice_structure']

    stages = practices['practice_structure']['stages']
    assert len(stages) == 6, f"Ожидается 6 этапов, получено {len(stages)}"


def test_stage_names():
    """Проверка названий этапов"""
    practices_path = os.path.join(os.path.dirname(__file__), '..', 'practices.json')

    with open(practices_path, 'r', encoding='utf-8') as f:
        practices = json.load(f)

    stages = practices['practice_structure']['stages']
    expected_names = ['Посадка', 'Всходы', 'Практика до микрозелени',
                      'Первый урожай', 'До беби-лифа', 'Финал']

    stage_names = [stage['stage_name'] for stage in stages]

    for expected in expected_names:
        assert expected in stage_names, f"Этап '{expected}' не найден"


def test_all_steps_have_required_fields():
    """Проверка что все шаги содержат обязательные поля"""
    practices_path = os.path.join(os.path.dirname(__file__), '..', 'practices.json')

    with open(practices_path, 'r', encoding='utf-8') as f:
        practices = json.load(f)

    stages = practices['practice_structure']['stages']

    for stage in stages:
        if 'steps' in stage:
            for step in stage['steps']:
                # Обязательные поля
                assert 'step_id' in step, f"step_id отсутствует в шаге {step}"
                assert 'type' in step, f"type отсутствует в шаге {step}"
                assert 'message' in step, f"message отсутствует в шаге {step}"
                assert 'buttons' in step, f"buttons отсутствует в шаге {step}"


def test_buttons_structure():
    """Проверка что кнопки имеют правильную структуру"""
    practices_path = os.path.join(os.path.dirname(__file__), '..', 'practices.json')

    with open(practices_path, 'r', encoding='utf-8') as f:
        practices = json.load(f)

    stages = practices['practice_structure']['stages']

    for stage in stages:
        if 'steps' in stage:
            for step in stage['steps']:
                buttons = step.get('buttons', [])
                for button in buttons:
                    assert 'text' in button, f"Кнопка без текста в шаге {step['step_id']}"
                    assert 'action' in button, f"Кнопка без действия в шаге {step['step_id']}"


def test_examples_menu_exists():
    """Проверка что меню примеров существует"""
    practices_path = os.path.join(os.path.dirname(__file__), '..', 'practices.json')

    with open(practices_path, 'r', encoding='utf-8') as f:
        practices = json.load(f)

    assert 'examples_menu' in practices
    assert 'categories' in practices['examples_menu']
    assert len(practices['examples_menu']['categories']) == 4


def test_recipes_exist():
    """Проверка что рецепты существуют"""
    practices_path = os.path.join(os.path.dirname(__file__), '..', 'practices.json')

    with open(practices_path, 'r', encoding='utf-8') as f:
        practices = json.load(f)

    assert 'recipes' in practices
    assert 'items' in practices['recipes']
    assert len(practices['recipes']['items']) == 5


def test_manifesto_exists():
    """Проверка что манифест существует"""
    practices_path = os.path.join(os.path.dirname(__file__), '..', 'practices.json')

    with open(practices_path, 'r', encoding='utf-8') as f:
        practices = json.load(f)

    assert 'manifesto' in practices
    assert 'principles' in practices['manifesto']
    assert len(practices['manifesto']['principles']) == 5


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
