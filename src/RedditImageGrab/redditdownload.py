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

logger = logging.getLogger()

import RedditImageGrab.reddit

class WrongFileTypeException(Exception):
    """Exception raised when incorrect content-type discovered"""


class FileExistsException(Exception):
    """Exception raised when file exists in specified directory"""


def extract_imgur_album_urls(album_url):
    """
    Given an imgur album url, attempt to extract the images within that
    album

    Returns:
        List of qualified imgur urls
    """
    response = urllib.request.urlopen(album_url)
    info = response.info()
    # Rudimentary check to ensure the url actually specifies an HTML file
    if 'content-type' in info and \
            not info['content-type'].startswith('text/html'):
        return []
    filedata = response.read()
    encoding = response.headers.get_content_charset()
    filedata = filedata.decode(encoding)
    match = re.compile(r'\"hash\":\"(.[^\"]*)\"')
    items = []
    memfile = io.StringIO(filedata)
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
        raise FileExistsException('url [{0}] already downloaded.'.format(url))
    response = urllib.request.urlopen(url)
    info = response.info()

    # Work out file type either from the response or the url.
    if 'content-type' in list(info.keys()):
        filetype = info['content-type']
    elif url.endswith('.jpg') or url.endswith('.jpeg'):
        filetype = 'image/jpeg'
    elif url.endswith('.png'):
        filetype = 'image/png'
    elif url.endswith('.gif'):
        filetype = 'image/gif'
    else:
        filetype = 'unknown'

    # Only try to download acceptable image types
    if not filetype in ['image/jpeg', 'image/png', 'image/gif']:
        raise WrongFileTypeException(
            'WRONG FILE TYPE: {0} has type: {1}!'.format(url, filetype))

    filedata = response.read()
    filehandle = open(dest_file, 'wb')
    filehandle.write(filedata)
    filehandle.close()


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

    # Create the specified directory if it doesn't already exist.
    if not os.path.exists(destination):
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
                    http.client.InvalidURL, TimeoutError,
                    UnicodeEncodeError) as error:
                logger.error("Error %s for %s", repr(error), urls)
                errors += 1
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
                    download_from_url(url, file_path)

                    # Image downloaded successfully!
                    logger.info('Downloaded url \"%s\" as \"%s\".', url,
                                file_name)
                    downloaded += 1
                    filecount += 1

                    if num > 0 and downloaded >= num:
                        finished = True
                        break
                except WrongFileTypeException as error:
                    if not quiet:
                        logger.info('{0}'.format(error))
                    skipped += 1
                except FileExistsException as error:
                    if not quiet:
                        logger.info('{0}'.format(error))
                    skipped += 1
                    if update:
                        logger.verbose('UPDATE: Update complete, done with '
                                       "subreddit \"%s\"", subreddit)
                        finished = True
                        break
                except (urllib.error.HTTPError, urllib.error.URLError,
                        http.client.InvalidURL, TimeoutError,
                        UnicodeEncodeError) as error:
                    logger.error("Error %s for %s", repr(error), urls)
                    errors += 1

            if finished:
                break
        last_item = item['id']
        logger.info('DONE: Downloaded %d files (Processed %d, Skipped %d, '
                    'Exists %d)',downloaded, processed, skipped, errors)
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
