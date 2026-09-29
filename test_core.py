# -*- coding: utf-8 -*-
"""Тест логики агрегации без экрана (запуск на ПК)."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core import AggregationReport


def make_agg(tmp):
    """Создаём тестовый файл агрегации: 2 паллеты x 3 короба x 2 бутылки."""
    p = os.path.join(tmp, 'agg.txt')
    rows = []
    for pidx, pallet in enumerate(('PAL1', 'PAL2')):
        for bidx in range(3):
            box = f'{pallet}_BOX{bidx}'
            for bottle_idx in range(2):
                bottle = f'B{pidx}{bidx}{bottle_idx}'
                rows.append(f'{bottle}\t{box}\t{pallet}')
    with open(p, 'w', encoding='utf-8', newline='\n') as f:
        f.write('\n'.join(rows) + '\n')
    return p


def run():
    tmp = tempfile.mkdtemp()
    agg = make_agg(tmp)
    rep = AggregationReport(agg)

    s = rep.stats()
    assert s['pallets_total'] == 2, s
    assert s['boxes_total'] == 6, s
    assert s['bottles_total'] == 12, s

    # Открываем паллету
    assert rep.scan_pallet('PAL1') is True
    assert rep.scan_pallet('NOPE') is False

    # Сканируем короб
    status, count = rep.scan_box('PAL1', 'PAL1_BOX0')
    assert status == 'ok' and count == 2, (status, count)

    # Дубликат
    status, count = rep.scan_box('PAL1', 'PAL1_BOX0')
    assert status == 'already', status

    # Короб чужой паллеты
    status, count = rep.scan_box('PAL1', 'PAL2_BOX1')
    assert status == 'not_in_pallet', status

    # Неизвестный короб
    status, count = rep.scan_box('PAL1', 'XXX')
    assert status == 'unknown_box', status

    # Второй короб этой паллеты
    status, count = rep.scan_box('PAL1', 'PAL1_BOX1')
    assert status == 'ok' and count == 2, (status, count)

    s = rep.stats()
    assert s['boxes_scanned'] == 2, s
    assert s['bottles_scanned'] == 4, s

    # Отчёт: только отсканированное
    report_lines = rep.build_report()
    assert len(report_lines) == 4, report_lines

    # Бой: вся агрегация минус отсканированное
    boi_lines = rep.build_boi()
    assert len(boi_lines) == 8, boi_lines
    assert 'PAL1_BOX0' not in ' '.join(boi_lines), 'BOX0 должен быть в отчёте, не в бое'

    # Сброс паллеты
    for box in rep.scanned_boxes['PAL1']:
        rep.scanned_box_set.discard(box)
    rep.scanned_boxes['PAL1'] = set()

    s = rep.stats()
    assert s['boxes_scanned'] == 0, s
    assert s['bottles_scanned'] == 0, s
    boi_lines = rep.build_boi()
    assert len(boi_lines) == 12, boi_lines

    # Сохранение
    out = os.path.join(tmp, 'report')
    os.makedirs(out, exist_ok=True)
    rp = os.path.join(out, 'report.txt')
    bp = os.path.join(out, 'boi.txt')
    rep.save_report(rp)
    rep.save_boi(bp)
    assert os.path.isfile(rp) and os.path.isfile(bp)
    with open(rp, encoding='utf-8') as f:
        assert sum(1 for _ in f) == 0  # после сброса пусто
    with open(bp, encoding='utf-8') as f:
        assert sum(1 for _ in f) == 12

    print('All logic checks passed OK')
    print('  pallets: %d, boxes: %d, bottles: %d' % (
        s['pallets_total'], s['boxes_total'], s['bottles_total']))


if __name__ == '__main__':
    run()
