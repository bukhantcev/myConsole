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

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Мой пульт ArtNet")
        self.setGeometry(100, 100, 640, 300)

        self.channels = []

        # Кнопка Clear (канал 1)
        self.clear_button = QPushButton("X", self)
        self.clear_button.setGeometry(20, 30, 60, 30)
        self.clear_button.clicked.connect(self.send_clear)

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

        self.score_button = QPushButton("Партитура", self)
        self.score_button.setGeometry(490, 260, 120, 30)
        self.score_button.clicked.connect(self.score_window.show)

        self.advance_cue_number()

        self.current_cue_key = None

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
        self.channels[channel_index].set_fade([value], 0)
        self.channels[channel_index]._target = [value]

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
        levels = {f"channel_{i+1}": ch.get_values()[0] for i, ch in enumerate(self.channels)}
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

        levels = {f"channel_{i+1}": ch.get_values()[0] for i, ch in enumerate(self.channels)}
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
                self.main_window.update_dmx(cue.get(f"channel_{i+1}", 0), i)
                val = cue.get(f"channel_{i+1}", 0)
                if i == 0:
                    self.main_window.clear_button.setDown(val > 127)
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

if __name__ == "__main__":
    app = QApplication(sys.argv)
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)

    window = MainWindow()
    window.show()

    asyncio.ensure_future(window.setup_artnet())

    with loop:
        loop.run_forever()