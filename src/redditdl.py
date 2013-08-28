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

import os
import sys
import optparse
import queue
import threading
import random
import time
import logging
import logging.handlers

import RedditImageGrab.redditdownload

NAME = "reddit-download"
VERSION = "0.1-dev"

PRIVILEGED_FOLDER = "/var/log"
UNPRIVILEGED_FOLDER = "/var/tmp"

# We can use /var/log/... if we are root or if it already exists with the
# correct permissions, otherwise we have to fall back to /var/tmp/...
logfile = ""
privileged_path = os.path.join(PRIVILEGED_FOLDER, NAME)
unprivileged_path = os.path.join(UNPRIVILEGED_FOLDER, NAME)
try:
    if os.getuid() == 0 or os.access(privileged_path, os.W_OK):
        logfile = privileged_path
    else: #maybe we are allowed to create the log folder? (unlikely, i admit it)
        if os.access(PRIVILEGED_FOLDER, os.W_OK):
            os.mkdir(privileged_path)
            logfile = privileged_path
        else:
            if not os.path.isdir(unprivileged_path):
                os.mkdir(unprivileged_path)
            if not os.access(unprivileged_path, os.W_OK):
                raise OSError("No access to %s" % unprivileged_path)
            logfile = unprivileged_path
    logfile = os.path.join(logfile, "run.log")
except OSError as error:
    print("Could not get a valid path for the log file. No logging to a file "
          "will be done. Error: %s" % repr(error))

DEFAULT_LIST_EXTENSION = ".list"
DEFAULT_FLOOD_TIMEOUT = 5000
DEFAULT_MAX_THREADS = 3
DEFAULT_CREATE_DESTINATION = False
DEFAULT_RECURSIVE = False
DEFAULT_DESTINATION = os.getcwd()
DEFAULT_NO_SFW = False
DEFAULT_NO_NSFW = False
DEFAULT_SCORE = 0
DEFAULT_REGEX = None
DEFAULT_SHUFFLE = None
DEFAULT_SHUFFLE_LISTS = False
DEFAULT_SHUFFLE_LIST_SUBREDDITS = False
DEFAULT_SHUFFLE_ALL_SUBREDDITS = False

EXIT_INVALID_DESTINATION = 1
ERROR_INVALID_COMMAND_LINE = 2 # same in optparse
ERROR_UNKNOWN = 100

COMMENT_CHAR = "#"

class LevelFilter(object):
    def __init__(self, minlvl=logging.NOTSET, maxlvl=logging.NOTSET):
        self.__setMinLevel(minlvl)
        self.__setMaxLevel(maxlvl)

    def filter(self, record):
        if (self.getMinLevel() != logging.NOTSET and
                record.levelno < self.getMinLevel()):
            return False
        if (self.getMaxLevel() != logging.NOTSET and
                record.levelno > self.getMaxLevel()):
            return False
        return True

    def getMinLevel(self):
        return self.__minlvl

    def getMaxLevel(self):
        return self.__maxlvl

    def __setMinLevel(self, minlvl):
        self.__minlvl = minlvl

    def __setMaxLevel(self, maxlvl):
        self.__maxlvl = maxlvl


def check_file(file_path, list_extension):
    return (file_path.endswith(list_extension)
            and os.path.basename(file_path) != list_extension)

def get_lists(directory, recursive, list_extension):
    if recursive:
        paths = list()
        for (root, _, files) in os.walk(directory):
            for filename in files:
                path = os.path.join(root, filename)
                if check_file(path, list_extension):
                    paths.append(path)
        return paths
    else:
        return [os.path.join(directory, path) for path in os.listdir(directory)
                if check_file(path, list_extension)]

def check_line(line):
    return line and not line.startswith(COMMENT_CHAR)

def parse_file(path):
    subreddits = list()
    for line in open(path):
        line = line.strip()
        if check_line(line):
            subreddits.append(line)
    return subreddits

# Worker method
def download_subreddit():
    # well ...
    global total_processed
    global total_downloaded
    global total_skipped
    global total_errors
    global score
    global max_downloads
    global no_sfw
    global no_nsfw
    global regex
    global verbose
    global flood_timeout
    while True:
        try:
            (subreddit, destination) = threadqueue.get(block=False)
        except queue.Empty:
            logger.info("No more items to process. Thread done.")
            return
        subreddit_destination = os.path.join(destination, subreddit)
        if not os.path.isdir(subreddit_destination):
            if os.path.exists(subreddit_destination):
                logger.error("Invalid destination: %s. Skipping subreddit %s",
                             subreddit_destination, subreddit)
                continue
            os.mkdir(subreddit_destination)

        logger.info("Starting download from /r/%s to %s", subreddit,
              subreddit_destination)

        #(total, downloaded, skipped, errors) = (10, 5, 3, 2)
        #time.sleep(random.randrange(3,8))

        # sfw and nsfw means (n)sfw ONLY ... ffs
        try:
            (total, downloaded, skipped, errors) = \
                RedditImageGrab.redditdownload.download(
                    subreddit, subreddit_destination, last="", score=score,
                    num=max_downloads, update=False, sfw=no_nsfw,
                    nsfw=no_sfw, regex=regex, verbose=verbose,
                    quiet=(not verbose), timeout=flood_timeout)
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception as e:
            logger.critical("Encountered unexpected exception %s. Aborting.",
                            repr(e), exc_info=True)
            sys.exit(ERROR_UNKNOWN)

        with lock:
            total_processed += total
            total_downloaded += downloaded
            total_skipped += skipped
            total_errors += errors

        logger.info("Done downloading from /r/%s to \"%s\" Downloaded: %d, "
                    "skipped/errors %d/%d, total processed: %d", subreddit,
                     subreddit_destination, downloaded, skipped, errors, total)
        threadqueue.task_done()




if __name__ == '__main__':
    usage = "Usage: %prog [options] FILE/DIRECTORY..."
    version = "%prog {0}".format(VERSION)
    parser = optparse.OptionParser(usage=usage, version=version)
    parser.add_option("-r", "--recursive", action="store_true",
                      dest="recursive", default=DEFAULT_RECURSIVE,
                      help="search the directories recursively")
    parser.add_option("-d", "--dest", dest="destination", metavar="DEST",
                      default=DEFAULT_DESTINATION,
                      help="the directory to download to, defaults to the "
                      "current working directory")
    parser.add_option("-c", "--create-dest", dest="create_destination",
                      default=DEFAULT_CREATE_DESTINATION, help="create the "
                      "destination directory if it does not exist",
                      action="store_true")
    parser.add_option("-t", "--threads", action="store", type="int",
                      dest="max_threads", default=DEFAULT_MAX_THREADS,
                      metavar="NUM", help="create a maximum of NUM threads "
                      "[default: {0}]".format(DEFAULT_MAX_THREADS))
    parser.add_option("-e", "--extension", action="store", type="string",
                      dest="list_extension", default=DEFAULT_LIST_EXTENSION,
                      metavar="EXT", help="change the extension of subreddit "
                      "list files [default: \"{0}\"]".
                      format(DEFAULT_LIST_EXTENSION))
    parser.add_option("--shuffle", action="store", dest="shuffle",
                      type="string", default=DEFAULT_SHUFFLE, metavar="OPTIONS",
                      help="changes the shuffling behaviour.Valid OPTIONS "
                      "include: lists, list-subreddits, all-subreddits")


    group = optparse.OptionGroup(parser, "filter options")
    group.add_option("--no-sfw", action="store_true", dest="no_sfw",
                     default=DEFAULT_NO_SFW, help="do not download images that "
                     "are sfw")
    group.add_option("--no-nsfw", action="store_true", dest="no_nsfw",
                     default=DEFAULT_NO_NSFW, help="do not download images that "
                     "are nsfw")
    group.add_option("--score", action="store", type="int", dest="score",
                     default=DEFAULT_SCORE, help="do not download images with a "
                     "rating lower than SCORE", metavar="SCORE")
    group.add_option("--regex", action="store", type="string", dest="regex",
                     default=DEFAULT_REGEX, help="only download images with "
                     "titles that match the given regular expression")
    parser.add_option_group(group)

    group = optparse.OptionGroup(parser, "download options")
    group.add_option("--max", action="store", type="int", dest="max_downloads",
                     default=0, help="download a maximum of NUM pictures per "
                     "subreddit", metavar="NUM")
    group.add_option("--flood-timeout", action="store", type="int",
                     dest="flood_timeout", default=DEFAULT_FLOOD_TIMEOUT,
                     metavar="MILLISECONDS", help="wait MILLISECONDS between "
                     "connections to the server [default: {0}]".
                     format(DEFAULT_FLOOD_TIMEOUT))

    parser.add_option_group(group)

    group = optparse.OptionGroup(parser, "output control")
    group.add_option("-q", "--quiet", action="store_true", dest="quiet",
                      help="be more quiet")
    group.add_option("-v", "--verbose", action="store_true", dest="verbose",
                      help="be more verbose")
    parser.add_option_group(group)

    group = optparse.OptionGroup(parser, "debug options")
    group.add_option("--debug", action="store_true", dest="debug",
                     help="print debug information")
    parser.add_option_group(group)

    (options, args) = parser.parse_args(sys.argv[1:])

    destination = options.destination
    regex = options.regex
    score = options.score
    no_sfw = options.no_sfw
    no_nsfw = options.no_nsfw
    max_downloads = options.max_downloads
    max_threads = options.max_threads
    flood_timeout = options.flood_timeout
    list_extension = options.list_extension
    shuffle = options.shuffle
    recursive = options.recursive
    verbose = options.verbose

    shuffle_lists = DEFAULT_SHUFFLE_LISTS
    shuffle_list_subreddits = DEFAULT_SHUFFLE_LIST_SUBREDDITS
    shuffle_all_subreddits = DEFAULT_SHUFFLE_ALL_SUBREDDITS

    if shuffle:
        shuffle_options = shuffle.split(',')
        if "lists" in shuffle_options:
            shuffle_lists = True
        if "list-subreddits" in shuffle_options:
            shuffle_list_subreddits = True
        if "all-subreddits" in shuffle_options:
            shuffle_all_subreddits = True
        # well ... it works?
        if [shuffle_lists, shuffle_list_subreddits, shuffle_all_subreddits].\
                count(True) != len(shuffle_options):
            print("--shuffle: invalid options: {0}".format(shuffle))
            sys.exit(ERROR_INVALID_COMMAND_LINE)

    if list_extension[0] != '.':
        list_extension = ".{0}".format(list_extension)

    if len(args) < 1:
        parser.error("expected at least one argument")

    if not os.path.isdir(destination):
        if os.path.exists(destination):
            print("Invalid destination: {0}".format(
                destination))
            sys.exit(EXIT_INVALID_DESTINATION)
        if not options.create_destination:
           print("{0} does not exist and shall now be created.".
                format(destination))
           sys.exit(EXIT_INVALID_DESTINATION)
        os.mkdir(destination)

    # arguments and options should be sane, we can start logging now
    logger = logging.getLogger()

    logger.setLevel(logging.DEBUG)

    logging.VERBOSE = 15
    logging.addLevelName(logging.VERBOSE, "VERBOSE")
    logging.Logger.verbose = \
        lambda obj, msg, *args, **kwargs: \
            obj.log(logging.VERBOSE, msg, *args, **kwargs)

    #logger.verbose = \
    #    lambda msg, *args, **kwargs: \
    #        logger.log(logging.VERBOSE, msg, *args, **kwargs)

    need_rollover = False
    if os.path.isfile(logfile):
        need_rollover = True

    stdout_handler = logging.StreamHandler(sys.stdout)
    stderr_handler = logging.StreamHandler(sys.stderr)
    logfile_handler = logging.NullHandler()
    logfile_handler = logging.handlers.RotatingFileHandler(logfile,
                                                           backupCount=9)

    if need_rollover:
        logfile_handler.doRollover()

    stdout_handler.addFilter(LevelFilter(minlvl=logging.NOTSET,
                                         maxlvl=logging.WARNING - 1))
    stderr_handler.addFilter(LevelFilter(minlvl=logging.WARNING,
                                         maxlvl=logging.CRITICAL))

    console_logging_level = logging.INFO
    if options.debug:
        console_logging_level = logging.DEBUG
    elif options.verbose:
        console_logging_level = logging.VERBOSE
    elif options.quiet:
        console_logging_level = logging.WARNING

    stdout_handler.setLevel(console_logging_level)
    stderr_handler.setLevel(console_logging_level)
    logfile_handler.setLevel(logging.DEBUG)

    formatter = logging.Formatter(
        fmt="[{asctime}] [{levelname}] [{threadName}] {message}",
        style='{')

    stdout_handler.setFormatter(formatter)
    stderr_handler.setFormatter(formatter)
    logfile_handler.setFormatter(formatter)

    logger.addHandler(stdout_handler)
    logger.addHandler(stderr_handler)
    logger.addHandler(logfile_handler)

    logger.debug("Logging setup completed")
    logger.debug("Command line: \"%s\"", " ".join(sys.argv))
    logger.debug("Options extracted: %s", options)
    logger.debug("Arguments extracted: %s", args)

    # TODO Dude, there is some work left in the next block ...
    paths = list() # lazyness
    # [ ( PATH , [ SUBREDDITS , ... ] ) , ... ]
    # Cannot be a dict, otherwise correct order would not be guaranteed
    lists = list()
    for path in args:
        if os.path.isdir(path):
            for list_path in get_lists(path, recursive=recursive,
                                      list_extension=list_extension):
                if list_path in paths:
                    logger.info("%s already encountered, ignored.", list_path)
                else:
                    lists.append((list_path, list()))
                    paths.append(list_path)
        elif os.path.isfile(path):
            if check_file(path, list_extension):
                if path in paths:
                    logger.info("%s already encountered, ignored.", path)
                else:
                    lists.append((path, list()))
                    paths.append(path)
        else:
            logger.error("Invalid path: %s not found.", path)

    if len(lists) == 0:
        logger.error("No lists found.")
        sys.exit(0)

    for (path, subreddits) in lists:
        subreddits.extend(parse_file(path))

    logger.debug("Subreddit lists: %s", lists)

    # shuffle subreddits in every list if necessary. if all subreddits all
    # shuffled anyway, we can skip this
    if shuffle_list_subreddits and not shuffle_all_subreddits:
        logger.debug("Shuffling subreddits in every list.")
        for (_, subreddits) in lists:
            random.shuffle(subreddits)

    # shuffle lists if necessary. again, not if all subreddits are shuffled
    # anyway
    if shuffle_lists and not shuffle_all_subreddits:
        logger.debug("Shuffling lists.")
        random.shuffle(lists)

    # if all subreddits should be shuffled, we have to repack "lists". we pack
    # all subreddits under one list
    if shuffle_all_subreddits:
        logger.critical("function implementation faulty, DO NO USE")
        raise NotImplementedError()
        all_subreddits_list = list()
        all_subreddits_list.append(("shuffled-subreddits",list()))
        for (_, subreddits) in lists:
            all_subreddits_list[0][1].extend(subreddits)
        lists = all_subreddits_list

    threadqueue = queue.Queue()
    lock = threading.Lock()

    total_processed = 0
    total_downloaded = 0
    total_skipped = 0
    total_errors = 0

    for (path, subreddits) in lists:
        logger.debug("Working on list \"%s\" with subreddits %s.", path,
                     subreddits)
        list_destination = os.path.join(
            destination, os.path.basename(path)[:-len(list_extension)])
        logger.debug("Desination set to \"%s\"", list_destination)
        if not os.path.isdir(list_destination):
            logger.debug("\"%s\" is not a directory.", list_destination)
            if os.path.exists(list_destination):
                logger.debug("\"%s\" is a valid path.", list_destination)
                logger.error("Invalid destination: %s. Skipping list %s",
                             list_destination, path)
                continue
            logger.debug("Creating destination directory \"%s\".",
                         list_destination)
            os.mkdir(list_destination)
        logger.info("Downloading subreddits in list \"%s\" into folder \"%s\"",
              os.path.basename(path), list_destination)
        for subreddit in subreddits:
            # Feed the queue
            threadqueue.put((subreddit, list_destination))
        # Start processing threads
        for i in range(min(len(subreddits), max_threads)):
            thread = threading.Thread(target=download_subreddit)
            thread.start()
            logger.debug("Started thread %s", thread.name)
            # prevent all threads from starting simultaneously
            time.sleep(flood_timeout/1000)
        logger.debug("Waiting for threads to finish ...")
        threadqueue.join()
        logger.debug("All threads finished.")
        logger.info("Downloads from subreddits in list \"%s\" completed, can "
            "be found in %s", os.path.basename(path), list_destination)


    logger.info("--------------------------------------")
    logger.info("Finished downloading.")
    logger.info("Total downloaded files: %s", total_downloaded)
    logger.info("Total skipped/errors:   %s/%s", total_skipped, total_errors)
    logger.info("Total processed:        %s", total_processed)
    logger.info("--------------------------------------")

    logger.debug("Shutting down logging system. Bye.")
    logging.shutdown()
