from .google_translate import translate as google_translate
from .tencent_translate import translate as tencent_translate

SERVICES = {
  "google": google_translate,
  "tencent": tencent_translate
}

def translate(src: str, service: str = "google"):
    return SERVICES[service](src)