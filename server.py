#!/usr/bin/env python3

from datetime import datetime,timedelta
from flask import current_app, Flask, g, render_template, redirect, request, Response
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

debug = False
if ('debug' in config['server']):
    config_debug = eval(config['server']['debug'])
    if (config_debug is True):
        debug = True

def clean_cache():
    ids = [key for key in comic_cache]
    for id in ids:
        if (('date' in comic_cache[id] and datetime.now() > comic_cache[id]['date'] + timedelta(hours=2)) or ('date' not in comic_cache[id])):
           del comic_cache[id]
#app.teardown_request(clean_cache)

def complementaryColor(my_hex):
    """Returns complementary RGB color

    Example:
    >>>complementaryColor('FFFFFF')
    '000000'
    """
    if my_hex[0] == '#':
        my_hex = my_hex[1:]
    rgb = (my_hex[0:2], my_hex[2:4], my_hex[4:6])
    comp = ['%02X' % (255 - int(a, 16)) for a in rgb]
    return ''.join(comp)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/bydate')
@app.route('/bydate/<int:year>')
@app.route('/bydate/<int:year>/<int:month>')
def bydate(year = None, month = None):
    items = []
    back = '/'
    clean_cache()
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
        for yacreader in yyreader.yacreader.get_comics_by_date(year, month):
            status = ''
            if (yacreader['read'] == 1):
                status = "DONE"
            elif (yacreader['current_page'] > 1):
                status = '*'
            items.append({ 'status': status, 'yacreader': yacreader, 'date':yacreader['date'].strftime('%m/%d/%Y'), 'short_volume':yacreader['volume'][0:25], 'datelink':'/bydate/{}'.format(yacreader['date'].strftime('%Y/%m')) }) 
        response = Response(render_template('comics_bydate.html', back = back, items = items))
        response.set_cookie('traversal_method', 'bydate', max_age=60*60*24*365)
        response.set_cookie('current_time', '{}/{}'.format(year, month), max_age=60*60*24*365)
        return response

@app.route('/byvolume')
@app.route('/byvolume/<volume>')
def byvolume(volume = None):
    items = []
    back = '/'
    clean_cache()
    if (volume is None):
        for volume in yyreader.yacreader.get_volumes():
            items.append({ 'url':'/byvolume/{}'.format(urllib.parse.quote(volume)), 'text':volume , 'short_text': volume[0:25] })
        return render_template('byvolume.html', back = back, items = items)
    else:
        back = '/byvolume'
        if (request.cookies.get('current_time')):
            back = '/bydate/' + request.cookies.get('current_time')
        volume = urllib.parse.unquote(volume)
        for yacreader in yyreader.yacreader.get_comics_by_volume(volume):
            status = ''
            if (yacreader['read'] == 1):
                status = 'DONE'
            elif (yacreader['current_page'] > 1):
                status = '*'
            items.append({ 'status': status, 'yacreader': yacreader, 'date':yacreader['date'].strftime('%m/%d/%Y'), 'short_volume':yacreader['volume'][0:25], 'datelink':'/bydate/{}#{}'.format(yacreader['date'].strftime('%Y/%m'), yacreader['id']) }) 

        response = Response(render_template('comics.html', back = back, items = items))
        response.set_cookie('traversal_method', 'byvolume', max_age=60*60*24*365)
        return response

@app.route('/cover/<int:id>')
def cover(id):
    cover_file = None
    if (id in comic_cache):
        cover_file = comic_cache[id]['cover']
    else:
        yacreader = yyreader.yacreader.get_comic_by_id(id)
        comic_cache[id] = {}
        comic_cache[id]['yacreader'] = yacreader
        comic_cache[id]['comic'] = yyreader.comic.comic(comic_dir + '/' + yacreader['path'])
        cover_file = yyreader.yacreader.get_cover_file(id, hash = yacreader['hash'])
        comic_cache[id]['cover'] = cover_file
        comic_cache[id]['date'] = datetime.now()
    
    cover_data = None
    with (open(cover_file, 'rb') as f):
        cover_data = f.read()

    if (cover_data is not None):
        return Response(cover_data, mimetype = 'image/jpeg')

@app.route('/read/<int:id>')
@app.route('/read/<int:id>/<int:page>')
def read(id, page = None):
    yacreader = None
    if (id in comic_cache):
        yacreader = comic_cache[id]['yacreader']
        c = comic_cache[id]['comic']
    else:
        yacreader = yyreader.yacreader.get_comic_by_id(id)
        c = yyreader.comic.comic(comic_dir + '/' + yacreader['path'])
        comic_cache[id] = {}
        comic_cache[id]['yacreader'] = yacreader
        comic_cache[id]['cover'] = yyreader.yacreader.get_cover_file(id, hash = yacreader['hash'])
        comic_cache[id]['comic'] = c
        comic_cache[id]['date'] = datetime.now()

    if (page is None):
        page = 1
        if ('current_page' in yacreader and yacreader['current_page'] is not None):
            page = int(yacreader['current_page'])
        if (page < 1): page = 1
        if (page > c.page_count()): page = c.page_count()
        return redirect('/read/{}/{}'.format(id, page))

    if (page < 1): page = 1
    if (page > c.page_count()): page = c.page_count()

    image_height = 1000

    color = c.page_color(page)
    text_color = '#' + complementaryColor(color)
    (w, h) = c.page_size(page)
    image_width = int((w/h) * image_height)

    back = '/bydate/{}#{}'.format(yacreader['date'].strftime('%Y/%m'), id)
    if (request.cookies.get('traversal_method') == 'bydate' and request.cookies.get('current_time')):
        back = '/bydate/{}#{}'.format(request.cookies.get('current_time'), id)
    elif (request.cookies.get('traversal_method') == 'byvolume'):
        back = '/byvolume/{}#{}'.format(urllib.parse.quote(yacreader['volume']), id)

    previous_page_url = back
    if (page > 1):
        previous_page_url = '/read/{}/{}'.format(id, (page-1))

    next_page_url = '/bydate/{}#{}'.format(request.cookies.get('current_time'), id)
    if (page < c.page_count()):
        next_page_url = '/read/{}/{}'.format(id, (page+1))
    elif (page == c.page_count()):
        if (request.cookies.get('traversal_method') == 'byvolume'):
            issues = yyreader.yacreader.get_comics_by_volume(yacreader['volume'])
            i = 0
            while (i < len(issues)):
                if (issues[i]['issue'] == yacreader['issue'] and i < (len(issues) - 1)):
                    next_page_url = '/read/{}'.format(issues[i+1]['id'])
                    break
                i = i + 1

    yyreader.yacreader.update_read_log(id, page, page_count = c.page_count())
    return render_template('read.html', page = page, yacreader = yacreader, img = { 'height': image_height, 'width': image_width , 'half_width': int(image_width/2) }, next_page_url = next_page_url, previous_page_url = previous_page_url, page_count = c.page_count(), back = back, data_dir = c.data_dir, datelink='/bydate/{}#{}'.format(yacreader['date'].strftime("%Y/%m"), id), background_color = color, text_color = text_color)

@app.route('/page/<int:id>/<int:page>')
def page(id, page):
    yacreader = None
    if (id in comic_cache):
        yacreader = comic_cache[id]['yacreader']
        c = comic_cache[id]['comic']
    else:
        yacreader = yyreader.yacreader.get_comic_by_id(id)
        c = yyreader.comic.comic('/Volumes/Media/Comics/' + yacreader['path'])
        comic_cache[id] = {}
        comic_cache[id]['yacreader'] = yacreader
        comic_cache[id]['comic'] = c
        comic_cache[id]['cover'] = yyreader.yacreader.get_cover_file(id, hash = yacreader['hash'])
        comic_cache[id]['date'] = datetime.now()

    if (page < 0): page = 1
    if (page > c.page_count()): page = c.page_count()

    return Response(c.page(page), mimetype = 'image/jpeg')

if __name__ == '__main__':
    yyreader.yacreader.init()
    app.run(port = config['server']['port'], host = '0.0.0.0', debug = debug)
