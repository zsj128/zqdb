import pymysql
try:
    conn=pymysql.connect(
        host="localhost",user='root',
        password='Aa@1233211234567',db='school'
    )
    cursor=conn.cursor()
    students=[(7,'李计',1),(8,'南宁',2)]
    sql="insert into student (id,name,c_id) values (%s,%s,%s)"
    cursor.executemany(sql,students)
    conn.commit()
    print(f'插入成功，影响行数：{cursor.rownumber}')
except pymysql.MySQLError as e:
    print(f'错误：{e}')
finally:
    cursor.close()
    conn.close()