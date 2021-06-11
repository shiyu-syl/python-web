import asyncio, logging, aiomysql

def log(sql,args=()):
    logging.info('SQL: %s' % sql)

async def create_pool(loop, **kw):
    logging.info('create database connection pool...')
    global __pool
    __pool = await aiomysql.create_pool(
        host = kw.get('host', 'locolhost'),
        port = kw.get('port', 8000),
        user = kw.get('user'),
        pw = kw.get('password'),
        db = kw.get('db'),
        charset = kw.get('charset', 'utf8'),
        autocommit=kw.get('autocommit', True),
        maxsize=kw.get('maxsize', 10),
        minsize=kw.get('minsize', 1),
        loop=loop
    )

async def select(sql, args, size = None):
    log(sql,args)
    global __pool
    with (await __pool) as conn:
        cur = await conn.cursor(aiomysql.DictCursor) #以字典格式返回
        await cur.execute(sql.replace('?','%s'), args or ())
        if size:
            rs = await cur.fetchmany(size)
        else:
            rs = await cur.fetchall()
        await cur.close()
        logging.info('rows returned: %s' % len(rs))

        return rs

async def execute(sql, args):
    log(sql,args)
    global __pool
    with (await __pool) as conn:
        try:
            cur = await conn.cursor()
            await cur.execute(sql.replace('?','%s'), args or ())
            affected = cur.rowcount
            await cur.close()
        except BaseException:
            raise
        return affected

def create_args_string(num):
    L = []
    for _ in range(num):
        L.append('?')
    return ','.join(L)

class Field(object):
    def __init__(self, name, colume_type, primary_key, default):
        self.name = name
        self.colume_type = colume_type
        self.primary_key = primary_key
        self.default = default
    
    def __str__(self):
        return '<%s, %s:%s>' % (self.__class__.__name__, self.column_type, self.name)

class StringField(Field):
    def __init__(self, name = None, primary_key = False, default = None, colume_type='varchar(100)'):
        super().__init__(name, colume_type, primary_key, default)

class BooleanField(Field):
    def __init__(self, name = None,  default = False):
        super().__init__(name, 'boolean', False, default)

class IntegerField(Field):
    def __init__(self, name = None, primary_key = False, default = 0):
        super().__init__(name, 'bigint', primary_key, default)

class FloatField(Field):
    def __init__(self, name = None, primary_key = False, default = 0.0):
        super().__init__(name, 'real', primary_key, default)

class TextField(Field):
    def __init__(self, name = None, default = None):
        super().__init__(name, 'text', False, default)


class ModelMetaclass(type):
    def __new__(cls, name, bases, attrs):
        if name == 'Model':
            return type.__new__(cls, name, bases, attrs)
        tableName = attrs.get('__table__', None) or name
        logging.info('found model: %s (table: %s)' % (name, tableName))

        mappings = dict()
        fileds = []
        primarykey = None


class Model(dict,metaclass = ModelMetaclass):
    def __init__(self, **kw):
        super().__init__(**kw)
    
    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(r"'Model' object has no attribute '%s'" % key)
    
    def __setattr__(self, key, value):
        self[key] = value
    
    def getValue(self, key):
        return getattr(self, key, None)

    def getValueOrDefault(self, key):
        value = getattr(self, key, None)
        if value is None:
            field = self.__mappings__[key]
            if field.default is not None:
                value = field.default() if callable(field.default) else field.default
                logging.debug('using default value for %s: %s' % (key, str(value)))
                setattr(self, key, value)
        
        return value








