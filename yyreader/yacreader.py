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
db = None
cursor = None

def connect():
    global config, db, cursor

    #if (db is not None and cursor is not None):
    #    return

    config = minorimpact.config.getConfig(script_name = 'yyreader')
    
    db_file = config['default']['db']
    if (os.path.exists(db_file) is None):
        raise Exception("{} does not exist".format(db_file))

    db = sqlite3.connect(db_file)
    cursor = db.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS comic_info_arc (id INTEGER PRIMARY KEY, storyArc TEXT NOT NULL, arcNumber INTEGER, arcCount INTEGER, comicVineID TEXT, comicInfoId INTEGER NOT NULL, FOREIGN KEY(comicInfoId) REFERENCES comic_info(id))')
    db.commit()
    try:
        cursor.execute('CREATE UNIQUE INDEX comic_info_arc_idx on comic_info_arc(storyArc, comicInfoId)')
        db.commit()
    except Exception as e:
        if (str(e) != 'index comic_info_arc_idx already exists'):
            raise e

    return db

def disconnect():
    global cursor, db

    if db is not None:
        db.close()

    db = None
    cursor = None

def convert_yacreader_date(yacreader_date):
    date = datetime.datetime.strptime(yacreader_date, '%d/%m/%Y')
    return date
    
def get_comic_by_id(id):
    connect()
    cursor.execute('select comic_info.volume, comic_info.number, comic_info.date, comic_info.id, comic.path, comic_info.read, comic_info.currentPage from comic_info, comic where comic.comicInfoId=comic_info.id and comic_info.id = ?', (id,))
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

        if (re.search(r'^/ByDate', path)):
            continue

        if (current_page is None or current_page == 0):
            current_page = 1
        comic_data = { 'id':id, 'volume':volume, 'issue':issue, 'date':date, 'path': path, 'read':read, 'current_page':current_page }

    disconnect()
    if (comic_data is None):
        raise Exception("invalid comic_info id: '{}'".format(id))

    return comic_data

# TODO: Turn these two "get_comics_by_*" into a single function, they do the same thing but with a slightly different SELECT.
def get_comics_by_date(year, month):
    connect()
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
    disconnect()
    return sorted(comics, key=lambda x:(x['date'], x['volume']) )

def get_comics_by_volume(volume):
    connect()
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

    disconnect()
    return sorted(comics, key=lambda x:(x['date'], x['volume']) )

def get_months(year):
    connect()
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
    disconnect()
    return sorted(months, key=lambda x:x)

def get_volumes():
    connect()
    volumes = []
    cursor.execute('select distinct(volume) from comic_info')
    rows = cursor.fetchall()
    for row in rows:
        if (row[0] is None):
            continue
        volumes.append(row[0])
    disconnect()
    return sorted(volumes, key=lambda x: x)

def get_years():
    connect()
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
    disconnect()
    return sorted(years, key=lambda x: x)

def update_read_log(id, page, page_count = None):
    connect()
    cursor.execute('update comic_info set hasBeenOpened = TRUE, currentPage = ? where comic_info.id = ?', (page, id))
    if (page_count is not None and page == page_count):
        cursor.execute('update comic_info set read = TRUE where comic_info.id = ?', (id,))

    db.commit()
    
    

