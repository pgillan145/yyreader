#!/usr/bin/env python3

from datetime import datetime,timedelta
from flask import current_app, Flask, g, render_template, redirect, Response
import http.server
import minorimpact.config
import os
import re
import socketserver
import sqlite3
import urllib.parse
import yyreader.comic
import yyreader.yacreader

config = minorimpact.config.getConfig(script_name = 'yyreader')
app = Flask(__name__, template_folder='templates')
app.config.from_mapping(
        #EXPLAIN_TEMPLATE_LOADING=True,
        #SECRET_KEY='dev',
        #DATABASE=config['default']['db'],
    )

comic_cache = {}
comic_dir = config['default']['comic_dir']
comic_dir = re.sub(r'/$', '', comic_dir)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/bydate')
@app.route('/bydate/<int:year>')
@app.route('/bydate/<int:year>/<int:month>')
def bydate(year = None, month = None):
    items = []
    back = '/'
    if (year is None and month is None):
        for year in yyreader.yacreader.get_years():
            items.append({ 'url':'/bydate/{}'.format(year), 'text':'{}'.format(year) })
        return render_template('byyear.html', back = back, items = items)
    elif (year is not None and month is None):
        back = '/bydate'
        for month in yyreader.yacreader.get_months(year):
            items.append({ 'url':'/bydate/{}/{}'.format(year, month), 'text':'{}/{}'.format(year, month) })
        return render_template('bymonth.html', back = back, items = items)
    elif (year is not None and month is not None):
        if (month < 10): month = '0{}'.format(month)
        back = '/bydate/{}'.format(year)
        for comic in yyreader.yacreader.get_comics_by_date(year, month):
            status = ''
            if (comic['read'] == 1):
                status = "DONE"
            elif (comic['current_page'] > 1):
                status = '*'
            #items.append({ 'url':'/read/{}'.format(comic['id']), 'text':'({}) {} #{}'.format(comic['date'].strftime('%Y/%m/%d'), comic['volume'], comic['issue']) })
            items.append({ 'status': status, 'comic': comic, 'date':comic['date'].strftime('%Y/%m/%d') }) 
        return render_template('comics_bydate.html', back = back, items = items)

@app.route('/byvolume')
@app.route('/byvolume/<volume>')
def byvolume(volume = None):
    #yyreader.yacreader.connect()
    items = []
    back = '/'
    if (volume is None):
        for volume in yyreader.yacreader.get_volumes():
            items.append({ 'url':'/byvolume/{}'.format(urllib.parse.quote(volume)), 'text':volume } )
        return render_template('byvolume.html', back = back, items = items)
    else:
        back = '/byvolume'
        volume = urllib.parse.unquote(volume)
        for comic in yyreader.yacreader.get_comics_by_volume(volume):
            status = ''
            if (comic['read'] == 1):
                status = 'DONE'
            elif (comic['current_page'] > 1):
                status = '*'
            items.append({ 'status': status, 'comic': comic, 'date':comic['date'].strftime('%Y/%m/%d') }) 

        return render_template('comics.html', back = back, items = items)

@app.route('/read/<int:id>')
@app.route('/read/<int:id>/<int:page>')
def read(id, page = None):
    comic = yyreader.yacreader.get_comic_by_id(id)
    if (id in comic_cache):
        c = comic_cache[id]['comic']
    else:
        c = yyreader.comic.comic(comic_dir + '/' + comic['path'])
        comic_cache[id] = {}
        comic_cache[id]['comic'] = c
        comic_cache[id]['date'] = datetime.now()

    if (page is None):
        page = 1
        if ('current_page' in comic and comic['current_page'] is not None):
            page = int(comic['current_page'])
        if (page < 1): page = 1
        if (page > c.page_count()): page = c.page_count()
        return redirect('/read/{}/{}'.format(id, page))

    image_height = 1000

    (w, h) = c.page_size(page)
    image_width = int((w/h) * image_height)

    if (page < 1): page = 1
    if (page > c.page_count()): page = c.page_count()

    previous_page_url = None
    if (page > 1):
        previous_page_url = '/read/{}/{}'.format(id, (page-1))
    next_page_url = None
    if (page < c.page_count()):
        next_page_url = '/read/{}/{}'.format(id, (page+1))

    yyreader.yacreader.update_read_log(id, page, page_count = c.page_count())
    return render_template('read.html', page = page, comic = comic, img = { 'height': image_height, 'width': image_width , 'half_width': int(image_width/2) }, next_page_url = next_page_url, previous_page_url = previous_page_url, page_count = c.page_count(), back = '/bydate/{}'.format(comic['date'].strftime('%Y/%m')), data_dir = c.data_dir)

@app.route('/page/<int:id>/<int:page>')
def page(id, page):
    comic = yyreader.yacreader.get_comic_by_id(id)
    if (id in comic_cache):
        c = comic_cache[id]['comic']
    else:
        comic = yyreader.yacreader.get_comic_by_id(id)
        c = yyreader.comic.comic('/Volumes/Media/Comics/' + comic['path'])
        comic_cache[id] = {}
        comic_cache[id]['comic'] = c
        comic_cache[id]['date'] = datetime.now()

    if (page < 0): page = 1
    if (page > c.page_count()): page = c.page_count()

    return Response(c.page(page), mimetype = 'image/jpeg')

if __name__ == '__main__':
    app.run(port = config['server']['port'], host = '0.0.0.0', debug = True)
