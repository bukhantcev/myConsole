from PyQt5.QtCore import QEvent
import sys
import asyncio
from PyQt5.QtWidgets import QApplication, QMainWindow, QSlider, QPushButton, QComboBox, QDialog, QTextEdit
from PyQt5.QtCore import Qt, QTimer
from qasync import QEventLoop
from pyartnet import ArtNetNode
from PyQt5.QtWidgets import QLineEdit, QLabel
import json
from PyQt5.QtWidgets import QDialog, QListWidget, QListWidgetItem
from PyQt5.QtWidgets import QMenu, QAction

# Глобальный перехватчик ошибок
def exception_hook(exctype, value, traceback):
    print("Exception:", value)
    sys.__excepthook__(exctype, value, traceback)

sys.excepthook = exception_hook

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Мой пульт ArtNet")
        self.setGeometry(100, 100, 640, 300)

        # ArtNet settings defaults
        self.artnet_mode = "Broadcast"
        self.artnet_ip = "127.0.0.1"
        self.artnet_universe = 0
        self.artnet_start_addr = 1

        self.channels = []

        self.current_cue_key = None
        # Settings button (gear)
        self.settings_button = QPushButton("⚙", self)
        self.settings_button.setGeometry(10, 10, 30, 30)
        self.settings_button.clicked.connect(self.show_settings_dialog)

        # Фейдер Opacity (канал 2)
        self.opacity_label = QLabel("Opacity", self)
        self.opacity_label.setGeometry(100, 10, 60, 20)
        self.opacity_slider = QSlider(self)
        self.opacity_slider.setStyleSheet("QSlider::handle:vertical { background: gray; height: 20px; width: 10px; }")
        self.opacity_slider.setOrientation(Qt.Vertical)
        self.opacity_slider.setGeometry(100, 30, 60, 180)
        self.opacity_slider.setRange(0, 255)
        self.opacity_slider.setValue(255)
        self.opacity_slider.valueChanged.connect(lambda val: (self.update_dmx(val, 1), self.mark_cue_modified()))

        # Выпадающий список ClipSelect (канал 3)
        self.clip_select = QComboBox(self)
        self.clip_select.setGeometry(180, 30, 110, 30)
        for i in range(1, 256):
            self.clip_select.addItem(f"Column {i}", i)
        self.clip_select.currentIndexChanged.connect(lambda index: (self.update_dmx(self.clip_select.itemData(index), 2), self.mark_cue_modified()))

        # Фейдер Transition (канал 4)
        self.transition_label = QLabel("Transition", self)
        self.transition_label.setGeometry(300, 10, 60, 20)
        self.transition_slider = QSlider(self)
        self.transition_slider.setStyleSheet("QSlider::handle:vertical { background: gray; height: 20px; width: 10px; }")
        self.transition_slider.setOrientation(Qt.Vertical)
        self.transition_slider.setGeometry(300, 30, 60, 180)
        self.transition_slider.setRange(0, 255)
        self.transition_slider.setValue(0)
        self.transition_slider.valueChanged.connect(lambda val: (self.update_dmx(val, 3), self.mark_cue_modified()))

        self.score_window = ScoreWindow(self)
        self.cue_name_input = QLineEdit(self)
        self.cue_name_input.setPlaceholderText("Cue Name")
        self.cue_name_input.setGeometry(20, 260, 200, 30)
        self.cue_name_input.textChanged.connect(self.mark_cue_modified)

        self.save_cue_button = QPushButton("Сохранить Cue", self)
        self.save_cue_button.setGeometry(230, 260, 120, 30)
        self.save_cue_button.clicked.connect(self.save_current_cue)

        self.update_cue_button = QPushButton("Обновить Cue", self)
        self.update_cue_button.setGeometry(360, 260, 120, 30)
        self.update_cue_button.clicked.connect(self.update_current_cue)
        self.update_cue_button.setEnabled(False)

        self.score_button = QPushButton("→", self)
        self.score_button.setGeometry(self.width() - 50, self.height() - 40, 40, 30)
        self.score_button.clicked.connect(self.toggle_score_window)

        # Blinde button and state
        self.blinde_button = QPushButton("Blinde", self)
        self.blinde_button.setGeometry(self.width() - 100, 10, 80, 30)
        self.blinde_button.clicked.connect(self.toggle_blinde)
        self.blinde_state = False
        self.blinde_timer = QTimer(self)
        self.blinde_timer.timeout.connect(self.blink_blinde_label)
        self.blinde_visible = True
        self._opacity_fade_timer = QTimer(self)

        self.advance_cue_number()

        self.current_cue_key = None
        self.score_window.hide()
    def show_settings_dialog(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Настройки ArtNet")
        dlg.setFixedSize(300, 220)

        mode_label = QLabel("Режим:", dlg)
        mode_label.move(20, 20)
        mode_combo = QComboBox(dlg)
        mode_combo.addItems(["Broadcast", "Unicast"])
        mode_combo.move(120, 20)
        # Set current mode
        idx = mode_combo.findText(getattr(self, "artnet_mode", "Broadcast"))
        if idx >= 0:
            mode_combo.setCurrentIndex(idx)

        ip_label = QLabel("Unicast IP:", dlg)
        ip_label.move(20, 60)
        ip_input = QLineEdit(dlg)
        ip_input.setText(getattr(self, "artnet_ip", "127.0.0.1"))
        ip_input.move(120, 60)

        universe_label = QLabel("Universe:", dlg)
        universe_label.move(20, 100)
        universe_input = QLineEdit(dlg)
        universe_input.setText(str(getattr(self, "artnet_universe", 0)))
        universe_input.move(120, 100)

        start_label = QLabel("Start Addr:", dlg)
        start_label.move(20, 140)
        start_input = QLineEdit(dlg)
        start_input.setText(str(getattr(self, "artnet_start_addr", 1)))
        start_input.move(120, 140)

        ok_btn = QPushButton("OK", dlg)
        ok_btn.move(100, 180)
        ok_btn.clicked.connect(lambda: (
            setattr(self, "artnet_mode", mode_combo.currentText()),
            setattr(self, "artnet_ip", ip_input.text()),
            setattr(self, "artnet_universe", int(universe_input.text())),
            setattr(self, "artnet_start_addr", int(start_input.text())),
            dlg.accept(),
            asyncio.ensure_future(self.setup_artnet())
        ))

        dlg.exec_()

        # Фейдер Opacity (канал 2)
        self.opacity_label = QLabel("Opacity", self)
        self.opacity_label.setGeometry(100, 10, 60, 20)
        self.opacity_slider = QSlider(self)
        self.opacity_slider.setStyleSheet("QSlider::handle:vertical { background: gray; height: 20px; width: 10px; }")
        self.opacity_slider.setOrientation(Qt.Vertical)
        self.opacity_slider.setGeometry(100, 30, 60, 180)
        self.opacity_slider.setRange(0, 255)
        self.opacity_slider.setValue(255)
        self.opacity_slider.valueChanged.connect(lambda val: (self.update_dmx(val, 1), self.mark_cue_modified()))

        # Выпадающий список ClipSelect (канал 3)
        self.clip_select = QComboBox(self)
        self.clip_select.setGeometry(180, 30, 110, 30)
        for i in range(1, 256):
            self.clip_select.addItem(f"Column {i}", i)
        self.clip_select.currentIndexChanged.connect(lambda index: (self.update_dmx(self.clip_select.itemData(index), 2), self.mark_cue_modified()))

        # Фейдер Transition (канал 4)
        self.transition_label = QLabel("Transition", self)
        self.transition_label.setGeometry(300, 10, 60, 20)
        self.transition_slider = QSlider(self)
        self.transition_slider.setStyleSheet("QSlider::handle:vertical { background: gray; height: 20px; width: 10px; }")
        self.transition_slider.setOrientation(Qt.Vertical)
        self.transition_slider.setGeometry(300, 30, 60, 180)
        self.transition_slider.setRange(0, 255)
        self.transition_slider.setValue(0)
        self.transition_slider.valueChanged.connect(lambda val: (self.update_dmx(val, 3), self.mark_cue_modified()))

        self.score_window = ScoreWindow(self)
        self.cue_name_input = QLineEdit(self)
        self.cue_name_input.setPlaceholderText("Cue Name")
        self.cue_name_input.setGeometry(20, 260, 200, 30)
        self.cue_name_input.textChanged.connect(self.mark_cue_modified)

        self.save_cue_button = QPushButton("Сохранить Cue", self)
        self.save_cue_button.setGeometry(230, 260, 120, 30)
        self.save_cue_button.clicked.connect(self.save_current_cue)

        self.update_cue_button = QPushButton("Обновить Cue", self)
        self.update_cue_button.setGeometry(360, 260, 120, 30)
        self.update_cue_button.clicked.connect(self.update_current_cue)
        self.update_cue_button.setEnabled(False)

        self.score_button = QPushButton("→", self)
        self.score_button.setGeometry(self.width() - 50, self.height() - 40, 40, 30)
        self.score_button.clicked.connect(self.toggle_score_window)

        # Blinde button and state
        self.blinde_button = QPushButton("Blinde", self)
        self.blinde_button.setGeometry(self.width() - 100, 10, 80, 30)
        self.blinde_button.clicked.connect(self.toggle_blinde)
        self.blinde_state = False
        self.blinde_timer = QTimer(self)
        self.blinde_timer.timeout.connect(self.blink_blinde_label)
        self.blinde_visible = True
        self._opacity_fade_timer = QTimer(self)

        self.advance_cue_number()

        self.current_cue_key = None
        self.score_window.hide()

    def toggle_score_window(self):
        if self.score_window.isVisible():
            self.score_window.hide()
            self.score_button.setText("→")
        else:
            geo = self.geometry()
            score_width = self.score_window.width()
            score_height = self.score_window.height()
            x = geo.x() + geo.width() + 10
            y = geo.y()
            self.score_window.setGeometry(x, y, score_width, score_height)
            self.score_window.show()
            self.score_button.setText("←")

    def mark_cue_modified(self):
        self.update_cue_button.setEnabled(True)

    def send_clear(self):
        self.update_dmx(255, 0)
        QTimer.singleShot(100, lambda: self.update_dmx(0, 0))

    async def setup_artnet(self):
        import socket
        # Остановить предыдущий ArtNet-узел перед созданием нового
        if hasattr(self, 'node') and self.node:
            if hasattr(self.node, '_refresh_task') and self.node._refresh_task:
                self.node._refresh_task.cancel()
                try:
                    task = getattr(self.node._refresh_task, "task", self.node._refresh_task)
                    if asyncio.isfuture(task) or asyncio.iscoroutine(task):
                        await asyncio.shield(task)
                except asyncio.CancelledError:
                    pass
                except Exception as e:
                    print(f"Ошибка завершения refresh_task: {e}")

            if hasattr(self.node, '_socket'):
                if hasattr(self, 'channels') and self.channels:
                    for ch in self.channels:
                        ch.set_fade([0], 0)
                try:
                    self.node._socket.close()
                    self.node._socket = None
                except Exception as e:
                    print(f"Ошибка при закрытии сокета: {e}")
                # <--- ADDITION: recreate socket if needed
                if self.node._socket is None:
                    import socket
                    self.node._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    if self.artnet_mode == "Broadcast":
                        self.node._socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

            self.node = None
        target_ip = self.artnet_ip if self.artnet_mode == "Unicast" else "255.255.255.255"
        self.node = ArtNetNode(target_ip, port=6454)
        # Установка SO_BROADCAST для режима Broadcast
        if self.artnet_mode == "Broadcast":
            self.node._socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        universe = self.node.add_universe(self.artnet_universe)
        self.channels = [universe.add_channel(start=self.artnet_start_addr + i, width=1) for i in range(4)]
        self.node.start_refresh()

    def update_dmx(self, value, channel_index, delay_ms=0):
        if not self.channels:
            return
        # всегда сохраняем в _target
        self.channels[channel_index]._target = [value]
        if not self.blinde_state:
            if delay_ms > 0:
                QTimer.singleShot(delay_ms, lambda: self.channels[channel_index].set_fade([value], 0))
            else:
                self.channels[channel_index].set_fade([value], 0)

    def toggle_blinde(self):
        self.blinde_state = not self.blinde_state
        if self.blinde_state:
            self.blinde_timer.start(500)
            self.blinde_button.setStyleSheet("background-color: red;")
            self.blinde_button.setText("Blinde")
            self.saved_output = [ch.get_values()[0] for ch in self.channels]
            self.blinde_active_cue_key = self.current_cue_key
        else:
            self.blinde_timer.stop()
            self.blinde_button.setStyleSheet("")
            self.blinde_button.setText("Blinde")

            # Восстановить Art-Net и текущую активную Cue
            try:
                with open("score.json", "r", encoding="utf-8") as f:
                    data = list(json.load(f).items())
                cue_data = dict(data)[self.blinde_active_cue_key]
                cue = cue_data["levels"]
                for i, val in enumerate(self.saved_output):
                    self.channels[i].set_fade([val], 0)
                    self.channels[i]._target = [val]
                for i, ch in enumerate(self.channels):
                    val = cue.get(f"channel_{i+1}", 0)
                    if i == 0:
                        pass  # канал 1 (Clear) не отображается в интерфейсе
                    elif i == 1:
                        self.opacity_slider.setValue(val)
                    elif i == 2:
                        index = self.clip_select.findData(val)
                        if index >= 0:
                            self.clip_select.setCurrentIndex(index)
                    elif i == 3:
                        self.transition_slider.setValue(val)

                if not self.blinde_state:
                    for i, ch in enumerate(self.channels):
                        val = cue.get(f"channel_{i+1}", 0)
                        if i == 3:
                            self.update_dmx(val, i, delay_ms=0)
                        else:
                            self.update_dmx(val, i, delay_ms=50)

                self.current_cue_key = self.blinde_active_cue_key
                self.cue_name_input.setText(cue_data["name"])
                # выделить текущую Cue в списке
                self.score_window.select_cue_by_id(self.current_cue_key)
                self.score_window.list_box.repaint()
                self.score_window.activate_cue(self.score_window.list_box.currentItem())
                # self.score_window.reload_list()  # удалено по заданию
            except Exception as e:
                print(f"Ошибка восстановления Cue: {e}")

    def blink_blinde_label(self):
        if self.blinde_visible:
            self.blinde_button.setStyleSheet("background-color: none; color: transparent;")
        else:
            self.blinde_button.setStyleSheet("background-color: red; color: white;")
        self.blinde_visible = not self.blinde_visible

    def save_current_cue(self):
        import uuid
        name = self.cue_name_input.text().strip()
        if not name:
            try:
                with open("score.json", "r", encoding="utf-8") as f:
                    data = json.load(f)
                index = len(data) + 1
            except FileNotFoundError:
                index = 1
            name = f"Cue {index}"
        levels = {f"channel_{i+1}": ch._target[0] if hasattr(ch, "_target") and ch._target else 0 for i, ch in enumerate(self.channels)}
        try:
            with open("score.json", "r", encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            data = {}

        cue_id = str(uuid.uuid4())
        data[cue_id] = {"name": name, "levels": levels}
        self.current_cue_key = cue_id

        with open("score.json", "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        self.score_window.reload_list()
        self.advance_cue_number()
        self.cue_name_input.clear()

    def update_current_cue(self):
        name = self.cue_name_input.text().strip()
        if not self.current_cue_key:
            return

        levels = {f"channel_{i+1}": ch._target[0] if hasattr(ch, "_target") and ch._target else 0 for i, ch in enumerate(self.channels)}
        try:
            with open("score.json", "r", encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            return

        # Обновляем по ID, независимо от имени
        if self.current_cue_key in data:
            data[self.current_cue_key]["name"] = name
            data[self.current_cue_key]["levels"] = levels

        # сохраняем порядок cue из list_box
        new_order = {}
        for i in range(self.score_window.list_box.count()):
            item = self.score_window.list_box.item(i)
            cue_id = item.data(Qt.UserRole)
            if cue_id in data:
                new_order[cue_id] = data[cue_id]
        data = new_order

        with open("score.json", "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        self.score_window.reload_list()
        self.update_cue_button.setEnabled(False)

    def advance_cue_number(self):
        pass

class ScoreWindow(QDialog):
    def __init__(self, main_window):
        super().__init__()
        self.setWindowTitle("Партитура")
        x = main_window.geometry().x() + main_window.geometry().width() + 10
        y = main_window.geometry().y()
        self.setGeometry(x, y, 400, 500)

        self.main_window = main_window

        self.list_box = QListWidget(self)
        self.list_box.setGeometry(10, 10, 380, 480)
        self.list_box.itemDoubleClicked.connect(self.activate_cue)
        self.list_box.installEventFilter(self)

        self.list_box.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list_box.customContextMenuRequested.connect(self.show_context_menu)

        # Enable drag and drop reordering
        self.list_box.setDragDropMode(QListWidget.InternalMove)
        self.list_box.setDefaultDropAction(Qt.MoveAction)

        self.reload_list()

    def reload_list(self):
        self.list_box.clear()
        current_id = self.main_window.current_cue_key
        try:
            with open("score.json", "r", encoding="utf-8") as f:
                self.data = json.load(f)

            for index, (cue_id, cue_data) in enumerate(self.data.items(), 1):
                item = QListWidgetItem()
                item.setData(Qt.UserRole, cue_id)
                item.setText(f"{index}. {cue_data.get('name', 'Cue')}")
                # Устанавливаем размер шрифта 14
                font = item.font()
                font.setPointSize(14)
                item.setFont(font)
                self.list_box.addItem(item)
        except FileNotFoundError:
            self.list_box.addItem("Нет сохранённых Cue")
        # Highlight/select current cue if any
        if current_id:
            for i in range(self.list_box.count()):
                item = self.list_box.item(i)
                if item.data(Qt.UserRole) == current_id:
                    self.list_box.setCurrentRow(i)
                    break
            self.highlight_current_cue()

    def activate_cue(self, item):
        # В режиме Blinde только применяем уровни, но не меняем визуальное выделение
        if self.main_window.blinde_state:
            apply_only = True
            # Set cue name input to the selected cue's name
            self.main_window.cue_name_input.setText(self.data[item.data(Qt.UserRole)]["name"])
        else:
            apply_only = False
        try:
            # Сброс цвета всех элементов и выделение активного
            from PyQt5.QtGui import QColor

            if not apply_only:
                for i in range(self.list_box.count()):
                    self.list_box.item(i).setBackground(QColor(0, 0, 0))  # черный фон
                    self.list_box.item(i).setForeground(Qt.white)         # белый текст
                item.setBackground(QColor(80, 80, 80))  # серый для активного
                item.setForeground(Qt.white)

            cue_id = item.data(Qt.UserRole)
            cue_data = self.data[cue_id]
            # Always set current_cue_key to the selected cue id
            self.main_window.current_cue_key = cue_id
            cue = cue_data["levels"]
            fade_time = int((cue.get("channel_4", 0) / 255) * 10000)
            # Only highlight if not in blinde_state
            if not self.main_window.blinde_state:
                self.main_window.score_window.highlight_current_cue()
            self.main_window.cue_name_input.setText(cue_data["name"])

            from functools import partial
            for i, ch in enumerate(self.main_window.channels):
                val = cue.get(f"channel_{i+1}", 0)
                if not self.main_window.blinde_state:
                    if i == 1:
                        self.main_window.channels[i]._target = [val]
                        self.main_window.channels[i].set_fade([val], fade_time)
                    else:
                        self.main_window.update_dmx(val, i, delay_ms=50)
                if i == 0:
                    pass  # канал 1 (Clear) не отображается в интерфейсе
                elif i == 1:
                    # Cancel previous fade timer and set new one for opacity slider
                    if hasattr(self.main_window, '_opacity_fade_timer') and self.main_window._opacity_fade_timer.isActive():
                        self.main_window._opacity_fade_timer.stop()
                    self.main_window._opacity_fade_timer = QTimer(self)
                    self.main_window._opacity_fade_timer.setSingleShot(True)
                    self.main_window._opacity_fade_timer.timeout.connect(partial(self.main_window.opacity_slider.setValue, val))
                    self.main_window._opacity_fade_timer.start(fade_time)
                elif i == 2:
                    index = self.main_window.clip_select.findData(val)
                    if index >= 0:
                        self.main_window.clip_select.setCurrentIndex(index)
                elif i == 3:
                    self.main_window.transition_slider.setValue(val)
        except Exception as e:
            print(f"Ошибка активации Cue: {e}")

    from PyQt5.QtCore import QEvent
    def eventFilter(self, source, event):
        if source == self.list_box and event.type() == QEvent.KeyPress:
            if event.key() in (Qt.Key_Return, Qt.Key_Enter):
                current_item = self.list_box.currentItem()
                if current_item:
                    self.activate_cue(current_item)
                return True
            elif event.key() == Qt.Key_Right:
                try:
                    current_id = self.main_window.current_cue_key
                    list_keys = []
                    for i in range(self.list_box.count()):
                        item = self.list_box.item(i)
                        list_keys.append(item.data(Qt.UserRole))
                    if current_id in list_keys:
                        idx = list_keys.index(current_id)
                        if idx < len(list_keys) - 1:
                            next_item = self.list_box.item(idx + 1)
                            self.list_box.setCurrentRow(idx + 1)
                            self.activate_cue(next_item)
                except Exception as e:
                    print(f"Ошибка перехода вправо: {e}")
                return True
            elif event.key() == Qt.Key_Left:
                try:
                    current_id = self.main_window.current_cue_key
                    list_keys = []
                    for i in range(self.list_box.count()):
                        item = self.list_box.item(i)
                        list_keys.append(item.data(Qt.UserRole))
                    if current_id in list_keys:
                        idx = list_keys.index(current_id)
                        if idx > 0:
                            prev_item = self.list_box.item(idx - 1)
                            self.list_box.setCurrentRow(idx - 1)
                            self.activate_cue(prev_item)
                except Exception as e:
                    print(f"Ошибка перехода влево: {e}")
                return True
        return super().eventFilter(source, event)

    def show_context_menu(self, position):
        item = self.list_box.itemAt(position)
        if item is None:
            return
        menu = QMenu()
        delete_action = QAction("Удалить", self)
        delete_action.triggered.connect(lambda: self.delete_cue(item))
        menu.addAction(delete_action)
        menu.exec_(self.list_box.viewport().mapToGlobal(position))

    def delete_cue(self, item):
        cue_index = self.list_box.row(item)
        try:
            with open("score.json", "r", encoding="utf-8") as f:
                data = list(json.load(f).items())
        except FileNotFoundError:
            return

        if cue_index < len(data):
            cue_id, _ = data[cue_index]
            data.pop(cue_index)
            data = dict(data)

            with open("score.json", "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            self.reload_list()

    def dropEvent(self, event):
        super().dropEvent(event)

        # сразу сохраняем новый порядок в JSON, как в update_current_cue
        try:
            with open("score.json", "r", encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            return

        # сохраняем порядок cue из list_box
        new_order = {}
        for i in range(self.list_box.count()):
            item = self.list_box.item(i)
            cue_id = item.data(Qt.UserRole)
            if cue_id in data:
                new_order[cue_id] = data[cue_id]

        with open("score.json", "w", encoding="utf-8") as f:
            json.dump(new_order, f, indent=2, ensure_ascii=False)

        self.reload_list()
        current_item = self.list_box.currentItem()
        if current_item:
            self.activate_cue(current_item)

    def save_new_order(self):
        try:
            new_order = {}
            # Очищаем self.data и переупорядочиваем по cue_id
            for i in range(self.list_box.count()):
                item = self.list_box.item(i)
                cue_id = item.data(Qt.UserRole)
                if cue_id in self.data:
                    new_order[cue_id] = self.data[cue_id]

            self.data = new_order  # Обновляем текущие данные
            with open("score.json", "w", encoding="utf-8") as f:
                json.dump(new_order, f, indent=2, ensure_ascii=False)
            # self.main_window.update_current_cue()  # Удалено по заданию
        except Exception as e:
            print(f"Ошибка сохранения порядка Cue: {e}")

    def select_cue_by_id(self, cue_id):
        try:
            for i in range(self.list_box.count()):
                item = self.list_box.item(i)
                if item.data(Qt.UserRole) == cue_id:
                    self.list_box.setCurrentRow(i)
                    self.highlight_current_cue()
                    break
        except Exception as e:
            print(f"Ошибка выделения Cue: {e}")

    def highlight_current_cue(self):
        from PyQt5.QtGui import QColor
        for i in range(self.list_box.count()):
            item = self.list_box.item(i)
            cue_id = item.data(Qt.UserRole)
            if cue_id == self.main_window.current_cue_key:
                item.setBackground(QColor(80, 80, 80))
                item.setForeground(Qt.white)
            else:
                item.setBackground(QColor(0, 0, 0))
                item.setForeground(Qt.white)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)

    window = MainWindow()
    window.show()

    asyncio.ensure_future(window.setup_artnet())

    with loop:
        loop.run_forever()