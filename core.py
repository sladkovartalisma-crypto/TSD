# -*- coding: utf-8 -*-
"""
Ядро логики агрегации пива.
Формат строки агрегации: бутылка<TAB>коробка<TAB>паллета
"""
import os
from collections import defaultdict


class AggregationReport:
    def __init__(self, agg_file_path):
        self.agg_file_path = agg_file_path

        # bottle -> (box, pallet)
        self.bottle_to_box_pallet = {}
        # box -> set(bottles)
        self.box_to_bottles = defaultdict(set)
        # pallet -> set(boxes)
        self.pallet_to_boxes = defaultdict(set)

        # pallet -> set(boxes) — отсканированные
        self.scanned_boxes = defaultdict(set)
        # Глобальный набор отсканированных коробов (для варианта B)
        self.scanned_box_set = set()

        self._load_aggregation()

    # ---------- Загрузка ----------
    def _load_aggregation(self):
        if not os.path.exists(self.agg_file_path):
            raise FileNotFoundError(f"Файл агрегации не найден: {self.agg_file_path}")

        with open(self.agg_file_path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.rstrip('\n\r')
                if not line.strip():
                    continue
                parts = line.split('\t')
                if len(parts) < 3:
                    parts = line.split()
                if len(parts) < 3:
                    print(f"Предупреждение: строка {line_num} пропущена")
                    continue

                bottle = parts[0].strip()
                box = parts[1].strip()
                pallet = parts[2].strip()

                self.bottle_to_box_pallet[bottle] = (box, pallet)
                self.box_to_bottles[box].add(bottle)
                self.pallet_to_boxes[pallet].add(box)

    # ---------- Сканирование ----------
    def scan_pallet(self, pallet_code):
        """True, если паллета есть в агрегации."""
        return pallet_code in self.pallet_to_boxes

    def scan_box(self, pallet_code, box_code):
        """
        Возвращает (status, count):
          ('ok', bottles_count)   — короб добавлен
          ('already', None)       — уже сканировался (дубликат)
          ('not_in_pallet', None) — короб не относится к этой паллете
          ('unknown_box', None)   — короба нет в агрегации
        """
        if box_code not in self.box_to_bottles:
            return ('unknown_box', None)
        if box_code not in self.pallet_to_boxes.get(pallet_code, set()):
            return ('not_in_pallet', None)
        if box_code in self.scanned_boxes[pallet_code]:
            return ('already', None)  # ДУБЛИКАТ — в отчёт не добавляем

        self.scanned_boxes[pallet_code].add(box_code)
        self.scanned_box_set.add(box_code)
        return ('ok', len(self.box_to_bottles[box_code]))

    # ---------- Отчёт ----------
    def build_report(self):
        """Только отсканированные коробки."""
        lines = []
        for pallet in sorted(self.scanned_boxes):
            for box in sorted(self.scanned_boxes[pallet]):
                for bottle in sorted(self.box_to_bottles[box]):
                    lines.append(f"{bottle}\t{box}\t{pallet}")
        return lines

    # ---------- Бой (Вариант B: вся агрегация минус отсканированное) ----------
    def build_boi(self):
        lines = []
        for box in sorted(self.box_to_bottles):
            if box in self.scanned_box_set:
                continue
            bottles = sorted(self.box_to_bottles[box])
            pallet = self.bottle_to_box_pallet[bottles[0]][1]
            for bottle in bottles:
                lines.append(f"{bottle}\t{box}\t{pallet}")
        return lines

    # ---------- Сохранение ----------
    @staticmethod
    def _write_file(path, lines):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8', newline='\n') as f:
            for line in lines:
                f.write(line + '\n')

    def save_report(self, path):
        self._write_file(path, self.build_report())

    def save_boi(self, path):
        self._write_file(path, self.build_boi())

    # ---------- Статистика ----------
    def stats(self):
        total_pallets = len(self.pallet_to_boxes)
        total_boxes = len(self.box_to_bottles)
        total_bottles = len(self.bottle_to_box_pallet)

        scanned_boxes = len(self.scanned_box_set)
        scanned_bottles = sum(len(self.box_to_bottles[b]) for b in self.scanned_box_set)

        return {
            'pallets_total': total_pallets,
            'pallets_scanned': len(self.scanned_boxes),
            'boxes_total': total_boxes,
            'boxes_scanned': scanned_boxes,
            'boxes_boi': total_boxes - scanned_boxes,
            'bottles_total': total_bottles,
            'bottles_scanned': scanned_bottles,
            'bottles_boi': total_bottles - scanned_bottles,
        }