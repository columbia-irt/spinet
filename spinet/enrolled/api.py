import logging
import sqlite3
import json
from   flask import Flask, jsonify, request
from time import sleep
from . import sup, db

log = logging.getLogger(__name__)


app = Flask(__name__)


# Intelligently apply new network configuration. Rollback to previous network
# configuration on errors.
def apply_network_configuration():
    prev = sup.list_networks()[0]

    ids = []
    try:
        for data in db.cursor().execute('SELECT attrs FROM net').fetchall():
            attrs = json.loads(data[0])

            if attrs['type'] == 'Open':
                attrs['key_mgmt'] = attrs.get('key_mgmt', 'NONE')

            del attrs['type']
            log.debug('Configuring network %s' % attrs['ssid'])
            ids.append(sup.create_network(attrs))

        log.debug('Enabling all newly configured networks')
        for id in ids:
            sup.enable_network(id)
    except Exception as e:
        logging.exception('Error while applying network configuration: %s', e)
        for id in ids:
            sup.remove_network(id)
        raise

    log.debug('Deleting previous network configuration')
    for row in prev:
        id = int(row[0])
        sup.remove_network(id)


@app.route('/')
def hello_world():
    return 'Enrolled'


@app.route('/net', methods=['GET'])
def list_networks():
    c = db.cursor()
    c.execute('SELECT id, attrs FROM net')
    data = [{**json.loads(attrs), **{'id': id}} for id, attrs in c.fetchall()]
    return jsonify(data)


@app.route('/net/<int:id>', methods=['GET'])
def get_network(id):
    c = db.cursor()
    c.execute('SELECT attrs FROM net WHERE id=?', (id,))
    attrs = json.loads(c.fetchone()[0])
    return jsonify({**attrs, **{'id': id}})


@app.route('/net/<int:id>', methods=['DELETE'])
def delete_network(id):
    c = db.cursor()
    c.execute('DELETE from net WHERE id=?', (id,))
    db.commit()
    return '', 204


@app.route('/net', methods=['POST'])
def add_network():
    data = request.get_json()

    try:
        del data['id']
    except KeyError:
        pass

    c = db.cursor()
    c.execute('INSERT INTO net (attrs) VALUES (?)', (json.dumps(data),))
    db.commit()

    return get_network(c.lastrowid)



@app.route('/apply', methods=['POST'])
def apply():
    sleep(2)
    apply_network_configuration()
    return '', 204
