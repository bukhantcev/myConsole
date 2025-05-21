from PyQt5.QtCore import QEvent
import sys
import asyncio
from PyQt5.QtWidgets import QApplication, QMainWindow, QSlider, QPushButton, QComboBox, QDialog, QTextEdit
from PyQt5.QtCore import Qt, QTimer
from qasync import QEventLoop
from pyartnet import ArtNetNode
from PyQt5.QtWidgets import QLineEdit, QLabel
import json
from PyQt5.QtWidgets import QDialog, QListWidget
from PyQt5.QtWidgets import QMenu, QAction

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Мой пульт ArtNet")
        self.setGeometry(100, 100, 640, 300)

        self.channels = []


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
        self.node = ArtNetNode('127.0.0.1', port=6454)
        universe = self.node.add_universe(0)
        self.channels = [universe.add_channel(start=i + 1, width=1) for i in range(4)]
        self.node.start_refresh()

    def update_dmx(self, value, channel_index):
        if not self.channels:
            return
        # всегда сохраняем в _target
        self.channels[channel_index]._target = [value]
        if not self.blinde_state:
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
                self.current_cue_key = self.blinde_active_cue_key
                self.cue_name_input.setText(cue_data["name"])
                # выделить текущую Cue в списке
                self.score_window.select_cue_by_id(self.current_cue_key)
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

        self.reload_list()

    def reload_list(self):
        self.list_box.clear()
        try:
            with open("score.json", "r", encoding="utf-8") as f:
                data = json.load(f)
            for idx, (cue_id, cue_data) in enumerate(data.items(), 1):
                name = cue_data.get("name", f"Cue {idx}")
                self.list_box.addItem(f"{idx}. {name}")
        except FileNotFoundError:
            self.list_box.addItem("Нет сохранённых Cue")

    def activate_cue(self, item):
        try:
            cue_name = item.text()
            if ". " in cue_name:
                cue_name = cue_name.split(". ", 1)[1]

            # Найти cue_id по порядку в списке
            cue_index = self.list_box.row(item)

            with open("score.json", "r", encoding="utf-8") as f:
                data = list(json.load(f).items())

            if cue_index >= len(data):
                return

            cue_key, cue_data = data[cue_index]
            cue = cue_data["levels"]
            self.main_window.current_cue_key = cue_key
            self.main_window.cue_name_input.setText(cue_data["name"])

            for i, ch in enumerate(self.main_window.channels):
                if not self.main_window.blinde_state:
                    self.main_window.update_dmx(cue.get(f"channel_{i+1}", 0), i)
                val = cue.get(f"channel_{i+1}", 0)
                if i == 0:
                    pass  # канал 1 (Clear) не отображается в интерфейсе
                elif i == 1:
                    self.main_window.opacity_slider.setValue(val)
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
                current_row = self.list_box.currentRow()
                if current_row < self.list_box.count() - 1:
                    self.list_box.setCurrentRow(current_row + 1)
                    self.activate_cue(self.list_box.currentItem())
                return True
            elif event.key() == Qt.Key_Left:
                current_row = self.list_box.currentRow()
                if current_row > 0:
                    self.list_box.setCurrentRow(current_row - 1)
                    self.activate_cue(self.list_box.currentItem())
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

    def select_cue_by_id(self, cue_id):
        try:
            with open("score.json", "r", encoding="utf-8") as f:
                data = list(json.load(f).items())
            for idx, (key, _) in enumerate(data):
                if key == cue_id:
                    self.list_box.setCurrentRow(idx)
                    break
        except Exception as e:
            print(f"Ошибка выделения Cue: {e}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)

    window = MainWindow()
    window.show()

    asyncio.ensure_future(window.setup_artnet())

    with loop:
        loop.run_forever()