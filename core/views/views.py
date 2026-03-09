"""
CISIS v3.16.0 — Общие views (главная страница, logout).

Файл: core/views/views.py
Действие: ПОЛНАЯ ЗАМЕНА файла

Изменения:
- Доступ к карточкам через PermissionChecker.has_journal_access()
- Убран хардкод ролей (if user.role in (...))
- Конфигурация отображения (иконка, URL, описание) осталась в коде
- Доступ управляется через /permissions/ (journals + role_permissions)
"""

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth import logout

from core.permissions import PermissionChecker


# Конфигурация карточек: отображение + привязка к журналу
WORKSPACE_CARDS = [
    {
        'journal_code': 'SAMPLES',
        'name': 'Журнал образцов',
        'icon': '🧪',
        'description': 'Регистрация и учёт образцов для испытаний',
        'url': 'journal_samples',
        'url_type': 'name',          # {% url ... %}
    },
    {
        'journal_code': 'LABELS',
        'requires_column': 'access',
        'name': 'Генератор этикеток',
        'icon': '🏷️',
        'description': 'Печать этикеток для образцов',
        'url': 'labels_page',
        'url_type': 'name',
    },
    {
        'journal_code': 'AUDIT_LOG',
        'requires_column': 'access',
        'name': 'Журнал аудита',
        'icon': '📋',
        'description': 'Все действия пользователей в системе',
        'url': 'audit_log',
        'url_type': 'name',
    },
    {
        'journal_code': 'CLIENTS',
        'requires_column': 'access',
        'name': 'Заказчики и договоры',
        'icon': '🏢',
        'description': 'Управление заказчиками и их договорами',
        'url': 'directory_clients',
        'url_type': 'name',
    },

    {
        'name': 'Файловый менеджер',
        'icon': '📁',
        'url': 'file_manager',
        'description': 'Просмотр и поиск файлов по категориям',
        'journal_code': 'FILES',
        'requires_column': 'equipment_files',
    },

    {
        'name': 'Справочник стандартов',  # было 'Показатели стандартов'
        'icon': '📚',  # было '📊'
        'url': 'standards_list',  # было 'standards_parameters_list'
        'description': 'Стандарты и определяемые показатели',
        'journal_code': 'SAMPLES',
        'requires_column': 'parameters_management',
    },

    {
        'code': 'EMPLOYEES',
        'name': 'Справочник сотрудников',
        'icon': '👥',
        'description': 'Управление сотрудниками',
        'url': 'employees',
        'journal_code': 'EMPLOYEES',
    },

    {
        'name': 'Аналитика',
        'icon': '📊',
        'url': 'analytics',
        'description': 'Статистика по центру',
        'journal_code': 'ANALYTICS',
        'requires_column': 'access'
    },

    {
        'name': 'Реестр оборудования',
        'icon': '🔬',
        'url': 'equipment_list',
        'description': 'Справочник оборудования лабораторий',
        'journal_code': 'EQUIPMENT',
        'requires_column': 'access',
    },
]


@login_required
def workspace_home(request):
    """Главная страница рабочего пространства с доступными разделами."""

    user = request.user
    available = []

    for card in WORKSPACE_CARDS:
        # Проверка доступа к журналу
        if not PermissionChecker.has_journal_access(user, card['journal_code']):
            continue

        # Доп. проверка столбца (напр. labels_access)
        requires_col = card.get('requires_column')
        if requires_col:
            if not PermissionChecker.can_view(user, card['journal_code'], requires_col):
                continue

        available.append({
            'name': card['name'],
            'icon': card['icon'],
            'description': card['description'],
            'url': card['url'],
            'url_type': card.get('url_type', 'name'),  # ← добавить эту строку
        })

        # SYSADMIN: карточка для доступа к Django Admin
    if user.role == 'SYSADMIN':
        available.append({
            'name': 'Django Admin',
            'icon': '⚙️',
            'description': 'Панель администратора',
            'url': '/admin/',
            'url_type': 'path',
        })

    return render(request, 'core/workspace_home.html', {
        'journals': available,
        'user': user,
    })


@login_required
def logout_view(request):
    """Выход из системы."""
    logout(request)
    return redirect('/workspace')