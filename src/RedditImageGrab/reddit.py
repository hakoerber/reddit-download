"""Return list of items from a sub-reddit of reddit.com."""
from urllib.request import urlopen, Request
from urllib.error import HTTPError
from json import JSONDecoder
import threading
import time
import logging

logger = logging.getLogger()

lock = threading.Lock()

def getitems(subreddit, previd, timeout):
    """Return list of items from a subreddit."""
    url = 'http://www.reddit.com/r/%s.json' % subreddit
    # Get items after item with 'id' of previd.

    hdr = { 'User-Agent' : 'RedditImageGrab script.' }

    if previd:
        url = '%s?after=t3_%s' % (url, previd)

    try:
        json = None
        # sends a request and locks for timeout milliseconds
        with lock:
            start = time.perf_counter()
            req = Request(url, headers=hdr)
            json = urlopen(req)
            sleep_time = timeout / 1000 - (time.perf_counter() - start)
            if sleep_time > 0:
                time.sleep(sleep_time)

        # reencode json from byte to string
        encoding = json.headers.get_content_charset()
        json = json.readall().decode(encoding)
        data = JSONDecoder().decode(json)
        items = [x['data'] for x in data['data']['children']]
    except HTTPError as ERROR:
        logger.error('HTTP ERROR: Code %s for %s.', ERROR.code, url)
        items = []
    return items

if __name__ == "__main__":

    print('Recent items for Python.')
    ITEMS = getitems('python')
    for ITEM in ITEMS:
        print('\t%s - %s' % (ITEM['title'], ITEM['url']))

    print('Previous items for Python.')
    OLDITEMS = getitems('python', ITEMS[-1]['id'])
    for ITEM in OLDITEMS:
        print('\t%s - %s' % (ITEM['title'], ITEM['url']))
