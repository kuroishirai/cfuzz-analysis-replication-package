import psycopg2
from psycopg2.extras import execute_values  # ←ファイルの最初の方にこれをimportして


class DB:
    def __init__(self, database, user, password, host, port):
        self.database = database
        self.user = user
        self.password = password
        self.host = host
        self.port = port

        self.connection = None
        self.cursor = None

    def executeQuery(self, queryType, query):
        if queryType.lower() == "select":
            self.cursor.execute(query)
            result = self.cursor.fetchall()
            return result

        elif queryType.lower() == "insert" or queryType.lower() == "update":
            self.cursor.execute(query)
            self.connection.commit()

    def connect(self):
        self.connection = psycopg2.connect(database=self.database, user=self.user, password=self.password, host=self.host, port=self.port)
        self.cursor = self.connection.cursor()

    def closeConnection(self):
        self.connection.close()

    def executeMany(self, query, values):
        self.cursor.executemany(query, values)
        self.connection.commit()
        
    def executeValues(self, query, values):
        execute_values(self.cursor, query, values)
        self.connection.commit()