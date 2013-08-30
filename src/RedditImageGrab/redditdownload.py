"""Download images from a reddit.com subreddit."""

import re
import io
import urllib.request
import urllib.error
import urllib.parse
import http.client
import argparse
import os.path
import logging
import sys
import multiprocessing
import time

import praw

USER_AGENT = ("reddit-download script. "
              "http://github.com/whatevsz/reddit-download")

reddit_api = praw.Reddit(USER_AGENT)

logger = logging.getLogger()

class WrongFileTypeException(Exception):
    """Exception raised when incorrect content-type discovered"""


class FileExistsException(Exception):
    """Exception raised when file exists in specified directory"""

urlopen_timeout_lock = multiprocessing.Lock()
urlopen_imgur_album_lock = multiprocessing.Lock()

def urlopen_timeout_wrapper(url, timeout=1000, lock=urlopen_timeout_lock):
    with urlopen_timeout_lock:
        #logger.critical("Aquired lock")
        start = time.perf_counter()

        logger.debug("Opening URL \"%s\"", url)
        response = urllib.request.urlopen(url)
        response_info = response.info()
        response_data = response.read()
        response_encoding = response.headers.get_content_charset()

        sleep_time = timeout / 1000 - (time.perf_counter() - start)
        if sleep_time > 0:
            #logger.critical("sleeptime %s", sleep_time)
            #logger.critical("doing a nap")
            time.sleep(sleep_time)
        #logger.critical("thanks for the lock, done with it")

    return (response_info, response_data, response_encoding)



def download_from_url(url, dest_file):
    # Don't download files multiple times!
    if os.path.exists(dest_file):
        raise FileExistsException('URL \"%s\" already downloaded.' % url)

    # Imgur does not care about extensions. If a MIME type is available, we will
    # change the extension accordingly if necessary

    (response_info, response_data, _) = urlopen_timeout_wrapper(url)
    filetype_mime = None
    if 'content-type' in list(response_info.keys()):
        filetype_mime = response_info['content-type']

    filetype_extension = None
    if url.endswith('.jpg') or url.endswith('.jpeg'):
        filetype_extension = 'image/jpeg'
    elif url.endswith('.png'):
        filetype_extension = 'image/png'
    elif url.endswith('.gif'):
        filetype_extension = 'image/gif'

    # if filetype_mime and filetype_extension diverge, filetype_mime takes
    # precedence
    if filetype_mime and filetype_mime != filetype_extension:
        extension = os.path.splitext(url.url.split("/")[-1])[1]
        url = url[:-len(extension)]
        if filetype_mime == 'image/jpeg':
            new_extension = '.jpg'
        if filetype_mime == 'image/png':
            new_extension = '.png'
        if filetype_mime == 'image/gif':
            new_extension = '.gif'
        url = "%s%s" % (url, new_extension)

    filetype = filetype_mime or filetype_extension

    # Only try to download acceptable image types
    if not filetype in ['image/jpeg', 'image/png', 'image/gif']:
        raise WrongFileTypeException(
            'WRONG FILE TYPE: URL \"%s\" has type: \"%s\"' % (url, filetype))

    with open(dest_file, 'wb') as filehandle:
        filehandle.write(response_data)


def extract_imgur_album_urls(album_url):
    (response_info, response_data, response_encoding) = \
        urlopen_timeout_wrapper(album_url, lock=urlopen_imgur_album_lock)
    response_data = response_data.decode(response_encoding)
    hash_regex = re.compile(r'\"hash\":\"(.[^\"]*)\"')
    items = []
    with io.StringIO(response_data) as memfile:
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
        logger.warning("\"%s\" might be an imgur URL. Please investigate.", url)
    else:
        return [url]


def truncate_filename(file_name, limit):
    # TODO maybe check if limit is too low?
    ext = os.path.splitext(file_name)[1]
    file_name = file_name[:(limit - len(ext))]
    file_name = "%s%s" % (file_name, ext)
    return file_name


# ATTENTION: editing this function might break the detection of already
# downloaded links!
def get_identifier(title):
    return title.replace('/', '-').lstrip(".")


# returns a tuple: (processed, downoaded, errors, skipped)
def download(subreddit, destination, last, score, num, update, sfw, nsfw, regex,
             verbose, quiet, timeout):

    if update:
        raise NotImplementedError(
            "The update functionality is not implemented.")

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

    url = "http://www.reddit.com/r/%s" % subreddit
    subreddit = reddit_api.get_subreddit(subreddit)
    subreddit_content = subreddit.get_hot()

    for submission in subreddit_content:
        processed += 1
        identifier = get_identifier(submission.title)

        if submission.score < score:
            logger.verbose("SCORE: \"%s\" has score of %s which is lower "
                            "than the required score of %s, will be "
                            "skipped.", title, submission.score, score)
            skipped += 1
            continue
        if sfw and submssion.over_18:
            logger.verbose('NSFW: \"%s\" is marked as NSFW, will be '
                            "skipped", title)
            skipped += 1
            continue
        if nsfw and not submssion.over_18:
            logger.verbose("NOT NSFW: \"%s\" is not marked as NSFW, will "
                            "be skipped.", title)
            skipped += 1
            continue
        if regex and not re.match(regex_compiled, submission.title):
            logger.verbose("REGEX: \"%s\" did not match regular expression "
                            "%s, will be skipped.", title)
            skipped += 1
            continue

        filecount = 0
        urls = []
        try:
            urls = extract_urls(submission.url)

        except (urllib.error.HTTPError, urllib.error.URLError,
                http.client.HTTPException, TimeoutError,
                UnicodeEncodeError, ConnectionError) as error:
            if urls:
                if len(urls) == 1:
                    urls = urls[0]
                logger.verbose("Error %s for %s", repr(error), urls)
            errors += 1
            continue


        for url in urls:
            try:
                # Only append numbers if more than one file.
                file_name = identifier
                if len(urls) > 1:
                    file_name = "%s_%s" % (file_name, filecount)
                # Shorted too long filenames
                if len(file_name) > max_filename_len:
                    logger.info("Filename \"%s\" is too long, will be "
                                "truncated to %d characters." , file_name,
                                max_filename_len)
                    file_name = truncate_filename(file_name, max_filename_len)
                file_path = os.path.join(destination, file_name)
                download_from_url(url, file_path)
                logger.verbose('Downloaded URL \"%s\" to \"%s\".', url,
                                file_path)
                downloaded += 1
                filecount += 1

                if num > 0 and downloaded >= num:
                    break
            except WrongFileTypeException as error:
                if not quiet:
                    logger.verbose('%s', error)
                skipped += 1
            except FileExistsException as error:
                if not quiet:
                    logger.verbose('%s', error)
                skipped += 1
                if update:
                    pass
            except (urllib.error.HTTPError, urllib.error.URLError,
                    http.client.HTTPException, TimeoutError,
                    UnicodeEncodeError, ConnectionError) as error:
                if urls:
                    if len(urls) == 1:
                        urls = urls[0]
                    logger.verbose("Error %s for %s", repr(error), urls)
                errors += 1
                continue

    return (processed, downloaded, skipped, errors)

### Only needed when called directly.
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Downloads files with specified extension from the specified subreddit.')
    parser.add_argument('reddit', metavar='<subreddit>', help='Subreddit name.')
    parser.add_argument('dir', metavar='<dest_file>', help='Dir to put downloaded files in.')
    parser.add_argument('-last', metavar='l', default='', required=False, help='ID of the last downloaded file.')
    parser.add_argument('-score', metavar='s', default=0, type=int, required=False, help='Minimum score of images to download.')
    parser.add_argument('-num', metavar='n', default=0, type=int, required=False, help='Number of images to download.')
    parser.add_argument('-update', default=False, action='store_true', required=False, help='Run until you encounter a file already downloaded.')
    parser.add_argument('-sfw', default=False, action='store_true', required=False, help='Download safe for work images only.')
    parser.add_argument('-nsfw', default=False, action='store_true', required=False, help='Download NSFW images only.')
    parser.add_argument('-regex', default=None, action='store', required=False, help='Use Python regex to filter based on title.')
    parser.add_argument('-verbose', default=False, action='store_true', required=False, help='Enable verbose output.')
    args = parser.parse_args()

    download(args.reddit, args.dir, args.last, args.score, args.num,
             args.update, args.sfw, args.nsfw, args.regex, args.verbose, False,
             1000)
