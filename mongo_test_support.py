"""Tests use only a dedicated local replica set, never the private Atlas .env."""
import os,uuid
from pymongo import MongoClient
from storage import MongoStore

def test_store():
    uri=os.environ.get('MONGODB_TEST_URI','mongodb://127.0.0.1:27018/?replicaSet=tppl-test')
    # A caller may explicitly choose a CI replica set, but must never use the app DB.
    name='tppl_test_'+uuid.uuid4().hex
    client=MongoClient(uri,serverSelectionTimeoutMS=5000,connectTimeoutMS=5000)
    return MongoStore(client,name)

def clean(store):
    if not store.database.startswith('tppl_test_'):raise ValueError('Refusing to drop a non-test database')
    store.client.drop_database(store.database);store.close()
