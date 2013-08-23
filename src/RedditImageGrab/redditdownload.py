"""Download images from a reddit.com subreddit."""

import re
import io
from urllib.request import urlopen
from urllib.error import HTTPError, URLError
from http.client import InvalidURL
from argparse import ArgumentParser
from os.path import exists as pathexists, join as pathjoin, basename as pathbasename, splitext as pathsplitext
from os import mkdir
from .reddit import getitems


class WrongFileTypeException(Exception):
    """Exception raised when incorrect content-type discovered"""


class FileExistsException(Exception):
    """Exception raised when file exists in specified directory"""


def extract_imgur_album_urls(album_url):
    """
    Given an imgur album URL, attempt to extract the images within that
    album

    Returns:
        List of qualified imgur URLs
    """
    try:
        response = urlopen(album_url)
    except HTTPError:
        return []
    info = response.info()

    # Rudimentary check to ensure the URL actually specifies an HTML file
    if 'content-type' in info and not info['content-type'].startswith('text/html'):
        return []

    filedata = response.read()
    encoding = response.headers.get_content_charset()
    filedata = filedata.decode(encoding)


    match = re.compile(r'\"hash\":\"(.[^\"]*)\"')

    items = []

    memfile = io.StringIO(filedata)

    for line in memfile.readlines():
        results = re.findall(match, line)
        if not results:
            continue

        items += results

    memfile.close()

    urls = ['http://i.imgur.com/%s.jpg' % (imghash) for imghash in items]

    return urls


def download_from_url(url, dest_file):
    """
    Attempt to download file specified by url to 'dest_file'

    Raises:
        WrongFileTypeException

            when content-type is not in the supported types or cannot
            be derived from the URL

        FileExceptionsException

            If the filename (derived from the URL) already exists in
            the destination directory.
    """
    # Don't download files multiple times!
    if pathexists(dest_file):
        raise FileExistsException('URL [%s] already downloaded.' % url)

    try:
        response = urlopen(url)
    except HTTPError:
        return

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
        raise WrongFileTypeException('WRONG FILE TYPE: %s has type: %s!' % (url, filetype))

    filedata = response.read()
    filehandle = open(dest_file, 'wb')
    filehandle.write(filedata)
    filehandle.close()


def process_imgur_url(url):
    """
    Given an imgur URL, determine if it's a direct link to an image or an
    album.  If the latter, attempt to determine all images within the album

    Returns:
        list of imgur URLs
    """
    if 'imgur.com/a/' in url:
        return extract_imgur_album_urls(url)

    # Change .png to .jpg for imgur urls.
    if url.endswith('.png'):
        url = url.replace('.png', '.jpg')
    else:
        # Extract the file extension
        ext = pathsplitext(pathbasename(url))[1]
        if not ext:
            # Append a default
            url += '.jpg'

    return [url]


def extract_urls(url):
    """
    Given an URL checks to see if its an imgur.com URL, handles imgur hosted
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


# returns a tuple: (total_processed, downoaded, errors, skipped, failed)
def download(subreddit, destination, last, score, num, update, sfw, nsfw, regex,
             verbose, quiet):
    if not quiet:
        print('Downloading images from "%s" subreddit' % (subreddit))

    TOTAL = DOWNLOADED = ERRORS = SKIPPED = FAILED = 0
    FINISHED = False

    # Create the specified directory if it doesn't already exist.
    if not pathexists(destination):
        mkdir(destination)

    # If a regex has been specified, compile the rule (once)
    RE_RULE = None
    if regex:
        RE_RULE = re.compile(regex)
    LAST = last

    while not FINISHED:
        ITEMS = getitems(subreddit, LAST)
        if not ITEMS:
            # No more items to process
            break

        for ITEM in ITEMS:
            TOTAL += 1

            identifier = ITEM["title"].replace('/', '-').lstrip(".")
            if ITEM['score'] < score:
                if verbose:
                    print('    SCORE: %s has score of %s which is lower than required score of %s.' % (identifier, ITEM['score'], ARGS.score))

                SKIPPED += 1
                continue
            elif sfw and ITEM['over_18']:
                if verbose:
                    print('    NSFW: %s is marked as NSFW.' % (identifier))

                SKIPPED += 1
                continue
            elif nsfw and not ITEM['over_18']:
                if verbose:
                    print('    Not NSFW, skipping %s' % (identifier))

                SKIPPED += 1
                continue
            elif regex and not re.match(RE_RULE, ITEM['title']):
                if verbose:
                    print('    Regex match failed')

                SKIPPED += 1
                continue

            FILECOUNT = 0
            URLS = extract_urls(ITEM['url'])
            for URL in URLS:
                try:
                    # Trim any http query off end of file extension.
                    FILEEXT = pathsplitext(URL)[1]
                    if '?' in FILEEXT:
                        FILEEXT = FILEEXT[:FILEEXT.index('?')]

                    # Only append numbers if more than one file.
                    FILENUM = ('_%d' % FILECOUNT if len(URLS) > 1 else '')
                    FILENAME = '%s%s%s' % (identifier, FILENUM, FILEEXT)
                    FILEPATH = pathjoin(destination, FILENAME)

                    # Download the image
                    download_from_url(URL, FILEPATH)

                    # Image downloaded successfully!
                    if not quiet:
                        print('    Downloaded URL [%s] as [%s].' % (URL, FILENAME))
                    DOWNLOADED += 1
                    FILECOUNT += 1

                    if num > 0 and DOWNLOADED >= num:
                        FINISHED = True
                        break
                except WrongFileTypeException as ERROR:
                    if not quiet:
                        print('    %s' % (ERROR))
                    SKIPPED += 1
                except FileExistsException as ERROR:
                    if not quiet:
                        print('    %s' % (ERROR))
                    ERRORS += 1
                    if update:
                        if not quiet:
                            print('    Update complete, exiting.')
                        FINISHED = True
                        break
                except HTTPError as ERROR:
                    if not quiet:
                        print('    HTTP ERROR: Code %s for %s.' % (ERROR.code, URL))
                    FAILED += 1
                except URLError as ERROR:
                    if not quiet:
                        print('    URL ERROR: %s!' % (URL))
                    FAILED += 1
                except InvalidURL as ERROR:
                    if not quiet:
                        print('    Invalid URL: %s!' % (URL))
                    FAILED += 1

            if FINISHED:
                break

        LAST = ITEM['id']
    if not quiet:
        print('Downloaded %d files (Processed %d, Skipped %d, Exists %d)' % (DOWNLOADED, TOTAL, SKIPPED, ERRORS))
    return (TOTAL, DOWNLOADED, SKIPPED, ERRORS)

### Only needed when called directly.
if __name__ == "__main__":
    PARSER = ArgumentParser(description='Downloads files with specified extension from the specified subreddit.')
    PARSER.add_argument('reddit', metavar='<subreddit>', help='Subreddit name.')
    PARSER.add_argument('dir', metavar='<dest_file>', help='Dir to put downloaded files in.')
    PARSER.add_argument('-last', metavar='l', default='', required=False, help='ID of the last downloaded file.')
    PARSER.add_argument('-score', metavar='s', default=0, type=int, required=False, help='Minimum score of images to download.')
    PARSER.add_argument('-num', metavar='n', default=0, type=int, required=False, help='Number of images to download.')
    PARSER.add_argument('-update', default=False, action='store_true', required=False, help='Run until you encounter a file already downloaded.')
    PARSER.add_argument('-sfw', default=False, action='store_true', required=False, help='Download safe for work images only.')
    PARSER.add_argument('-nsfw', default=False, action='store_true', required=False, help='Download NSFW images only.')
    PARSER.add_argument('-regex', default=None, action='store', required=False, help='Use Python regex to filter based on title.')
    PARSER.add_argument('-verbose', default=False, action='store_true', required=False, help='Enable verbose output.')
    ARGS = PARSER.parse_args()

    download(ARGS.reddit, ARGS.dir, ARGS.last, ARGS.score, ARGS.num,
             ARGS.update, ARGS.sfw, ARGS.nsfw, ARGS.regex, ARGS.verbose, False)


