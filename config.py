import os
import os.path

RSS_BASE = "http://rss.arxiv.org/rss/"
API_BASE = "http://export.arxiv.org/api/query"
CACHE_FETCH = "cache/fetch/"
if not os.path.exists(CACHE_FETCH):
    os.makedirs(CACHE_FETCH)
CACHE_GEN = "cache/gen/"
if not os.path.exists(CACHE_GEN):
    os.makedirs(CACHE_GEN)
