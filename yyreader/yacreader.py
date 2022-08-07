#!/usr/bin/env python3

import argparse
from datetime import datetime, timedelta
import magic
import minorimpact.config
import os
import os.path
import re
import sqlite3
import sys
import re
import shutil
from . import comic, parser

config = None

def main():
    parser = argparse.ArgumentParser(description="Scan comic directory")
    parser.add_argument('-v', '--verbose', action='store_true')
    parser.add_argument('-y', '--yes', action='store_true')
    parser.add_argument('-1', '--once', help = "Just process a single entry, for testing.  Also enables --verbose and --debug.", action='store_true')
    parser.add_argument('-s', '--scan', action='store_true', help = "Analyze the database, looking for anomalies.")
    parser.add_argument('--dupes', help = "With --scan, tries to identify duplicated records. (NOT IMPLEMENTED)", action='store_true')
    parser.add_argument('--filedate', help = "With --scan, finds all files with mismatches database date entries.", action='store_true')
    parser.add_argument('--filetype', help = "With --scan, finds all files with data that doesn't match their extension.", action='store_true')
    parser.add_argument('--holes', help = "With --scan, finds volumes with missing issues. (NOT IMPLEMENTED)", action='store_true')
    parser.add_argument('--verify', help = "With --scan, recheck database items against file and comicvine data. (NOT IMPLEMENTED)", action='store_true')
    parser.add_argument('--xml', help = "With --scan, finds files with invalid ComicInfo.xml files. (NOT IMPLEMENTED)", action='store_true')
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

    init_db()
    con = connect()
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
            #c = comic.comic(config['default']['comic_dir'] + path, args = args)
            if (args.filedate):
                file_name = config['default']['comic_dir'] + path
                parse_data = parser.parse(file_name, args = args)
                if ('date' in parse_data):
                    file_date = parse_data['date']
                    dbdate = convert_yacreader_date(date)
                    if (file_date != dbdate.strftime('%Y-%m-%d')):
                        print("{}: dbdate '{}' doesn't match file date '{}'".format(file_name, dbdate.strftime('%Y-%m-%d'), file_date))
                        if (comicvine_id is not None):
                            print("comicvine url: https://comicvine.gamespot.com/unknown/4000-{}".format(comicvine_id))
            if (args.filetype):
                magic_str = magic.from_file(file_name)
                for ext in comic.ext_map:
                    if (re.search('\\.{}$'.format(ext), file_name) and re.search('^{}'.format(comic.ext_map[ext]), magic_str) is None):
                        print("{}: extension '{}' doesn't match file type '{}'".format(file_name, ext, magic_str[:16]))
                        new_ext = None
                        for ext2 in comic.ext_map:
                            if (re.search('^{}'.format(comic.ext_map[ext2]), magic_str)):
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
            if (args.xml):
                #TODO: scan files for valid, up-to-date ComicInfo.xml files.  The Notes field should contain "yyreader xml v1", at this point...
                #TODO: Make the xml version a variable.
                print("This isn't written yet, check back, like, later, and stuff.")
                pass
            if (args.holes):
                #TODO: Scan all the existing volumes for "holes" -- places where the numbers either don't start with 1, or skip some value.  (Check comicvine for "total
                #   number of issues"?  I mean, that's a good idea, but for current titles the caching tends to make more difficult than it ought to be.)
                print("This doesn't exist yet either.")
                pass
            if (args.verify):
                #TODO: Compare what's in the database to what's in the file and what's in comicvine, and then retrieve, rewrite and reupdate everything.
                #TODO: Make an optional "subset" value (ie, a number of items or a percentage) that can be set, so that only a portion of the whole will be checked rather
                #   than however many thousands of items exist?  Maybe add also add a "last_checked" field somewhere so we know not to check the same items more than
                #   once every x days.
                print("Nope.")
                pass
            if (args.dupes):
                #TODO: Identify duplicate issues.
                print("Nein.")
                pass
            
        elif (args.update):
            #TODO: Settle on what 'done' means when it comes to what data should be in the yacreader database.  Technically all we need is issue number, date and volume to
            #   just read the books, but I also want arcs, publishers and some of the creatives in there for filtering and searching.
            #if (comicvine_id is not None and date is not None and title is not None and writer is not None and penciller is not None):
            #    continue
            if (date is not None and issue is not None and volume is not None):
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

            c = comic.comic(config['default']['comic_dir'] + path, args = args)
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
                except Exception as e:
                    print(e)
                    break

                for arc in arcs:
                    if (args.debug): print("insert into comic_info_arc (storyArc, comicInfoId) values ({}, {})".format(arc, comic_info_id))
                    try:
                        if (args.dryrun is False):
                            cur.execute('insert into comic_info_arc (storyArc, comicInfoId) values (?, ?)', (arc, comic_info_id))
                    except Exception as e:
                        if (str(e) != 'UNIQUE constraint failed: comic_info_arc.storyArc, comic_info_arc.comicInfoId'):
                            print(e)
                            pass
                con.commit()

        #if (i > 10): break
        if (args.once is True): break

def connect():
    global config

    if (config is None):
        config = minorimpact.config.getConfig(script_name = 'yyreader')
    
    db_file = config['default']['db']
    if (os.path.exists(db_file) is None):
        raise Exception("{} does not exist".format(db_file))

    db = sqlite3.connect(db_file)
    return db
    
def init_db():
    db = connect()
    cursor = db.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS comic_info_arc (id INTEGER PRIMARY KEY, storyArc TEXT NOT NULL, arcNumber INTEGER, arcCount INTEGER, comicVineID TEXT, comicInfoId INTEGER NOT NULL, FOREIGN KEY(comicInfoId) REFERENCES comic_info(id))')
    cursor.execute('CREATE TABLE IF NOT EXISTS read_log (id INTEGER PRIMARY KEY, start_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP, currentPage INTEGER default 1, end_date TIMESTAMP, mod_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP, comicInfoId INTEGER NOT NULL, FOREIGN KEY(comicInfoId) REFERENCES comic_info(id))')
    cursor.execute('CREATE TABLE IF NOT EXISTS beacon (id INTEGER PRIMARY KEY, name TEXT NOT NULL, mod_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')
    cursor.execute('CREATE TABLE IF NOT EXISTS link (id INTEGER PRIMARY KEY, name TEXT, foreComicId INTEGER NOT NULL, aftComicId INTEGER NOT NULL, mod_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY(foreComicId) REFERENCES comic_info(id), FOREIGN KEY(aftComicId) REFERENCES comic_info(id))')
    db.commit()
    try:
        cursor.execute('CREATE UNIQUE INDEX comic_info_arc_idx on comic_info_arc(storyArc, comicInfoId)')
        db.commit()
    except Exception as e:
        if (re.search('^index (.+) already exists$', str(e)) is None):
            raise e
    try:
        cursor.execute('CREATE UNIQUE INDEX beacon_idx on beacon(name)')
        db.commit()
    except Exception as e:
        if (re.search('^index (.+) already exists$', str(e)) is None):
            raise e
    try:
        cursor.execute('CREATE UNIQUE INDEX link_idx on link(foreComicId)')
        db.commit()
    except Exception as e:
        if (re.search('^index (.+) already exists$', str(e)) is None):
            raise e
    db.close()

def convert_yacreader_date(yacreader_date):
    date = datetime.strptime(yacreader_date, '%d/%m/%Y')
    return date

def add_beacon(name):
    db = connect()
    cursor = db.cursor()
    try:
        cursor.execute('insert into beacon (name, mod_date) values (?,  CURRENT_TIMESTAMP)', (name, ))
        db.commit()
    except Exception as e:
        print(e)
    db.close()

def delete_beacon(name):
    db = connect()
    cursor = db.cursor()
    try:
        cursor.execute('delete from beacon where name = ?', (name, ))
        db.commit()
    except Exception as e:
        print(e)
    db.close()

def get_beacon(name):
    beacon = None
    db = connect()
    cursor = db.cursor()
    cursor.execute('select id, name, mod_date from beacon where name = ?', (name, ))
    rows = cursor.fetchall()
    if (len(rows) > 0):
        id = rows[0][0]
        name = rows[0][1]
        mod_date = rows[0][2]
        beacon = { 'id':id, 'name':name, 'mod_date':mod_date }
    db.close()
    return beacon

def get_beacons():
    db = connect()
    cursor = db.cursor()
    cursor.execute('select id, name, mod_date from beacon order by mod_date desc')
    rows = cursor.fetchall()
    beacons = []
    for row in rows:
        id = row[0]
        name = row[1]
        mod_date = row[2]
        beacons.append({ 'id':id, 'name':name, 'mod_date':mod_date })
    db.close()
    return beacons

def get_comic_by_id(id, db = None):
    if (db is None):
        local_db = connect()
    else:
        local_db = db
    cursor = local_db.cursor()
    cursor.execute('select comic_info.volume, comic_info.number, comic_info.date, comic_info.id, comic.path, comic_info.read, comic_info.currentPage, comic_info.hash from comic_info, comic where comic.comicInfoId=comic_info.id and comic_info.id = ?', (id,))
    rows = cursor.fetchall()
    comic_data = None
    for row in rows:
        volume = row[0]
        issue = row[1]
        date = convert_yacreader_date(row[2])
        id = row[3]
        path = row[4]
        read = row[5]
        current_page = row[6]
        hash = row[7]
        fore_id = None
        aft_id = None
        
        cursor.execute('select foreComicId from link where aftComicId=?', (id, ))
        linkrow = cursor.fetchone()
        if (linkrow is not None):
            fore_id = linkrow[0]
        cursor.execute('select aftComicId from link where foreComicId=?', (id, ))
        linkrow = cursor.fetchone()
        if (linkrow is not None):
            aft_id = linkrow[0]

        if (current_page is None or current_page == 0):
            current_page = 1
        comic_data = { 'id':id, 'volume':volume, 'issue':issue, 'date':date, 'path': path, 'read':read, 'current_page':current_page, 'hash':hash, 'fore_id':fore_id, 'aft_id': aft_id }

    if (db is None):
        local_db.close()

    if (comic_data is None):
        raise Exception("invalid comic_info id: '{}'".format(id))

    return comic_data

# TODO: Turn these two "get_comics_by_*" into a single function, they do the same thing but with a slightly different SELECT.
def get_comics_by_date(year, month, db = None):
    if (db is None):
        local_db = connect()
    else:
        local_db = db

    cursor = local_db.cursor()
    if (month < 10): month = '0{}'.format(month)
    comics = []
    sql = 'select volume, number, date, id, read, currentPage from comic_info where date like "%/{}/{}"'
    #print(sql.format(month, year))
    cursor.execute(sql.format(month, year))
    rows = cursor.fetchall()
    for row in rows:
        volume = row[0]
        issue = row[1]
        date = convert_yacreader_date(row[2])
        id = row[3]
        read = row[4]
        current_page = row[5]

        comics.append(get_comic_by_id(id, db = local_db))
    if (db is None):
        local_db.close()
    return sorted(comics, key=lambda x:(x['date'], x['volume']) )

def get_cover(id, hash = None):
    cover_data = None
    cover_file = get_cover_file(id, hash = hash)
    with (open(cover_file, 'rb') as f):
        cover_data = f.read()
    return cover_data

def get_cover_file(id, hash = None):
    if (hash is None):
        comic = get_comic_by_id(id)
        hash = comic['hash']
    cover_file = config['default']['comic_dir'] + '/' + '.yacreaderlibrary/covers/' + hash + '.jpg'

    return cover_file

def get_comics_by_volume(volume, db = None):
    if (db is None):
        local_db = connect()
    else:
        local_db = db
    cursor = local_db.cursor()

    comics = []
    cursor.execute('select volume, number, date, id, read, currentPage from comic_info where volume = "{}"'.format(volume))
    rows = cursor.fetchall()
    for row in rows:
        volume = row[0]
        issue = row[1]
        date = convert_yacreader_date(row[2])
        id = row[3]
        read = row[4]
        current_page = row[5]

        comics.append(get_comic_by_id(id, db = local_db))

    if (db is None):
        local_db.close()
    return sorted(comics, key=lambda x:(x['date'], x['volume']) )

def get_history():
    db = connect()
    cursor = db.cursor()
    comics = []
    cursor.execute('select ci.volume, ci.number, ci.date, ci.id, ci.read, ci.currentPage, read_log.end_date, read_log.mod_date from comic_info ci, read_log where ci.id=read_log.comicInfoID')
    rows = cursor.fetchall()
    for row in rows:
        volume = row[0]
        issue = row[1]
        date = convert_yacreader_date(row[2])
        id = row[3]
        read = row[4]
        current_page = row[5]
        end_date = row[6]
        mod_date = row[7]

        if (current_page is None or current_page == 0):
            current_page = 1

        comics.append({ 'id':id, 'volume':volume, 'issue':issue, 'date':date, 'read':read, 'current_page':current_page, 'end_date':end_date, 'mod_date':mod_date })

    db.close()
    return sorted(comics, key=lambda x:(x['end_date'] if (x['end_date'] is not None) else x['mod_date']), reverse = True)

def get_months(year, db = None):
    if (db is None):
        local_db = connect()
    else:
        local_db = db
    cursor = local_db.cursor()

    year = int(year)
    months = []
    cursor.execute('select distinct(date) from comic_info')
    rows = cursor.fetchall()
    for row in rows:
        if (row[0] is None):
            continue
        date = convert_yacreader_date(row[0])
        if (date.year != year):
            continue
        month = int(date.strftime('%m'))
        if (month not in months):
            months.append(month)
    if (db is None):
        local_db.close()

    return sorted(months, key=lambda x:x)

def get_head_comic(id, db = None):
    if (db is None):
        local_db = connect()
    else:
        local_db = db
    cursor = local_db.cursor()

    y = get_comic_by_id(id, local_db)
    while (y['fore_id'] is not None):
        y = get_comic_by_id(y['fore_id'], local_db)

    if (db is None):
        local_db.close()
    return y

def get_next_comic(id, db = None):
    if (db is None):
        local_db = connect()
    else:
        local_db = db
    cursor = local_db.cursor()

    comic_data = None
    y = get_comic_by_id(id, local_db)

    if (y['aft_id'] is not None):
        comic_data = get_comic_by_id(y['aft_id'], db = local_db)
    else:
        head = get_head_comic(id, db = local_db)

        (year, month) = head['date'].strftime('%Y|%-m').split('|')
        year = int(year)
        month = int(month)
        issues = get_comics_by_date(year, month, db = local_db)
        i = 0
        for issue in issues:
            if (issue['id'] == head['id']):
                current = i
                break
            i = i + 1

        while (comic_data is None and year is not None and month is not None and len(issues) > 0):
            i = 0
            for issue in issues:
                if (i > current):
                    n = issues[i]
                    # When moving naturally from item to the next, skip anything that's part of a link chain.
                    if (n['fore_id'] is None):
                        comic_data = n
                        break
                    # TODO: Make an option so that anything that's already 'read' will also be skipped
                    current = i
                i = i + 1
            if (comic_data is None):
                (year, month) = get_next_date(year, month, db = local_db)
                issues = get_comics_by_date(year, month, db = local_db)
                current = -1

    if (db is None):
        local_db.close()
    return comic_data

def get_next_date(year, month, db = None):
    if (db is None):
        local_db = connect()
    else:
        local_db = db
    cursor = local_db.cursor()

    year = int(year)
    month = int(month)
    next_year = None
    next_month = None
    months = get_months(year, db = local_db)
    if (month == months[len(months)-1]):
        years = get_years()
        for i in range(0, len(years)):
            if (years[i] == year and i < len(years)):
                next_year = years[i+1]
                break
        if (next_year is not None):
            months = get_months(next_year, db = local_db)
            next_month = months[0]
    else:
        next_year = year
        next_month = month + 1
    if (db is None):
        local_db.close()
    return (next_year, next_month)

def get_previous_comic(id, db = None):
    if (db is None):
        local_db = connect()
    else:
        local_db = db
    cursor = local_db.cursor()

    comic_data = None
    y = get_comic_by_id(id, local_db)

    if (y['fore_id'] is not None):
        comic_data = get_comic_by_id(y['fore_id'], db = local_db)
    else:
        (year, month) = y['date'].strftime('%Y|%-m').split('|')
        year = int(year)
        month = int(month)
        issues = get_comics_by_date(year, month, db = local_db)

        i = len(issues) - 1
        for issue in list(reversed(issues)):
            if (issue['id'] == y['id']):
                current = i
                break
            i = i - 1

        while (comic_data is None and year is not None and month is not None and len(issues) > 0):
            i = len(issues) - 1
            for issue in list(reversed(issues)):
                if (i < current):
                    n = issues[i]
                    # When moving naturally from item to the previous, skip anything that's part of a link chain.
                    if (n['fore_id'] is None):
                        comic_data = n
                        break
                    # TODO: Make an option so that anything that's already 'read' will also be skipped
                    current = i
                i = i - 1
            if (comic_data is None):
                (year, month) = get_previous_date(year, month, db = local_db)
                issues = get_comics_by_date(year, month, db = local_db)
                current = len(issues)

    if (db is None):
        local_db.close()
    return comic_data

def get_previous_date(year, month, db = None):
    if (db is None):
        local_db = connect()
    else:
        local_db = db
    cursor = local_db.cursor()

    year = int(year)
    month = int(month)
    prev_year = None
    prev_month = None
    months = get_months(year, db = local_db)
    if (month == months[0]):
        years = get_years()
        for i in range(0, len(years)):
            if (years[i] == year and i > 0):
                prev_year = years[i-1]
                break
            
        if (prev_year is not None):
            months = get_months(prev_year, db = local_db)
            prev_month = months[len(months)-1]
    else:
        prev_year = year
        prev_month = month - 1

    if (db is None):
        local_db.close()
    return (prev_year, prev_month)

def get_volumes():
    db = connect()
    cursor = db.cursor()
    volumes = []
    cursor.execute('select distinct(volume) from comic_info')
    rows = cursor.fetchall()
    for row in rows:
        if (row[0] is None):
            continue
        volumes.append(row[0])
    db.close()
    return sorted(volumes, key=lambda x: x)

def get_years():
    db = connect()
    cursor = db.cursor()
    years = []
    cursor.execute('select distinct(date) from comic_info')
    rows = cursor.fetchall()
    for row in rows:
        if (row[0] is None):
            continue
        date = convert_yacreader_date(row[0])
        year = date.year
        if (year not in years):
            years.append(year)
    db.close()
    return sorted(years, key=lambda x: x)

def link(foreid, aftid):
    db = connect()
    cursor = db.cursor()
    try:
        cursor.execute('insert into link(foreComicId, aftComicId) values (?, ?)', (foreid, aftid))
        db.commit()
    except Exception as e:
        if (re.search('^UNIQUE constraint failed:', str(e)) is None):
            raise e
    db.close()

def unlink(aftid):
    db = connect()
    cursor = db.cursor()
    try:
        cursor.execute('delete from link where aftComicId = ?', (aftid, ))
        db.commit()
    except Exception as e:
        raise e
    db.close()

def update_beacon(name):
    db = connect()
    cursor = db.cursor()
    try:
        cursor.execute('update beacon set mod_date =  CURRENT_TIMESTAMP where name = ?', (name, ))
        db.commit()
    except Exception as e:
        pass
    db.close()

def update_read_log(id, page, page_count = None):
    db = connect()
    cursor = db.cursor()
    if (page > 1):
        cursor.execute('update comic_info set hasBeenOpened = TRUE, currentPage = ? where comic_info.id = ?', (page, id))
        db.commit()

    cursor.execute('select id, start_date, end_date from read_log where comicInfoId = ? order by id desc limit 1', (id,))
    rows = cursor.fetchall()
    if (len(rows) == 0 and page > 1):
        # Never been read, start a new record
        cursor.execute('insert into read_log (start_date, currentPage, comicInfoId) values (DATETIME("now","localtime"), ?, ?)', (page, id))
        db.commit()
    elif (len(rows) > 0 and rows[0][2] is not None and datetime.fromisoformat(rows[0][2]) < (datetime.now() - timedelta(hours = 24)) and page > 1): 
        # Previously completed, but more than 24 hours have gone by, so start a new record. 
        cursor.execute('insert into read_log (start_date, currentPage, comicInfoId) values (DATETIME("now","localtime"), ?, ?)', (page, id))
        db.commit()
    elif (len(rows) > 0 and rows[0][2] is not None and datetime.fromisoformat(rows[0][2]) > (datetime.now() - timedelta(hours = 24)) and page > 1): 
        # Completed less than 24 hours ago, just update the currentPage.
        cursor.execute('update read_log set currentPage = ?, mod_date = DATETIME("now","localtime") where id = ?', (page, rows[0][0]))
        db.commit()
    elif (len(rows) > 0 and rows[0][2] is None):
        # Started, but not completed: set the current page.
        cursor.execute('update read_log set currentPage = ?, mod_date = DATETIME("now","localtime") where id = ?', (page, rows[0][0]))
        db.commit()
    # This falls through if there's no existing record and the page number is '1', because sometimes I like to peruse the covers and I don't want to litter
    #   up the log with a bunch of lookey-loo's.

    if (page_count is not None and page >= page_count):
        cursor.execute('update comic_info set read = TRUE where comic_info.id = ?', (id, ))
        cursor.execute('update read_log set end_date = DATETIME("now","localtime"), mod_date = DATETIME("now","localtime") where end_date is NULL and comicInfoID = ?', (id,))
        db.commit()
    db.close()

