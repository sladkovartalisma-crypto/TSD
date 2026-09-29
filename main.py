# -*- coding: utf-8 -*-
"""
Приложение для ТСД АТОЛ Smart M20 (Android + Kivy).
Сканирование паллет и коробов пива.
С звуковым и визуальным сопровождением.
С прогрессом по паллете, показом последнего короба, сбросом паллеты и вибрацией.

Ввод ШК идёт с аппаратного 2D-сканера ТСД через режим USB HID Keyboard:
сканер «печатает» код как текст в поле ввода.
"""
import os
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.filechooser import FileChooserListView
from kivy.uix.progressbar import ProgressBar
from kivy.core.window import Window
from kivy.clock import Clock
from kivy.utils import platform
from kivy.graphics import Color, Rectangle
from kivy.metrics import dp

from core import AggregationReport

# ---------- Пути ----------
APP_DIR = os.path.dirname(os.path.abspath(__file__))
SOUNDS_DIR = os.path.join(APP_DIR, 'sounds')
SOUND_OK = os.path.join(SOUNDS_DIR, 'beep_ok.wav')
SOUND_ERR = os.path.join(SOUNDS_DIR, 'beep_err.wav')

if platform == 'android':
    try:
        from android.storage import primary_external_storage_path
        EXTERNAL_DIR = os.path.join(
            primary_external_storage_path(), 'Download', 'BeerAggregation'
        )
    except Exception:
        EXTERNAL_DIR = '/sdcard/Download/BeerAggregation'
else:
    EXTERNAL_DIR = os.path.join(APP_DIR, 'output')

REPORT_NAME = 'report.txt'
BOI_NAME = 'boi.txt'
REPORT_SUBDIR = 'report'


# ---------- Разрешения Android ----------
def request_android_permissions():
    """Запрашивает доступ к памяти и «Все файлы» (Android 11+)."""
    if platform != 'android':
        return
    try:
        from android.permissions import request_permissions, Permission
        request_permissions([
            Permission.READ_EXTERNAL_STORAGE,
            Permission.WRITE_EXTERNAL_STORAGE,
        ])
    except Exception as e:
        print(f'Разрешения не запрошены: {e}')


def has_all_files_access():
    """True, если выдано разрешение «Доступ ко всем файлам»."""
    if platform != 'android':
        return True
    try:
        from jnius import autoclass
        Environment = autoclass('android.os.Environment')
        return bool(Environment.isExternalStorageManager())
    except Exception as e:
        print(f'Проверка доступа к файлам не удалась: {e}')
        return False


def open_all_files_settings():
    """Открывает системный экран выдачи «Доступа ко всем файлам»."""
    if platform != 'android':
        return
    try:
        from jnius import autoclass
        Intent = autoclass('android.content.Intent')
        Settings = autoclass('android.provider.Settings')
        Uri = autoclass('android.net.Uri')
        PythonActivity = autoclass('org.kivy.android.PythonActivity')

        activity = PythonActivity.mActivity
        pkg = activity.getPackageName()
        intent = Intent(Settings.ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION)
        intent.setData(Uri.parse('package:' + pkg))
        activity.startActivity(intent)
    except Exception as e:
        print(f'Не удалось открыть настройки доступа: {e}')

# ---------- Вибрация (только Android) ----------
_VIBRATE_ENABLED = False
_vibrator = None
if platform == 'android':
    try:
        from plyer import vibrator as _vibrator_module
        _vibrator = _vibrator_module
        _VIBRATE_ENABLED = True
    except Exception as e:
        print(f'Вибрация недоступна: {e}')


def vibrate_one_shot():
    """Одиночная вибрация (успех). На ПК — ничего."""
    if not _VIBRATE_ENABLED:
        return
    try:
        _vibrator.vibrate(0.1)  # 100 мс
    except Exception:
        pass


def vibrate_triple():
    """Тройная вибрация (ошибка). На ПК — ничего."""
    if not _VIBRATE_ENABLED:
        return
    try:
        _vibrator.vibrate(0.08)
        Clock.schedule_once(lambda dt: _vibrator.vibrate(0.08), 0.12)
        Clock.schedule_once(lambda dt: _vibrator.vibrate(0.08), 0.24)
    except Exception:
        pass


# ---------- Звук (звуковой движок Kivy, работает и на Android) ----------
_SOUND_ENABLED = False
try:
    from kivy.core.audio import SoundLoader
    _SOUND_ENABLED = True
except Exception as e:
    print(f'Звук отключён: {e}')


class SoundPlayer:
    def __init__(self):
        self.ok = None
        self.err = None
        if not _SOUND_ENABLED:
            return
        try:
            if os.path.exists(SOUND_OK):
                self.ok = SoundLoader.load(SOUND_OK)
            if os.path.exists(SOUND_ERR):
                self.err = SoundLoader.load(SOUND_ERR)
        except Exception as e:
            print(f'Ошибка загрузки звуков: {e}')

    def play_ok(self):
        if self.ok:
            try:
                self.ok.play()
            except Exception:
                pass

    def play_err(self):
        if self.err:
            try:
                self.err.play()
            except Exception:
                pass


class MainLayout(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(orientation='vertical', padding=8, spacing=6, **kwargs)

        self.report_logic = None
        self.current_pallet = None
        self.log_lines = []
        self.sound = SoundPlayer()

        # --- Фон для цветовой вспышки ---
        with self.canvas.before:
            self._flash_color = Color(0, 0, 0, 0)
            self._flash_rect = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._update_flash_rect, size=self._update_flash_rect)

        # --- Заголовок ---
        self.title = Label(
            text='Агрегация пива\nЗагрузите файл агрегации',
            size_hint_y=0.08, font_size='16sp', halign='center',
        )
        self.title.bind(width=lambda *x: setattr(
            self.title, 'text_size', (self.title.width, None)))
        self.add_widget(self.title)

        # --- Последний отсканированный короб (крупно) ---
        self.last_box_label = Label(
            text='—',
            size_hint_y=0.10, font_size='26sp', bold=True,
            halign='center', color=(0.2, 0.6, 1, 1),
        )
        self.last_box_label.bind(width=lambda *x: setattr(
            self.last_box_label, 'text_size', (self.last_box_label.width, None)))
        self.add_widget(self.last_box_label)

        # --- Поле ввода ШК ---
        self.scan_input = TextInput(
            hint_text='Сканируйте ШК паллеты или короба',
            multiline=False, size_hint_y=0.08, font_size='18sp',
        )
        self.scan_input.bind(on_text_validate=self.on_scan)
        self.add_widget(self.scan_input)

        # Автофокус: код со сканера должен попадать в поле без касания экрана
        Clock.schedule_once(lambda dt: self.focus_scan_input(), 0.5)

        # --- Прогресс по паллете ---
        prog_box = BoxLayout(size_hint_y=0.07, spacing=6)
        self.progress_label = Label(
            text='Паллета не открыта', font_size='13sp',
            size_hint_x=0.45, halign='left',
        )
        self.progress_label.bind(width=lambda *x: setattr(
            self.progress_label, 'text_size', (self.progress_label.width, None)))
        prog_box.add_widget(self.progress_label)

        self.progress_bar = ProgressBar(max=100, value=0)
        prog_box.add_widget(self.progress_bar)
        self.add_widget(prog_box)

        # --- Ряд кнопок 1 ---
        row1 = BoxLayout(size_hint_y=0.09, spacing=6)
        self.btn_load = Button(text='Загрузить агрегацию', font_size='13sp')
        self.btn_load.bind(on_release=self.load_aggregation)
        row1.add_widget(self.btn_load)

        self.btn_close_pallet = Button(text='Паллета закрыта', font_size='13sp')
        self.btn_close_pallet.bind(on_release=self.close_pallet)
        row1.add_widget(self.btn_close_pallet)

        self.btn_reset_pallet = Button(text='Сбросить паллету', font_size='13sp')
        self.btn_reset_pallet.bind(on_release=self.reset_pallet)
        row1.add_widget(self.btn_reset_pallet)
        self.add_widget(row1)

        # --- Ряд кнопок 2 ---
        row2 = BoxLayout(size_hint_y=0.09, spacing=6)
        self.btn_finish = Button(text='Сформировать отчёты', font_size='13sp')
        self.btn_finish.bind(on_release=self.finish)
        row2.add_widget(self.btn_finish)
        self.add_widget(row2)

        # --- Лог ---
        self.log_label = Label(
            text='', halign='left', valign='top', font_size='12sp',
        )
        self.log_label.bind(width=lambda *x: setattr(
            self.log_label, 'text_size', (self.log_label.width, None)))
        scroll = ScrollView(size_hint_y=0.42)
        scroll.add_widget(self.log_label)
        self.add_widget(scroll)

        self.log('Готово. Загрузите файл агрегации.')

    # ---------- Фокус поля сканера ----------
    def focus_scan_input(self):
        """Возвращает фокус в поле ввода — код со сканера идёт туда."""
        try:
            self.scan_input.focus = True
        except Exception:
            pass

    # ---------- Вспышка ----------
    def _update_flash_rect(self, *args):
        self._flash_rect.pos = self.pos
        self._flash_rect.size = self.size

    def flash(self, success=True):
        if success:
            self._flash_color.rgba = (0, 1, 0, 0.35)
        else:
            self._flash_color.rgba = (1, 0, 0, 0.45)
        Clock.schedule_once(self._clear_flash, 0.25)

    def _clear_flash(self, *args):
        self._flash_color.rgba = (0, 0, 0, 0)

    # ---------- Обратная связь (звук + вибрация + вспышка) ----------
    def feedback_ok(self):
        self.flash(True)
        self.sound.play_ok()
        vibrate_one_shot()

    def feedback_err(self):
        self.flash(False)
        self.sound.play_err()
        vibrate_triple()

    # ---------- Лог ----------
    def log(self, msg):
        self.log_lines.append(msg)
        if len(self.log_lines) > 300:
            self.log_lines = self.log_lines[-300:]
        self.log_label.text = '\n'.join(self.log_lines)

    # ---------- Прогресс по паллете ----------
    def update_progress(self):
        """Обновляет индикатор: сколько коробов отсканировано из N."""
        if self.current_pallet is None or self.report_logic is None:
            self.progress_label.text = 'Паллета не открыта'
            self.progress_bar.value = 0
            return

        total = len(self.report_logic.pallet_to_boxes.get(self.current_pallet, set()))
        scanned = len(self.report_logic.scanned_boxes.get(self.current_pallet, set()))
        self.progress_label.text = f'Коробов: {scanned} из {total}'
        self.progress_bar.value = (scanned / total * 100) if total else 0

    # ---------- Загрузка агрегации ----------
    def load_aggregation(self, *args):
        start_dir = EXTERNAL_DIR if os.path.isdir(EXTERNAL_DIR) else APP_DIR

        chooser = FileChooserListView(
            path=start_dir,
            filters=['*.txt', '*.TXT'],
        )

        buttons = BoxLayout(size_hint_y=0.15, spacing=8)
        btn_open = Button(text='Открыть')
        btn_cancel = Button(text='Отмена')
        buttons.add_widget(btn_open)
        buttons.add_widget(btn_cancel)

        content = BoxLayout(orientation='vertical')
        content.add_widget(chooser)
        content.add_widget(buttons)

        popup = Popup(
            title='Выберите файл агрегации',
            content=content,
            size_hint=(0.95, 0.95),
        )

        def on_open(*_):
            if not chooser.selection:
                return
            filepath = chooser.selection[0]
            if not os.path.isfile(filepath):
                return
            popup.dismiss()
            self._load_from_path(filepath)

        def on_cancel(*_):
            popup.dismiss()

        btn_open.bind(on_release=on_open)
        btn_cancel.bind(on_release=on_cancel)
        popup.open()

    def _load_from_path(self, filepath):
        try:
            self.report_logic = AggregationReport(filepath)
        except Exception as e:
            self.show_popup('Ошибка загрузки', str(e))
            self.feedback_err()
            return

        self.current_pallet = None
        self.last_box_label.text = '—'
        self.update_progress()

        s = self.report_logic.stats()
        self.log(f'✅ Загружено: {filepath}')
        self.log(f'   Паллет: {s["pallets_total"]}, '
                 f'коробов: {s["boxes_total"]}, '
                 f'бутылок: {s["bottles_total"]}')

        # Список паллет (первые 20, чтобы не засорять лог)
        pallets = sorted(self.report_logic.pallet_to_boxes.keys())
        self.log(f'📋 Паллет в агрегации: {len(pallets)}')
        for p in pallets[:20]:
            boxes_count = len(self.report_logic.pallet_to_boxes[p])
            self.log(f'   ...{p[-10:]} — {boxes_count} кор.')
        if len(pallets) > 20:
            self.log(f'   ... и ещё {len(pallets) - 20}')

        self.log('-' * 40)
        self.title.text = 'Сканируйте паллету'
        self.feedback_ok()

    # ---------- Скан ----------
    def on_scan(self, instance):
        """Приём кода со сканера (сканер работает как клавиатура)."""
        code = instance.text.strip()
        instance.text = ''
        try:
            self._handle_scan(code)
        finally:
            # Возвращаем фокус — следующий скан без касания экрана
            Clock.schedule_once(lambda dt: self.focus_scan_input(), 0.05)

    def _handle_scan(self, code):
        if not code:
            return
        if self.report_logic is None:
            self.log('⚠ Сначала загрузите файл агрегации')
            self.feedback_err()
            return

        # Паллета ещё не открыта — этот скан считаем паллетой
        if self.current_pallet is None:
            if self.report_logic.scan_pallet(code):
                self.current_pallet = code
                self.log(f'📦 Паллета: {code}')
                self.title.text = f'Паллета: ...{code[-8:]}'
                self.last_box_label.text = '—'
                self.update_progress()
                self.feedback_ok()
            else:
                self.log(f'❌ Паллета {code} не найдена в агрегации')
                self.feedback_err()
            return

        # Иначе — короб
        status, count = self.report_logic.scan_box(self.current_pallet, code)
        if status == 'ok':
            self.log(f'  ✅ Короб ...{code[-10:]} — {count} бут.')
            self.last_box_label.text = f'...{code[-10:]}'
            self.update_progress()
            self.feedback_ok()
        elif status == 'already':
            self.log(f'  ⚠ Короб ...{code[-10:]} УЖЕ отсканирован (пропущен)')
            self.last_box_label.text = f'⚠ ...{code[-10:]}'
            self.feedback_err()
        elif status == 'not_in_pallet':
            self.log(f'  ❌ Короб ...{code[-10:]} не относится '
                     f'к паллете ...{self.current_pallet[-8:]}')
            self.last_box_label.text = f'❌ ...{code[-10:]}'
            self.feedback_err()
        elif status == 'unknown_box':
            self.log(f'  ❌ Короб ...{code[-10:]} отсутствует в агрегации')
            self.last_box_label.text = f'❌ ...{code[-10:]}'
            self.feedback_err()

    # ---------- Закрытие паллеты ----------
    def close_pallet(self, *args):
        if self.current_pallet:
            self.log(f'🏁 Паллета ...{self.current_pallet[-8:]} закрыта')
            self.current_pallet = None
            self.title.text = 'Сканируйте паллету'
            self.last_box_label.text = '—'
            self.update_progress()
            self.feedback_ok()
        else:
            self.log('ℹ Нет открытой паллеты')

    # ---------- Сброс текущей паллеты ----------
    def reset_pallet(self, *args):
        """Полный сброс: удаляет все отсканированные короба текущей паллеты."""
        if not self.current_pallet:
            self.log('ℹ Нет открытой паллеты')
            return

        # Спрашиваем подтверждение
        content = BoxLayout(orientation='vertical', spacing=8, padding=8)
        content.add_widget(Label(
            text=f'Сбросить все короба паллеты\n...{self.current_pallet[-10:]}?'
        ))
        btn_row = BoxLayout(size_hint_y=0.3, spacing=8)
        btn_yes = Button(text='Да, сбросить')
        btn_no = Button(text='Отмена')
        btn_row.add_widget(btn_yes)
        btn_row.add_widget(btn_no)
        content.add_widget(btn_row)

        popup = Popup(title='Подтверждение', content=content,
                      size_hint=(0.8, 0.4))

        def do_reset(*_):
            popup.dismiss()
            pallet = self.current_pallet
            # Удаляем короба этой паллеты из глобального набора
            boxes = self.report_logic.scanned_boxes.get(pallet, set())
            for box in boxes:
                self.report_logic.scanned_box_set.discard(box)
            self.report_logic.scanned_boxes[pallet] = set()
            self.log(f'🔄 Паллета ...{pallet[-8:]} сброшена ({len(boxes)} кор.)')
            self.last_box_label.text = '—'
            self.update_progress()
            self.feedback_ok()

        def do_cancel(*_):
            popup.dismiss()

        btn_yes.bind(on_release=do_reset)
        btn_no.bind(on_release=do_cancel)
        popup.open()

    # ---------- Формирование отчётов ----------
    def finish(self, *args):
        if self.report_logic is None:
            self.show_popup('Ошибка', 'Агрегация не загружена')
            self.feedback_err()
            return

        if self.current_pallet:
            self.log(f'🏁 Паллета ...{self.current_pallet[-8:]} закрыта автоматически')
            self.current_pallet = None
            self.update_progress()

        saved_paths = []
        for base_dir in (EXTERNAL_DIR, APP_DIR):
            out_dir = os.path.join(base_dir, REPORT_SUBDIR)
            try:
                os.makedirs(out_dir, exist_ok=True)
                rp = os.path.join(out_dir, REPORT_NAME)
                bp = os.path.join(out_dir, BOI_NAME)
                self.report_logic.save_report(rp)
                self.report_logic.save_boi(bp)
                saved_paths.append(out_dir)
            except Exception as e:
                self.log(f'⚠ Не удалось сохранить в {out_dir}: {e}')

        if not saved_paths:
            self.show_popup('Ошибка', 'Не удалось сохранить файлы ни в одну папку')
            self.feedback_err()
            return

        s = self.report_logic.stats()
        self.log('=' * 40)
        self.log('📊 ИТОГИ:')
        self.log(f'  Паллет отсканировано: {s["pallets_scanned"]} '
                 f'из {s["pallets_total"]}')
        self.log(f'  Коробов в отчёте: {s["boxes_scanned"]} '
                 f'из {s["boxes_total"]}')
        self.log(f'  Коробов в бое: {s["boxes_boi"]}')
        self.log(f'  Бутылок в отчёте: {s["bottles_scanned"]} '
                 f'из {s["bottles_total"]}')
        self.log(f'  Бутылок в бое: {s["bottles_boi"]}')
        for p in saved_paths:
            self.log(f'📄 Сохранено: {p}')

        self.feedback_ok()
        self.show_popup(
            'Готово',
            'Сохранено в:\n' + '\n'.join(saved_paths) + '\n\n'
            f'Коробов в бое: {s["boxes_boi"]}\n'
            f'Бутылок в бое: {s["bottles_boi"]}'
        )

    # ---------- Popup ----------
    def show_popup(self, title, text):
        popup = Popup(
            title=title,
            content=Label(text=text),
            size_hint=(0.9, 0.5),
        )
        popup.open()


class BeerAggregationApp(App):
    def build(self):
        Window.softinput_mode = 'below_target'
        self.root_layout = MainLayout()

        if platform == 'android':
            request_android_permissions()
            Clock.schedule_once(self.check_file_access, 1.0)

        return self.root_layout

    def check_file_access(self, *args):
        """Напоминает выдать «Доступ ко всем файлам», если его нет."""
        if has_all_files_access():
            return

        root = self.root_layout
        root.log('⚠ Нужен доступ к файлам — нажмите кнопку ниже')

        content = BoxLayout(orientation='vertical', spacing=8, padding=8)
        content.add_widget(Label(
            text='Для чтения агрегации и сохранения\n'
                 'отчётов в папку Download выдайте\n'
                 'приложению «Доступ ко всем файлам».'
        ))
        btn_row = BoxLayout(size_hint_y=0.3, spacing=8)
        btn_go = Button(text='Открыть настройки')
        btn_later = Button(text='Позже')
        btn_row.add_widget(btn_go)
        btn_row.add_widget(btn_later)
        content.add_widget(btn_row)

        popup = Popup(title='Доступ к файлам', content=content,
                      size_hint=(0.9, 0.45))

        def go(*_):
            popup.dismiss()
            open_all_files_settings()

        btn_go.bind(on_release=go)
        btn_later.bind(on_release=lambda *_: popup.dismiss())
        popup.open()


if __name__ == '__main__':
    BeerAggregationApp().run()
