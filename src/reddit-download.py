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


if __name__ == '__main__':
    main()
