import datetime
import re
import pickle

import pytz

_local_tz = pytz.timezone("Asia/Shanghai")
_utc_tz = pytz.timezone("UTC")


def get_local_time(raw_datetime: datetime.datetime | str) -> datetime.datetime:
    if raw_datetime is str:
        raw_datetime = datetime.datetime.fromisoformat(raw_datetime)
    return raw_datetime.astimezone(_local_tz)


def get_utc_time(raw_datetime: datetime.datetime | str) -> datetime.datetime:
    if raw_datetime is str:
        raw_datetime = datetime.datetime.fromisoformat(raw_datetime)
    return raw_datetime.astimezone(_utc_tz)


def pre_process_abstract(raw_text: str) -> str:
    lines = raw_text.splitlines()
    paragraphs = []
    assert lines[0].startswith("  ")
    for line in lines:
        if line.startswith("  "):
            paragraphs.append(line[2:])
        else:
            paragraphs[-1] += " " + line
    return "\n\n".join(paragraphs)\



def pre_proc_title(raw_title: str) -> str:
    return re.sub(r'\s+', ' ', raw_title)


def pkl_load(obj_path):
    with open(obj_path, 'rb') as pkl_file:
        obj = pickle.load(pkl_file)
    return obj


def pkl_dump(obj, obj_path):
    with open(obj_path, "wb") as pkl_file:
        pickle.dump(obj, pkl_file)
