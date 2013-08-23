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
import time
import random

LIST_EXTENSION = ".list"
COMMENT_CHAR = "#"
MAX_THREADS = 10

def check_file(file_path):
    return (file_path.endswith(LIST_EXTENSION)
            and os.path.basename(file_path) != LIST_EXTENSION)

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

    #group = optparse.OptionGroup(parser, "standard options")
    #parser.add_option_group(group)

    (options, args) = parser.parse_args(sys.argv[1:])

    if len(args) < 1:
        parser.error("expected at least one argument")

    destination = options.destination

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
            print("start downlading from ", subreddit)
            time.sleep(random.randrange(1,10))
            print("done downloading from ", subreddit)
            threadqueue.task_done()

    for (path, subreddits) in lists:
        print("Downloading subreddits in list \"{0}\" into folder {1}".
              format(os.path.basename(path), destination))
        for subreddit in subreddits:
            # Feed the queue
            threadqueue.put((subreddit, destination))
        # Start processing threads
        for i in range(MAX_THREADS):
            thread = threading.Thread(target=download_subreddit)
            print("Starting thread...")
            thread.start()
        threadqueue.join()
        print("Downloads from subreddits in list \"{0}\" completed, can be"
              "found in {1}".
              format(os.path.basename(path), destination))




if __name__ == '__main__':
    main()
