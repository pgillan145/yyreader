#!/usr/bin/env python3

import argparse
from datetime import datetime, timedelta
from dumper import dump
from yyreader import comic
import magic
import minorimpact
import minorimpact.config
import os
import os.path
import re
import sqlite3
import sys
import re
import shutil
import yyreader.backend

config = None

def main():
    global config

    argparser = argparse.ArgumentParser(description="Scan comic directory", formatter_class=argparse.RawTextHelpFormatter)

    argparser.add_argument('-v', '--verbose', action='store_true')
    argparser.add_argument('-y', '--yes', action='store_true')
    argparser.add_argument('-1', '--one', help = "Just process a single entry, for testing.  Also enables --verbose and --debug.", action='store_true')
    argparser.add_argument('-u', '--update', action='store_true', help = "Update item metadata.")
    argparser.add_argument('--debug', action='store_true')
    argparser.add_argument('--dryrun', action='store_true')

    #argparser.add_argument('--comicvine',  help = "Pull external comicvine data when running --update, otherwise just update with what can be parsed from the filename.", action='store_true')
    #argparser.add_argument('--series', metavar = 'VOL', help = "Only --update or --scan comics in VOL.")


    args = argparser.parse_args()
    config = minorimpact.config.getConfig(script_name = 'yyreader')

    if (args.one is True):
        args.verbose = True
        args.debug = True

    yyreader.backend.init_db()

    db = yyreader.backend.connect()
    cur = db.cursor()

    comic_dir = config['default']['comic_dir']
    if (args.verbose): print(f"reading {comic_dir}")
    comic_files = minorimpact.readdir(comic_dir)
    i = 0
    for comic_file in sorted(comic_files):
        #if (re.search('Deadpool & Wolverine WWIII', comic_file) is None): continue
        c = comic.comic(comic_file)
        try:
            yyreader.backend.scan(c)
        except Exception as e:
            continue
        if (args.one is True): break

    db.close()


if __name__ == '__main__':
    main()
