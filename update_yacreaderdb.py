#!/usr/bin/env python3

import argparse
import minorimpact.config
import os.path
import re
import sqlite3
import sys
import yyreader.comic

def main():
    parser = argparse.ArgumentParser(description="Scan comic directory")
    parser.add_argument('--dir', metavar = 'DIR',  help = "Scan DIR")
    parser.add_argument('-v', '--verbose', action='store_true')
    parser.add_argument('-y', '--yes', action='store_true')
    parser.add_argument('-1', '--once', help = "Just process a single entry, for testing.  Also enabled --verbose and --debug.", action='store_true')
    parser.add_argument('--debug', action='store_true')

    args = parser.parse_args()
    config = minorimpact.config.getConfig(script_name = 'yyreader')
    db = config['default']['db']
    if (os.path.exists(db) is None):
        raise Exception("{} does not exist".format(db))

    comicvine = True
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


    cur.execute('select comic.path, comic_info.volume, comic_info.number, comic_info.date, comic.id, comic_info.id, comic_info.comicVineID, comic_info.title, comic_info.storyArc from comic, comic_info where comic.comicInfoId=comic_info.id')
    rows = cur.fetchall()
    i = 0
    for row in rows:
        path = row[0]
        comic_info_id = row[5]

        if (re.search('^/ByDate', path) is not None):
            continue

        if (comicvine is True):
            #   comicVineID            date                   title 
            if (row[6] is not None and row[3] is not None and row[7] is not None):
                continue
        elif (row[3] is not None):
            continue

        if (args.debug): print("-----")
        if (args.debug): print("path: " + path)
        if (args.debug): print("date: " + str(row[3]))
        if (args.debug): print("comicInfoId: " + str(comic_info_id))
        if (args.debug): print("comicVineID: " + str(row[6]))

        c = yyreader.comic.comic(config['default']['comic_dir'] + path, args = args)
        if ('date' in c.parse_data):
            if (c.parse_data['date'] is not None):
                print("updating " + path)
                if (args.debug): print(c.parse_data)
                date = c.parse_data['date']
                volume = c.parse_data['title'] + ' (' + c.parse_data['start_year'] + ')'
                issue_name = None
                issue_id = None
                arcs = []
                arc_name = None
                publisher = None
                if (comicvine is True):
                    comicvine_data = yyreader.comicvine.search(c.parse_data, config['comicvine']['api_key'], cache_file = config['default']['cache_file'], args = args)
                    if (comicvine_data is None):
                        continue
                    if (args.debug): print(comicvine_data)
                    date = comicvine_data['date']
                    volume = comicvine_data['volume_name'] + ' (' + comicvine_data['start_year'] + ')'
                    issue_name = comicvine_data['issue_name']
                    issue_id = comicvine_data['issue_id']
                    publisher = comicvine_data['publisher']
                    details = yyreader.comicvine.get_issue_details(issue_id, config['comicvine']['api_key'], cache_file = config['default']['cache_file'], args = args)
                    if (details['story_arc_credits'] is not None):
                        for arc in details['story_arc_credits']:
                            #{'api_detail_url': 'https://comicvine.gamespot.com/api/story_arc/4045-60684/', 'id': 60684, 'name': 'Fallen Order', 'site_detail_url': 'https://comicvine.gamespot.com/fallen-order/4045-60684/'}
                            if (args.debug): print(arc)
                            arcs.append({'name': arc['name'], 'id': arc['id']})
                            if (arc_name is None): arc_name = arc['name']
                    # By setting these to '' in the database, rather than None (or NULL), we're indicating that we made the attempt to collect the data, and the canonical source returned
                    #   'nothing'.
                    if (issue_name is None): issue_name = ''
                    if (arc_name is None): arc_name = ''
                    if (publisher is None): publisher = ''

                i += 1
                m = re.search('^(?P<year>\d\d\d\d)-(?P<month>\d\d)-(?P<day>\d\d)$', date)
                dbdate = m.group('day') + '/' + m.group('month') + '/' + m.group('year')
                if (args.debug): print("update comic_info set edited = TRUE, date = {}, volume = {}, number = {}, title = {}, comicVineID = {}, storyArc = {}, publisher = {} where id = {}".format(dbdate, volume, c.parse_data['issue'], issue_name, issue_id, arc_name, publisher, comic_info_id))
                try:
                    cur.execute('update comic_info set edited = TRUE, date = ?, volume = ?, number = ?, title = ?, comicVineID = ?, storyArc = ?, publisher = ? where id = ?', (dbdate, volume, c.parse_data['issue'], issue_name, issue_id, arc_name, publisher, comic_info_id))
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
                        print(e)
                        break

                if (len(arcs) > 1):
                    break

        if (args.once is True):
            break

if __name__ == '__main__':
    main()

