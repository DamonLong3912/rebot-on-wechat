import json

import pymysql
import redis

from common.log import logger


def select_user(remark_name=None, attr_status=None):
    # 打开数据库连接
    db = pymysql.connect(host='43.133.70.210',
                         user='root',
                         password='qqa520',
                         database='wechat-gpt',
                         charset='utf8mb4',
                         cursorclass=pymysql.cursors.DictCursor)
    try:
        # 使用 cursor() 方法创建一个游标对象 cursor
        cursor = db.cursor()
        # 使用 execute()  方法执行 SQL 查询
        if remark_name is not None and remark_name != '':
            cursor.execute(f"select * from wechat_user where remark_name='{remark_name}'")
        elif attr_status is not None and attr_status != '':
            cursor.execute(f"select * from wechat_user where attr_status='{attr_status}'")

        # 使用 fetchone() 方法获取单条数据.
        data = cursor.fetchone()

        return data
    except Exception as e:
        logger.warn("[WX] mysql failed: " + str(e))
        return None
    finally:
        db.close()


def insert_user(remark_name: str, recharge_amount: float, attr_status: str):
    # 打开数据库连接
    db = pymysql.connect(host='43.133.70.210',
                         user='root',
                         password='qqa520',
                         database='wechat-gpt',
                         charset='utf8mb4',
                         cursorclass=pymysql.cursors.DictCursor)
    try:
        # 使用 cursor() 方法创建一个游标对象 cursor
        cursor = db.cursor()

        if remark_name is None or remark_name == '':
            remark_name = attr_status

        # 使用 execute()  方法执行 SQL 查询
        cursor.execute(
            f"INSERT INTO wechat_user (remark_name, recharge_amount,attr_status) VALUES ('{remark_name}', {recharge_amount},'{attr_status}') ON DUPLICATE KEY UPDATE recharge_amount = recharge_amount+{recharge_amount}")

        # 提交事务
        db.commit()
        return True
    except pymysql.MySQLError as e:
        # 处理异常
        logger.warn("[WX] mysql failed: " + str(e))
        return False
    except Exception as e:
        logger.warn("[WX] mysql failed: " + str(e))
        return False
    finally:
        db.close()

def uptdate_user(id,remark_name: str, attr_status: str):
    # 打开数据库连接
    db = pymysql.connect(host='43.133.70.210',
                         user='root',
                         password='qqa520',
                         database='wechat-gpt',
                         charset='utf8mb4',
                         cursorclass=pymysql.cursors.DictCursor)
    try:
        # 使用 cursor() 方法创建一个游标对象 cursor
        cursor = db.cursor()


        # 使用 execute()  方法执行 SQL 查询
        cursor.execute(
            f"UPDATE wechat_user SET remark_name='{remark_name}', attr_status='{attr_status}' WHERE id={id}")

        # 提交事务
        db.commit()
        return True
    except pymysql.MySQLError as e:
        # 处理异常
        logger.warn("[WX] mysql failed: " + str(e))
        return False
    except Exception as e:
        logger.warn("[WX] mysql failed: " + str(e))
        return False
    finally:
        db.close()


# 扣费
def fee_deduction(remark_name, rmb_total_price: float, attr_status: str):
    # 打开数据库连接
    db = pymysql.connect(host='43.133.70.210',
                         user='root',
                         password='qqa520',
                         database='wechat-gpt',
                         charset='utf8mb4',
                         cursorclass=pymysql.cursors.DictCursor)
    try:
        # 使用 cursor() 方法创建一个游标对象 cursor
        cursor = db.cursor()
        # 使用 execute()  方法执行 SQL 查询

        if remark_name is not None and remark_name !='':
            cursor.execute(
                f"update wechat_user set quota_used=quota_used+{rmb_total_price} where remark_name='{remark_name}'")
        else:
            cursor.execute(
                f"update wechat_user set quota_used=quota_used+{rmb_total_price} where attr_status='{attr_status}'")

        # 提交事务
        db.commit()
        return True
    except pymysql.MySQLError as e:
        # 处理异常
        logger.warn(f"[WX] {remark_name}： 充值异常: " + str(e))
        return False
    except Exception as e:
        logger.warn(f"[WX] {remark_name}：充值异常: " + str(e))
        return False
    finally:
        db.close()

# # 如果你知道Redis容器的IP地址
# redis_ip = '127.0.0.1'  # 示例IP地址，根据实际情况替换
# redis_port = 6379
#
# # 连接到Redis
# r = redis.StrictRedis(host=redis_ip, port=redis_port, decode_responses=True,password='difyai123456')
#
# # 测试连接
# r.set('test', '100')
# print(r.get('test'))
