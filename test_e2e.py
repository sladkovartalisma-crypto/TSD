# -*- coding: utf-8 -*-
"""
Сквозной тест: прогон сценариев сканирования через реальный код MainLayout.
Проверяет загрузку агрегации, скан паллеты, коробов, дубликатов, боя и отчётов.
"""
import os
import sys
import tempfile

os.environ.setdefault('KIVY_NO_CONSOLELOG', '1')
os.environ.setdefault('KIVY_NO_ARGS', '1')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import main as M  # noqa: E402


class FakeInput:
    """Имитация поля ввода: сканер «печатает» код и жмёт Enter."""
    def __init__(self):
        self.text = ''


def make_agg(path):
    """2 паллеты x 3 короба x 2 бутылки."""
    rows = []
    for pidx, pallet in enumerate(('PAL_A', 'PAL_B')):
        for bidx in range(3):
            box = '%s-BOX%d' % (pallet, bidx)
            for bottle_idx in range(2):
                rows.append('B%d%d%d\t%s\t%s' % (pidx, bidx, bottle_idx, box, pallet))
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write('\n'.join(rows) + '\n')


def scan(w, code):
    """Прогон одной операции сканирования через on_scan()."""
    inp = FakeInput()
    inp.text = code
    w.on_scan(inp)
    return w.log_lines[-1]


def main():
    tmp = tempfile.mkdtemp()
    agg = os.path.join(tmp, 'agg.txt')
    make_agg(agg)

    w = M.MainLayout()

    # 1. До загрузки агрегации — ошибка
    msg = scan(w, 'PAL_A')
    assert 'Сначала загрузите' in msg, msg

    # 2. Загрузка агрегации
    w._load_from_path(agg)
    assert w.report_logic is not None
    assert w.title.text == 'Сканируйте паллету', w.title.text

    # 3. Открытие паллеты
    msg = scan(w, 'PAL_A')
    assert 'Паллета' in msg and 'не найдена' not in msg, msg
    assert w.current_pallet == 'PAL_A', w.current_pallet

    # 4. Неизвестная паллета
    w.current_pallet = None
    msg = scan(w, 'GHOST')
    assert 'не найдена' in msg, msg

    # 5. Открываем PAL_A заново
    msg = scan(w, 'PAL_A')
    assert w.current_pallet == 'PAL_A', msg

    # 6. Скан коробов
    msg = scan(w, 'PAL_A-BOX0')
    assert '2 бут' in msg, msg
    msg = scan(w, 'PAL_A-BOX1')
    assert '2 бут' in msg, msg

    # 7. Прогресс
    w.update_progress()
    assert '2 из 3' in w.progress_label.text, w.progress_label.text
    assert 66 < w.progress_bar.value < 67, w.progress_bar.value

    # 8. Дубликат
    msg = scan(w, 'PAL_A-BOX0')
    assert 'УЖЕ' in msg, msg

    # 9. Короб чужой паллеты
    msg = scan(w, 'PAL_B-BOX1')
    assert 'не относится' in msg, msg

    # 10. Несуществующий короб
    msg = scan(w, 'NOPE')
    assert 'отсутствует' in msg, msg

    # 11. Закрытие паллеты
    w.close_pallet()
    assert w.current_pallet is None
    assert 'не открыта' in w.progress_label.text

    # 12. Вторая паллета полностью
    scan(w, 'PAL_B')
    for i in range(3):
        scan(w, 'PAL_B-BOX%d' % i)
    w.update_progress()
    assert '3 из 3' in w.progress_label.text, w.progress_label.text
    assert w.progress_bar.value == 100.0, w.progress_bar.value

    # 13. Сброс паллеты (эмуляция подтверждения)
    w.current_pallet = 'PAL_B'
    boxes = w.report_logic.scanned_boxes.get('PAL_B', set())
    for box in boxes:
        w.report_logic.scanned_box_set.discard(box)
    w.report_logic.scanned_boxes['PAL_B'] = set()
    w.update_progress()
    assert '0 из 3' in w.progress_label.text, w.progress_label.text
    assert w.progress_bar.value == 0.0

    # 14. Формирование отчётов
    total_boxes = len(w.report_logic.box_to_bottles)          # 6
    total_bottles = len(w.report_logic.bottle_to_box_pallet)  # 12
    w.report_logic.scanned_boxes['PAL_A'] = {'PAL_A-BOX0', 'PAL_A-BOX1'}
    w.report_logic.scanned_box_set = {'PAL_A-BOX0', 'PAL_A-BOX1'}
    report_lines = w.report_logic.build_report()
    boi_lines = w.report_logic.build_boi()
    assert len(report_lines) == 4, len(report_lines)
    assert len(boi_lines) == total_bottles - 4, len(boi_lines)
    s = w.report_logic.stats()
    assert s['boxes_scanned'] == 2 and s['boxes_boi'] == total_boxes - 2, s
    assert s['bottles_boi'] == total_bottles - 4, s

    print('E2E OK: все сценарии сканирования прошли')
    print('  итог: коробов %d/%d, бутылок %d/%d, бой %d бут.' % (
        s['boxes_scanned'], s['boxes_total'],
        s['bottles_scanned'], s['bottles_total'], s['bottles_boi']))


if __name__ == '__main__':
    main()
