import sys


class TerminalLogger(object):
    def __init__(self, filename="src/logs/terminal.log"):
        self.terminal = sys.__stdout__
        self.log = open(filename, "a", encoding="utf-8", buffering=1)

    def write(self, message):
        self.terminal.write(message)
        self.log.write(message)
        self.log.flush()

    def flush(self):
        self.terminal.flush()
        self.log.flush()
