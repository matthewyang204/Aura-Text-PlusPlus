"""
Integrated Linter for Aura Text
Provides real-time error/warning indicators using pylint
"""
import os
import sys
import tempfile
import time
import hashlib
import atexit
import shutil
import getpass

from PyQt6.QtCore import Qt, QObject, pyqtSignal, QTimer
from PyQt6.QtWidgets import QDockWidget, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QPushButton
from PyQt6.QtGui import QColor
from PyQt6.Qsci import QsciScintilla

from pylint.lint import Run
from pylint.reporters import BaseReporter

from auratext.Misc.boilerplates import get_appdata_dirs
from auratext.Misc.import_res import notepadequalequalComponentImportPathAppend
sys.path.append(notepadequalequalComponentImportPathAppend)

from notepadequalequal.zencodings import write_file
local_app_data, script_dir = get_appdata_dirs()

class LintMessage:
    """Represents a single lint message"""
    def __init__(self, line: int, column: int, severity: str, message: str, linter: str, code: str = ""):
        self.line = line
        self.column = column
        self.severity = severity  # 'error', 'warning', 'info', 'convention'
        self.message = message
        self.linter = linter
        self.code = code

    def __repr__(self):
        return f"LintMessage(line={self.line}, severity={self.severity}, message={self.message})"

class CollectingReporter(BaseReporter):
    def __init__(self):
        super().__init__()
        self.messages = []

    def handle_message(self, msg):
        self.messages.append(msg)

    def display_messages(self, layout):
        pass

    def _display(self, layout):
        pass

class Linter(QObject):
    def __init__(self):
        super().__init__()
        self.finished = pyqtSignal(list)
        self.sysTempDir = tempfile.gettempdir()
        dir_string = hashlib.sha256(str(time.time()).encode()).hexdigest()[:8]
        user_string = getpass.getuser()
        self.tempdir = os.path.join(self.sysTempDir, f"pylint-run-{user_string}-{dir_string}")
        if not os.path.exists(self.tempdir):
            os.makedirs(self.tempdir)

        self._destroyed = False
        atexit.register(self.destroy)
    
    def destroy(self):
        if self._destroyed:
            return
        if os.path.exists(self.tempdir):
            try:
                shutil.rmtree(self.tempdir)
                print("Cleaned up code linter temp directory successfully.")
                self._destroyed = True
            except Exception as e:
                print(f"Error cleaning up temp directory: {e}")

    def __del__(self):
        self.destroy()

    def generate_timehash(self):
        return hashlib.sha256(str(time.time()).encode()).hexdigest()[:8]

    def run(self, content):
        messages = self.run_pylint(content)
        return messages
        
    def run_pylint(self, content):
        reporter = CollectingReporter()
        timehash = self.generate_timehash()
        filename = os.path.join(self.tempdir, f"{timehash}.py")
        write_file(content, filename, encoding='utf-8')
        try:
            Run([filename], reporter=reporter, exit=False)
        except Exception as e:
            print(f"Error running pylint: {e}")
            return []
        return reporter.messages

class LinterMessageItem(QDockWidget):
    def __init__(self, messages, parent=None):
        super().__init__('Linter Messages', parent)
        self.messages = messages
        self.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)
        self._last_status_snapshot = None
        self.parent = parent

        self.main_widget = QWidget()
        self.main_layout = QVBoxLayout(self.main_widget)
        self.header_layout = QHBoxLayout()
        self.button_layout = QHBoxLayout()
        self.main_layout.addLayout(self.button_layout)
        self.main_layout.addLayout(self.header_layout)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        # Top buttons
        self.reanalyze_button = QPushButton("Force Reanalyzation")
        self.reanalyze_button.clicked.connect(self.reanalyze)
        self.button_layout.addWidget(self.reanalyze_button)

        # Header
        header = QLabel("Linting Results")
        header.setStyleSheet(f"""
            QLabel {{
                padding: 8px 12px;
                font-size: 11px;
                font-weight: normal;
                letter-spacing: 0.5px;
            }}
        """)

        self.header_layout.addWidget(header)

        self.message_display = QWidget()
        self.message_layout = QVBoxLayout(self.message_display)
        self.message_layout.setContentsMargins(0, 0, 0, 0)
        self.message_layout.setSpacing(0)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setWidget(self.message_display)

        self.lint_timer = QTimer(self)
        self.lint_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.lint_timer.setSingleShot(True)
        self.lint_timer.timeout.connect(self.reanalyze)
        self.parent.current_editor.textChanged.connect(self.live)

        self.main_layout.addWidget(self.scroll)

        self.setWidget(self.main_widget)

        # Uninitialized widgets
        self.msg_label = None

    def __repr__(self):
        return f"LinterMessageItem(messages={self.messages})"

    def display(self, messages=None):
        if messages is None:
            messages = self.messages
        else:
            self.messages = messages
        print("Linting results:")
        lintMsgStr = ""
        for msg in messages:
            severity = msg.msg_id[0].upper()

            print(f"{severity}: Line {msg.line}, Col {msg.column}: {msg.msg} ({msg.msg_id}:{msg.symbol})")

            new_line = f"{severity}: Line {msg.line}, Col {msg.column}: {msg.msg} ({msg.msg_id}:{msg.symbol})"
            lintMsgStr += new_line + '\n\n'
        
        if self.msg_label is None:
            self.msg_label = QLabel(lintMsgStr)
            self.msg_label.setStyleSheet(f"""
                QLabel {{
                    padding: 6px 10px;
                    font-size: 10px;
                    font-weight: normal;
                    letter-spacing: 0.5px;
                }}
            """)
            self.msg_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            self.message_layout.addWidget(self.msg_label)
        else:
            self.msg_label.setText(lintMsgStr)

    def reanalyze(self):
        if self.parent.current_editor is None or self.parent.current_editor.linter is None:
            print("WARNING: Not linting due to current editor not having a 'linter' object")
            return
        messages = self.parent.current_editor.linter.run(self.parent.current_editor.text())
        self.display(messages=messages)

    def live(self):
        self.lint_timer.stop()
        self.lint_timer.start(500)