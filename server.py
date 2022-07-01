#!/usr/bin/env python3

from datetime import datetime,timedelta
import http.server
import minorimpact.config
import os
import re
import socketserver
import sqlite3
import urllib.parse
import yyreader.comic
import yyreader.yacreader

comic_cache = {}

config = minorimpact.config.getConfig(script_name = 'yyreader')
comic_dir = config['default']['comic_dir']
comic_dir = re.sub(r'/$', '', comic_dir)

PORT = int(config['server']['port'])

def main():
    class ComicHTTPRequestHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            if (self.path == '/'):
                output = "<!DOCTYPE HTML>\n<html><body>\n"
                output = output + "<a href='/bydate'>By Date</a><br />"
                output = output + "<a href='/bytitle'>By Title</a><br />"
                output = output + "</body></html>\n"
                self.send_header('Content-type', 'text/html')
                self.end_headers()
                self.wfile.write(output.encode('utf-8'))

            elif (re.search('favicon.ico', self.path)):
                self.send_header('Content-type', 'image/jpeg')
                self.end_headers()
                with open('./favicon.ico', 'rb') as f:
                    self.wfile.write(f.read())

            elif (re.search(r'^/read/(\d+)/?$', self.path.lower())):
                m = re.search(r'^/read/(\d+)/?$', self.path.lower())
                id = m.group(1)
                current_page = 1
                comic = yyreader.yacreader.get_comic_by_id(id)
                if ('current_page' in comic and comic['current_page'] is not None):
                    current_page = comic['current_page']

                output = "<!DOCTYPE HTML>\n<html><head><meta http-equiv='refresh' content='0; url=/read/{}/{}' /></head></html>\n".format(id, current_page)
                self.send_header('Content-type', 'text/html')
                self.end_headers()
                self.wfile.write(output.encode('utf-8'))

            # /read/8289/1
            elif (re.search(r'^/read/(\d+)/(\d+)/?$', self.path.lower())):
                m = re.search(r'^/read/(\d+)/(\d+)/?$', self.path.lower())
                id = m.group(1)
                page = int(m.group(2))

                comic = yyreader.yacreader.get_comic_by_id(id)

                if (id in comic_cache):
                    c = comic_cache[id]['comic']
                else:
                    c = yyreader.comic.comic(comic_dir + '/' + comic['path'])
                    comic_cache[id] = {}
                    comic_cache[id]['comic'] = c
                    comic_cache[id]['date'] = datetime.now()

                if (page > c.page_count()):
                    page = c.page_count()

                output = "<!DOCTYPE HTML>\n<html><body>\n"
                output = output + "<table>"
                output = output + "<tr><td><a href=/bydate/{}>{}</a></td></tr>".format(comic['date'].strftime('%Y/%m'), comic['date'].strftime('%Y/%m'))
                output = output + "<tr><td>"
                if (page > 1):
                    output = output + "<a href=/read/{}/{}>Previous Page</a>".format(id, (page-1))
                output = output + "</td>"
                output = output + "<td><a href='/bytitle/{}'>{}</a> #{} ({} of {})</td>".format(urllib.parse.quote(comic['title']), comic['title'], comic['issue'], page, c.page_count())
                output = output + "<td>"
                if (page < c.page_count()):
                    output = output + "<a href=/read/{}/{}>Next Page</a>".format(id, (page+1))
                output = output + "</td></tr>\n"
                output = output + "<tr><td colspan = 3><img src='/page/{}/{}' height='750'></td></tr>\n".format(id, page)
                output = output + "<tr><td>"
                if (page > 1):
                    output = output + "<a href=/read/{}/{}>Previous Page</a>".format(id, (page-1))
                output = output + "</td>"
                output = output + "<td>" + c.page_file(page) + "</td>\n"
                output = output + "<td>"
                if (page < c.page_count()):
                    output = output + "<a href=/read/{}/{}>Next Page</a>".format(id, (page+1))
                output = output + "</td></tr>\n"
                output = output + "</table>\n"
                output = output + "</body></html>\n"

                self.send_header('Content-type', 'text/html')
                self.end_headers()
                self.wfile.write(output.encode('utf-8'))
                yyreader.yacreader.update_read_log(id, page, page_count = c.page_count())

            elif (re.search(r'^/page/(\d+)/(\d+)?$', self.path.lower())):
                m = re.search(r'^/page/(\d+)/(\d+)/?$', self.path.lower())
                id = m.group(1)
                page = int(m.group(2))
                if (id in comic_cache):
                    c = comic_cache[id]['comic']
                else:
                    comic = yyreader.yacreader.get_comic_by_id(id)
                    c = yyreader.comic.comic('/Volumes/Media/Comics/' + comic['path'])
                    comic_cache[id] = {}
                    comic_cache[id]['comic'] = c
                    comic_cache[id]['date'] = datetime.now()

                self.send_header('Content-type', 'image/jpeg')
                self.end_headers()
                self.wfile.write(c.page(page))

            # /bydate/1994/12
            elif (re.search(r'^/bydate/(\d\d\d\d)/(\d\d)/?$', self.path.lower())):
                m = re.search(r'^/bydate/(\d\d\d\d)/(\d\d)/?$', self.path.lower())
                year = m.group(1)
                month = m.group(2)
                output = "<!DOCTYPE HTML>\n<html><body>\n"
                output = output + "<a href='/bydate/{}'>&lt;-- {}</a><br />\n".format(year, year)
                output = output + "<table>\n"
                for comic in yyreader.yacreader.get_comics_by_date(year, month):
                    output = output + "<tr>\n  <td>"
                    if (comic['read'] == 1):
                        output = output + "DONE"
                    elif (comic['current_page'] > 1):
                        output = output + "*"
                    output = output + "</td>\n  <td><a href='/read/{}'>({}) {} #{}</a></td>\n".format(comic['id'], comic['date'].strftime('%Y/%m/%d'), comic['title'], comic['issue'])
                    output = output + "</tr>\n"
                output = output + "</table>\n"
                output = output + "</body></html>\n"
                self.send_header('Content-type', 'text/html')
                self.end_headers()
                self.wfile.write(output.encode('utf-8'))

            # /bydate/1994
            elif (re.search('^/bydate/([0-9][0-9][0-9][0-9])/?$', self.path.lower())):
                m = re.search('^/bydate/([0-9][0-9][0-9][0-9])/?$', self.path.lower())
                year = m.group(1)
                output = "<!DOCTYPE HTML>\n<html><body>\n"
                output = output + "<a href='/bydate'>&lt;--Back</a><br />"
                for month in yyreader.yacreader.get_months(year):
                    output = output + "<a href='/bydate/{}/{}'>{}/{}</a><br />\n".format(year, month, year, month)
                output = output + "</body></html>\n"
                self.send_header('Content-type', 'text/html')
                self.end_headers()
                self.wfile.write(output.encode('utf-8'))

            # /bydate
            elif (re.search(r'/bydate/?$', self.path.lower())):
                output = "<!DOCTYPE HTML>\n<html><body>\n"
                output = output + "<a href='/'>&lt;-- Back</a><br />\n"
                output = output + "<table>\n"
                for year in yyreader.yacreader.get_years():
                    output = output + "<tr>\n  <td>"
                    output = output + "</td>  <td><a href='/bydate/{}'>{}</a></td>\n".format(year, year)
                    output = output + "</tr>\n"
                output = output + "</table>\n"
                output = output + "</body></html>\n"
                self.send_header('Content-type', 'text/html')
                self.end_headers()
                self.wfile.write(output.encode('utf-8'))

            # /bytitle/ALF (1998)
            elif (re.search(r'^/bytitle/([^/]+)/?$', self.path.lower())):
                m = re.search(r'^/bytitle/([^/ ]+)/?$', self.path)
                title = urllib.parse.unquote(m.group(1))
                output = "<!DOCTYPE HTML>\n<html><body>\n"
                output = output + "<a href='/bytitle'>&lt;-- Back</a><br />\n"
                output = output + "<table>\n"
                for comic in yyreader.yacreader.get_comics_by_title(title):
                    output = output + "<tr>\n  <td>"
                    if (comic['read'] == 1):
                        output = output + "DONE"
                    elif (comic['current_page'] > 1):
                        output = output + "*"
                    output = output + "  </td>\n  <td>{}</td>\n  <td><a href='/read/{}'>#{}</a></td>\n  <td><a href='/bydate/{}/{}'>{}</a></td>\n".format(comic['title'], comic['id'], comic['issue'], comic['date'].year, comic['date'].strftime('%m'), comic['date'].strftime('%Y/%m/%d'))
                    output = output + "</tr>\n"
                output = output + "</table>\n"
                output = output + "</body></html>\n"
                self.send_header('Content-type', 'text/html')
                self.end_headers()
                self.wfile.write(output.encode('utf-8'))

            # /bytitle
            elif (re.search(r'^/bytitle/?$', self.path.lower())):
                output = "<!DOCTYPE HTML>\n<html><body>\n"
                output = output + "<a href='/'>&lt;-- Back</a><br />\n"
                for title in yyreader.yacreader.get_titles():
                    output = output + "<a href='/bytitle/{}'>{}</a><br />\n".format(urllib.parse.quote(title), title)
                output = output + "</body></html>\n"
                self.send_header('Content-type', 'text/html')
                self.end_headers()
                self.wfile.write(output.encode('utf-8'))

            elif (self.path == '/test'):
                self.send_header('Content-type', 'image/jpeg')
                self.end_headers()
                c = yyreader.comic.comic('/Users/pgillan/dev/yyreader/test_data/test.cbz')
                self.wfile.write(c.page(1))
            else:
                self.send_header('Content-type', 'text/html')
                self.wfile.write("Hello".encode('utf-8'))

    #Handler = http.server.SimpleHTTPRequestHandler
    #Handler = ComicHTTPRequestHandler()

    yyreader.yacreader.connect()
    with socketserver.TCPServer(("", PORT), ComicHTTPRequestHandler) as httpd:
        print("serving at port ", PORT) 
        httpd.serve_forever()


if __name__ == '__main__':
    main()
