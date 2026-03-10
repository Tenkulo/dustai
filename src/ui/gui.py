import sys
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QLineEdit, QPushButton, QLabel, QSizePolicy
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette

class DUSTAIGUI(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('DUST AI - Autonomous Agent')
        self.setGeometry(100, 100, 800, 600)
        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout()

        # Output Display (Scrollable)
        self.output_display = QTextEdit()
        self.output_display.setReadOnly(True)
        self.output_display.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        main_layout.addWidget(self.output_display)

        # Status Bar / Controls
        control_layout = QHBoxLayout()

        # Model Status Indicator
        self.status_indicator = QLabel()
        self.status_indicator.setFixedSize(20, 20)
        self.set_status(False)  # Initial status: red (offline)
        control_layout.addWidget(self.status_indicator)

        # Agent/Chat Mode Button
        self.mode_button = QPushButton('Agent Mode')
        self.mode_button.setCheckable(True)
        self.mode_button.setChecked(True) # Default to Agent Mode
        self.mode_button.clicked.connect(self.toggle_mode)
        control_layout.addWidget(self.mode_button)

        # Spacer to push elements to left
        control_layout.addStretch(1)

        main_layout.addLayout(control_layout)

        # Chat Input
        input_layout = QHBoxLayout()
        self.chat_input = QLineEdit()
        self.chat_input.setPlaceholderText('Type your message here...')
        self.chat_input.returnPressed.connect(self.send_message)
        input_layout.addWidget(self.chat_input)

        self.send_button = QPushButton('Send')
        self.send_button.clicked.connect(self.send_message)
        input_layout.addWidget(self.send_button)

        main_layout.addLayout(input_layout)

        self.setLayout(main_layout)

    def toggle_mode(self):
        if self.mode_button.isChecked():
            self.mode_button.setText('Agent Mode')
            self.append_output('Mode switched to: Agent')
        else:
            self.mode_button.setText('Chat Mode')
            self.append_output('Mode switched to: Chat')

    def send_message(self):
        message = self.chat_input.text()
        if message:
            self.append_output(f'[You]: {message}')
            self.chat_input.clear()
            # In a real app, you'd send this message to your backend/agent

    def append_output(self, text):
        self.output_display.append(text)

    def set_status(self, is_online: bool):
        palette = self.status_indicator.palette()
        if is_online:
            palette.setColor(self.status_indicator.backgroundRole(), QColor('green'))
        else:
            palette.setColor(self.status_indicator.backgroundRole(), QColor('red'))
        self.status_indicator.setPalette(palette)
        self.status_indicator.setAutoFillBackground(True)
        self.status_indicator.setStyleSheet("border-radius: 10px;") # Make it circular


if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = DUSTAIGUI()
    window.show()
    sys.exit(app.exec())