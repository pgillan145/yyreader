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

class EmptyDirException(Exception):
    pass

class YearException(Exception):
    pass

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

        # TODO: Remove some of thos duplicated code.  We really want to test everything that isn't cached, then start looking at the
        #   already cached values to see if the md5 has changed and we need to start checking again.
        rescan = 0
        while (rescan < 2):
            i = 0
            for c_file in c_files:
                i = i + 1
                if (args.filter and re.search(args.filter, c_file) is None):
                    continue

                if (args.verbose): print(f"\rverifying {i}/{file_count}", end='')
                # Don't re-test anything until we've tested everything new.
                if (rescan == 0 and c_file in cache['verify']): continue

                try:
                    c = verify(c_file, args.target, args = args)
                except comicvine.VolumeNotFoundException as e:
                    print(e)
                except comic.FileExistsException as e:
                    print(e)
                except comic.FileSizeException as e:
                    print(e)

                write_cache(config['default']['cache_file'])
            if (args.verbose): print("")
            rescan += 1

    elif (args.action == 'scan'):
        if ('scan_log' not in config['default'] or config['default']['scan_log'] == ''):
            print(f"{config['default']['scan_log']} not set")
            sys.exit()


        api_key = config['comicvine']['api_key']

        if (api_key is None):
            raise(Exception("No comicvine api key defined"))

        if ('scan' not in cache or args.clear_cache is True):
            cache['scan'] = {}

        rescan = 0
        while (rescan < 1):
            scan_dir(args.target, api_key, config['default']['scan_log'], cache_file = config['default']['cache_file'], pub_filter = args.publisher, year = args.year, verbose = args.verbose, debug = args.debug, slow = args.slow, rescan = False if (rescan == 0) else True)
            rescan += 1

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


def scan(target, publisher, series, api_key, year = None, verbose = False, debug = False, headless = True, slow = False):
    global cache
    if (debug): print(f"reading {publisher}/{series}/")

    missing = {}
    start_year = None
    ver = None
    parsed_series = parser.parse_series(series) #, debug = args.debug)
    if ('volume' in parsed_series):
        start_year = parsed_series['volume']['start_year']
        ver = parsed_series['volume']['ver']
        volume = parser.make_volume(parsed_series['volume']['start_year'], ver = parsed_series['volume']['ver'])

    if (year is not None and int(start_year) > int(year)):
        if (debug): print(f"  released after {year}, skipping")
        return missing

    c_dir = target + '/' + publisher + '/' + series
    c_md5 = minorimpact.md5dir(c_dir)

    if (series in cache['scan'][publisher] and
        cache['scan'][publisher][series]['version'] == __version__ and
        'md5' in cache['scan'][publisher][series] and cache['scan'][publisher][series]['md5'] == c_md5):
        if (debug): print("  cached, skipping")
        return missing

    series_name = parser.series_filename(series, reverse = True)
    print(f"scanning {publisher}/{series_name} ({volume}):")

    c_files = os.listdir(c_dir)
    if (len(c_files) == 0):
        raise EmptyDirException(f"{publisher}/{c_dir} is empty")

    issues = {}
    sample_issue = None
    for c_file in sorted(c_files):
        if (re.match("^\.", c_file)): continue
        try:
            #print(f"loading {c_file}")
            c = comic.comic(c_dir + '/' + c_file, cache = cache, verbose = verbose, debug = False)
            #print(f"{c_file} issue()={c.issue()}, parse_data['issue']={c.parse_data['issue']}, url={c.url()}")
            if (sample_issue is None): sample_issue = c
            #print(f"  sample_issue.issue()={sample_issue.issue()}, sample_issue.parse_data['issue']={sample_issue.parse_data['issue']}, sample_issue.url={sample_issue.url()}")
            issues[parser.massage_issue(c.issue())] = parser.parse_date(c.date())
        except comic.ExtensionMismatchException as e:
            # If we can't read the file because the extension is wrong and the file is undreadable, automatically mark it as
            #   'missing', but with a special error code.
            print(e)
            parse_data = parser.parse(c_file)
            missing[parse_data['issue']] = { 'date':parse_data['date'], 'url':'', 'error':'extension' }

    #print(f"  FUCK sample_issue.issue()={sample_issue.issue()}, sample_issue.parse_data['issue']={sample_issue.parse_data['issue']}, sample_issue.url={sample_issue.url()}")
    if (sample_issue is None):
        raise Exception(f"No sample issue found for {publisher}/{series_name} ({volume}):")

    valid_year = False
    for issue in issues.keys():
        # If we asked to scan a particular year, only work on seriess with issues released during that
        #   year.
        if (year is not None and year == issues[issue]['year']):
            valid_year = True
            break

    if (year is True and valid_year is False):
        raise YearException(f"no releases in {year}")

    if (len(issues) > 0):
        if (verbose): print("  collecting volume info from comicvine")
        try:
            if (verbose):
                #print("sample_issue.data=")
                #dump(sample_issue.data)
                #print("sample_issue.parse_data=")
                #dump(sample_issue.parse_data)
                print(f"    sample issue:     {sample_issue.issue()}")
                print(f"    sample issue url: {sample_issue.url()}")
            # Get the volume information based on one of the issues. That way, we can triangluate based on name, issue number and release data and end up
            #   with as close to a perfect volume match as possible.
            comicvine_data = comicvine.search(sample_issue.parse_data, api_key, cache = cache, debug = debug, headless = headless, verbose = verbose, slow = slow)
            comicvine_volume = comicvine.get_volume(comicvine_data['volume_id'], api_key, cache = cache, verbose = verbose, debug = debug, slow = slow)
        except comicvine.VolumeNotFoundException as e:
            print(e)
            missing[sample_issue.issue()] = { 'date':sample_issue.date(), 'url':sample_issue.url(), 'error':'volume' }
            return missing
        except Exception as e:
            print(traceback.format_exc())
            return missing

        if (comicvine_volume is None):
            # I need to look into this if we throw this exception, since it should have been caught by the VolumeNotFoundException
            # above.
            raise Exception(f"INVESTIGATE: can't find comicvine match for {publisher}/{series} ({volume}) #{sample_issue.issue()}")
        else:
            # Get the "count of issues" from comicvine for this series and compare them.  If they match, we should be golden.
            # TODO: Fixure out if we're actually golden - what are the occasions when the counts might match but we're still missing issues?
            #   1. We have multiple copies of one issue but are missing another (No - the list of issues indexed by number, so multiple issues
            #       would only be counted as one.
            #   2. I accidently scooped in a "cover only" version of the issue, rather than the full issue.
            #       TODO: Check to see how many pages a comic is and flag it if it's too low.
            #   3. A comic is neither 'cbr' nor 'cbz', and is therefore actually invalid.
            #   4. 2 & 3 seem like they're more 'verify' than 'scan'.
            series_total = comicvine_volume['count_of_issues']
            series_count = len(issues)

            if (series_count == series_total):
                print("  {}/{} totals match".format(series_count, series_total))
                cache['scan'][publisher][series] = { 'date':datetime.now(), 'version':__version__, 'md5':c_md5 }
            else:
                # count value from comicvine doesn't match the number of files, so let's dig deeper
                if (verbose): print("  collecting issue list from comicvine")
                comicvine_issues = comicvine.get_issues(comicvine_volume['id'], api_key, cache = cache, verbose = verbose, debug = debug, detailed = False, slow = slow, headless = headless)

                series_total = len(comicvine_issues)
                if (series_total == len(issues) and len(missing) == 0):
                    # In theory this should never be different than 'count_of_issues' and should never come up.  I'm half
                    #   tempted to count it as an error.
                    print("  {}/{}: issue counts match".format(series_count, series_total))
                    cache['scan'][publisher][series] = { 'date':datetime.now(), 'version':__version__, 'md5':c_md5 }
                elif (len(issues) > len(comicvine_issues)):
                    # We've got more issues 
                    print(f"  too many issues:")
                    print(f"    issues:           {len(issues)}")
                    print(f"    comicvine issues: {len(comicvine_issues)}")
                    volume_url = comicvine.volume_url(comicvine_volume['id'])
                    print(f"    comicvine volume: {volume_url}")
                    print(f"    sample issue:     {sample_issue.issue()}")
                    print(f"    issue url:        {sample_issue.url()}")
                    missing[sample_issue.issue()] = { 'date':sample_issue.date(), 'url':volume_url, 'error':'overcount' }
                    return missing
                else:
                    # Go through the list of issues we got from comicvine.
                    for i in sorted(comicvine_issues, key = lambda x:x['issue_number']):
                        i['issue_number'] = parser.massage_issue(i['issue_number'])
                        if (i['issue_number'] not in issues and i['issue_number'] not in missing):
                            # Comicvine gave us an issue we don't have.
                            date = ''
                            if ('date' in i and i['date'] is not None):
                                date = i['date']

                            # It's not in out list of issues, and we can't check the date to see if it's too "old",
                            #   so add it to the list of 'missing' issues.
                            missing[i['issue_number']] = { 'date':date, 'url':comicvine.issue_url(i['id']), 'error':'missing' }
                        elif (i['issue_number'] in issues and i['issue_number'] in missing and missing[i['issue_number']]['error'] == 'missing'):
                            # If something was previously marked 'missing' but it's here, delete it.
                            del missing[i['issue_number']]

                    if (len(missing) > 0):
                        # If we've got anything in the 'missing' pile, don't cache this directory.
                        print("  missing issues:")
                        for i in missing:
                            print(f"    {i}:{missing[i]['error']}")
                    else:
                        if (verbose):
                            print(f"  count mismatches:")
                            print(f"    missing: {len(missing)}")
                            print(f"    issues: {len(issues)}")
                            print(f"    comicvine issues: {len(comicvine_issues)}")
                            volume_url = comicvine.volume_url(comicvine_volume['id'])
                            print(f"    comicvine volume: {volume_url}")
                            print(f"    sample issue url: {sample_issue.url()}")
                        raise Exception("we don't have any missing issues but our counts don't match and I don't know why!")
                        #cache['scan'][publisher][series] = { 'date':datetime.now(), 'version':__version__, 'md5':c_md5 }

    #dump(missing)
    return missing

def scan_dir(target, api_key, scan_log, cache_file = None, pub_filter = None, year = None, verbose = False, debug = False, headless = True, rescan = False, slow = False):
    global cache
    missing = {}

    if (os.path.exists(scan_log)):
        with open(scan_log, 'r') as f:
            # Load data into missing object
            line = f.readline()
            while(line):
                line = line.strip()
                s = line.split('|')
                if (len(s) == 6):
                    (error, publisher, series, issue, date, url) = s
                    if (os.path.exists(f'{target}/{publisher}') is True):
                        if (publisher not in missing):
                            missing[publisher] = {}
                        if (os.path.exists(f'{target}/{publisher}/{series}') is True):
                            if (series not in missing[publisher]):
                                missing[publisher][series] = {}
                            missing[publisher][series][issue] = { 'date':date, 'url':url, 'error':error}
                else:
                    print(f"invalid line: '{line}'")
                line = f.readline()

    publishers = sorted(os.listdir(target))
    i = 0
    for publisher in publishers:
        if (re.match("^\.", publisher)): continue
        if (pub_filter is not None and pub_filter.lower() != publisher.lower()):
            continue
        if (publisher not in cache['scan']): cache['scan'][publisher] = {}
        if (publisher not in missing): missing[publisher] = {}
        seriess = sorted(os.listdir(target + '/' + publisher))
        for series in seriess:
            if (re.match("^\.", series)): continue
            if (rescan is False and series in cache['scan'][publisher]): continue
            try:
                m = scan(target, publisher, series, api_key, year = year, verbose = verbose, debug = debug, headless = headless, slow = slow)
                if (len(m) > 0):
                    if (publisher not in missing):
                        missing[publisher] = {}
                    missing[publisher][series] = m
                else:
                    if (publisher in missing):
                        if (series in missing[publisher]):
                            del missing[publisher][series]
                        if (len(missing[publisher]) == 0):
                            del missing[publisher]
            except EmptyDirException as e:
                print(e)
                continue
            except YearException as e:
                print(e)
                continue

            write_cache(cache_file)

            done = False
            interrupted = False
            while done is False:
                try:
                    with open(scan_log, 'w') as f:
                        # Load data into missing object
                        for pub in sorted(missing.keys()):
                            for series in sorted(missing[pub].keys()):
                                for issue in sorted(missing[pub][series].keys()):
                                    date = missing[pub][series][issue]['date']
                                    url = missing[pub][series][issue]['url']
                                    error = missing[pub][series][issue]['error']
                                    f.write(f'{error}|{pub}|{series}|{issue}|{date}|{url}\n')
                    done = True
                except KeyboardInterrupt:
                    print("scan log dump interrupted - retrying")
                    interrupted = True
                    continue
            if (interrupted is True):
                sys.exit()
            #if (len(m) > 0):
            #    sys.exit()

            #c = minorimpact.getChar()
            #if (c == 'q'):
            #    sys.exit()

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


