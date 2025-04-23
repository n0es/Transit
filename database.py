import sqlite3

if __name__ == '__main__':
    conn = sqlite3.connect('transit.db')
    c = conn.cursor()

    c.execute('''INSERT INTO vehicles ''')