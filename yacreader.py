#!/usr/bin/env python3

import argparse
import datetime
import magic
import minorimpact.config
import os.path
import re
import shutil
import sqlite3
import sys
import yyreader.comic
import yyreader.parser
import yyreader.yacreader

def main():
    parser = argparse.ArgumentParser(description="Scan comic directory")
    parser.add_argument('-v', '--verbose', action='store_true')
    parser.add_argument('-y', '--yes', action='store_true')
    parser.add_argument('-1', '--once', help = "Just process a single entry, for testing.  Also enables --verbose and --debug.", action='store_true')
    parser.add_argument('-s', '--scan', action='store_true', help = "Analyze the database, looking for anomalies.")
    parser.add_argument('--filedate', help = "With --scan, finds all files with mismatches database date entries.", action='store_true')
    parser.add_argument('--filetype', help = "With --scan, finds all files with data that doesn't match their extension.", action='store_true')
    parser.add_argument('-u', '--update', action='store_true', help = "Update item metadata.")
    #parser.add_argument('--comicvine',  help = "Pull external comicvine data when running --update, otherwise just update with what can be parsed from the filename.", action='store_true')
    parser.add_argument('--volume', metavar = 'VOL', help = "Only --update or --scan comics in VOL.")
    parser.add_argument('--debug', action='store_true')
    parser.add_argument('--dryrun', action='store_true')

    args = parser.parse_args()
    config = minorimpact.config.getConfig(script_name = 'yyreader')
    
    if (args.once is True):
        args.verbose = True
        args.debug = True

    yyreader.yacreader.init()
    con = yyreader.yacreader.connect()
    cur = con.cursor()

    cur.execute('select comic.path, comic_info.volume, comic_info.number, comic_info.date, comic.id, comic_info.id, comic_info.comicVineID, comic_info.title, comic_info.storyArc, comic_info.writer, comic_info.penciller, comic.fileName from comic, comic_info where comic.comicInfoId=comic_info.id')
    rows = cur.fetchall()
    i = 0
    for row in rows:
        path = row[0]
        volume = row[1]
        issue = row[2]
        date = row[3]
        comic_info_id = row[5]
        comicvine_id = row[6]
        title = row[7]
        writer = row[9]
        penciller = row[10]
        fileName = row[11]

        if (args.volume is not None):
            if (re.search(args.volume, volume) is None or re.search(args.volume, path) is None):
                continue

        if (args.scan):
            #c = yyreader.comic.comic(config['default']['comic_dir'] + path, args = args)
            if (args.filedate):
                file_name = config['default']['comic_dir'] + path
                parse_data = yyreader.parser.parse(file_name, args = args)
                if ('date' in parse_data):
                    file_date = parse_data['date']
                    dbdate = yyreader.yacreader.convert_yacreader_date(date)
                    if (file_date != dbdate.strftime('%Y-%m-%d')):
                        print("{}: dbdate '{}' doesn't match file date '{}'".format(file_name, dbdate.strftime('%Y-%m-%d'), file_date))
                        if (comicvine_id is not None):
                            print("comicvine url: https://comicvine.gamespot.com/unknown/4000-{}".format(comicvine_id))
            if (args.filetype):
                magic_str = magic.from_file(file_name)
                for ext in yyreader.comic.ext_map:
                    if (re.search('\\.{}$'.format(ext), file_name) and re.search('^{}'.format(yyreader.comic.ext_map[ext]), magic_str) is None):
                        print("{}: extension '{}' doesn't match file type '{}'".format(file_name, ext, magic_str[:16]))
                        new_ext = None
                        for ext2 in yyreader.comic.ext_map:
                            if (re.search('^{}'.format(yyreader.comic.ext_map[ext2]), magic_str)):
                                new_ext = ext2
                                break
                        if (new_ext is None):
                            print("'{}' is unknown".format(magic_str))
                            break

                        if (args.yes):
                            c = 'y'
                        else:
                            c = minorimpact.getChar(default='y', end='\n', prompt="change file extension to {}? (Y/n) ".format(new_ext), echo=True).lower()
                        if (c == 'q'):
                            sys.exit()
                        elif (c == 'y'):
                                new_file_name = re.sub('\\.{}$'.format(ext), '.{}'.format(new_ext), file_name)
                                print("moving {} to {}".format(file_name, new_file_name))
                                if (args.dryrun is False):
                                    shutil.move(file_name, new_file_name)

                                new_path = re.sub('\\.{}$'.format(ext), '.{}'.format(new_ext), path)
                                new_fileName = re.sub('\\.{}$'.format(ext), '.{}'.format(new_ext), fileName)
                                print("update comic set path = {}, fileName = {} where comicInfoId = {}".format(new_path, new_fileName, comic_info_id))
                                if (args.dryrun is False):
                                    try:
                                        cur.execute('update comic set path = ?, fileName = ? where comicInfoId = ?', (new_path, new_fileName, comic_info_id))
                                        con.commit()
                                    except Exception as e:
                                        print(e)
                        break
            
        elif (args.update):
            #if (comicvine_id is not None and date is not None and title is not None and writer is not None and penciller is not None):
            #    continue
            if (date is not None and issue is not None):
                if (args.debug): print("--SKIP--")
                if (args.debug): print("path: " + path)
                if (args.debug): print("issue: " + str(issue))
                if (args.debug): print("date: " + str(date))
                if (args.debug): print("comicInfoId: " + str(comic_info_id))
                if (args.debug): print("comicVineID: " + str(comicvine_id))
                continue

            if (args.debug): print("--UPDATE--")
            if (args.debug): print("path: " + path)
            if (args.debug): print("date: " + str(date))
            if (args.debug): print("comicInfoId: " + str(comic_info_id))
            if (args.debug): print("comicVineID: " + str(comicvine_id))

            c = yyreader.comic.comic(config['default']['comic_dir'] + path, args = args)
            if (c.get('date') is not None):
                    print("updating " + path)

                    arcs = c.get('story_arcs')
                    arc_name = arcs[0] if (len(arcs) > 0) else None
                    characters = '\n'.join(c.get('characters')) if (c.get('characters')) else None
                    colorist = '\n'.join(c.get('colorists')) if (c.get('colorists')) else None
                    description = c.get('description')
                    inker = '\n'.join(c.get('inkers')) if (c.get('inkers')) else None
                    issue = c.get('issue')
                    issue_id = c.get('issue_id')
                    issue_name = c.get('name')
                    letterer = '\n'.join(c.get('letterers')) if (c.get('letterers')) else None
                    date = c.get('date')
                    penciller = '\n'.join(c.get('pencillers')) if (c.get('pencillers')) else None
                    publisher = c.get('publisher')
                    volume = c.get('volume')
                    writer = '\n'.join(c.get('writers')) if (c.get('writers')) else None

                    i = i + 1
                    m = re.search('^(?P<year>\d\d\d\d)-(?P<month>\d\d)-(?P<day>\d\d)$', date)
                    dbdate = m.group('day') + '/' + m.group('month') + '/' + m.group('year')
                    if (args.debug): print("update comic_info set edited = TRUE, date = {}, volume = {}, number = {}, title = {}, comicVineID = {}, storyArc = {}, publisher = {}, writer = {}, penciller = {}, synopsis = {}, letterer = {}, inker = {}, colorist = {}, characters = {} where id = {}".format(dbdate, volume, issue, issue_name, issue_id, arc_name, publisher, writer, penciller, description, letterer, inker, colorist, characters, comic_info_id))
                    try:
                        if (args.dryrun is False):
                            cur.execute('update comic_info set edited = TRUE, date = ?, volume = ?, number = ?, title = ?, comicVineID = ?, storyArc = ?, publisher = ?, writer = ?, penciller = ?, synopsis = ?, letterer = ?, inker = ?, colorist = ?, characters = ? where id = ?', (dbdate, volume, issue, issue_name, issue_id, arc_name, publisher, writer, penciller, description, letterer, inker, colorist, characters, comic_info_id))
                            con.commit()
                        pass
                    except Exception as e:
                        print(e)
                        break

                    for arc in arcs:
                        if (args.debug): print("insert into comic_info_arc (storyArc, comicInfoId) values ({}, {})".format(arc, comic_info_id))
                        try:
                            if (args.dryrun is False):
                                cur.execute('insert into comic_info_arc (storyArc, comicInfoId) values (?, ?)', (arc, comic_info_id))
                                con.commit()
                            pass
                        except Exception as e:
                            if (str(e) != 'UNIQUE constraint failed: comic_info_arc.storyArc, comic_info_arc.comicInfoId'):
                                print(e)
                                break

        #if (i > 10): break
        if (args.once is True): break

if __name__ == '__main__':
    main()

