"""Read private database settings without logging the connection URI."""
import os
from pathlib import Path

ROOT=Path(__file__).resolve().parent

def settings():
    values={}
    path=ROOT/'.env'
    if path.exists():
        for line in path.read_text(encoding='utf-8').splitlines():
            if line.strip() and not line.lstrip().startswith('#') and '=' in line:
                key,value=line.split('=',1);values[key.strip()]=value.strip().strip('"').strip("'")
    for key in ('MONGODB_URI','MONGODB_DATABASE'):
        if key in os.environ:values[key]=os.environ[key]
    if not values.get('MONGODB_URI'):raise ValueError('Set MONGODB_URI in the private .env file or environment')
    name=values.get('MONGODB_DATABASE','tppl_erp')
    if not name or len(name)>63 or any(x in name for x in '/\\. "$*<>:|?'):
        raise ValueError('MONGODB_DATABASE must be a valid database name')
    return values['MONGODB_URI'],name

def client():
    from pymongo import MongoClient
    uri,name=settings()
    return MongoClient(uri,serverSelectionTimeoutMS=8000,connectTimeoutMS=8000,socketTimeoutMS=20000,maxPoolSize=20),name

if __name__=='__main__':
    from pymongo.errors import PyMongoError,OperationFailure
    connection=None
    try:
        connection,name=client()
        connection.admin.command('ping')
        collections=connection[name].list_collection_names()
        print('MongoDB connection authenticated. Target database:',name)
        print('Target collections:',', '.join(collections) if collections else '(empty)')
    except OperationFailure as e:
        print('MongoDB authentication/permission error. Code:',e.code)
        raise SystemExit(1)
    except PyMongoError as e:
        print('MongoDB is not reachable:',type(e).__name__,'Check Atlas network access and the cluster address.')
        raise SystemExit(1)
    finally:
        if connection is not None:connection.close()
