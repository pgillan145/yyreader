__version__ = '0.0.2'

from os import listdir
from os.path import isdir, isfile, join
from time import time

import argparse
from . import comic
from . import comicvine
from . import parser
from datetime import datetime, timedelta
from dumper import dump
from hashlib import md5
import magic
import minorimpact
import minorimpact.config
import os
import os.path
import pickle
import re
import shutil
import sys
import traceback

cache = {}

def main():
    global cache

    config = minorimpact.config.getConfig(script_name = 'yyreader')


    argparser = argparse.ArgumentParser(description = "yyreader", formatter_class=argparse.RawTextHelpFormatter)
    argparser.add_argument('action', nargs='?', default='box', help = '''Specify one of the following:
  'box'  Move files in DIR to TARGET (default)
  'verify'   scan files in TARGET for incomplete meta data.''')
    argparser.add_argument('--clear_cache', help = "Clear the cache.", action='store_true')
    argparser.add_argument('--file', metavar = 'FILE',  help = "process FILE")
    argparser.add_argument('--filter', metavar = 'FILTER',  help = "Only verify series that match FILTER")
    argparser.add_argument('--dir', metavar = 'DIR',  help = "process files in DIR")
    argparser.add_argument('--large', help = "allow importing files larger than 'maximum_file_size' MB. default: 100", action='store_true')
    argparser.add_argument('--one', help = " ", action='store_true')
    argparser.add_argument('--publisher', metavar = 'PUBLISHER',  help = "limit scan to PUBLISHER")
    argparser.add_argument('--slow', help = "Pull comicvine data at a slightly reduced rate, so as not to stress the API.", action='store_true')
    argparser.add_argument('--small', help = f"allow importing files smaller than 'minimum_file_size' MB. default: 1", action='store_true')
    argparser.add_argument('--target', metavar = 'TARGET',  help = "Move files to TARGET", default = config['default']['comic_dir'])
    argparser.add_argument('--year', metavar = 'YEAR', help = "When adding new items, assume YEAR for any file that doesn't include it.  While scanning, limit results to YEAR.")
    argparser.add_argument('--existing', metavar = 'EXIST', help = "Move any files that already exist to EXIST", default = config['default']['existing_dir'])
    argparser.add_argument('--debug', help = "extra extra loud output", action='store_true')
    argparser.add_argument('-d', '--dryrun', help = "don't actually make any changes to anything", action='store_true')
    argparser.add_argument('-v', '--verbose', help = "extra loud output", action='store_true')
    argparser.add_argument('-y', '--yes', help = "Always say yes", action='store_true')
    args = argparser.parse_args()
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
    # 'verify' is essentially just running 'box' on everything that's in the target directory.  The main difference is that it will
    #    maintain a log of everything it's already verified so as not to have to run through again unless it's changed -- but under the hood
    #   they are both running the 'box' method, which renames, moves and updates the comicinfo.xml file based on informatin it pulls from
    #   comicvine.  'scan' runs through each series directory looking for 'missing' issues.
    if (args.action == 'box'):
        if (args.dir is not None):
            if (os.path.exists(args.dir) is False):
                raise Exception(f"{args.dir} does not exist")
            if (os.path.isdir(args.dir) is False):
                raise Exception(f"{args.dir} is not a directory")

            c_files = minorimpact.readdir(args.dir)
        elif (args.file is not None):
            c_files = [ args.file ]

        for c_file in sorted(c_files):
            box(c_file, args.target, args = args, large = args.large, small = args.small)
            write_cache(config['default']['cache_file'], args = args)

    elif (args.action == 'verify'):
        if ('verify' not in cache or args.clear_cache is True):
            cache['verify'] = {}

        base_dir = args.target
        if (args.dir is not None):
            base_dir = args.dir
        c_files = sorted(minorimpact.readdir(base_dir))
        file_count = len(c_files)

        i = 0
        for c_file in c_files:
            i = i + 1
            if (args.filter and re.search(args.filter, c_file) is None):
                continue

            if (args.verbose): print(f"\rscanning {i}/{file_count}", end='')
            # Don't re-test anything until we've tested everything new.
            if (c_file in cache['verify']): continue

            try:
                if (args.verbose): print(f"\rscanning {i}/{file_count}", end='')
                c = verify(c_file, base_dir, args = args)
            except comicvine.VolumeNotFoundException as e:
                print(e)
            except comic.FileExistsException as e:
                print(e)
            except comic.FileSizeException as e:
                print(e)

            write_cache(config['default']['cache_file'])

        i = 0
        for c_file in c_files:
            if (args.filter and re.search(args.filter, c_file) is None):
                continue
            i = i + 1
            #if (i > 10 and args.yes): break
            try:
                if (args.verbose): print(f"\rscanning {i}/{file_count}", end='')
                c = verify(c_file, args.target, args = args)
            except comicvine.VolumeNotFoundException as e:
                print(e)
            except comic.FileExistsException as e:
                print(e)
            except comic.FileSizeException as e:
                print(e)


    elif (args.action == 'scan'):
        if ('missing_log' not in config['default'] or config['default']['missing_log'] == ''):
            print(f"{config['default']['missing_log']} not set")
            sys.exit()

        missing = {}
        # if config['default']['missing_log'] exists
        if (os.path.exists(config['default']['missing_log'])):
            with open(config['default']['missing_log'], 'r') as f:
                # Load data into missing object
                line = f.readline()
                s = line.split('/')
                if (len(s) == 3):
                    (publisher, series, issue) = s
                    if (publisher not in missing):
                        missing[publisher] = {}
                    if (series not in missing[publisher]):
                        missing[publisher][series] = []
                    missing[publisher][series].append(issue)
                else:
                    print(f"invalid line: '{line}'")
        api_key = config['comicvine']['api_key']
        oldest_year = 1901
        if ('oldest_year' in config['default']):
            oldest_year = int(config['default']['oldest_year'])

        if (api_key is None):
            raise(Exception("No comicvine api key defined"))

        if ('scan' not in cache or args.clear_cache is True):
            cache['scan'] = {}
        publishers = sorted(os.listdir(args.target))
        i = 0
        for publisher in publishers:
            if (re.match("^\.", publisher)): continue
            if (args.publisher is not None and args.publisher.lower() != publisher.lower()):
                continue
            if (publisher not in cache['scan']): cache['scan'][publisher] = {}
            if (publisher not in missing): missing[publisher] = {}
            if (args.debug): print(f"{publisher}/")
            seriess = sorted(os.listdir(args.target + '/' + publisher))
            for series in seriess:
                if (re.match("^\.", series)): continue
                if (args.debug): print(f"  {series}")

                start_year= None
                ver = None
                parsed_series = parser.parse_series(series) #, debug = args.debug)
                if ('volume' in parsed_series):
                    start_year = parsed_series['volume']['start_year']
                    ver = parsed_series['volume']['ver']
                    volume = parser.make_volume(parsed_series['volume']['start_year'], ver = parsed_series['volume']['ver'])

                if (args.year is not None and int(start_year) > int(args.year)):
                    if (args.debug): print(f"  released after {start_year}, skipping")
                    continue

                c_dir = args.target + '/' + publisher + '/' + series
                c_md5 = minorimpact.md5dir(c_dir)

                if (series in cache['scan'][publisher] and
                    cache['scan'][publisher][series]['version'] == __version__ and
                    'md5' in cache['scan'][publisher][series] and cache['scan'][publisher][series]['md5'] == md5):
                    if (args.debug): print("    cached, skipping")
                    continue

                c_files = os.listdir(c_dir)
                series_name = parser.series_filename(series, reverse = True)

                issues = {}

                for c_file in c_files:
                    if (re.match("^\.", c_file)): continue
                    c = comic.comic(c_dir + '/' + c_file, cache = cache, verbose = args.verbose, debug = False)
                    issues[parser.massage_issue(c.issue())] = parser.parse_date(c.date())

                valid_year = False
                for issue in issues.keys():
                    # If we asked to scan a particular year, only work on seriess with issues released during that
                    #   year.
                    if (args.year is not None and args.year == issues[issue]['year']):
                        valid_year = True
                        break

                if (args.year is True and valid_year is False):
                    if (args.debug): print(f"    no releases in {args.year}. skipping")
                    continue

                if (len(issues) > 0):
                    print("    collecting volume info from comicvine")
                    try:
                        result = comicvine.search_volumes(series_name, api_key, start_year = start_year, cache = cache, verbose = args.verbose, headless = args.yes, debug = False) #debug = args.debug)
                    except Exception as e:
                        print(e)
                        continue

                    if (result is None):
                        print("    can't find comicvine match, skipping")
                    else:
                        series_total = result['count_of_issues']
                        series_count = len(issues)
                        if (series_count == series_total):
                            if (args.verbose): print("    {}/{} totals match".format(series_count, series_total))
                        else:
                            if (args.debug): print("    collecting issue list from comicvine")
                            comicvine_issues = comicvine.get_issues(result['id'], api_key, cache = cache, verbose = args.verbose, debug = args.debug, detailed = False)
                            for i in comicvine_issues:
                                i['issue_number'] = parser.massage_issue(i['issue_number'])
                                if ('store_date' in i and i['store_date'] is not None):
                                    i['date'] = i['store_date']
                                elif ('cover_date' in i and i['cover_date'] is not None):
                                    i['date'] = i['cover_date']

                            series_total = 0
                            if (series_total == len(issues)):
                                if (args.verbose):
                                    print("    {}/{}: issue compare complete".format(series_count, series_total))
                                del missing[publisher][series]
                            else:
                                for i in sorted(comicvine_issues, key = lambda x:x['issue_number']):
                                    if (i['issue_number'] not in issues):
                                        date = ''
                                        if ('date' in i and i['date'] is not None):
                                            date = i['date']
                                            year = parser.parse_date(i['date'])['year']
                                            if (year is not None and int(year) >= oldest_year):
                                                if series not in missing[publisher]:
                                                    missing[publisher][series] = []
                                                missing[publisher][series].append(i['issue_number'])
                                    elif (series in missing[publisher] and i['issue_number'] in missing[publisher][series]):
                                        missing[publisher][series].remove(i['issue_number'])

                                if (series in missing[publisher]):
                                    if (len(missing[publisher][series]) > 0):
                                        print("    missing issues:")
                                        for i in missing[publisher][series]:
                                            print('      ', i)
                                    else:
                                        if (args.verbose): print("  {}/{}: issues post {} complete".format(series_count, result['count_of_issues'], oldest_year-1))
                                        del missing[publisher][series]

                cache['scan'][publisher][series] = { 'date':datetime.now(), 'version':__version__, 'md5':md5 }

                write_cache(config['default']['cache_file'])
                # TODO: Protect this from keyboard interrupts.
                with open(config['default']['missing_log'], 'w') as f:
                    # Load data into missing object
                    for pub in missing.keys():
                        for series in missing[pub].keys():
                            for issue in missing[pub][series]:
                                f.write('{}/{}/{}\n'.format(pub, series, issue))
    elif (args.action == 'rescan'):
        api_key = config['comicvine']['api_key']
        oldest_year = 1901
        if ('oldest_year' in config['default']):
            oldest_year = int(config['default']['oldest_year'])

        if (api_key is None):
            raise(Exception("No comicvine api key defined"))

        if ('scan' not in cache):
            print('No scan history.')
            sys.exit()

        for publisher in cache['scan'].keys():
            for series in cache['scan'][publisher].keys():


                start_year= None
                ver = None
                parsed_series = parser.parse_series(series) #, debug = args.debug)
                if ('volume' in parsed_series):
                    start_year = parsed_series['volume']['start_year']
                    ver = parsed_series['volume']['ver']
                    volume = parser.make_volume(parsed_series['volume']['start_year'], ver = parsed_series['volume']['ver'])

                if (cache['scan'][publisher][series]['method'] != 'skipped'):
                    continue

                c_dir = args.target + '/' + publisher + '/' + series
                if (os.path.exists(c_dir) is False):
                    print("{} doesn't exist, clearing cache".format(c_dir))
                    del cache['scan'][publisher][series]
                    write_cache(config['default']['cache_file'])
                    continue

                scan(c_dir, api_key, oldest_year = oldest_year, args = args)

    else:
        print("Unknown action: {}".format(args.action))


def box(comic_file, target, args = minorimpact.default_arg_flags, large = False, small = False):
    global cache

    if (os.path.exists(comic_file) is False):
        print(f"{comic_file} does not exist")
        return
    print("boxing {}".format(comic_file))

    (root, ext) = os.path.splitext(comic_file)
    if (root + ext.lower() != comic_file):
        comic_file = change_extension(comic_file, ext.lower())

    try:
        c = comic.comic(comic_file, cache = cache, verbose = args.verbose, debug = args.debug)
        c.box(args = args, target_dir = args.target, headless = args.yes, large = large, small = small)
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
                    c = comic.comic(new_comic_file, verbose = args.verbose, debug = args.debug)
                    c.box(args = args, target_dir = args.target, headless = args.yes)
                except comic.FileExistsException as e:
                    print(e)
                    if (args.existing is not None):
                        print(f"  moving {c.file} to {args.existing}")
                        try:
                            if (args.dryrun is False): shutil.move(c.file, args.existing)
                        except shutil.Error as she:
                            print(she)
                except Exception as e:
                    print(traceback.format_exc())
        else:
            print("{} has unknown data: '{}'".format(comic_file, magic_str))
    except comic.FileExistsException as e:
        print(e)
        if (args.existing is not None):
            print(f"  moving {c.file} to {args.existing}")
            try:
                if (args.dryrun is False): shutil.move(c.file, args.existing)
            except shutil.Error as she:
                print(she)
    except comicvine.IssueNotFoundException as e:
        print(e)
    except comicvine.VolumeNotFoundException as e:
        print(e)
    except comicvine.UserException as e:
        pass
    except Exception as e:
        print(traceback.format_exc())
    print("\n")

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

def scan(c_dir, api_key, oldest_year = 1901, verbose = False, debug = False):
    c_files = os.listdir(c_dir)
    series = parser.series_filename(series, reverse = True) #, debug = args.debug)

    issues = {}

    for c_file in c_files:
        if (re.match("^\.", c_file)): continue
        c = comic.comic(c_dir + '/' + c_file, cache = cache, verbose = args.verbose, debug = args.debug)

        issues[parser.massage_issue(c.issue())] = parser.parse_date(c.date())

    go_for_it = False
    for issue in issues.keys():
        if (args.year is not None and args.year == issues[issue]['year']):
            go_for_it = True
            break

    if (len(issues) > 0 and go_for_it):
        if (args.verbose): print("scanning {} ({})".format(series, volume))
        try:
            result = comicvine.search_volumes(series, api_key, start_year = start_year, cache = cache, verbose = args.verbose, debug = args.debug, headless = args.yes)
        except Exception as e:
            print(e)
            return

        if (result is None):
            print("  Can't find comicvine series for {}".format(series))
        else:
            series_total = result['count_of_issues']
            series_count = len(issues)
            if (series_count == series_total):
                if (args.verbose): print("  ... {}/{}".format(series_count, series_total))
                cache['scan'][publisher][series] = { 'date':datetime.now(), 'version':__version__, 'md5':md5, 'method':'auto'}
            else:
                comicvine_issues = comicvine.get_issues(result['id'], api_key, cache = cache, verbose = args.verbose, debug = args.debug, detailed = False)
                for i in comicvine_issues:
                    i['issue_number'] = parser.massage_issue(i['issue_number'])
                    if ('store_date' in i and i['store_date'] is not None):
                        i['date'] = i['store_date']
                    elif ('cover_date' in i and i['cover_date'] is not None):
                        i['date'] = i['cover_date']

                series_total = 0
                if (series_total == len(issues)):
                    if (args.verbose):
                        print("  ... {}/{}: complete".format(series_count, series_total))
                    cache['scan'][publisher][series] = { 'date':datetime.now(), 'version':__version__, 'method':'auto', 'md5':md5 }
                else:
                    missing = []
                    for i in sorted(comicvine_issues, key = lambda x:x['issue_number']):
                        if (i['issue_number'] not in issues):
                            date = ''
                            if ('date' in i and i['date'] is not None):
                                date = i['date']
                                year = parser.parse_date(i['date'])['year']
                                if (year is not None and int(year) >= oldest_year):
                                    missing.append(i['issue_number'] + ' - ' + date)

                    if (len(missing) > 0):
                        print("    ..missing issues:")
                        for i in missing:
                            print('    ', i)
                        if (args.yes is False):
                            c = minorimpact.getChar(default='n', end='\n', prompt=f"  mark {series} as 'skipped'? (y/N) ", echo=True).lower()
                            if (c == 'y'):
                                cache['scan'][publisher][series] = { 'date':datetime.now(), 'version':__version__, 'method':'skipped', 'md5':md5 }
                            elif (c == 'q'):
                                write_cache(config['default']['cache_file'])
                                sys.exit()
                    else:
                        if (args.verbose):
                            print("  ... {}/{}: complete post {}".format(series_count, result['count_of_issues'], oldest_year-1))
                        cache['scan'][publisher][series] = { 'date':datetime.now(), 'version':__version__, 'method':'auto', 'md5':md5 }

    write_cache(config['default']['cache_file'])

def verify (comic_file, target_dir, args = minorimpact.default_arg_flags):
    global cache
    if (args.verbose): verbose = True

    c = comic.comic(comic_file, cache = cache, verbose = args.verbose, debug = args.debug)

    if (c.file in cache['verify'] and
        cache['verify'][c.file]['md5'] == c.md5() and
        args.clear_cache is False and
        cache['verify'][c.file]['version'] == __version__):
        if (args.debug): print("  {}\n    previously verified {}".format(comic_file, cache['verify'][c.file]['date']))
        return c

    if (args.verbose): print("\nverifying {}".format(comic_file))
    verified = c.box(args = args, target_dir = target_dir, headless = args.yes, verify = True, slow = args.slow, large = args.large)
    if (verified == 100):
        if (args.verbose): print("  verified (score: {})".format(verified))
        cache['verify'][c.file] = { 'date':datetime.now(), 'md5':c.md5(), 'version':__version__ }
    else:
        if (args.verbose): print("  failed (score: {})".format(verified))
        if (c.file in cache['verify']):
            del cache['verify'][c.file]

    if (comic_file != c.file and comic_file in cache['verify']):
        del cache['verify'][comic_file]

    if (args.verbose): print('')
    return c

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


