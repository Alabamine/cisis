"""
CISIS — View для авторизации через workspace.

Файл: core/views/auth_views.py
"""

from django.shortcuts import render, redirect
from django.contrib.auth import login

from core.models import User


def workspace_login(request):
    """Страница входа в систему."""
    if request.user.is_authenticated:
        return redirect('/workspace/')

    error = None
    username = ''

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        next_url = request.POST.get('next', '/workspace/')

        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            user = None

        if user and user.check_password(password):
            if not user.is_active:
                error = 'Учётная запись деактивирована. Обратитесь к администратору.'
            else:
                login(request, user, backend='core.auth_backend.CustomUserBackend')
                return redirect(next_url or '/workspace/')
        else:
            error = 'Неверный логин или пароль.'

    return render(request, 'core/login.html', {
        'error': error,
        'username': username,
        'next': request.GET.get('next', '/workspace/'),
    })
