# -*- coding: utf-8 -*-
"""Проверка, что дерево виджетов main.py собирается без ошибок (mock-окно, без экрана)."""
import os
import sys

os.environ.setdefault('KIVY_NO_CONSOLELOG', '1')
os.environ.setdefault('KIVY_NO_ARGS', '1')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import main as M  # noqa: E402

w = M.MainLayout()
print('WIDGET_TREE_OK children=%d' % len(w.children))
print('BUTTONS_OK' if hasattr(w, 'btn_load') else 'BUTTONS_MISSING')
