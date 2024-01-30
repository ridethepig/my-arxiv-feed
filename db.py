import sqlite3
from dataclasses import dataclass

from arxivdata import ATOMItem, parse_atom

DB_PATH = "cache/arxivfeed.db"
create_table_querys = [
    '''
CREATE TABLE IF NOT EXISTS paper_meta (
    arxivid VARCHAR(20) PRIMARY KEY,
    id TEXT,
    updated TEXT,
    published TEXT,
    title TEXT,
    summary TEXT,
    author TEXT,
    comment TEXT,
    link_abs TEXT,
    link_pdf TEXT,
    category TEXT,
    primary_category TEXT
)
''',
    '''
CREATE TABLE IF NOT EXISTS translations (
    arxivid VARCHAR(20) PRIMARY KEY,
    title TEXT,
    abs TEXT
)
''',
    '''
CREATE TABLE IF NOT EXISTS daily (
    arxivid VARCHAR(20) PRIMARY KEY,
    arxivtime TEXT,
    category VARCHAR(16)
)
'''
]
conn: sqlite3.Connection = None


@dataclass
class TransItem:
    arxivid: str  # unique id
    title: str
    abs: str


@dataclass
class MainLogItem:
    arxivid: str
    arxivtime: str
    category: str


def paper_meta_get(arxivid: str) -> ATOMItem:
    select_query = "SELECT * FROM paper_meta WHERE arxivid = ?"
    result = conn.execute(select_query, (arxivid,)).fetchone()
    if result is not None:
        return ATOMItem(
            arxivid=result[0],
            id=result[1],
            updated=result[2],
            published=result[3],
            title=result[4],
            summary=result[5],
            author=result[6].split(','),  # 将逗号分隔的字符串转换为列表
            comment=result[7],
            link_abs=result[8],
            link_pdf=result[9],
            category=result[10].split(','),  # 将逗号分隔的字符串转换为列表
            primary_category=result[11]
        )
    else:
        return None


def paper_meta_set(atom_item: ATOMItem, force: bool = False):
    check_query = 'SELECT arxivid FROM paper_meta WHERE arxivid = ?'
    insert_replace_query = '''
    INSERT OR REPLACE INTO paper_meta VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    '''

    result = conn.execute(check_query, (atom_item.arxivid,)).fetchone()
    if result is not None and not force:
        return
    conn.execute(insert_replace_query, (
        atom_item.arxivid,
        atom_item.id,
        atom_item.updated,
        atom_item.published,
        atom_item.title,
        atom_item.summary,
        ','.join(atom_item.author),
        atom_item.comment,
        atom_item.link_abs,
        atom_item.link_pdf,
        ','.join(atom_item.category),
        atom_item.primary_category
    ))


def translation_get(arxivid):
    with conn:
        result = conn.execute('''
            SELECT * FROM translations WHERE arxivid = ?
        ''', (arxivid,)).fetchone()
        if result:
            return TransItem(*result)
        else:
            return None


def translation_set(translation: TransItem, force: bool = False):
    check_query = 'SELECT arxivid FROM translations WHERE arxivid = ?'
    insert_replace_query = '''INSERT OR REPLACE INTO translations VALUES (?, ?, ?)'''

    result = conn.execute(check_query, (translation.arxivid,)).fetchone()
    if result is not None and not force:
        return
    conn.execute(insert_replace_query, (
        translation.arxivid,
        translation.title,
        translation.abs
    ))


def daily_set(item: MainLogItem):
    insert_or_replace_query = '''
    INSERT OR REPLACE INTO daily VALUES (?, ?, ?)
    '''
    conn.execute(insert_or_replace_query, (
        item.arxivid,
        item.arxivtime,
        item.category
    ))


def daily_get_by_arxivid(arxivid):
    get_query = 'SELECT * FROM daily WHERE arxivid = ?'
    result = conn.execute(get_query, (arxivid,)).fetchone()
    if result:
        return MainLogItem(*result)
    else:
        return None


def daily_get_by_date(arxivtime: str):
    get_query = 'SELECT * FROM daily WHERE arxivtime = ?'
    results = conn.execute(get_query, (arxivtime,)).fetchall()
    return [result[0] for result in results]


def init_db():
    global conn
    conn = sqlite3.connect(DB_PATH)
    for create_table_query in create_table_querys:
        conn.execute(create_table_query)


def close_db():
    conn.close()


if __name__ == "__main__":
    with open("cache/fetch/2024-01-14-pagesize20-0af64b863fb1f3180514115e0030fe9a1626933c964da7a632635b0e74da0ab0.atom", "rb") as f:
        atom_str = f.read()
    atoms = parse_atom(atom_str=atom_str)
    for create_table_query in create_table_querys:
        conn.execute(create_table_query)
    paper_meta_set(atom_item=atoms[0])
    paper_meta_set(atom_item=atoms[1])
    paper_meta_set(atom_item=atoms[0])
    paper_meta_set(atom_item=atoms[3])
    print(paper_meta_get(atoms[0].arxivid))
    translation_set(TransItem("111", None, "shit"))
    print(translation_get("111"))
    conn.commit()
    conn.close()
