import logging
from . import db

log = logging.getLogger(__name__)


def initialize_db():
    c = db.cursor()
    c.execute('''
    CREATE TABLE IF NOT EXISTS net
     (id      INTEGER PRIMARY KEY AUTOINCREMENT,
      attrs   TEXT,
      created text    DEFAULT CURRENT_TIMESTAMP)
    ''')
    db.commit()
