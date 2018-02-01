import json
import logging
import sqlite3
from   . import db

log = logging.getLogger(__name__)


def initialize_db():
    c = db.cursor()

    c.execute('''
    CREATE TABLE IF NOT EXISTS net
     (id      INTEGER PRIMARY KEY AUTOINCREMENT,
      ssid    TEXT    NOT NULL,
      type    TEXT    NOT NULL CHECK (type IN ("Open", "WPA-PSK", "WPA2-802.1X")),
      attrs   TEXT,
      created text    DEFAULT CURRENT_TIMESTAMP)
    ''')
    c.execute('''
    CREATE INDEX IF NOT EXISTS ssid_idx ON net (ssid)
    ''')

    db.commit()


def add_net(ssid, type_='WPA-PSK', **kwargs):
    c = db.cursor()
    c.execute('INSERT INTO net (ssid, type, attrs) VALUES (?,?,?)',
              (ssid, type_, json.dumps(kwargs)))
    db.commit()


def remove_net(id):
    c = db.cursor()
    c.execute('DELETE FROM net WHERE id=?', (id,))
    db.commit()
