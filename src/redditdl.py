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

LIST_EXTENSION = ".list"
COMMENT_CHAR = "#"

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




if __name__ == '__main__':
    main()
