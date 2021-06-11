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
        fields = []
        primarykey = None

        for k,v in attrs.items():
            if isinstance(v, Field):
                logging.info('found mapping: %s -> %s' % (k,v))
                mappings[k] = v
                if v.primary_key:
                    if primarykey:
                        raise RuntimeError('Duplicate primary key for filed: %s' %k)
                    primarykey = k
                else:
                    fields.append(k)
        
        if not primarykey:
            raise RuntimeError('primary key not found')
        
        for k in mappings.keys():
            attrs.pop(k)
        
        escaped_fields = list(map(lambda f: '`%s`' % f, fields))
        # map(square,[1,2,3,4,5]) 计算这个list里的平方 结果返回一个iterator
        attrs['__mappings__'] = mappings
        attrs['__table__'] = tableName
        attrs['__primary_key__'] = primarykey
        attrs['__fields__'] = fields
        attrs['__select__'] = 'select `%s`, %s from `%s`' % (primarykey, ','.join(escaped_fields), tableName)
        attrs['__insert__'] = 'insert into `%s` ( %s, `%s`) values (%s)' % (tableName, ','.join(escaped_fields), primarykey, create_args_string(len(escaped_fields)+1))
        attrs['__update__'] = 'update `%s` set %s where `%s` = ?' % (tableName, ','.join(map(lambda f : '`%s` = ?' % mappings.get(f).name or f, fields)), primarykey)
        attrs['__delete__'] = 'delete from `%s` where `%s` = ?' % (tableName, primarykey)


class Model(dict, metaclass = ModelMetaclass):
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

    @classmethod
    async def findAll(cls, where = None, args = None, **kw):
        sql = [cls.__select__]
        if where:
            sql.append('where')
            sql.append(where) #这里不会有注入的可能吗？
        if args is None:
            args = []
        
        orderBy = kw.get('orderBy', None)
        if orderBy:
            sql.append('order by')
            sql.append(orderBy) #为什么不添加在args?
        
        limit = kw.get('limit', None)
        if limit:
            sql.append('limit')
            if isinstance(limit,int):
                sql.append('?')
                args.append(limit)
            elif isinstance(limit,tuple) and len(limit) == 2:
                sql.append('?, ?')
                args.extend(limit)
            else:
                raise ValueError('Invalid limit value: %s' % str(limit))
            
        rs = await select(' '.join(sql), args)
        return [cls(**r) for r in rs]
    
    @classmethod
    async def findNumber(cls, selectField, where=None, args=None):
        sql = ['select %s _num_ from `%s`' % (selectField, cls.__table)]
        #这里的selectField是count(*)之类的?
        if where:
            sql.append('where')
            sql.append(where)
        rs = await select(' '.join(sql), args, 1)
        if len(rs) == 0:
            return None
        return rs[0]['_num_']
    
    @classmethod
    async def find(cls,pk):
        rs = await select('%s where `%s` = ?' % (cls.__select__, cls.__primary_key__))
        if len(rs) == 0:
            return None
        return cls(**rs[0])
    
    async def save(self):
        args = list(map(self.getValueOrDefault, self.__fields__))
        args.append(self.getValueOrDefault(self.__primary_key__))
        rows = await execute(self.__insert__, args)
        if rows != 1:
            logging.warning('failed to insert record: affected rows: %s' % rows)

    async def update(self):
        args = list(map(self.getValueOrDefault, self.__fields__))
        args.append(self.getValueOrDefault(self.__primary_key__))
        rows = await execute(self.__update__, args)
        if rows != 1:
            logging.warning('failed to update by primary key: affected rows: %s' % rows)

    async def remove(self):
        args = [self.getValue(self.__primary_key__)]
        rows = await execute(self.__delete__, args)
        if rows != 1:
            logging.warning('failed to remove by primary key: affected rows: %s' % rows)
        

    








