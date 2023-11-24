__version__ = '0.0.2'

from os import listdir
from os.path import isdir, isfile, join
from time import time

import argparse
from . import comic
from . import comicvine
import magic
import minorimpact
import minorimpact.config
import os
import os.path
import pickle
import re
import shutil
import sys

cache = {}

def main():
    global cache

    config = minorimpact.config.getConfig(script_name = 'yyreader')


    parser = argparse.ArgumentParser(description = "yyreader", formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument('action', nargs='?', default='box', help = '''Specify one of the following:
  'box'  Move files in DIR to TARGET (default)
  'verify'   scan files in TARGET for incomplete meta data.''')
    parser.add_argument('--file', metavar = 'FILE',  help = "process FILE")
    parser.add_argument('--dir', metavar = 'DIR',  help = "process files in DIR")
    parser.add_argument('--target', metavar = 'TARGET',  help = "Move files to TARGET", default = config['default']['comic_dir'])
    parser.add_argument('--year', metavar = 'YEAR', help = "Assume YEAR for any file that doesn't include it")
    parser.add_argument('--existing', metavar = 'EXIST', help = "Move any files that already exist to EXIST", default = config['default']['existing_dir'])
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
            args.file = None

    read_cache(config['default']['cache_file'], args = args)

    if (args.action == 'box'):
        if (args.dir is not None):
            if (os.path.exists(args.dir) is False):
                raise Exception(f"{args.dir} does not exist")
            if (os.path.isdir(args.dir) is False):
                raise Exception(f"{args.dir} is not a directory")

            c_files = minorimpact.readdir(args.dir)
        elif (args.file is not None):
            c_files = [ args.file ]

        for c_file in c_files:
            box(c_file, args.target, args = args)
            write_cache(config['default']['cache_file'], args = args)

    elif (args.action == 'verify'):
        c_files = minorimpact.readdir(args.target)
        i = 0
        for c_file in c_files:
            i = i + 1
            if (i > 2): break
            verify(c_file, args = args)
            write_cache(config['default']['cache_file'])

def box(comic_file, target, args = minorimpact.default_arg_flags):
    global cache

    if (os.path.exists(comic_file) is False):
        print(f"{comic_file} does not exist")
        return
    print("boxing {}".format(comic_file))

    (root, ext) = os.path.splitext(comic_file)
    if (root + ext.lower() != comic_file):
        comic_file = change_extension(comic_file, ext.lower())

    try:
        c = comic.comic(comic_file, cache = cache)
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

def read_cache(cache_file, args = minorimpact.default_arg_flags):
    global cache

    if (cache_file is None):
        if (args.debug): print("no cache file defined")
        return

    if (os.path.exists(cache_file) is True):
        if (args.debug): print("reading cache from {}".format(cache_file))
        with open(cache_file, 'rb') as f:
            cache = pickle.load(f)
    else:
        if (args.debug): print("{} does not exist".format(cache_file))

def verify (comic_file, args = minorimpact.default_arg_flags):
    global cache
    print("verifying {}".format(comic_file))

    c = comic.comic(comic_file, cache = cache)
    comicvine_data = c.comicvine_search(args = args, headless = args.yes)
    parse_data = c.parse_data
    print(parse_data)
    print(comicvine_data)
    # write the data the file.  take this code from comic.box() and break it out into a function.

def write_cache(cache_file, args = minorimpact.default_arg_flags):
    global cache

    if (cache_file is None):
        if (args.debug): print("no cache file defined")
        return

    if (args.debug): print("writing cache to {}".format(cache_file))
    pickle_data = pickle.dumps(cache)
    done = False
    interrupted = False
    while done is False:
        try:
            with open(cache_file, 'wb') as f:
                f.write(pickle_data)
            done = True
        except KeyboardInterrupt:
            print("cache dump interrupted - retrying")
            interrupted = True
            continue
    if (interrupted is True):
        sys.exit()


