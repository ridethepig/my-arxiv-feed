from dataclasses import dataclass

import lxml.etree as etree

import utils
from utils import logger

ABS_PREFIX = "http://arxiv.org/abs/"


@dataclass
class RSSItem:
    title: str
    link: str
    desc: str
    author: str
    id_short: str

    def is_update(self) -> bool:
        return self.title.find("UPDATED)") != -1


@dataclass
class RSSMeta:
    title: str
    description: str
    update_date: str
    subject: str


@dataclass
class RSSMetaNew:
    title: str
    description: str
    lastBuildDate: str
    pubDate: str

@dataclass
class RSSItemNew:
    arxivid: str
    title: str
    link: str
    description: str
    announcetype: str
    authors: str
    
    def is_update(self) -> bool:
        return self.announcetype.find("new") != -1
    def is_crosslist(self) -> bool:
        return self.announcetype.find("cross") != -1

@dataclass
class ATOMItem:
    arxivid: str
    id: str
    updated: str
    published: str
    title: str
    summary: str
    author: list[str]
    comment: str | None
    link_abs: str
    link_pdf: str
    category: list[str]
    primary_category: str

    def is_update(self) -> bool:
        return self.updated != self.published


def parse_atom(atom_str: str) -> list[ATOMItem]:
    atom = etree.XML(atom_str)
    nsmap = atom.nsmap
    nsmap["ns"] = nsmap[None]
    nsmap["arxiv"] = "http://arxiv.org/schemas/atom"
    del nsmap[None]  # none key is not allow in lxml xpath
    entries = atom.xpath("/ns:feed/ns:entry", namespaces=nsmap)
    query_results = []
    for entry in entries:
        id = entry.xpath("./ns:id", namespaces=nsmap)[0].text
        assert id.startswith(ABS_PREFIX)
        id_short = id.removeprefix(ABS_PREFIX)
        updated = entry.xpath("./ns:updated", namespaces=nsmap)[0].text
        published = entry.xpath("./ns:published", namespaces=nsmap)[0].text
        title = entry.xpath("./ns:title", namespaces=nsmap)[0].text
        summary = entry.xpath("./ns:summary", namespaces=nsmap)[0].text

        comment_elems = entry.xpath("./arxiv:comment", namespaces=nsmap)
        comment = None if len(comment_elems) == 0 else comment_elems[0].text

        author_elems = entry.xpath("./ns:author/ns:name", namespaces=nsmap)
        authors = [elem.text for elem in author_elems]

        link_abs = entry.xpath("./ns:link[@rel='alternate']", namespaces=nsmap)[0].attrib["href"]
        link_pdf = entry.xpath("./ns:link[@title='pdf']", namespaces=nsmap)[0].attrib["href"]

        primary_category = entry.xpath("./arxiv:primary_category",
                                       namespaces=nsmap)[0].attrib["term"]
        category_elems = entry.xpath("./ns:category", namespaces=nsmap)
        categories = [elem.attrib["term"] for elem in category_elems]

        atom_item = ATOMItem(
            id=id,
            arxivid=id_short,
            updated=updated,
            published=published,
            title=title.replace('\n', ''),
            summary=summary,
            author=authors,
            comment=comment,
            link_abs=link_abs,
            link_pdf=link_pdf,
            category=categories,
            primary_category=primary_category,
        )
        query_results.append(atom_item)
    return query_results


def parse_rss_new(rss_str: str) -> tuple[RSSMetaNew, list[RSSItemNew]]:
    xml = etree.XML(rss_str)
    nsmap = xml.nsmap
    def get_text(item, xpath: str) -> str: return item.xpath(xpath,  namespaces=nsmap)[0].text

    rss_chan = xml.xpath("/rss/channel")[0]

    meta_title = get_text(rss_chan, "./title")
    meta_description = get_text(rss_chan, "./description")
    meta_lastBuildDate = get_text(rss_chan, "./lastBuildDate")
    meta_pubDate = get_text(rss_chan, "./pubDate")
    rss_meta = RSSMetaNew(title=meta_title,
                          description=meta_description,
                          lastBuildDate=meta_lastBuildDate,
                          pubDate=meta_pubDate)
    logger.debug(rss_meta)

    items = rss_chan.xpath("./item", namespaces=nsmap)
    rss_items = list()
    logger.info(f"{meta_title} {len(items)} Updates")
    for item in items:
        item_title = get_text(item, "title")
        item_link = get_text(item, "link")
        item_description = get_text(item, "./description")
        item_announce_type = get_text(item, "./arxiv:announce_type")
        item_guid = get_text(item, "./guid")
        item_authors = item.xpath("./dc:creator", namespaces=nsmap)

        _authors = ",".join([_author.text for _author in item_authors])
        _arxivid = item_guid.split(":")[-1]
        rss_item = RSSItemNew(
            arxivid=_arxivid,
            title=item_title,
            link=item_link,
            description=item_description,
            announcetype=item_announce_type,
            authors=_authors
        )
        rss_items.append(rss_item)
        logger.debug(f"  {item_title}")
    
    return rss_meta, rss_items


def parse_rss(rss_str: str) -> tuple[RSSMeta, list[RSSItem]]:
    xml = etree.XML(rss_str)
    nsmap = xml.nsmap
    nsmap["ns"] = nsmap[None]
    del nsmap[None]  # none key is not allow in lxml xpath
    title = xml.xpath("/rdf:RDF/ns:channel/ns:title", namespaces=nsmap)[0].text
    description = xml.xpath("/rdf:RDF/ns:channel/ns:description", namespaces=nsmap)[0].text
    update_date = xml.xpath("/rdf:RDF/ns:channel/dc:date", namespaces=nsmap)[0].text
    subject = xml.xpath("/rdf:RDF/ns:channel/dc:subject", namespaces=nsmap)[0].text

    logger.debug(f"""---
MetaData
  Title - {title}
  Desc - {description}
  Date - {update_date} {utils.get_local_time(update_date)}
  Subject - {subject}
""")
    rss_metadata = RSSMeta(title=title, description=description,
                           update_date=update_date, subject=subject)

    items = xml.xpath("/rdf:RDF/ns:item", namespaces=nsmap)
    logger.info(f"{len(items)} Updates")

    rss_results = []
    for item in items:
        _title = item.xpath("./ns:title", namespaces=nsmap)[0].text
        _link = item.xpath("./ns:link", namespaces=nsmap)[0].text
        assert _link.startswith(ABS_PREFIX)
        _id = _link.removeprefix(ABS_PREFIX)
        _description = item.xpath("./ns:description", namespaces=nsmap)[0].text
        _authors = item.xpath("./dc:creator", namespaces=nsmap)[0].text
        data = RSSItem(_title, _link, _description, _authors, _id)
        rss_results.append(data)
        logger.debug(f"  {_title}")
    return rss_metadata, rss_results
