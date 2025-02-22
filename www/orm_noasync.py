import  logging, pymysql

def log(sql,args=()):
    logging.info('SQL: %s' % sql)
'''
def create_pool(**kw):
    logging.info('create database connection pool...')
    global __pool
    __pool = pymysql.connect(
        host = kw.get('host', 'localhost'),
        port = kw.get('port', 9000),
        user = kw.get('user'),
        passwd = kw.get('password'),
        db = kw.get('db'),
    )
'''

def create_pool(Host, Username, pw, Db): #加上指定port就失败……为什么
    print('create database connection pool...')
    global __pool
    __pool = pymysql.connect(
        host = Host,
        user = Username,
        passwd = pw,
        db = Db)

def select(sql, args, size = None):
    log(sql,args)
    global __pool
    with  __pool as conn:
        cur = conn.cursor(pymysql.cursors.DictCursor) #以字典格式返回
        cur.execute(sql.replace('?','%s'), args or ())
        if size:
            rs = cur.fetchmany(size)
        else:
            rs = cur.fetchall()
        cur.close()
        logging.info('rows returned: %s' % len(rs))

        return rs

def execute(sql, args):
    log(sql,args)
    global __pool
    with __pool as conn:
        try:
            cur = conn.cursor()
            cur.execute(sql.replace('?','%s'), args or ())
            conn.commit()
            affected = cur.rowcount
            cur.close()
        except BaseException:
            raise
        return affected

def create_args_string(num):
    L = []
    for _ in range(num):
        L.append('?')
    return ','.join(L)

class Field(object):
    def __init__(self, name, column_type, primary_key, default):
        self.name = name
        self.column_type = column_type
        self.primary_key = primary_key
        self.default = default
    
    def __str__(self):
        return '<%s, %s:%s>' % (self.__class__.__name__, self.column_type, self.name)

class StringField(Field):
    def __init__(self, name = None, primary_key = False, default = None, column_type='varchar(100)'):
        super().__init__(name, column_type, primary_key, default)

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
        if name=='Model':
            return type.__new__(cls, name, bases, attrs)
        tableName = attrs.get('__table__', None) or name
        logging.info('found model: %s (table: %s)' % (name, tableName))
        mappings = dict()
        fields = []
        primaryKey = None
        for k, v in attrs.items():
            if isinstance(v, Field):
                logging.info('  found mapping: %s ==> %s' % (k, v))
                mappings[k] = v
                if v.primary_key:
                    if primaryKey:
                        raise RuntimeError('Duplicate primary key for field: %s' % k)
                    primaryKey = k
                else:
                    fields.append(k)
        if not primaryKey:
            raise RuntimeError('Primary key not found.')
        for k in mappings.keys():
            attrs.pop(k)
        escaped_fields = list(map(lambda f: '`%s`' % f, fields))
        attrs['__mappings__'] = mappings # 保存属性和列的映射关系
        attrs['__table__'] = tableName
        attrs['__primary_key__'] = primaryKey # 主键属性名
        attrs['__fields__'] = fields # 除主键外的属性名
        attrs['__select__'] = 'select `%s`, %s from `%s`' % (primaryKey, ', '.join(escaped_fields), tableName)
        attrs['__insert__'] = 'insert into `%s` (%s, `%s`) values (%s)' % (tableName, ', '.join(escaped_fields), primaryKey, create_args_string(len(escaped_fields) + 1))
        attrs['__update__'] = 'update `%s` set %s where `%s`=?' % (tableName, ', '.join(map(lambda f: '`%s`=?' % (mappings.get(f).name or f), fields)), primaryKey)
        attrs['__delete__'] = 'delete from `%s` where `%s`=?' % (tableName, primaryKey)
        return type.__new__(cls, name, bases, attrs)


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
    def findAll(cls, where = None, args = None, **kw):
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
            
        rs = select(' '.join(sql), args)
        return [cls(**r) for r in rs]
    
    @classmethod
    def findNumber(cls, selectField, where=None, args=None):
        sql = ['select %s _num_ from `%s`' % (selectField, cls.__table)]
        #这里的selectField是count(*)之类的?
        if where:
            sql.append('where')
            sql.append(where)
        rs = select(' '.join(sql), args, 1)
        if len(rs) == 0:
            return None
        return rs[0]['_num_']
    
    @classmethod
    def find(cls,pk):
        rs = select('%s where `%s` = ?' % (cls.__select__, cls.__primary_key__))
        if len(rs) == 0:
            return None
        return cls(**rs[0])
    
    def save(self):
        args = list(map(self.getValueOrDefault, self.__fields__))
        args.append(self.getValueOrDefault(self.__primary_key__))
        rows = execute(self.__insert__, args)
        if rows != 1:
            logging.warning('failed to insert record: affected rows: %s' % rows)

    def update(self):
        args = list(map(self.getValueOrDefault, self.__fields__))
        args.append(self.getValueOrDefault(self.__primary_key__))
        rows = execute(self.__update__, args)
        if rows != 1:
            logging.warning('failed to update by primary key: affected rows: %s' % rows)

    def remove(self):
        args = [self.getValue(self.__primary_key__)]
        rows = execute(self.__delete__, args)
        if rows != 1:
            logging.warning('failed to remove by primary key: affected rows: %s' % rows)
        

    








