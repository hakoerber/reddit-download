# -*- encoding: utf-8 -*-
# Copyright (c) 2013 Hannes Körber <hannes.koerber@gmail.com>
#
# This file is part of reddit-download.
#
# reddit-download is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# reddit-download is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import logging
import multiprocessing
import socket
import time

import requests

USER_AGENT = ("reddit-download script. "
              "http://github.com/whatevsz/reddit-download")
REDDIT_LINK_LIMIT = 1000
REDDIT_MIN_TIMEOUT = 2000
TIMEOUT = 10.0

logger = logging.getLogger()

# Disable logging for the requests module.
requests_log = logging.getLogger("requests")
requests_log.setLevel(logging.WARNING)

lock = multiprocessing.Lock()


class RedditLink(object):
    def __init__(self, title, url, name, score, nsfw):
        self.nsfw = nsfw
        self.name = name
        self.url = url
        self.score = score
        self.title = title


def get_links(subreddit, timeout=REDDIT_MIN_TIMEOUT, limit=None, headers=None,
              params=None):
    # param limit:
    # return LIMIT links, up to an upstream maximum of 1000
    # if None or 0, request as many links as possible

    # timeout must be at least 2000 ms, otherwise a warning will be issued and
    # 2000 will be selected, as reddit asks for a 2 second timeout between
    # requests:
    # https://github.com/reddit/reddit/wiki/API
    #  Make no more than thirty requests per minute. This allows some
    # burstiness to your requests, but keep it sane. On average, we should see
    # no more than one request every two seconds from you.

    url = "http://www.reddit.com/r/" + subreddit + ".json"

    headers = {'User-Agent': USER_AGENT}

    headers = headers or {}
    params = params or {}
    limit = limit or REDDIT_LINK_LIMIT
    params["limit"] = limit
    if timeout < REDDIT_MIN_TIMEOUT:
        logger.warning("A timeout of %d milliseconds is against the reddit "
                       "API rules. It will be set to %d milliseconds instead.",
                       timeout, REDDIT_MIN_TIMEOUT)
        timeout = REDDIT_MIN_TIMEOUT

    links = 0
    last_request = 0
    firstrun = True
    # sends a request and locks for timeout milliseconds
    while links < limit:
        with lock:
            time_since_last_request = time.monotonic() - last_request
            if time_since_last_request < timeout / 1000 and not firstrun:
                sleeptime = timeout / 1000 - time_since_last_request
                time.sleep(sleeptime)
            firstrun = False
            last_request = time.monotonic()
            json_data = None
            try:
                json_data = requests.get(
                    url, params=params, headers=headers, timeout=TIMEOUT).\
                    json()
            except (requests.packages.urllib3.exceptions.TimeoutError,
                    TimeoutError, requests.exceptions.Timeout,
                    socket.timeout):
                logger.verbose("Connection to \"%s\" timed out.", url)
            except ValueError:
                pass
            try:
                if json_data:
                    for link in json_data["data"]["children"]:
                        link_data = link["data"]
                        link = RedditLink(link_data["title"],
                                          link_data["url"],
                                          link_data["name"],
                                          link_data["score"],
                                          link_data["over_18"])
                        yield link
                        links += 1
                        if links >= limit:
                            return
                else:
                    return
            except KeyError:
                logger.error("URL \"%s\" returned an invalid JSON. Skipping "
                             "this page.", url)
                continue
        after = json_data["data"]["after"]
        if not after:
            # last page
            return
        params["after"] = after
