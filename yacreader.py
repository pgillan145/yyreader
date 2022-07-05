#!/usr/bin/env python3

import argparse
import datetime
import minorimpact.config
import os.path
import re
import sqlite3
import sys
import yyreader.comic
import yyreader.yacreader

def main():
    parser = argparse.ArgumentParser(description="Scan comic directory")
    parser.add_argument('-v', '--verbose', action='store_true')
    parser.add_argument('-y', '--yes', action='store_true')
    parser.add_argument('-1', '--once', help = "Just process a single entry, for testing.  Also enables --verbose and --debug.", action='store_true')
    parser.add_argument('-s', '--scan', action='store_true', help = "Analyze the database, looking for anomalies.")
    parser.add_argument('-u', '--update', action='store_true', help = "Update item metadata.")
    parser.add_argument('--comicvine',  help = "Pull external comicvine data when running --update,  otherwise just update with can be parsed from the filename.", action='store_true')
    parser.add_argument('--volume', metavar = 'VOL', help = "Only update comics in VOL.")
    parser.add_argument('--debug', action='store_true')

    args = parser.parse_args()
    config = minorimpact.config.getConfig(script_name = 'yyreader')
    db = config['default']['db']
    if (os.path.exists(db) is None):
        raise Exception("{} does not exist".format(db))

    
    if (args.once is True):
        args.verbose = True
        args.debug = True

    con = sqlite3.connect(db)
    cur = con.cursor()
    cur.execute('CREATE TABLE IF NOT EXISTS comic_info_arc (id INTEGER PRIMARY KEY, storyArc TEXT NOT NULL, arcNumber INTEGER, arcCount INTEGER, comicVineID TEXT, comicInfoId INTEGER NOT NULL, FOREIGN KEY(comicInfoId) REFERENCES comic_info(id))')
    con.commit()
    try:
        cur.execute('CREATE UNIQUE INDEX comic_info_arc_idx on comic_info_arc(storyArc, comicInfoId)')
        con.commit()
    except Exception as e:
        if (str(e) != 'index comic_info_arc_idx already exists'):
            print(e)
            sys.exit(1)


    cur.execute('select comic.path, comic_info.volume, comic_info.number, comic_info.date, comic.id, comic_info.id, comic_info.comicVineID, comic_info.title, comic_info.storyArc, comic_info.writer, comic_info.penciller from comic, comic_info where comic.comicInfoId=comic_info.id')
    rows = cur.fetchall()
    i = 0
    for row in rows:
        path = row[0]
        volume = row[1]
        date = row[3]
        comic_info_id = row[5]
        comicvine_id = row[6]
        title = row[7]
        writer = row[9]
        penciller = row[10]

        if (args.scan):
            c = yyreader.comic.comic(config['default']['comic_dir'] + path, args = args)
            if ('date' in c.parse_data and date is not None):
                dbdate = yyreader.yacreader.convert_yacreader_date(date)
                filedate = datetime.datetime.strptime(c.parse_data['date'], '%Y-%m-%d')
                if (filedate != dbdate):
                    print("{}: dbdate '{}' doesn't match file date '{}'".format(config['default']['comic_dir'] + path, dbdate.strftime('%Y-%m-%d'), filedate.strftime('%Y-%m-%d')))
                    if (comicvine_id is not None):
                        print("comicvine url: https://comicvine.gamespot.com/unknown/4000-{}".format(comicvine_id))
        elif (args.update):
            if (re.search('^/ByDate', path) is not None):
                continue

            if (args.comicvine is True and (comicvine_id is not None and date is not None and title is not None and writer is not None and penciller is not None)):
                continue
            elif (args.comicvine is False and (date is not None)):
                continue

            if (args.debug): print("-----")
            if (args.debug): print("path: " + path)
            if (args.debug): print("date: " + str(date))
            if (args.debug): print("comicInfoId: " + str(comic_info_id))
            if (args.debug): print("comicVineID: " + str(row[6]))

            c = yyreader.comic.comic(config['default']['comic_dir'] + path, args = args)
            if ('date' in c.parse_data):
                if (c.parse_data['date'] is not None):
                    if (args.volume is not None and volume is not None):
                        if (re.search(args.volume, volume) is None):
                            continue
                    print("updating " + path)
                    if (args.debug): print(c.parse_data)
                    arcs = []
                    arc_name = None
                    new_date = c.parse_data['date']
                    volume = c.parse_data['volume'] + ' (' + c.parse_data['start_year'] + ')'
                    issue_name = None
                    issue_id = None
                    penciler = None
                    publisher = None
                    writer = None
                    if (args.comicvine is True):
                        comicvine_data = yyreader.comicvine.search(c.parse_data, config['comicvine']['api_key'], cache_file = config['default']['cache_file'], args = args)
                        if (comicvine_data is None):
                            continue
                        if (args.debug): print("comicvine_data: {}".format(comicvine_data))
                        new_date = comicvine_data['date']
                        volume = comicvine_data['volume_name'] + ' (' + comicvine_data['start_year'] + ')'
                        issue_name = comicvine_data['issue_name']
                        issue_id = comicvine_data['issue_id']
                        publisher = comicvine_data['publisher']
                        details = yyreader.comicvine.get_issue_details(issue_id, config['comicvine']['api_key'], cache_file = config['default']['cache_file'], args = args)
                        if (details['story_arc_credits'] is not None):
                            for arc in details['story_arc_credits']:
                                if (args.debug): print(arc)
                                arcs.append({'name': arc['name'], 'id': arc['id']})
                                if (arc_name is None): arc_name = arc['name']
                        if (details['person_credits'] is not None):
                            #{'api_detail_url': 'https://comicvine.gamespot.com/api/person/4040-40982/', 'id': 40982, 'name': 'Joe Kelly', 'site_detail_url': 'https://comicvine.gamespot.com/joe-kelly/4040-40982/', 'role': 'writer'}
                            for person in details['person_credits']:
                                if (person['role'] == 'writer'):
                                    if (writer is None): 
                                        writer = person['name']
                                    else:
                                        writer = writer + '\n' + person['name']
                                elif (person['role'] == 'penciler'):
                                    if (penciler is None): 
                                        penciler = person['name']
                                    else:
                                        penciler = penciler + '\n' + person['name']

                        # By setting these to '' in the database, rather than None (or NULL), we're indicating that we made the attempt to collect the data, and the canonical source returned
                        #   'nothing'.
                        if (issue_name is None): issue_name = ''
                        if (arc_name is None): arc_name = ''
                        if (penciler is None): penciler = ''
                        if (publisher is None): publisher = ''
                        if (writer is None): writer = ''

                    i += 1
                    m = re.search('^(?P<year>\d\d\d\d)-(?P<month>\d\d)-(?P<day>\d\d)$', new_date)
                    dbdate = m.group('day') + '/' + m.group('month') + '/' + m.group('year')
                    if (args.debug): print("update comic_info set edited = TRUE, date = {}, volume = {}, number = {}, title = {}, comicVineID = {}, storyArc = {}, publisher = {}, writer = {}, penciller = {} where id = {}".format(dbdate, volume, c.parse_data['issue'], issue_name, issue_id, arc_name, publisher, writer, penciler, comic_info_id))
                    try:
                        cur.execute('update comic_info set edited = TRUE, date = ?, volume = ?, number = ?, title = ?, comicVineID = ?, storyArc = ?, publisher = ?, writer = ?, penciller = ? where id = ?', (dbdate, volume, c.parse_data['issue'], issue_name, issue_id, arc_name, publisher, writer, penciler, comic_info_id))
                        con.commit()
                        pass
                    except Exception as e:
                        print(e)
                        break

                    for arc in arcs:
                        if (args.debug): print("insert into comic_info_arc (storyArc, comicVineID, comicInfoId) values ({}, {}, {})".format(arc['name'], arc['id'], comic_info_id))
                        try:
                            cur.execute('insert into comic_info_arc (storyArc, comicVineID, comicInfoId) values (?, ?, ?)', (arc['name'], arc['id'], comic_info_id))
                            con.commit()
                            pass
                        except Exception as e:
                            if (str(e) != 'UNIQUE constraint failed: comic_info_arc.storyArc, comic_info_arc.comicInfoId'):
                                print(e)
                                break

        if (args.once is True):
            break

if __name__ == '__main__':
    main()

