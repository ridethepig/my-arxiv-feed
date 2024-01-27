from peewee import *
from arxivdata import ATOMItem, parse_atom

db = SqliteDatabase("cache/arxiv.db")


class BaseModel(Model):
    class Meta:
        database = db


class Translation(BaseModel):
    arxiv_id = CharField(20, unique=True)
    trs_title = TextField(null=True)
    trs_abs = TextField(null=True)


class Metadata(BaseModel):
    id_short = CharField(20, unique=True)
    id = TextField()
    updated = CharField(64)
    published = CharField(64)
    title = TextField()
    summary = TextField()
    author = TextField()
    comment = TextField(null=True)
    link_abs = TextField()
    link_pdf = TextField()
    category = TextField()
    primary_category = CharField(20)


def translation_get(arxiv_id: str):
    query = Translation.select().where(Translation.arxiv_id == arxiv_id)
    if len(query) == 0:
        return None, None
    assert len(query) == 1
    for entry in query:
        return entry.trs_title, entry.trs_abs


def translation_save(arxiv_id: str, title: str = None, abstract: str = None):
    assert title or abstract
    query: ModelSelect = Translation.select().where(Translation.arxiv_id == arxiv_id)
    if len(query) == 0:
        Translation.create(arxiv_id=arxiv_id, trs_title=title, trs_abs=abstract)
    else:
        assert len(query) == 1
        for entry in query:
            if title:
                entry.trs_title = title
            if abstract:
                entry.trs_abs = abstract
            entry.save()


def metadata_get(arxiv_id: str) -> ATOMItem | None:
    print(f"get{arxiv_id}")
    query = Metadata.select().where(Metadata.id_short == arxiv_id)
    if len(query) == 0:
        return None
    assert len(query) == 1
    for entry in query:
        return ATOMItem(
            id=entry.id,
            id_short=entry.id_short,
            updated=entry.updated,
            published=entry.published,
            title=entry.title,
            summary=entry.summary,
            author=entry.author.split(","),
            comment=entry.comment,
            link_abs=entry.link_abs,
            link_pdf=entry.link_pdf,
            category=entry.category.split(","),
            primary_category=entry.primary_category,
        )


def metadata_save(metadata: ATOMItem):
    print(f"save{metadata.id_short}")
    query = Metadata.select().where(Metadata.id_short == metadata.id_short)
    record = Metadata(
            id_short=metadata.id_short,
            id=metadata.id,
            updated=metadata.updated,
            published=metadata.published,
            title=metadata.title,
            summary=metadata.summary,
            author=",".join(metadata.author),
            comment=metadata.comment,
            link_abs=metadata.link_abs,
            link_pdf=metadata.link_pdf,
            category=",".join(metadata.category),
            primary_category=metadata.primary_category,
        )
    if len(query) == 0:
        record.save(force_insert=True)
    else:
        record.save()


db.create_tables([Translation, Metadata])

if __name__ == "__main__":
    # trslt = Trslt.create(arxiv_id = "1111.11231v2")
    translation_save("1111", title="你", abstract="Shit")
    print(translation_get("1111"))
    import datetime
    print(datetime.datetime.now())
    with open("cache/fetch/2024-01-14-pagesize20-0af64b863fb1f3180514115e0030fe9a1626933c964da7a632635b0e74da0ab0.atom", "rb") as f:
        atom_str = f.read()
    atoms = parse_atom(atom_str=atom_str)
    print(datetime.datetime.now())
    metadata_save(atoms[0])
    metadata_save(atoms[1])
    metadata_save(atoms[2])
    print(datetime.datetime.now())
    print(metadata_get(atoms[0].id_short))
    print(metadata_get(atoms[1].id_short))
    print(metadata_get(atoms[2].id_short))
    print(datetime.datetime.now())

