import argparse
import http.client
import io
import logging
import multiprocessing
import os
import os.path
import re
import socket
import time
import urllib.error
import urllib.parse
import urllib.request

import requests

from . import reddit

USER_AGENT = ("reddit-download script. "
              "http://github.com/whatevsz/reddit-download")
TIMEOUT = 10.0

logger = logging.getLogger()


class WrongFileTypeException(Exception):
    """Exception raised when incorrect content-type discovered"""


class FileExistsException(Exception):
    """Exception raised when file exists in specified directory"""


request_timeout_lock = multiprocessing.Lock()
request_imgur_album_lock = multiprocessing.Lock()
last_request = 0
firstrun = True


def urlopen_timeout_wrapper(url, lock, timeout=200):
    global last_request, firstrun
    # sends a request and locks for timeout milliseconds
    with lock:
        time_since_last_request = time.monotonic() - last_request
        if time_since_last_request < timeout / 1000 and not firstrun:
            sleeptime = timeout / 1000 - time_since_last_request
            time.sleep(sleeptime)
        firstrun = False
        last_request = time.monotonic()

        logger.debug("Opening URL \"%s\"", url)
        response = None
        try:
            response = requests.get(url, timeout=TIMEOUT)
        except (requests.packages.urllib3.exceptions.TimeoutError,
                requests.exceptions.Timeout,
                socket.timeout):
            raise

    return response


def download_from_url(url, destination, identifier, files_in_dest,
                      max_filename_len):
    # Extension is not significant
    if identifier in files_in_dest:
        raise FileExistsException('URL \"%s\" already downloaded.' % url)

    # Imgur does not care about extensions. If a MIME type is available, we
    # will change the extension accordingly if necessary
    response = None
    try:
        response = urlopen_timeout_wrapper(url, request_timeout_lock)
    except (requests.packages.urllib3.exceptions.TimeoutError,
            requests.exceptions.Timeout, socket.timeout) as error:
        raise
    extension_mime = None
    filetype_mime = None
    if 'content-type' in response.headers.keys():
        filetype_mime = response.headers['content-type']
    if filetype_mime == "image/jpeg" or filetype_mime == "image/jpg":
        extension_mime = ".jpg"
    elif filetype_mime == "image/png":
        extension_mime = ".png"
    elif filetype_mime == "image/gif":
        extension_mime = ".gif"

    extension_url = os.path.splitext(url.split("/")[-1])[1]

    # if filetype_mime and filetype_url diverge, filetype_mime takes
    # precedence
    extension = extension_mime or extension_url

    # Only try to download acceptable image types
    if not extension in [".jpg", ".png", ".gif"]:
        raise WrongFileTypeException(
            'WRONG FILE TYPE: URL \"%s\" has is of type \"%s\"' % (url,
                                                                   extension))

    dest_file_name = identifier + extension

    # Shortened too long filenames
    if len(dest_file_name) > max_filename_len:
        logger.info("Filename \"%s\" is too long, will be "
                    "truncated to %d characters.", dest_file_name,
                    max_filename_len)
        dest_file_name = truncate_filename(dest_file_name, max_filename_len)

    dest_path = os.path.join(destination, dest_file_name)

    # wtf python, figure it out
    filehandle = None
    try:
        filehandle = open(dest_path, 'wb')
        filehandle.write(response.content)
    except OSError as error:
        if error.errno == 36:
            # dirty as fuck, i dont care anymore
            pass
            #dest_file_name = truncate_filename(dest_file_name,
            #                                   20)
            #dest_path = os.path.join(destination, dest_file_name)
            #with open(dest_path, 'wb') as filehandle:
            #    filehandle.write(response.content)
        else:
            raise
    finally:
        if filehandle:
            filehandle.close()

    logger.verbose('Downloaded URL \"%s\" to \"%s\".', url,
                   dest_path)


def extract_imgur_album_urls(album_url):
    try:
        response = \
            urlopen_timeout_wrapper(album_url, lock=request_imgur_album_lock)
    except (requests.packages.urllib3.exceptions.TimeoutError,
            requests.exceptions.Timeout, socket.timeout):
        return []
    hash_regex = re.compile(r'\"hash\":\"(.[^\"]*)\"')
    items = []
    with io.StringIO(response.text) as memfile:
        for line in memfile.readlines():
            results = re.findall(hash_regex, line)
            if results:
                items.extend(results)

    urls = ['http://i.imgur.com/{0}.jpg'.format(imghash) for imghash in items]
    return urls


def process_imgur_url(url):
    if urllib.parse.urlparse(url).path.startswith("/a/"):
        return extract_imgur_album_urls(url)
    elif 'imgur.com/a/' in url:
        logger.warning("\"%s\" might be an imgur album. Please investigate.",
                       url)
    return [url]


def extract_urls(url):
    if 'imgur.com' in urllib.parse.urlparse(url).netloc:
        return process_imgur_url(url)
    elif 'imgur.com' in url:
        logger.warning("\"%s\" might be an imgur URL. Please investigate.",
                       url)
    return [url]


def truncate_filename(file_name, limit):
    ext = os.path.splitext(file_name)[1]
    file_name = file_name[:(limit - len(ext))]
    file_name = "%s%s" % (file_name, ext)
    return file_name


# ATTENTION: editing this function might break the detection of already
# downloaded links!
def get_identifier(title):
    return title.replace('/', '-').lstrip(".")


# returns a tuple: (processed, downoaded, errors, skipped)
def download(subreddit, destination, last, score, num, update, sfw, nsfw,
             regex, verbose, quiet, timeout):

    if update:
        raise NotImplementedError(
            "The update functionality is not implemented.")

    files_in_dest = os.listdir(destination)
    # Extensions are not significant
    files_in_dest = [os.path.splitext(f)[0] for f in files_in_dest]
    max_filename_len = os.statvfs(destination)[9]
    processed = 0
    downloaded = 0
    errors = 0
    skipped = 0

    # Create the specified directory if it doesn't already exist.
    if not os.path.exists(destination):
        logger.debug("Directory \"%s\" does not exist, will be created.",
                     destination)
        os.mkdir(destination)

    # If a regex has been specified, compile the rule (once)
    regex_compiled = None
    if regex:
        regex_compiled = re.compile(regex)

    links = reddit.get_links(subreddit, timeout=timeout, limit=num)

    for link in links:
        processed += 1
        if not link:
            continue
        identifier = get_identifier(link.title)

        if link.score < score:
            logger.verbose("SCORE: \"%s\" has score of %s which is lower "
                           "than the required score of %s, will be skipped.",
                           link.title, link.score, score)
            skipped += 1
            continue
        if sfw and link.nsfw:
            logger.verbose('NSFW: \"%s\" is marked as NSFW, will be '
                           "skipped", link.title)
            skipped += 1
            continue
        if nsfw and not link.nsfw:
            logger.verbose("NOT NSFW: \"%s\" is not marked as NSFW, will "
                           "be skipped.", link.title)
            skipped += 1
            continue
        if regex and not re.match(regex_compiled, link.title):
            logger.verbose("REGEX: \"%s\" did not match regular expression "
                           "%s, will be skipped.", link.title)
            skipped += 1
            continue

        filecount = 0
        urls = []
        try:
            urls = extract_urls(link.url)

        except (urllib.error.HTTPError,
                urllib.error.URLError,
                http.client.HTTPException,
                TimeoutError,
                UnicodeEncodeError,
                ConnectionError,
                requests.exceptions.RequestException,
                requests.exceptions.ConnectionError,
                requests.exceptions.HTTPError,
                requests.packages.urllib3.exceptions.DecodeError,
                requests.packages.urllib3.exceptions.LocationParseError,
                ValueError) as error:
            if urls:
                if len(urls) == 1:
                    urls = urls[0]
                logger.verbose("Error %s for %s", repr(error), urls)
            errors += 1
            continue

        if not urls:
            continue

        for url in urls:
            try:
                # Only append numbers if more than one file.
                mutated_identifier = identifier
                if len(urls) > 1:
                    mutated_identifier += "_%s" % filecount

                # has to be updated BEFORE calling download_from_url(), as it
                # might raise a FileExistsException, continue, the next
                # mutated_identifier would be the same as before,
                # download_from_url() would raise the same exception, and so
                # on, so all leftover items of an imgur album would be skipped.
                filecount += 1

                download_from_url(url, destination, mutated_identifier,
                                  files_in_dest, max_filename_len)
                downloaded += 1

                if num > 0 and downloaded >= num:
                    break
            except WrongFileTypeException as error:
                if not quiet:
                    logger.verbose('%s', error)
                skipped += 1
            except (requests.packages.urllib3.exceptions.TimeoutError,
                    requests.exceptions.Timeout, socket.timeout) as error:
                logger.verbose("Connection to \"%s\" timed out.", url)
                errors += 1
                continue
            except FileExistsException as error:
                if not quiet:
                    logger.verbose('%s', error)
                skipped += 1
            except (urllib.error.HTTPError,
                    urllib.error.URLError,
                    http.client.HTTPException,
                    TimeoutError,
                    UnicodeEncodeError,
                    ConnectionError,
                    requests.exceptions.RequestException,
                    requests.exceptions.ConnectionError,
                    requests.exceptions.HTTPError,
                    requests.packages.urllib3.exceptions.DecodeError,
                    requests.packages.urllib3.exceptions.LocationParseError,
                    ValueError) as error:
                if urls:
                    if len(urls) == 1:
                        urls = urls[0]
                    logger.verbose("Error %s for %s", repr(error), urls)
                errors += 1
                continue

    return (processed, downloaded, skipped, errors)

### Only needed when called directly.
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Downloads files with specified extension from the "
        "specified subreddit.")
    parser.add_argument('reddit', metavar='<subreddit>',
                        help='Subreddit name.')
    parser.add_argument('dir', metavar='<identifier>',
                        help='Dir to put downloaded files in.')
    parser.add_argument('-last', metavar='l', default='', required=False,
                        help='ID of the last downloaded file.')
    parser.add_argument('-score', metavar='s', default=0, type=int,
                        required=False, help='Minimum score of images to '
                        'download.')
    parser.add_argument('-num', metavar='n', default=0, type=int,
                        required=False, help='Number of images to download.')
    parser.add_argument('-update', default=False, action='store_true',
                        required=False, help='Run until you encounter a file '
                        'already downloaded.')
    parser.add_argument('-sfw', default=False, action='store_true',
                        required=False, help='Download safe for work images '
                        'only.')
    parser.add_argument('-nsfw', default=False, action='store_true',
                        required=False, help='Download NSFW images only.')
    parser.add_argument('-regex', default=None, action='store', required=False,
                        help='Use Python regex to filter based on title.')
    parser.add_argument('-verbose', default=False, action='store_true',
                        required=False, help='Enable verbose output.')
    args = parser.parse_args()

    download(args.reddit, args.dir, args.last, args.score, args.num,
             args.update, args.sfw, args.nsfw, args.regex, args.verbose, False,
             1000)
