"""Download images from a reddit.com subreddit."""

import re
import io
import urllib.request
import urllib.error
import http.client
import argparse
import os.path
import logging
import sys
import threading
import time

import RedditImageGrab.reddit

logger = logging.getLogger()

class WrongFileTypeException(Exception):
    """Exception raised when incorrect content-type discovered"""


class FileExistsException(Exception):
    """Exception raised when file exists in specified directory"""

urlopen_timeout_lock = threading.Lock()
urlopen_imgur_album_lock = threading.Lock()

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


def extract_imgur_album_urls(album_url):
    """
    Given an imgur album url, attempt to extract the images within that
    album

    Returns:
        List of qualified imgur urls
    """
    (response_info, response_data, response_encoding) = \
        urlopen_timeout_wrapper(album_url, lock=urlopen_imgur_album_lock)
    # Rudimentary check to ensure the url actually specifies an HTML file
    if 'content-type' in response_info and \
            not response_info['content-type'].startswith('text/html'):
        return []
    response_data = response_data.decode(response_encoding)
    match = re.compile(r'\"hash\":\"(.[^\"]*)\"')
    items = []
    memfile = io.StringIO(response_data)
    for line in memfile.readlines():
        results = re.findall(match, line)
        if results:
            items.extend(results)

    memfile.close()
    urls = ['http://i.imgur.com/{0}.jpg'.format(imghash) for imghash in items]
    return urls


def download_from_url(url, dest_file):
    """
    Attempt to download file specified by url to 'dest_file'

    Raises:
        WrongFileTypeException

            when content-type is not in the supported types or cannot
            be derived from the url

        FileExceptionsException

            If the filename (derived from the url) already exists in
            the destination directory.
    """
    # Don't download files multiple times!
    if os.path.exists(dest_file):
        raise FileExistsException('URL \"%s\" already downloaded.' % url)
    (response_info, response_data, _) = urlopen_timeout_wrapper(url)
    # Work out file type either from the response or the url.
    if 'content-type' in list(response_info.keys()):
        filetype = response_info['content-type']
    elif url.endswith('.jpg') or url.endswith('.jpeg'):
        filetype = 'image/jpeg'
    elif url.endswith('.png'):
        filetype = 'image/png'
    elif url.endswith('.gif'):
        filetype = 'image/gif'
    else:
        filetype = response_info["content-type"]

    # Only try to download acceptable image types
    if not filetype in ['image/jpeg', 'image/png', 'image/gif']:
        raise WrongFileTypeException(
            'WRONG FILE TYPE: URL \"%s\" has type: \"%s\"' % (url, filetype))

    with open(dest_file, 'wb') as filehandle:
        filehandle.write(response_data)


def process_imgur_url(url):
    """
    Given an imgur url, determine if it's a direct link to an image or an
    album.  If the latter, attempt to determine all images within the album

    Returns:
        list of imgur urls
    """
    if 'imgur.com/a/' in url:
        return extract_imgur_album_urls(url)

    # Change .png to .jpg for imgur urls.
    if url.endswith('.png'):
        url = url.replace('.png', '.jpg')
    else:
        # Extract the file extension
        ext = os.path.splitext(os.path.basename(url))[1]
        if not ext:
            # Append a default
            url += '.jpg'

    return [url]


def extract_urls(url):
    """
    Given an url checks to see if its an imgur.com url, handles imgur hosted
    images if present as single image or image album.

    Returns:
        list of image urls.
    """
    urls = []

    if 'imgur.com' in url:
        urls = process_imgur_url(url)
    else:
        urls = [url]

    return urls

def get_identifier(title):
    return title.replace('/', '-').lstrip(".")


# returns a tuple: (processed, downoaded, errors, skipped)
def download(subreddit, destination, last, score, num, update, sfw, nsfw, regex,
             verbose, quiet, timeout):

    processed = 0
    downloaded = 0
    errors = 0
    skipped = 0
    finished = False
    update_mode = False


    # Create the specified directory if it doesn't already exist.
    if not os.path.exists(destination):
        logger.debug("Directory \"%s\" does not exist, will be created.",
                     destination)
        os.mkdir(destination)

    # If a regex has been specified, compile the rule (once)
    regex_compiled = None
    if regex:
        regex_compiled = re.compile(regex)
    last_item = last
    if not last_item:
        list_item = ""

    while not finished:
        items = RedditImageGrab.reddit.getitems(subreddit, previd=last_item,
                                                timeout=timeout)
        if not items:
            # No more items to process
            break

        for item in items:
            processed += 1

            title = item["title"]
            identifier = get_identifier(title)
            if item['score'] < score:
                logger.verbose("SCORE: \"%s\" has score of %s which is lower "
                               "than the required score of %s, will be "
                               "skipped.", title, item['score'], args.score)
                skipped += 1
                continue
            if sfw and item['over_18']:
                logger.verbose('NSFW: \"%s\" is marked as NSFW, will be '
                               "skipped", title)
                skipped += 1
                continue
            if nsfw and not item['over_18']:
                logger.verbose("NOT NSFW: \"%s\" is not marked as NSFW, will "
                               "be skipped.", title)
                skipped += 1
                continue
            if regex and not re.match(regex_compiled, item['title']):
                logger.verbose("REGEX: \"%s\" did not match regular expression "
                               "%s, will be skipped.", title)
                skipped += 1
                continue

            filecount = 0
            urls = []
            try:
                urls = extract_urls(item['url'])
            except (urllib.error.HTTPError, urllib.error.URLError,
                    http.client.HTTPException, TimeoutError,
                    UnicodeEncodeError, ConnectionError) as error:
                if urls:
                    if len(urls) == 1:
                        urls = urls[0]
                    logger.verbose("Error %s for %s", repr(error), urls)
                errors += 1
                continue

            update = False

            for url in urls:
                try:
                    # Trim any http query off end of file extension.
                    file_extension = os.path.splitext(url)[1]
                    if '?' in file_extension:
                        file_extension = \
                            file_extension[:file_extension.index('?')]

                    # Only append numbers if more than one file.
                    file_number = ('_{0}'.format(
                        filecount if len(urls) > 1 else ''))
                    file_name = '{0}{1}{2}'.format(identifier, file_number,
                                                    file_extension)
                    file_path = os.path.join(destination, file_name)

                    # Download the image
                    try:
                        download_from_url(url, file_path)
                    except OSError as error:
                        if error.errno == 36: # file name too long
                            # shorten basename to [SHORTENED] and 10 characters
                            # hope that works
                            logger.info("File path %s had to be shortened.",
                                        file_path)
                            file_path = os.path.join(os.path.dirname(file_path),
                                "[SHORTENED] {0}".format(os.path.basename(
                                file_path)[:10]))
                            download_from_url(url, file_path)
                        else:
                            raise
                    # Image downloaded successfully!

                    if update_mode:
                        logger.critical(" ------------------------------------")
                        logger.critical(" ------------------------------------")
                        logger.critical(" ------------------------------------")
                        logger.critical("--update failed, encountered new link")
                        logger.critical(" ------------------------------------")
                        logger.critical(" ------------------------------------")
                        logger.critical(" ------------------------------------")
                        sys.exit(13)
                        sys.exit(37)


                    logger.verbose('Downloaded URL \"%s\" to \"%s\".', url,
                                   file_path)
                    downloaded += 1
                    filecount += 1

                    if num > 0 and downloaded >= num:
                        finished = True
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
                        if not update_mode:
                            update_mode = True
                            logger.verbose('UPDATE: Update complete, done with '
                                        "subreddit \"%s\"", subreddit)
                            #finished = True
                            #break
                            continue
                except (urllib.error.HTTPError, urllib.error.URLError,
                        http.client.HTTPException, TimeoutError,
                        UnicodeEncodeError, ConnectionError) as error:
                    if urls:
                        if len(urls) == 1:
                            urls = urls[0]
                        logger.verbose("Error %s for %s", repr(error), urls)
                    errors += 1
                    continue

            if finished:
                break
        last_item = item['id']
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
