"""
Integrated Linter for Aura Text
Provides real-time error/warning indicators using pylint
"""
import os
import sys
import subprocess
import threading
import platform
from typing import List, Dict, Tuple, Optional
import tempfile
import time
import hashlib
import atexit

from PyQt6.QtCore import QObject, pyqtSignal, QTimer
from PyQt6.QtGui import QColor
from PyQt6.Qsci import QsciScintilla

from io import StringIO
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
        self.tempdir = os.path.join(self.sysTempDir, f"pylint-run-{dir_string}")
        if not os.path.exists(self.tempdir):
            os.makedirs(self.tempdir)

        self._destroyed = False
        atexit.register(self.destroy)
    
    def destroy(self):
        if self._destroyed:
            return
        if os.path.exists(self.tempdir):
            try:
                os.rmdir(self.tempdir)
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
        write_file(filename, content, encoding='utf-8')
        try:
            Run([filename], reporter=reporter, exit=False)
        except Exception as e:
            print(f"Error running pylint: {e}")
            return []
        return reporter.messages
