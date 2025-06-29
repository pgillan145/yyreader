import argparse
from datetime import datetime, timedelta
from dumper import dump
import magic
import minorimpact.config
import os
import os.path
from PIL import Image
import re
import sqlite3
import sys
import re
import shutil
from . import comic, parser

config = None

config = None

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
    global config

    if (config is None):
        config = minorimpact.config.getConfig(script_name = 'yyreader')


    db = connect()
    cursor = db.cursor()

    cursor.execute('CREATE TABLE IF NOT EXISTS comic_info (id INTEGER PRIMARY KEY,title TEXT,coverPage INTEGER DEFAULT 1,numPages INTEGER,number INTEGER,isBis BOOLEAN,count INTEGER,volume TEXT,storyArc TEXT,arcNumber INTEGER,arcCount INTEGER,genere TEXT,writer TEXT,penciller TEXT,inker TEXT,colorist TEXT,letterer TEXT,coverArtist TEXT,date TEXT,publisher TEXT,format TEXT,color BOOLEAN,ageRating BOOLEAN,synopsis TEXT,characters TEXT,notes TEXT,hash TEXT UNIQUE NOT NULL,edited BOOLEAN DEFAULT 0,read BOOLEAN DEFAULT 0,hasBeenOpened BOOLEAN DEFAULT 0,rating INTEGER DEFAULT 0,currentPage INTEGER DEFAULT 1, bookmark1 INTEGER DEFAULT -1, bookmark2 INTEGER DEFAULT -1, bookmark3 INTEGER DEFAULT -1, brightness INTEGER DEFAULT -1, contrast INTEGER DEFAULT -1, gamma INTEGER DEFAULT -1, comicVineID TEXT,lastTimeOpened INTEGER,coverSizeRatio REAL,originalCoverSize STRING,manga BOOLEAN DEFAULT 0, added INTEGER, type INTEGER DEFAULT 0, editor TEXT, imprint TEXT, teams TEXT, locations TEXT, series TEXT, alternateSeries TEXT, alternateNumber TEXT, alternateCount INTEGER, languageISO TEXT, seriesGroup TEXT, mainCharacterOrTeam TEXT, review TEXT, tags TEXT)')
    cursor.execute('CREATE TABLE IF NOT EXISTS folder (id INTEGER PRIMARY KEY,parentId INTEGER NOT NULL,name TEXT NOT NULL,path TEXT NOT NULL,finished BOOLEAN DEFAULT 0,completed BOOLEAN DEFAULT 1,numChildren INTEGER,firstChildHash TEXT,customImage TEXT,manga BOOLEAN DEFAULT 0, added INTEGER, updated INTEGER, type INTEGER DEFAULT 0,FOREIGN KEY(parentId) REFERENCES folder(id) ON DELETE CASCADE)')
    cursor.execute('CREATE TABLE IF NOT EXISTS comic (id INTEGER PRIMARY KEY, parentId INTEGER NOT NULL, comicInfoId INTEGER NOT NULL, fileName TEXT NOT NULL, path TEXT, FOREIGN KEY(parentId) REFERENCES folder(id) ON DELETE CASCADE, FOREIGN KEY(comicInfoId) REFERENCES comic_info(id))')
    cursor.execute('CREATE TABLE IF NOT EXISTS db_info (version TEXT NOT NULL)')
    cursor.execute('CREATE TABLE IF NOT EXISTS label (id INTEGER PRIMARY KEY, name TEXT NOT NULL, color TEXT NOT NULL, ordering INTEGER NOT NULL)')
    cursor.execute('CREATE TABLE IF NOT EXISTS comic_label (comic_id INTEGER, label_id INTEGER, ordering INTEGER, FOREIGN KEY(label_id) REFERENCES label(id) ON DELETE CASCADE, FOREIGN KEY(comic_id) REFERENCES comic(id) ON DELETE CASCADE, PRIMARY KEY(label_id, comic_id))')
    cursor.execute('CREATE TABLE IF NOT EXISTS reading_list (id INTEGER PRIMARY KEY, parentId INTEGER, ordering INTEGER DEFAULT 0, name TEXT NOT NULL, finished BOOLEAN DEFAULT 0, completed BOOLEAN DEFAULT 1, manga BOOLEAN DEFAULT 0, FOREIGN KEY(parentId) REFERENCES reading_list(id) ON DELETE CASCADE)')
    cursor.execute('CREATE TABLE IF NOT EXISTS comic_reading_list (reading_list_id INTEGER, comic_id INTEGER, ordering INTEGER, FOREIGN KEY(reading_list_id) REFERENCES reading_list(id) ON DELETE CASCADE, FOREIGN KEY(comic_id) REFERENCES comic(id) ON DELETE CASCADE, PRIMARY KEY(reading_list_id, comic_id))')
    cursor.execute('CREATE TABLE IF NOT EXISTS default_reading_list (id INTEGER PRIMARY KEY, name TEXT NOT NULL)')
    cursor.execute('CREATE TABLE IF NOT EXISTS comic_default_reading_list (comic_id INTEGER, default_reading_list_id INTEGER, ordering INTEGER, FOREIGN KEY(default_reading_list_id) REFERENCES default_reading_list(id) ON DELETE CASCADE, FOREIGN KEY(comic_id) REFERENCES comic(id) ON DELETE CASCADE,PRIMARY KEY(default_reading_list_id, comic_id))')


    cursor.execute('CREATE TABLE IF NOT EXISTS arclinkskip (id INTEGER PRIMARY KEY, comicInfoId INTEGER NOT NULL, mod_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY(comicInfoId) REFERENCES comic_info(id) ON DELETE CASCADE)')
    cursor.execute('CREATE TABLE IF NOT EXISTS beacon (id INTEGER PRIMARY KEY, name TEXT NOT NULL, mod_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')
    cursor.execute('CREATE TABLE IF NOT EXISTS comic_info_arc (id INTEGER PRIMARY KEY, storyArc TEXT NOT NULL, arcNumber INTEGER, arcCount INTEGER, comicVineID TEXT, comicInfoId INTEGER NOT NULL, FOREIGN KEY(comicInfoId) REFERENCES comic_info(id) ON DELETE CASCADE)')
    cursor.execute('CREATE TABLE IF NOT EXISTS link (id INTEGER PRIMARY KEY, name TEXT, foreComicId INTEGER NOT NULL, aftComicId INTEGER NOT NULL, mod_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY(foreComicId) REFERENCES comic_info(id) ON DELETE CASCADE, FOREIGN KEY(aftComicId) REFERENCES comic_info(id) ON DELETE CASCADE)')
    cursor.execute('CREATE TABLE IF NOT EXISTS read_log (id INTEGER PRIMARY KEY, start_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP, currentPage INTEGER default 1, end_date TIMESTAMP, comicInfoId INTEGER NOT NULL, mod_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY(comicInfoId) REFERENCES comic_info(id) ON DELETE CASCADE)')
    cursor.execute('CREATE TABLE IF NOT EXISTS quit_series (id INTEGER PRIMARY KEY, series TEXT NOT NULL, volume TEXT NOT NULL, mod_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')
    db.commit()

    # Add indexes
    indexes = [
                'CREATE UNIQUE INDEX arclinkskip_idx on arclinkskip(comicInfoId)',
                'CREATE UNIQUE INDEX beacon_idx on beacon(name)',
                'CREATE UNIQUE INDEX comic_info_arc_idx on comic_info_arc(storyArc, comicInfoId)',
                'CREATE INDEX comic_default_reading_list_ordering_index ON label (ordering)',
                'CREATE INDEX comic_label_ordering_index ON label (ordering)',
                'CREATE INDEX comic_reading_list_ordering_index ON label (ordering)',
                'CREATE INDEX label_ordering_index ON label (ordering)',
                'CREATE UNIQUE INDEX link_idx on link(foreComicId)',
                'CREATE INDEX reading_list_ordering_index ON label (ordering)',
              ]

    for index in indexes:
        try:
            cursor.execute(index)
            db.commit()
        except Exception as e:
            if (re.search('^index (.+) already exists$', str(e)) is None):
                raise e

    # insert initial data
    inserts = [
                "INSERT INTO folder (id, parentId, name, path) VALUES (1,1,'root','/')",
              ]

    for insert in inserts:
        try:
            cursor.execute(insert)
            db.commit()
        except Exception as e:
            if (re.search(r'^UNIQUE constraint failed: folder\.id', str(e)) is None):
                raise e

    db.close()

def add_beacon(name):
    db = connect()
    cursor = db.cursor()
    try:
        cursor.execute('insert into beacon (name, mod_date) values (?,  CURRENT_TIMESTAMP)', (name, ))
        db.commit()
    except Exception as e:
        print(e)
    db.close()

def add_comic(comic, db = None):
    # TODO: Make an 'update_comic' function that will update the database with changes.
    if (db is None):
        local_db = connect()
    else:
        local_db = db

    cursor = local_db.cursor()

    #sql = {}
    #cursor.execute(build_sql(sql), sql['params'])

    folder_id = get_folder_id(comic)


    #TODO: Settle on what 'done' means when it comes to what data should be in the yacreader database.  Technically all we need is issue number, date and volume to
    #   just read the books, but I also want arcs, publishers and some of the creatives in there for filtering and searching.
    #if (comicvine_id is not None and date is not None and title is not None and writer is not None and penciller is not None):
    #    continue

    arcs = comic.get('story_arcs')
    arc_name = arcs[0] if (len(arcs) > 0) else None
    #print(f"arc_name:{arc_name}")
    characters = ','.join(comic.get('characters')) if (comic.get('characters')) else None
    colorist = ','.join(comic.get('colorists')) if (comic.get('colorists')) else None
    description = comic.get('description')
    inker = ','.join(comic.get('inkers')) if (comic.get('inkers')) else None
    issue = comic.get('issue')
    issue_id = comic.get('issue_id')
    issue_name = comic.get('name')
    letterer = ','.join(comic.get('letterers')) if (comic.get('letterers')) else None
    date = comic.get('date')
    penciller = ','.join(comic.get('pencillers')) if (comic.get('pencillers')) else None
    publisher = comic.get('publisher')
    series = comic.get('series')
    writer = ','.join(comic.get('writers')) if (comic.get('writers')) else None

    sql = { 'insert': 'comic_info',
            'fields': ['series', 'title', 'number', 'date', 'hash', 'volume', 'numPages', 'storyArc', 'publisher', 'writer', 'penciller', 'synopsis', 'letterer', 'inker', 'colorist', 'characters' ],
            'params': [ comic.series(), comic.get('issue_name'), comic.issue(), convert_date_to_yacreader(comic.date()), comic.md5(), comic.get('volume'), comic.page_count(), arc_name, publisher, writer, penciller, description, letterer, inker, colorist, characters ],
          }
    sql_string = build_sql(sql)
    #print (sql_string)
    cursor.execute(sql_string, sql['params'])
    comic_id = cursor.lastrowid

    sql = { 'insert': 'comic',
            'fields': ['parentId', 'comicInfoId', 'fileName', 'path'],
            'params': [ folder_id, comic_id, os.path.split(comic.file)[1], re.sub( config['default']['comic_dir'], '', comic.file) ],
          }
    sql_string = build_sql(sql)
    #print (sql_string)
    cursor.execute(sql_string, sql['params'])

    for arc in arcs:
        sql = { 'insert': 'comic_info_arc',
                'fields': ['storyArc', 'comicInfoId'],
                'params': [arc, comic_id],
              }
        sql_string = build_sql(sql)
        #print (sql_string)
        try:
            cursor.execute(sql_string, sql['params'])
        except Exception as e:
            if (str(e) != 'UNIQUE constraint failed: comic_info_arc.storyArc, comic_info_arc.comicInfoId'):
                print(e)
                pass

    local_db.commit()

    cover_dir = config['default']['cache_dir'] + '/covers/'
    os.makedirs(cover_dir, exist_ok = True)
    cover_file = f'{cover_dir}/{comic.md5()}.jpg'
    cover_data = comic.page(1, crop = False, thumbnail=True)

    with open(cover_file, 'bw') as f:
        f.write(cover_data)

    comic_data = get_comic_by_id(comic_id, db = local_db)

    if (db is None):
        local_db.close();

    return comic_data

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
    #print(sql)
    return

def build_sql(sql):
    sql_string = ''
    if ('select' in sql):
        sql_string = 'select ' + sql['select']
        sql_string = sql_string + ' from '
        sql_string = sql_string + sql['from']
        if ('where' in sql and sql['where'] != ''):
            sql_string = sql_string + ' where '
            sql_string = sql_string + sql['where']

        if ('order' in sql and sql['order'] != ''):
            sql_string = sql_string + ' order by '
            sql_string = sql_string + sql['order']
    elif ('insert' in sql):
        sql_string = 'insert into ' + sql['insert']
        fields = []
        values = []
        if (len(sql['fields']) != len(sql['params'])):
            raise Eception("invalid number of fields or parameters")

        for field in sql['fields']:
            fields.append(field)
            values.append('?')
        sql_string = sql_string + '(' + ','.join(fields) + ') values (' + ','.join(values) + ')'
    elif ('update' in sql):
        sql_string = 'update ' + sql['update']
        fields = []
        values = []
        sql_string = sql_string + 'set '
        for field in sql['fields']:
            sql_string = sql_string + f'{field} = ?, '
        sql_string = re.sub(r', $', '', sql_string)

    return sql_string

def convert_date_to_yacreader(date):
    yacreader_date = datetime.fromisoformat(date).strftime('%-d/%-m/%Y')
    #print(f"yacreader_date:{yacreader_date}")
    return yacreader_date

def convert_yacreader_date(yacreader_date):
    #print("yacreader_date:{}".format(yacreader_date))
    date = datetime.strptime(yacreader_date, '%d/%m/%Y')
    return date

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

def get_comic_by_series(series, issue, date, db = None):
    sql = { 'select': 'comic_info.volume, comic_info.number as issue, comic_info.date, comic_info.id, comic.path, comic_info.read, comic_info.currentPage, comic_info.hash, comic.id as comic_id, comic_info.publisher, comic_info.series', 'from':'comic_info, comic', 'where':'comic.comicInfoId=comic_info.id and comic_info.series = ? and comic_info.number = ? and comic_info.date = ?', 'params':[series, issue, date]}

    return get_comic(sql, db = db)

def get_comic_by_id(id, db = None):
    sql = { 'select': 'comic_info.volume, comic_info.number as issue, comic_info.date, comic_info.id, comic.path, comic_info.read, comic_info.currentPage, comic_info.hash, comic.id as comic_id, comic_info.publisher, comic_info.series', 'from':'comic_info, comic', 'where':'comic.comicInfoId=comic_info.id and comic_info.id = ?', 'params':[id]}

    comic_data = get_comic(sql, db = db)
    return comic_data

def get_comic(sql, db = None):
    if (sql is None):
        raise Exception("SQL not defined")

    if (db is None):
        local_db = connect()
    else:
        local_db = db

    cursor = local_db.cursor()

    sql_text = f"{build_sql(sql), sql['params']}"

    #print(sql_text)
    cursor.execute(build_sql(sql), sql['params'])

    rows = cursor.fetchall()
    comic_data = None
    for row in rows:
        issue = row['issue']
        volume = row['volume']
        series = row['series']
        m = re.search(r'^(.+) \((\d\d\d\d)\)$', volume)
        if (m is not None):
            if (series is None):
                series = m[1]
            volume = m[2]

        date = convert_yacreader_date(row[2])
        id = row['id']
        path = row['path']
        read = row['read']
        read = True if read > 0 else False
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

        start_date = None
        end_date = None
        mod_date = None
        history = cursor.execute('select start_date, end_date, mod_date from read_log where comicInfoID = ? order by start_date desc' , (comic_id,)).fetchall()
        if (history is not None and len(history)>0):
            start_date = history[0]['start_date']
            end_date = history[0]['end_date']
            mod_date = history[0]['mod_date']

        read_previous = get_read_previous(series, volume, db = db)

        other_read = cursor.execute('select comic_info.id from comic_info, read_log where read_log.comicInfoID=comic_info.id and comic_info.series=? and comic_info.volume=? and read_log.end_date not NULL', (series, volume,)).fetchall()
        if (other_read is not None and len(other_read)>0):
            previous_read = True

        comic_data = { 'id':id, 'series':series, 'volume':volume, 'issue':issue, 'date':date, 'path': path, 'read':read, 'current_page':current_page, 'hash':hash, 'publisher':publisher, 'fore_id':fore_id, 'aft_id': aft_id, 'labels':labels, 'read_previous': read_previous, 'start_date':start_date, 'end_date':end_date, 'mod_date':mod_date }

    if (db is None):
        local_db.close()

    #if (comic_data is None):
    #    raise Exception(f"couldn't find data for {sql_text}")

    return comic_data

def get_comics_by_current(db = None):
    if (db is None):
        local_db = connect()
    else:
        local_db = db

    cursor = local_db.cursor()

    # THIS NEEDS TO GO THROUGHT EVERYTHING THAT'S BEEN READ, IDENTIFY THE SERIES, THEN COLLECT THE NEXT
    # ISSUE THAT COMES AFTER THE LATEST READ ISSUE.
    max_read = {}
    history = get_history(db = db)
    for c in history:
        #print(c['series'], c['volume'], c['issue'])
        s = c['series']
        v = c['volume']
        cursor.execute('select * from quit_series where series = ? and volume = ?', (s, v, ))
        q = cursor.fetchall()
        if (q is not None and len(q) > 0):
            continue
        sv = f'{s} ({v})'
        if (c['series'] not in max_read or (c['series'] in max_read and max_read[c['series']]['date'] < c['date'])):
            max_read[sv] = c

    comics = []
    for sv in max_read:
        c = max_read[sv]
        s = c['series']
        v = c['volume']
        i = c['issue']
        if (c['read'] is False):
            comics.append(c)
        else:
            series_comics = get_comics_by_series(sv, db = db)
            print(sv, i, c['date'], c['read'])
            for c2 in sorted(series_comics, key = lambda x:(x['date'])):
                print(c2['issue'], c2['date'], c2['read'])
                if (c2['date'] > c['date'] and c2['read'] is False):
                    comics.append(c2)
                    break

    if (db is None):
        local_db.close()

    return sorted(comics, key = lambda x:(x['date']))

def get_comics_by_date(year, month, db = None):
    #print(month)
    zmonth = month
    #print(month)
    if (month < 10): zmonth = '0{}'.format(month)
    sql = { 'select': 'comic_info.volume, comic_info.number, comic_info.date, comic_info.id, comic_info.read, comic_info.currentPage, comic_info.series',
            'from': 'comic_info',
            'where': 'date like "%/{}/{}" or date like "%/{}/{}"'.format(month, year, zmonth, year),
            'params': []
        }

    return get_comics(sql, db = db)

def get_comics_by_series(series, db = None, filter = None):
    volume = ''

    m = re.search(r'^(.+) \((\d\d\d\d(-\d)?)\)$', series)
    if (m is not None):
        series = m[1]
        volume = m[2]

    comics = []
    sql = {}
    sql['select'] = 'comic_info.series, comic_info.number, comic_info.date, comic_info.id, comic_info.read, comic_info.currentPage, comic_info.volume'
    sql['from'] = 'comic_info'
    sql['where'] = 'comic_info.series = ? and comic_info.volume = ?'
    sql['params'] = [series, volume]
    if (filter):
        add_filter(sql, filter)

    return get_comics(sql, db = db)

def get_comics(sql, db = None):
    if (db is None):
        local_db = connect()
    else:
        local_db = db

    cursor = local_db.cursor()
    #zmonth = month
    #if (month < 10): zmonth = '0{}'.format(month)
    #sql = { 'select': 'volume, number, date, id, read, currentPage, series', 'from':'comic_info', 'where':'date like "%/{}/{}" or date like "%/{}/{}"'.format(month, year, zmonth, year), 'params':[]}
    #print(build_sql(sql), sql['params'])
    comics = []
    if (re.search(r'comic_info\.id', sql['select']) is None):
        sql['select'] = f'{sql["select"]}, comic_info.id'
    if (re.search(r'comic_info\.series', sql['select']) is None):
        sql['select'] = f'{sql["select"]}, comic_info.series'
    if (re.search(r'comic_info\.volume', sql['select']) is None):
        sql['select'] = f'{sql["select"]}, comic_info.volume'

    print(build_sql(sql), sql['params'])
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
    cover_file = config['default']['cache_dir'] + '/covers/' + hash + '.jpg'

    return cover_file

def get_folder_id(comic, db = None):
    local_db = db
    if (db is None):
        local_db = connect()

    cursor = local_db.cursor()

    comic_dir = config['default']['comic_dir']
    tmp_file = re.sub(comic_dir, '', os.path.split(comic.file)[0])

    s = tmp_file.split('/')
    current_path = '/'
    parent_id = 1
    folder_id = None
    for i in s:
        current_path = f'{current_path}/{i}'
        current_path = re.sub(r'^//', '/', current_path)

        try:
            folder_id = cursor.execute('select id from folder where path=?', (current_path, )).fetchone()[0]
        except:
            cursor.execute('insert into folder (parentId, name, path) VALUES (?,?,?)', (parent_id,i,current_path))
            folder_id = cursor.lastrowid
            parent_id = folder_id
            local_db.commit()


    if (db is None):
        local_db.close()

    if (folder_id is None):
        raise Exception(f"Can't get folder id for {comic.file}")

    return folder_id

def get_history(db = None, filter = None):
    sql = {}
    sql['select'] = 'comic_info.series, comic_info.number, comic_info.date, comic_info.id, comic_info.read, comic_info.currentPage, read_log.end_date, read_log.mod_date'
    sql['from'] = 'comic_info, read_log'
    sql['where'] = 'comic_info.id = read_log.comicInfoID'
    sql['params'] = []
    if (filter):
        add_filter(sql, filter)

    print(build_sql(sql))
    comics = get_comics(sql, db = db)
    for c in comics:
        if (c['current_page'] is None or c['current_page'] == 0):
            c['current_page'] = 1

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
    #print(f"rows:{len(rows)}")

    #dump(rows)
    for row in rows:
        #print(row[0])
        if (row[0] is None):
            continue
        date = convert_yacreader_date(row[0])
        #print(date.year)
        if (date.year != year):
            continue
        month = int(date.strftime('%m'))
        if (month not in months):
            months.append(month)

    #dump(months)
    if (db is None):
        local_db.close()

    return sorted(months, key=lambda x:x)

def get_head_comic(id, db = None):
    if (db is None):
        local_db = connect()
    else:
        local_db = db
    cursor = local_db.cursor()

    y = get_comic_by_id(id, db = local_db)
    while (y['fore_id'] is not None):
        y = get_comic_by_id(y['fore_id'], db = local_db)

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

    y = get_comic_by_id(id, db = local_db)
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
                if (year is None or month is None):
                    break
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
    if (len(months) == 0 or month == months[len(months)-1]):
        years = get_years(db = local_db)
        for i in range(0, len(years)):
            if (years[i] == year and i < (len(years) - 1)):
                next_year = years[i+1]
                break
        if (next_year is not None):
            months = get_months(next_year, db = local_db)
            if (len(months) > 0): next_month = months[0]
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
        #print(y['date'])
        (year, month) = y['date'].strftime('%Y|%-m').split('|')
        year = int(year)
        month = int(month)
        #print(year, month)
        issues = get_comics_by_date(year, month, db = local_db)

        i = len(issues) - 1
        for issue in list(reversed(issues)):
            if (issue['id'] == y['id']):
                current = i
                break
            i = i - 1

        #print(len(issues))
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
                if (year is None or month is None):
                    break
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
    if (len(months) == 0 or month == months[0]):
        years = get_years()
        for i in range(0, len(years)):
            if (years[i] == year and i > 0):
                prev_year = years[i-1]
                break

        if (prev_year is not None):
            months = get_months(prev_year, db = local_db)
            if (len(months) > 0): prev_month = months[len(months)-1]
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
    sql = { 'select': 'distinct(comic_info.publisher)',
            'from':'comic_info',
            'where':'comic_info.publisher is not NULL',
            'params':[] }
    cursor.execute(build_sql(sql), sql['params'])
    rows = cursor.fetchall()
    for row in rows:
        if (row[0] is None):
            continue
        publishers.append(row[0])
    db.close()
    return sorted(publishers, key=lambda x: x)

def get_seriess(filter = None):
    db = connect()
    cursor = db.cursor()

    sql = { 'select': 'comic_info.id, comic_info.volume, comic_info.series, comic.path, comic_info.date, comic_info.number', 'from':'comic_info, comic', 'where':'comic.comicInfoId=comic_info.id', 'params': []}
    if (filter is not None):
        add_filter(sql, filter)
    #print(build_sql(sql), sql['params'])
    cursor.execute(build_sql(sql), sql['params'])
    rows = cursor.fetchall()
    seriess = {}
    updates = {}
    for row in rows:
        id = row['id']
        date = row['date']
        series = row['series']
        volume = row['volume']
        path = row['path']
        number = row['number']
        parsed_data = parser.parse(path)

        # Reset the series field based on the path if series is NULL; not sure which stupid thing I did made
        #   this happen.
        if ((series is None or series == 'None') and volume is not None and re.search('^\d\d\d\d$', volume)):
            #print("{} ({}): {}".format(series, volume, path))
            new_series = re.search('^(.+) \(\d\d\d\d\)$', path.split('/')[2])[1]
            new_series = parser.massage_series(new_series, reverse=True)
            #print("series missing from {}, setting to {}".format(path, new_series))
            cursor.execute("update comic_info set series=? where id=? and volume = ?", (new_series, id, volume, ))
            db.commit()
            series = new_series

        # This was fix a database issue where everything used to be in volume instead of series.
        if (volume is not None and re.search('^(.+) \((\d\d\d\d)\)$', volume) is not None):
            m = re.search('^(.+) \((\d\d\d\d)\)$', volume)
            series = m[1]
            new_volume = m[2]
            if (series + new_volume not in updates):
                cursor.execute("update comic_info set series=?, volume=? where series is NULL and volume=? and id=?", (series, new_volume, volume, id,))
                db.commit()
                updates[series+new_volume] = 1
            volume = new_volume

        # If series or volume are none, parse them from the 'path' field.
        if (series is None):
            #series = parser.massage_series(parsed_data['series'], reverse=True)
            series = parsed_data['series']
            cursor.execute("update comic_info set series=? where series is NULL and id=?", (series, id,))
            db.commit()
            print(f"parsed series from filename: '{series}'")
        if (volume is None):
            volume = parsed_data['volume']
            print(f"parsed volume for '{series}' from filename: '{volume}'")
            cursor.execute("update comic_info set volume=? where volume is NULL and id=?", (volume, id,))
            db.commit()
        if (date is None):
            date = f"{parsed_data['day']}/{parsed_data['month']}/{parsed_data['year']}"
            print(f"parsed date for '{series} ({volume})' from filename: '{date}'")
            cursor.execute("update comic_info set date=? where date is NULL and id=?", (date, id,))
            db.commit()
        if (number is None):
            number = parsed_data['issue']
            print(f"parsed number for '{series} ({volume})' from filename: '{number}'")
            cursor.execute("update comic_info set number=? where number is NULL and id=?", (number, id,))
            db.commit()

        seriess['{} ({})'.format(series, volume)] = 1
    db.close()
    return sorted(seriess.keys(), key=lambda x:x.lower())

def get_read_previous(series, volume, db = None):
    if (db is None):
        local_db = connect()
    else:
        local_db = db

    cursor = local_db.cursor()

    rows = None
    try:
        # TODO: could just select count(*) and not pull hundreds of records for no reason
        cursor.execute('select id, number, read from comic_info where series = ? and volume = ? and read = 1', (series, volume, ))
        rows = cursor.fetchall()
        print(series, volume, len(rows))
    except Exception as e:
        #print(e)
        pass

    if (db is None):
        local_db.close()

    if (rows is not None and len(rows)>0):
        return True

    return False

def get_years(db = None):
    if (db is None):
        local_db = connect()
    else:
        local_db = db
    cursor = local_db.cursor()
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

    if (db is None):
        local_db.close()

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

def mark_unread(id, db = None):
    if (db is None):
        local_db = connect()
    else:
        local_db = db
    cursor = local_db.cursor()

    #try:
    cursor.execute('update comic_info set read = 0, currentPage = 1, lastTimeOpened = NULL where id = ?', (id,))
    cursor.execute('delete from read_log where comicInfoId = ? and end_date is NULL', (id, ))
    local_db.commit()
    #except Exception as e:
    #    print(e)

    if (db is None):
        local_db.close()

def quit_series(series, db = None):
    if (db is None):
        local_db = connect()
    else:
        local_db = db
    cursor = local_db.cursor()

    volume = None
    m = re.search(r'^(.+) \((\d\d\d\d(-\d)?)\)$', series)
    if (m is not None):
        series = m[1]
        volume = m[2]

    if (volume is not None):
        cursor.execute('insert into quit_series (series, volume) values (?, ?)', (series, volume, ))
        local_db.commit()

    if (db is None):
        local_db.close()

def scan(comic):
    db = connect()
    cursor = db.cursor()

    folder_id = get_folder_id(comic, db = db)

    print(f"folder_id:{folder_id}")

    comic_data = get_comic_by_series(comic.series(), comic.issue(), comic.date())
    if (comic_data is None):
        comic_data = add_comic(comic, db = db)

    if (comic_data is None):
        raise Exception("couldn't add comic to database")
    #print(comic_data['id'])

    #try:
        #comic_id = cursor.execute('select id from comic_info where series=?', (id, )).fetchone()[0]

    #cursor.execute('delete from comic_label where comic_id = ?', (comic_id, ))
    #for label in labels:
    #    count = cursor.execute('select count(*) from label, comic_label where label.id=comic_label.label_id and label.name = ?', (label,)).fetchone()[0]
    #    cursor.execute('insert into comic_label (label_id,comic_id, ordering) select label.id, ?, ? from label where label.name = ?', (comic_id, count+1, label))

    db.close()

def set_labels(id, labels):
    local_db = connect()
    cursor = local_db.cursor()

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

