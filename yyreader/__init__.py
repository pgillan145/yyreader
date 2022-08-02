__version__ = '0.0.2'

from os import listdir
from os.path import isdir, isfile, join
from time import time

import argparse
from . import comic
import magic
import minorimpact
import minorimpact.config
import os
import os.path
import re
import shutil
import sys

def main():
    config = minorimpact.config.getConfig(script_name = 'yyreader')

    parser = argparse.ArgumentParser(description = "yyreader")
    parser.add_argument('--file', metavar = 'FILE',  help = "process FILE")
    parser.add_argument('--dir', metavar = 'DIR',  help = "process files in DIR")
    parser.add_argument('--target', metavar = 'TARGET',  help = "Move files to TARGET", default = config['default']['comic_dir'])
    parser.add_argument('--year', metavar = 'YEAR', help = "Assume YEAR for any file that doesn't include it")
    parser.add_argument('--existing', metavar = 'EXIST', help = "Move any files that already exist to EXIST")
    parser.add_argument('--debug', help = "extra extra loud output", action='store_true')
    parser.add_argument('-d', '--dryrun', help = "don't actually make any changes to anything", action='store_true')
    parser.add_argument('-v', '--verbose', help = "extra loud output", action='store_true')
    parser.add_argument('-y', '--yes', help = "Always say yes", action='store_true')
    args = parser.parse_args()
    if (args.debug): args.verbose = True

    if (args.existing is not None):
        args.existing = re.sub('/$','', args.existing)
        if (os.path.isdir(args.existing) is False):
            sys.exit(f"{args.existing} doesn't exist.")

    if (args.file is not None):
        c_file = re.sub('/$','', args.file)
        if (os.path.exists(c_file) and os.path.isdir(c_file) and args.dir is None):
            args.dir = c_file

    if (args.dir is not None):
        if (os.path.exists(args.dir) is False):
            raise Exception(f"{args.dir} does not exist")

        for c_file in minorimpact.readdir(args.dir):
            box(c_file, args.target, args = args)

    elif (args.file is not None):
        box(args.file, args.target, args = args)

def box(comic_file, target, args = minorimpact.default_arg_flags):
    if (os.path.exists(comic_file) is False):
        print(f"{comic_file} does not exist")
        return
    print("processing {}".format(comic_file))

    (root, ext) = os.path.splitext(comic_file)
    if (root + ext.lower() != comic_file):
        comic_file = change_extension(comic_file, ext.lower())

    try:
        c = comic.comic(comic_file)
        c.box(args.target, args = args)
    except comic.ExtensionMismatchException as e:
        print(e)
        magic_str = magic.from_file(comic_file)
        new_ext = None
        for ext2 in comic.ext_map:
            if (re.search('^{}'.format(comic.ext_map[ext2]), magic_str)):
                new_ext = ext2
                break
        if (new_ext is not None):
            new_comic_file = change_extension(comic_file, new_ext)
            if (new_comic_file != comic_file and new_comic_file is not None):
                try:
                    c = comic.comic(new_comic_file)
                    c.box(args.target, args = args)
                except comic.FileExistsException as e:
                    print(e)
                    if (args.existing is not None):
                        print(f"  moving {c.file} to {args.existing}")
                        if (args.dryrun is False): shutil.move(c.file, args.existing)
                except Exception as e:
                    print(e)
        else:
            print("{} has unknown data: '{}'".format(comic_file, magic_str))
    except comic.FileExistsException as e:
        print(e)
        if (args.existing is not None):
            print(f"  moving {c.file} to {args.existing}")
            if (args.dryrun is False): shutil.move(c.file, args.existing)
    except Exception as e:
        print(e)

def change_extension(file_name, new_extension):
    if (re.search(r'^\.', new_extension)):
        new_extension = re.sub(r'^\.', '', new_extension)
    (root, ext) = os.path.splitext(file_name)
    new_file = re.sub(ext, '.' + new_extension, file_name)
    print(f"  moving {file_name} to {new_file}")
    shutil.move(file_name, new_file)
    return new_file

