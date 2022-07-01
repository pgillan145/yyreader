__version__ = '0.0.2'

from os import listdir
from os.path import isdir, isfile, join
from time import time

import argparse
from . import comic
import minorimpact
import minorimpact.config
import os
import os.path
import re
import sys

def main():
    parser = argparse.ArgumentParser(description = "yyreader")
    parser.add_argument('--file', metavar = 'FILE',  help = "process FILE")
    parser.add_argument('--dir', metavar = 'DIR',  help = "process files in DIR")
    parser.add_argument('--target', metavar = 'TARGET',  help = "Move files to TARGET")
    parser.add_argument('--year', metavar = 'YEAR', help = "Assume YEAR for any file that doesn't include it")
    parser.add_argument('--debug', help = "extra extra loud output", action='store_true')
    parser.add_argument('-d', '--dryrun', help = "don't actually make any changes to anything", action='store_true')
    parser.add_argument('-v', '--verbose', help = "extra loud output", action='store_true')
    parser.add_argument('-y', '--yes', help = "Always say yes", action='store_true')
    args = parser.parse_args()
    if (args.debug): args.verbose = True

    config = minorimpact.config.getConfig(script_name = 'yyreader')

    if (args.file is not None):
        c_file = re.sub('/$','', args.file)
        if (os.path.exists(c_file) is False):
            sys.exit(f"{c_file} does not exist")
        
        try:
            c = comic.comic(c_file)
            c.box(args.target, args = args)
        except Exception as e:
            print(e)
    else:
        comic_dir = args.dir
        if (os.path.exists(comic_dir) is False):
            raise Exception(f"{comic_dir} does not exist")

        files = minorimpact.readdir(comic_dir)
        for c_file in files:
            if ('ByName' in c_file or 'ByDate' in c_file):
                continue
            try:
                c = comic.comic(c_file)
                c.box(args.target, args = args)
            except Exception as e:
                print(e)
        pass

