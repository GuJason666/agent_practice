import sqlite3

conn = sqlite3.connect("users.db")
cursor = conn.cursor()
cursor.execute("DROP TABLE IF EXISTS users")
cursor.execute("""
        CREATE TABLE users(
            id INTEGER PRIMARY KEY,
            name TEXT,
            city TEXT,
            age INTEGER
        )
    """)
users = [
    (1, "张伟", "北京",28),
    (2, "王芳", "上海", 32),
    (3, "李伟", "广州", 25),
    (4, "刘洋", "深圳", 30),
    (5, "陈杰", "杭州", 27),
]
cursor.executemany("INSERT INTO users VALUES(?,?,?,?)", users)
conn.commit()
conn.close()
print("✅ 数据库创建完成，users.db 里有 6 条用户数据。")