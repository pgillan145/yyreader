#!/usr/bin/env python3

from datetime import datetime, timedelta
import minorimpact.config
import os
import os.path
import re
import sqlite3
import sys
import re
#import urllib.parse
#import yyreader.comic

config = None

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

def get_comic_by_id(id):
    db = connect()
    cursor = db.cursor()
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

        if (current_page is None or current_page == 0):
            current_page = 1
        comic_data = { 'id':id, 'volume':volume, 'issue':issue, 'date':date, 'path': path, 'read':read, 'current_page':current_page, 'hash':hash }

    db.close()
    if (comic_data is None):
        raise Exception("invalid comic_info id: '{}'".format(id))

    return comic_data

# TODO: Turn these two "get_comics_by_*" into a single function, they do the same thing but with a slightly different SELECT.
def get_comics_by_date(year, month):
    db = connect()
    cursor = db.cursor()
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

        if (current_page is None or current_page == 0):
            current_page = 1

        comics.append({ 'id':id, 'volume':volume, 'issue':issue, 'date':date, 'read':read, 'current_page':current_page })
    db.close()
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

def get_comics_by_volume(volume):
    db = connect()
    cursor = db.cursor()
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

        if (current_page is None or current_page == 0):
            current_page = 1

        comics.append({ 'id':id, 'volume':volume, 'issue':issue, 'date':date, 'read':read, 'current_page':current_page })

    db.close()
    return sorted(comics, key=lambda x:(x['date'], x['volume']) )

def get_history():
    db = connect()
    cursor = db.cursor()
    comics = []
    cursor.execute('select ci.volume, ci.number, ci.date, ci.id, ci.read, ci.currentPage from comic_info ci, read_log where ci.id=read_log.comicInfoID order by read_log.mod_date desc')
    rows = cursor.fetchall()
    for row in rows:
        volume = row[0]
        issue = row[1]
        date = convert_yacreader_date(row[2])
        id = row[3]
        read = row[4]
        current_page = row[5]

        if (current_page is None or current_page == 0):
            current_page = 1

        comics.append({ 'id':id, 'volume':volume, 'issue':issue, 'date':date, 'read':read, 'current_page':current_page })

    db.close()
    return comics

def get_months(year):
    year = int(year)
    db = connect()
    cursor = db.cursor()
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
    db.close()
    return sorted(months, key=lambda x:x)

def get_nextdate(year, month):
    year = int(year)
    month = int(month)
    next_year = None
    next_month = None
    db = connect()
    cursor = db.cursor()
    months = get_months(year)
    if (month == months[len(months)-1]):
        years = get_years()
        for i in range(0, len(years)):
            if (years[i] == year and i < len(years)):
                next_year = years[i+1]
                break
        if (next_year is not None):
            months = get_months(next_year)
            next_month = months[0]
    else:
        next_year = year
        next_month = month + 1
    db.close()
    return (next_year, next_month)

def get_prevdate(year, month):
    year = int(year)
    month = int(month)
    prev_year = None
    prev_month = None
    db = connect()
    cursor = db.cursor()
    months = get_months(year)
    if (month == months[0]):
        years = get_years()
        for i in range(0, len(years)):
            if (years[i] == year and i > 0):
                prev_year = years[i-1]
                break
            
        if (prev_year is not None):
            months = get_months(prev_year)
            prev_month = months[len(months)-1]
    else:
        prev_year = year
        prev_month = month - 1

    db.close()
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
    cursor.execute('update comic_info set hasBeenOpened = TRUE, currentPage = ? where comic_info.id = ?', (page, id))
    db.commit()
    cursor.execute('select id, start_date, end_date from read_log where comicInfoId = ? order by id desc limit 1', (id,))
    rows = cursor.fetchall()
    if (len(rows) == 0 or (rows[0][2] is not None and datetime.fromisoformat(rows[0][2]) < (datetime.now() - timedelta(hours = 1)))): 
        if (page > 1):
            cursor.execute('insert into read_log (start_date, currentPage, comicInfoId) values (DATETIME("now","localtime"), ?, ?)', (page, id))
    else:
        cursor.execute('update read_log set currentPage = ?, mod_date = DATETIME("now","localtime") where id = ?', (page, rows[0][0]))
    db.commit()

    if (page_count is not None and page >= page_count):
        cursor.execute('update comic_info set read = TRUE where comic_info.id = ?', (id, ))
        cursor.execute('update read_log set end_date = DATETIME("now","localtime"), mod_date = DATETIME("now","localtime") where end_date is NULL and comicInfoID = ?', (id,))
        db.commit()
    db.close()

