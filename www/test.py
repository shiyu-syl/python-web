import orm_noasync
from models import User, Testing
import logging
import pymysql
logging.basicConfig(level=logging.INFO)


def test():
    orm_noasync.create_pool(Username='root', pw='123456', Db='awesome', Host = 'localhost')

    print(type(User))
    u = User(name='Test2', email='test2@qq.com', passwd='12345678902', image='about:blank2')
    u.save()


if __name__ == '__main__':
    test()