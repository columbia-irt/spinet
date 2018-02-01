import sys
import logging

DEBUG = logging.DEBUG
INFO = logging.INFO

root = logging.getLogger()
console = logging.StreamHandler(sys.stdout)
formatter = logging.Formatter('%(message)s')


def set_log_level(level):
    root.setLevel(level)
    console.setLevel(level)


def get_log_level():
    return root.getEffectiveLevel()


def setup():
    console.setFormatter(formatter)
    root.addHandler(console)

    set_log_level(logging.INFO)
