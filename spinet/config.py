

class Config(object):
    def __init__(self, db):
        self.db = db

        c = db.cursor()
        c.execute('''
        CREATE TABLE IF NOT EXISTS config
        (id      INTEGER PRIMARY KEY AUTOINCREMENT,
        name    TEXT UNIQUE,
        value   TEXT)
        ''')
        db.commit()


    def __setitem__(self, key, value):
        c = self.db.cursor();
        c.execute('INSERT INTO config (name, value) VALUES (?, ?)', (key, value))
        self.db.commit()


    def __getitem__(self, key):
        c = self.db.cursor();
        c.execute('SELECT value FROM config where name=?', (key,))
        row = c.fetchone()
        if row is None:
            raise KeyError(key)
        return row[0]


    def __delitem__(self, key):
        c = self.db.cursor()
        c.execute('DELETE FROM config where name=?', (key,))
        self.db.commit()


    def clear(self):
        c = self.db.cursor()
        c.execute('DELETE FROM config')
        self.db.commit()
