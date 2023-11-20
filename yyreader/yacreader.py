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
    argparser = argparse.ArgumentParser(description="Scan comic directory", formatter_class=argparse.RawTextHelpFormatter)
    argparser.add_argument('action', help = '''Specify one of the following:
  'deleted'  look for files that have been deleted but are still in the database.
  'filedate' find all files with mismatches database date entries.
  'filetype' find all files with data that doesn't match their extension.
  'xml'      files with invalid ComicInfo.xml files. (NOT IMPLEMENTED)
  'dupes'    try to identify duplicated records. (NOT IMPLEMENTED)
  'holes'    find volumes with missing issues. (NOT IMPLEMENTED)
  'verify'   recheck database items against file and comicvine data. (NOT IMPLEMENTED) ''')

    argparser.add_argument('-v', '--verbose', action='store_true')
    argparser.add_argument('-y', '--yes', action='store_true')
    argparser.add_argument('-1', '--one', help = "Just process a single entry, for testing.  Also enables --verbose and --debug.", action='store_true')
    argparser.add_argument('-u', '--update', action='store_true', help = "Update item metadata.")
    #argparser.add_argument('--comicvine',  help = "Pull external comicvine data when running --update, otherwise just update with what can be parsed from the filename.", action='store_true')
    argparser.add_argument('--volume', metavar = 'VOL', help = "Only --update or --scan comics in VOL.")
    argparser.add_argument('--debug', action='store_true')
    argparser.add_argument('--dryrun', action='store_true')


    args = argparser.parse_args()
    config = minorimpact.config.getConfig(script_name = 'yyreader')

    if (args.one is True):
        args.verbose = True
        args.debug = True

    init_db()
    db = connect()
    cur = db.cursor()

    if (args.action == 'deleted'):
        cur.execute("SELECT id, volume, number from comic_info")
        rows = cur.fetchall()
        i = 1
        for row in rows:
            id = row[0]
            volume = row[1]
            number = row[2]
            print("scanning comic_info {} of {}".format(i, len(rows)), end='\r')
            cur.execute("SELECT path, fileName from comic where comicInfoId=?", (id, ))
            rows2 = cur.fetchall()
            if (len(rows2) == 0):
                print("\ndeleting", id, volume, number, "from comic_info")
                cur.execute('delete from comic_info where id = ?', (id, ))
                db.commit()
            i = i + 1

        cur.execute("SELECT id, comicInfoId from read_log")
        rows = cur.fetchall()
        i = 1
        for row in rows:
            id = row[0]
            comic_info_id = row[1]
            print("scanning read_log {} of {}".format(i, len(rows)), end='\r')
            cur.execute("SELECT id, volume, number from comic_info where id=?", (comic_info_id, ))
            rows2 = cur.fetchall()
            if (len(rows2) == 0):
                print("\ndeleting", id, "from read_log")
                cur.execute('delete from comic_info where id = ?', (id, ))
                db.commit()
            i = i + 1
        print('')

        cur.execute("SELECT id, comicInfoId from comic_info_arc")
        rows = cur.fetchall()
        i = 1
        for row in rows:
            id = row[0]
            comic_info_id = row[1]
            print("scanning comic_info_arc {} of {}".format(i, len(rows)), end='\r')
            cur.execute("SELECT id, volume, number from comic_info where id=?", (comic_info_id, ))
            rows2 = cur.fetchall()
            if (len(rows2) == 0):
                print("\ndeleting", id, "from comic_info_arc")
                cur.execute('delete from comic_info_arc where id = ?', (id, ))
                db.commit()
            i = i + 1
        print('')

        cur.execute("SELECT id, foreComicId, aftComicId from link")
        i = 1
        rows = cur.fetchall()
        for row in rows:
            id = row[0]
            fore_id = row[1]
            aft_id = row[2]
            print("scanning link {} of {}".format(i, len(rows)), end='\r')
            cur.execute("SELECT id, volume, number from comic_info where id=?", (fore_id, ))
            rows2 = cur.fetchall()
            if (len(rows2) == 0):
                print("\ndeleting", id, "from link")
                cur.execute('delete from link where id = ?', (id, ))
                db.commit()
            cur.execute("SELECT id, volume, number from comic_info where id=?", (aft_id, ))
            rows2 = cur.fetchall()
            if (len(rows2) == 0):
                print("\ndeleting", id, "from link")
                cur.execute('delete from link where id = ?', (id, ))
                db.commit()
            i = i + 1
        print('')

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

        if (args.action in ('filetype', 'filedate', 'xml', 'verify', 'dupes', 'holes')):
            #c = comic.comic(config['default']['comic_dir'] + path, args = args)
            if (args.action == 'filedate'):
                file_name = config['default']['comic_dir'] + path
                parse_data = parser.parse(file_name, args = args)
                if ('date' in parse_data):
                    file_date = parse_data['date']
                    if (re.search(r'^0\/', date) is None):
                        dbdate = convert_yacreader_date(date)
                        if (file_date != dbdate.strftime('%Y-%m-%d')):
                            print("{}: dbdate '{}' doesn't match file date '{}'".format(file_name, dbdate.strftime('%Y-%m-%d'), file_date))
                            if (comicvine_id is not None):
                                print("comicvine url: https://comicvine.gamespot.com/unknown/4000-{}".format(comicvine_id))
            if (args.action == 'filetype'):
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
                                        db.commit()
                                    except Exception as e:
                                        print(e)
                        break
            if (args.action ==  'xml'):
                #TODO: scan files for valid, up-to-date ComicInfo.xml files.  The Notes field should contain "yyreader xml v1", at this point...
                #TODO: Make the xml version a variable.
                print("This isn't written yet, check back, like, later, and stuff.")
                pass
            if (args.action == 'holes'):
                #TODO: Scan all the existing volumes for "holes" -- places where the numbers either don't start with 1, or skip some value.  (Check comicvine for "total
                #   number of issues"?  I mean, that's a good idea, but for current titles the caching tends to make more difficult than it ought to be.)
                print("This doesn't exist yet either.")
                pass
            if (args.action == 'verify'):
                #TODO: Compare what's in the database to what's in the file and what's in comicvine, and then retrieve, rewrite and reupdate everything.
                #TODO: Make an optional "subset" value (ie, a number of items or a percentage) that can be set, so that only a portion of the whole will be checked rather
                #   than however many thousands of items exist?  Maybe add also add a "last_checked" field somewhere so we know not to check the same items more than
                #   once every x days.
                print("Nope.")
                pass
            if (args.action == 'dupes'):
                #TODO: Identify duplicate issues.
                print("Nein.")
                pass

        elif (args.update):
            #TODO: Settle on what 'done' means when it comes to what data should be in the yacreader database.  Technically all we need is issue number, date and volume to
            #   just read the books, but I also want arcs, publishers and some of the creatives in there for filtering and searching.
            #if (comicvine_id is not None and date is not None and title is not None and writer is not None and penciller is not None):
            #    continue
            if (date is not None and issue is not None and volume is not None and re.search(r'^0\/', date) is None):
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
                db.commit()

        #if (i > 10): break
        if (args.one is True): break
    db.close()

def connect():
    global config

    if (config is None):
        config = minorimpact.config.getConfig(script_name = 'yyreader')

    db_file = config['default']['db']
    if (os.path.exists(db_file) is None):
        raise Exception("{} does not exist".format(db_file))

    db = sqlite3.connect(db_file)
    db.row_factory = sqlite3.Row
    return db

def init_db():
    db = connect()
    cursor = db.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS comic_info_arc (id INTEGER PRIMARY KEY, storyArc TEXT NOT NULL, arcNumber INTEGER, arcCount INTEGER, comicVineID TEXT, comicInfoId INTEGER NOT NULL, FOREIGN KEY(comicInfoId) REFERENCES comic_info(id) ON DELETE CASCADE)')
    cursor.execute('CREATE TABLE IF NOT EXISTS read_log (id INTEGER PRIMARY KEY, start_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP, currentPage INTEGER default 1, end_date TIMESTAMP, comicInfoId INTEGER NOT NULL, mod_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY(comicInfoId) REFERENCES comic_info(id) ON DELETE CASCADE)')
    cursor.execute('CREATE TABLE IF NOT EXISTS beacon (id INTEGER PRIMARY KEY, name TEXT NOT NULL, mod_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')
    cursor.execute('CREATE TABLE IF NOT EXISTS link (id INTEGER PRIMARY KEY, name TEXT, foreComicId INTEGER NOT NULL, aftComicId INTEGER NOT NULL, mod_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY(foreComicId) REFERENCES comic_info(id) ON DELETE CASCADE, FOREIGN KEY(aftComicId) REFERENCES comic_info(id) ON DELETE CASCADE)')
    cursor.execute('CREATE TABLE IF NOT EXISTS arclinkskip (id INTEGER PRIMARY KEY, comicInfoId INTEGER NOT NULL, mod_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY(comicInfoId) REFERENCES comic_info(id) ON DELETE CASCADE)')
    db.commit()
    indexes = [ 'CREATE UNIQUE INDEX comic_info_arc_idx on comic_info_arc(storyArc, comicInfoId)',
                'CREATE UNIQUE INDEX beacon_idx on beacon(name)',
                'CREATE UNIQUE INDEX link_idx on link(foreComicId)',
                'CREATE UNIQUE INDEX arclinkskip_idx on arclinkskip(comicInfoId)',
              ]
    for index in indexes:
        try:
            cursor.execute(index)
            db.commit()
        except Exception as e:
            if (re.search('^index (.+) already exists$', str(e)) is None):
                raise e
    db.close()

def convert_yacreader_date(yacreader_date):
    #print("yacreader_date:{}".format(yacreader_date))
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

def add_filter(sql, filter):
    if ('params' not in sql):
        sql['params'] = []
    for f in filter:
        if (len(filter[f]) == 0):
            continue

        if ('where' not in sql):
            sql['where'] = ''
        if (sql['where'] != ''):
            sql['where'] = sql['where'] + ' and '

        if (f == 'labels'):
            sql['from'] = sql['from'] + ', label, comic_label, comic'
            sql['where'] = sql['where'] + 'label.id = comic_label.label_id and comic_label.comic_id=comic.id and comic.comicInfoId=comic_info.id and '
            w = ''
            for label in filter[f]:
                w = w + 'label.name = ? or '
                sql['params'].append(label)
            w = re.sub(' or $', '', w)
            sql['where'] = sql['where'] + '(' + w + ')'

        if (f == 'publishers'):
            w = ''
            for publisher in filter[f]:
                w = w + 'comic_info.publisher = ? or '
                sql['params'].append(publisher)
            w = re.sub(' or $', '', w)
            sql['where'] = sql['where'] + '(' + w + ')'
    print(sql)
    return

def build_sql(sql):
    sql_string = ''
    sql_string = 'select ' + sql['select']
    sql_string = sql_string +  ' from '
    sql_string = sql_string + sql['from']
    if ('where' in sql and sql['where'] != ''):
        sql_string = sql_string + ' where '
        sql_string = sql_string + sql['where']
    if ('order' in sql and sql['order'] != ''):
        sql_string = sql_string + ' order by '
        sql_string = sql_string + sql['order']
    return sql_string

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
    sql = { 'select': 'comic_info.volume, comic_info.number as issue, comic_info.date, comic_info.id, comic.path, comic_info.read, comic_info.currentPage, comic_info.hash, comic.id as comic_id, comic_info.publisher, comic_info.series', 'from':'comic_info, comic', 'where':'comic.comicInfoId=comic_info.id and comic_info.id = ?', 'params':[id]}
    #print(build_sql(sql), sql['params'])
    cursor.execute(build_sql(sql), sql['params'])
    rows = cursor.fetchall()
    comic_data = None
    for row in rows:
        issue = row['issue']
        volume = row['volume']
        series = row['series']
        m = re.search('^(.+) \((\d\d\d\d)\)$', volume)
        if (m is not None):
            if (series is None):
                series = m[1]
            volume = m[2]

        date = convert_yacreader_date(row[2])
        id = row['id']
        path = row['path']
        read = row['read']
        current_page = row['currentPage']
        hash = row['hash']
        comic_id = row['comic_id']
        publisher = row['publisher']
        fore_id = None
        aft_id = None
        #print("date:{}, series:{}, volume:{}".format(date, series, volume))
        

        linkrow = cursor.execute('select foreComicId from link where aftComicId=?', (id, )).fetchone()
        if (linkrow is not None):
            fore_id = linkrow[0]
        linkrow = cursor.execute('select aftComicId from link where foreComicId=?', (id, )).fetchone()
        if (linkrow is not None):
            aft_id = linkrow[0]

        labelrows = cursor.execute('select label.name from label, comic_label where label.id = comic_label.label_id and comic_label.comic_id = ?', (comic_id,)).fetchall()
        labels = []
        for labelrow in labelrows:
            labels.append(labelrow[0])

        if (current_page is None or current_page == 0):
            current_page = 1
        comic_data = { 'id':id, 'series':series, 'volume':volume, 'issue':issue, 'date':date, 'path': path, 'read':read, 'current_page':current_page, 'hash':hash, 'publisher':publisher, 'fore_id':fore_id, 'aft_id': aft_id, 'labels':labels }

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
    sql = { 'select': 'volume, number, date, id, read, currentPage, series', 'from':'comic_info', 'where':'date like "%/{}/{}"'.format(month, year), 'params':[]}
    #print(build_sql(sql), sql['params'])
    cursor.execute(build_sql(sql), sql['params'])
    rows = cursor.fetchall()
    for row in rows:
        series = row['series']
        volume = row['volume']
        m = re.search('^(.+) \((\d\d\d\d)\)$',volume)
        if (m is not None):
            if (series is None):
                series = m[1]
            volume = m[2]
        issue = row['number']
        date = convert_yacreader_date(row['date'])
        id = row['id']
        read = row['read']
        current_page = row['currentPage']
        #print("date:{}, series:{}, volume:{}".format(date, series, volume))

        comics.append(get_comic_by_id(id, db = local_db))
    if (db is None):
        local_db.close()
    return sorted(comics, key=lambda x:(x['date'], x['series'], x['volume']) )

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

def get_comics_by_volume(volume, db = None, filter = None):
    if (db is None):
        local_db = connect()
    else:
        local_db = db
    cursor = local_db.cursor()

    comics = []
    sql = {}
    sql['select'] = 'comic_info.volume, comic_info.number, comic_info.date, comic_info.id, comic_info.read, comic_info.currentPage'
    sql['from'] = 'comic_info'
    sql['where'] = 'comic_info.volume = ?'
    sql['params'] = [volume]
    if (filter):
        add_filter(sql, filter)

    #print(build_sql(sql), sql['params'])
    cursor.execute(build_sql(sql), sql['params'])

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

def get_labels():
    local_db = connect()
    cursor =  local_db.connect()

    labels = []
    cursor.execute('select distinct(label.name) as name from label order by name')
    rows = cursor.fetchall()
    for row in rows:
        labels.append(row[0])

    local_db.close()
    return labels

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

def get_labels():
    db = connect()
    cursor = db.cursor()
    labels = []
    sql = { 'select': 'distinct(label.name)', 'from':'label', 'where':'label.name is not NULL', 'params':[] }
    cursor.execute(build_sql(sql), sql['params'])
    rows = cursor.fetchall()
    for row in rows:
        if (row[0] is None):
            continue
        labels.append(row[0])
    db.close()
    return sorted(labels, key=lambda x: x)

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

def get_publishers():
    db = connect()
    cursor = db.cursor()
    publishers = []
    sql = { 'select': 'distinct(comic_info.publisher)', 'from':'comic_info', 'where':'comic_info.publisher is not NULL', 'params':[] }
    cursor.execute(build_sql(sql), sql['params'])
    rows = cursor.fetchall()
    for row in rows:
        if (row[0] is None):
            continue
        publishers.append(row[0])
    db.close()
    return sorted(publishers, key=lambda x: x)

def get_volumes(filter = None):
    db = connect()
    cursor = db.cursor()
    volumes = []
    sql = { 'select': 'distinct(comic_info.volume)', 'from':'comic_info', 'params':[]}
    if (filter is not None):
        add_filter(sql, filter)
    #print(build_sql(sql), sql['params'])
    cursor.execute(build_sql(sql), sql['params'])
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

def link(foreid, aftid, db = None):
    if (db is None):
        local_db = connect()
    else:
        local_db = db
    cursor = local_db.cursor()

    try:
        cursor.execute('insert into link(foreComicId, aftComicId) values (?, ?)', (foreid, aftid))
        local_db.commit()
    except Exception as e:
        if (re.search('^UNIQUE constraint failed:', str(e)) is None):
            raise e
    if (db is None):
        local_db.close()

def set_labels(id, labels):
    local_db = connect()
    cursor =  local_db.cursor()

    comic_id = cursor.execute('select id from comic where comicInfoId=?', (id, )).fetchone()[0]
    cursor.execute('delete from comic_label where comic_id = ?', (comic_id, ))
    for label in labels:
        count = cursor.execute('select count(*) from label, comic_label where label.id=comic_label.label_id and label.name = ?', (label,)).fetchone()[0]
        cursor.execute('insert into comic_label (label_id,comic_id, ordering) select label.id, ?, ? from label where label.name = ?', (comic_id, count+1, label))
    
    local_db.commit()
    local_db.close()
    return 

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

