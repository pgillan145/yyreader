#!/usr/bin/env python3

import datetime
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
    
def init():
    db = connect()
    cursor = db.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS comic_info_arc (id INTEGER PRIMARY KEY, storyArc TEXT NOT NULL, arcNumber INTEGER, arcCount INTEGER, comicVineID TEXT, comicInfoId INTEGER NOT NULL, FOREIGN KEY(comicInfoId) REFERENCES comic_info(id))')
    cursor.execute('CREATE TABLE IF NOT EXISTS read_log (id INTEGER PRIMARY KEY, start_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP, currentPage INTEGER default 1, end_date TIMESTAMP, comicInfoId INTEGER NOT NULL, FOREIGN KEY(comicInfoId) REFERENCES comic_info(id))')
    db.commit()
    try:
        cursor.execute('CREATE UNIQUE INDEX comic_info_arc_idx on comic_info_arc(storyArc, comicInfoId)')
        db.commit()
    except Exception as e:
        if (str(e) != 'index comic_info_arc_idx already exists'):
            raise e
    db.close()

def convert_yacreader_date(yacreader_date):
    date = datetime.datetime.strptime(yacreader_date, '%d/%m/%Y')
    return date
    
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

def get_months(year):
    db = connect()
    cursor = db.cursor()
    months = []
    cursor.execute('select distinct(date) from comic_info')
    rows = cursor.fetchall()
    for row in rows:
        if (row[0] is None):
            continue
        date = convert_yacreader_date(row[0])
        if (date.year != int(year)):
            continue
        month = date.strftime('%m')
        if (month not in months):
            months.append(month)
    db.close()
    return sorted(months, key=lambda x:x)

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

def update_read_log(id, page, page_count = None):
    db = connect()
    cursor = db.cursor()
    cursor.execute('update comic_info set hasBeenOpened = TRUE, currentPage = ? where comic_info.id = ?', (page, id))
    db.commit()
    cursor.execute('select id, start_date, end_date from read_log where comicInfoId = ? order by id desc limit 1', (id,))
    rows = cursor.fetchall()
    if (len(rows) == 0 or (rows[0][2] is not None)): 
        #TODO: If end-date is within a couple of hours, don't make a new record
        cursor.execute('insert into read_log (start_date, currentPage, comicInfoId) values (DATETIME("now","localtime"), ?, ?)', (page, id))
    else:
        cursor.execute('update read_log set currentPage = ? where id = ?', (page, rows[0][0]))
    db.commit()

    if (page_count is not None and page == page_count):
        cursor.execute('update comic_info set read = TRUE where comic_info.id = ?', (id,))
        cursor.execute('update read_log set end_date = DATETIME("now","localtime") where end_date is NULL and comicInfoID = ?', (id,))
        db.commit()
    db.close()

