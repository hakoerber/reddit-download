# -*- encoding: utf-8 -*-
# Copyright (c) 2013 Hannes Körber <hannes.koerber@gmail.com>
#
# This file is part of reddit-download.
#
# autobackup is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# autobackup is distributed in the hope that it will be useful,
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

import RedditImageGrab.redditdownload

DEFAULT_LIST_EXTENSION = ".list"
DEFAULT_FLOOD_TIMEOUT = 1000
DEFAULT_MAX_THREADS = 10
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

COMMENT_CHAR = "#"

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
        return [path for path in os.listdir(directory)
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

def main():
    usage = "Usage: %prog [options] FILE/DIRECTORY..."
    version = "%prog 0.1-dev"
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
                      "list files [default: {0}]".
                      format(DEFAULT_LIST_EXTENSION))
    parser.add_option("--flood-timeout", action="store", type="int",
                      dest="flood_timeout", default=DEFAULT_FLOOD_TIMEOUT,
                      metavar="MILLISECONDS", help="wait MILLISECONDS between "
                      "connections to the server [default: {0}]".
                      format(DEFAULT_FLOOD_TIMEOUT))
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
    parser.add_option_group(group)

    group = optparse.OptionGroup(parser, "output control")
    group.add_option("-q", "--quiet", action="store_false", dest="verbose",
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
    recursive=options.recursive

    shuffle_lists = DEFAULT_SHUFFLE_LISTS
    shuffle_list_subreddits = DEFAULT_SHUFFLE_LIST_SUBREDDITS
    shuffle_all_subreddits = DEFAULT_SHUFFLE_ALL_SUBREDDITS
    if shuffle:
        options = shuffle.split(',')
        if "lists" in options:
            shuffle_lists = True
        if "list-subreddits" in options:
            shuffle_list_subreddits = True
        if "all-subreddits" in options:
            shuffle_all_subreddits = True
        # well ... it works?
        if [shuffle_lists, shuffle_list_subreddits, shuffle_all_subreddits].\
                count(True) != len(options):
            print("--shuffle: invalid options: {0}".format(shuffle))

    if list_extension[0] != '.':
        list_extension = ".{0}".format(list_extension)

    if len(args) < 1:
        parser.error("expected at least one argument")

    if not os.path.exists(destination):
        if not options.create_destination:
            print("{0} does not exist and shall now be created.".
                format(destination))
            sys.exit(1)
        else:
            os.mkdir(destination)

    if not os.path.isdir(destination):
        print("{0} is not a valid directory.".format(destination))
        sys.exit(2)

    # TODO Dude, there is some work left in the next block ...
    paths = list() # lazyness
    # [ ( PATH , [ SUBREDDITS , ... ] ) , ... ]
    # Cannot be a dict, otherwise correct order would not be guaranteed
    lists = list()
    for path in args:
        if os.path.isdir(path):
            for path in get_lists(path, recursive=recursive,
                                  list_extension=list_extension):
                if path in paths:
                    print("{0} already encountered, ignored.".format(path))
                else:
                    lists.append((path, list()))
                    paths.append(path)
        elif os.path.isfile(path):
            if check_file(path):
                if path in paths:
                    print("{0} already encountered, ignored.".format(path))
                else:
                    lists.append((path, list()))
                    paths.append(path)
        else:
            print("Invalid path: {0} not found.".format(
                path))

    for (path, subreddits) in lists:
        subreddits.extend(parse_file(path))

    if len(lists) == 0:
        print("No lists found.")
        sys.exit(0)

    # shuffle subreddits in every list if necessary. if all subreddits all
    # shuffled anyway, we can skip this
    if shuffle_list_subreddits and not shuffle_all_subreddits:
        for (_, subreddits) in lists:
            random.shuffle(subreddits)

    # shuffle lists if necessary. again, not if all subreddits are shuffled
    # anyway
    if shuffle_lists and not shuffle_all_subreddits:
        random.shuffle(lists)

    # if all subreddits should be shuffled, we have to repack "lists". we pack
    # all subreddits under one list
    if shuffle_all_subreddits:
        all_subreddits_list = list()
        all_subreddits_list.append(("shuffled-subreddits",list()))
        for (_, subreddits) in lists:
            all_subreddits_list[0][1].extend(subreddits)
        lists = all_subreddits_list


    threadqueue = queue.Queue()

    # Worker method
    def download_subreddit():
        while True:
            try:
                (subreddit, destination) = threadqueue.get(block=False)
            except queue.Empty:
                print("No more items to process. Thread done.")
                return
            print("Starting download from /r/{0} to {1}".
                  format(subreddit, destination))

            (total, downloaded, skipped, errors) = \
                RedditImageGrab.redditdownload.download(
                    subreddit, destination, last="", score=score,
                    num=max_downloads, update=False, sfw=(not no_sfw),
                    nsfw=(not no_nsfw), regex=regex, verbose=False, quiet=True)

            print("Done downloading from /r/{0} to {1}".
                  format(subreddit, destination))
            print ("Downloaded: {0}, skipped/errors {1}/{2}, ",
                   "total processed: {3}".format(downloaded, skipped, errors,
                                                 total))
            threadqueue.task_done()

    for (path, subreddits) in lists:
        print("Downloading subreddits in list \"{0}\" into folder {1}".
              format(os.path.basename(path), destination))
        for subreddit in subreddits:
            # Feed the queue
            threadqueue.put((subreddit, destination))
        # Start processing threads
        for i in range(min(len(subreddits), max_threads)):
            thread = threading.Thread(target=download_subreddit)
            thread.start()
            # prevent all threads from starting simultaneously
            time.sleep(flood_timeout/1000)
        threadqueue.join()
        print("Downloads from subreddits in list \"{0}\" completed, can be"
              "found in {1}".
              format(os.path.basename(path), destination))




if __name__ == '__main__':
    main()
