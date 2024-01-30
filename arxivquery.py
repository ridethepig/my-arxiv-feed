import datetime
import hashlib
import os
import os.path as path
import time

import requests

from config import API_BASE, CACHE_FETCH, RSS_BASE
from utils import logger


def query_rss(subcategory="cs", force=False) -> str:
    rss_url = RSS_BASE + subcategory
    rss_file_name = f"{datetime.date.today()}-{subcategory}.xml"
    rss_file_path = path.join(CACHE_FETCH, rss_file_name)
    if path.exists(rss_file_path) and not force:
        logger.warning(f"use cached `{rss_file_path}`")
        with open(rss_file_path, "rb") as f:
            rss_str = f.read()
        return rss_str
    logger.info(f"getting rss from {rss_url}")
    rss_resp = requests.get(rss_url)
    with open(rss_file_path, "w") as f:
        f.write(rss_resp.text)
    logger.info(f"rss got from {rss_url}")
    return rss_resp.text.encode()


def query_atom(id_list, items_per_req=20, force=False, req_interval=3):
    start = 0
    atom_strs = []
    while start < len(id_list):
        id_list_slice = id_list[start: start + items_per_req]
        start += items_per_req
        id_list_str = ",".join(id_list_slice)
        id_list_hash = hashlib.sha256(id_list_str.encode()).hexdigest()
        atom_file_name = f"{datetime.date.today()}-pagesize{items_per_req}-{id_list_hash}.atom"
        atom_file_path = path.join(CACHE_FETCH, atom_file_name)

        if path.exists(atom_file_path) and not force:
            logger.warning(f"use cached `{atom_file_path}`")
            with open(atom_file_path, "rb") as f:
                atom_str = f.read()
                atom_strs.append(atom_str)
            continue

        params = {"id_list": id_list_str, "max_results": items_per_req}
        logger.info(f"query for {len(id_list_slice)} items")
        atom_resp = requests.get(API_BASE, params=params)
        with open(atom_file_path, "w") as f:
            f.write(atom_resp.text)
        logger.info(f"query done from {atom_resp.url}")
        atom_strs.append(atom_resp.text.encode())
        time.sleep(req_interval)
    return atom_strs
