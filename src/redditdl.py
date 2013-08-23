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

import RedditImageGrab.redditdownload

DEFAULT_LIST_EXTENSION = ".list"
COMMENT_CHAR = "#"

def check_file(file_path):
    return (file_path.endswith(list_extension)
            and os.path.basename(file_path) != list_extension)

def get_lists(directory, recursive):
    if recursive:
        paths = list()
        for (root, _, files) in os.walk(directory):
            for filename in files:
                path = os.path.join(root, filename)
                if check_file(path):
                    paths.append(path)
        return paths
    else:
        return [path for path in os.listdir(directory)
                if check_file(path)]

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
                      dest="recursive", default=False,
                      help="search the directories recursively")
    parser.add_option("-d", "--dest", dest="destination", metavar="DEST",
                      default=os.getcwd(),
                      help="the directory to download to, defaults to the "
                      "current working directory")
    parser.add_option("-c", "--create-dest", dest="create_destination",
                      default=False, help="create the destination directory if "
                      "it does not exist", action="store_true")
    parser.add_option("-t", "--threads", action="store", type="int",
                      dest="max_threads", default=10, metavar="NUM",
                      help="create a maximum of NUM threads [default: 10]")
    parser.add_option("-e", "--extension", action="store", type="string",
                      dest="list_extension", default=DEFAULT_LIST_EXTENSION,
                      metavar="EXT", help="change the extension of subreddit "
                      "list files [default: .list]")

    group = optparse.OptionGroup(parser, "filter options")
    group.add_option("--no-sfw", action="store_true", dest="nosfw",
                     default=False, help="do not download images that are sfw")
    group.add_option("--no-nsfw", action="store_true", dest="nonsfw",
                     default=False, help="do not download images that are nsfw")
    group.add_option("--score", action="store", type="int", dest="score",
                     default=0, help="do not download images with a rating "
                     "lower than SCORE", metavar="SCORE")
    group.add_option("--regex", action="store", type="string", dest="regex",
                     default=None, help="only download images with titles that "
                     "match the given regular expression")
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
    nosfw = options.nosfw
    nonsfw = options.nonsfw
    max_downloads = options.max_downloads
    max_threads = options.max_threads
    list_extension = options.list_extension
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
            for path in get_lists(path, recursive=options.recursive):
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
                    num=max_downloads, update=False, sfw=(not nosfw),
                    nsfw=(not nonsfw), regex=regex, verbose=False, quiet=True)

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
        threadqueue.join()
        print("Downloads from subreddits in list \"{0}\" completed, can be"
              "found in {1}".
              format(os.path.basename(path), destination))




if __name__ == '__main__':
    main()
