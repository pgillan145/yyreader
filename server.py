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
    if (request.cookies.get('current_time')):
        return redirect('/bydate/{}'.format(request.cookies.get('current_time')))
    return redirect('/bydate')

@app.route('/bydate')
@app.route('/bydate/<int:year>')
@app.route('/bydate/<int:year>/<int:month>')
def bydate(year = None, month = None):
    items = []
    up = None
    back = None
    if (request.cookies.get('current_time')):
        back = {'url':'/bydate/{}'.format(request.cookies.get('current_time')), 'text':'/'.join(list(reversed(request.cookies.get('current_time').split('/')))) }
    forth = None
    clean_cache()
    if (year is None and month is None):
        for year in yyreader.yacreader.get_years():
            items.append({ 'url':'/bydate/{}'.format(year), 'text':'{}'.format(year) })
        return render_template('byyear.html', back = back, items = items, nav = { 'back':back, 'forth':forth, 'up': up })
    elif (year is not None and month is None):
        years = yyreader.yacreader.get_years()
        i = 0
        while i < len(years):
            if (years[i] == year):
                if (i > 0): back = { 'url': '/bydate/{}'.format(years[i-1]), 'text':'{}'.format(years[i-1]) } 
                if (i < len(years)-1): forth = { 'url': '/bydate/{}'.format(years[i+1]), 'text':'{}'.format(years[i+1]) } 
                break
            i = i + 1
        up = { 'url':'/bydate', 'text':'ByDate' }
        for month in yyreader.yacreader.get_months(year):
            items.append({ 'url':'/bydate/{}/{}'.format(year, month), 'text':'{}/{}'.format(month, year) })
        return render_template('bymonth.html', back = back, items = items, nav = { 'back':back, 'forth':forth, 'up': up })
    elif (year is not None and month is not None):
        up = { 'url':'/bydate/{}'.format(year), 'text':str(year) }
        if (month > 1):
            back = { 'url':'/bydate/{}/{}'.format(year, month-1), 'text':'{}/{}'.format(month-1, year) }
        elif (month == 1):
            #TODO: Figure out what the previous month and year actually are
            back = { 'url':'/bydate/{}/{}'.format(year-1, 12), 'text':'{}/{}'.format(12, year-1) }

        if (month < 12):
            forth = { 'url':'/bydate/{}/{}'.format(year, month+1), 'text':'{}/{}'.format(month+1, year) }
        elif (month == 12):
            #TODO: Figure out what the next month and year actually are
            forth = { 'url':'/bydate/{}/{}'.format(year+1, 1), 'text':'{}/{}'.format(1, year+1) }
            
        for yacreader in yyreader.yacreader.get_comics_by_date(year, month):
            status = ''
            if (yacreader['read'] == 1):
                status = "DONE"
            elif (yacreader['current_page'] > 1):
                status = '*'
            items.append({ 'status': status, 'yacreader': yacreader, 'date':yacreader['date'].strftime('%m/%d/%Y'), 'short_volume':yacreader['volume'][0:25], 'datelink':'/bydate/{}'.format(yacreader['date'].strftime('%Y/%m')) }) 
        response = Response(render_template('comics.html', items = items, nav = {'back':back, 'forth':forth, 'up':up, 'view':{'url':'/byvolume', 'text':'Volumes' } }))
        response.set_cookie('traversal_method', 'bydate', max_age=60*60*24*365)
        response.set_cookie('current_time', '{}/{}'.format(year, month), max_age=60*60*24*365)
        response.delete_cookie('up')
        return response

@app.route('/byvolume')
@app.route('/byvolume/<volume>')
def byvolume(volume = None):
    items = []
    back = { 'url':'/bydate/{}'.format(request.cookies.get('current_time')), 'text':'/'.join(list(reversed(request.cookies.get('current_time').split('/')))) }
    up = None
    forth = None
    view = {'url':'/bydate', 'text':'Dates' }
    clean_cache()
    if (volume is None):
        last = None
        index = []
        for volume in yyreader.yacreader.get_volumes():
            if (volume[0:1] != last):
                last = volume[0:1]
                items.append({ 'name':last })
                index.append({ 'url':'#{}'.format(last), 'text':last })

            items.append({ 'url':'/byvolume/{}'.format(urllib.parse.quote(volume)), 'text':volume, 'name':None })
        return render_template('byvolume.html', items = items, nav = {'back':back, 'forth':forth, 'up':up, 'view':view }, index = index)
    else:
        up = { 'url':'/byvolume', 'text':'By Volume' }
        volume = urllib.parse.unquote(volume)
        for yacreader in yyreader.yacreader.get_comics_by_volume(volume):
            status = ''
            if (yacreader['read'] == 1):
                status = 'DONE'
            elif (yacreader['current_page'] > 1):
                status = '*'
            items.append({ 'status': status, 'yacreader': yacreader, 'date':yacreader['date'].strftime('%m/%d/%Y'), 'datelink':'/bydate/{}#{}'.format(yacreader['date'].strftime('%Y/%m'), yacreader['id']) }) 

        response = Response(render_template('comics.html', back = back, items = items, nav = {'back':back, 'forth':forth, 'up':up, 'view':view} ))
        response.set_cookie('traversal_method', 'byvolume', max_age=60*60*24*365)
        response.delete_cookie('up')
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

@app.route('/history')
def history():
    back = None
    if (request.cookies.get('current_time')):
        back = { 'url':'/bydate/{}#{}'.format(request.cookies.get('current_time'), id), 'text':'/'.join(list(reversed(request.cookies.get('current_time').split('/')))) }
    up = { 'url':'/', 'text':'Index' }
    forth = None
    items = []
    for yacreader in yyreader.yacreader.get_history():
        status = ''
        if (yacreader['read'] == 1):
            status = "DONE"
        elif (yacreader['current_page'] > 1):
            status = '*'
        items.append({ 'status': status, 'yacreader': yacreader, 'date':yacreader['date'].strftime('%m/%d/%Y'), 'datelink':'/bydate/{}'.format(yacreader['date'].strftime('%Y/%m')) }) 
    response = Response(render_template('history.html',  items = items, nav = { 'up':up, 'back':back, 'forth':forth }))
    response.set_cookie('up', '/history|History')
    return response

@app.route('/read/<int:id>')
@app.route('/read/<int:id>/<int:page>')
@app.route('/read/<int:id>/<int:page>/<int:half>')
def read(id, page = None, half = None):
    yacreader = None
    yacreader = yyreader.yacreader.get_comic_by_id(id)
    if (id in comic_cache):
        #yacreader = comic_cache[id]['yacreader']
        c = comic_cache[id]['comic']
    else:
        c = yyreader.comic.comic(comic_dir + '/' + yacreader['path'])
        comic_cache[id] = {}
        comic_cache[id]['yacreader'] = yacreader
        comic_cache[id]['cover'] = yyreader.yacreader.get_cover_file(id, hash = yacreader['hash'])
        comic_cache[id]['comic'] = c
        comic_cache[id]['date'] = datetime.now()

    if (page is None):
        page = 1
        if ('current_page' in yacreader and yacreader['current_page'] is not None and yacreader['current_page'] < c.page_count()):
            page = int(yacreader['current_page'])

    if (page < 1): page = 1
    if (page > c.page_count()): page = c.page_count()

    (w, h) = c.page_size(page)
    image_height = h
    image_width = w
    if (image_height < image_width and half is None):
        half = 1

    color = c.page_color(page)
    text_color = '#' + complementaryColor(color)

    forth = None
    back = None
    if (request.cookies.get('current_time')):
        back = { 'url':'/bydate/{}#{}'.format(request.cookies.get('current_time'), id), 'text':'/'.join(list(reversed(request.cookies.get('current_time').split('/')))) }
        if (yacreader['date'].strftime('%Y/%-m') != request.cookies.get('current_time')):
            forth = { 'url':'/bydate/{}#{}'.format(yacreader['date'].strftime('%Y/%m'), id), 'text':'{}'.format(yacreader['date'].strftime('%m/%d/%Y')) }
    
    #up = None
    #if (request.cookies.get('up')):
    #    up = { 'url':request.cookies.get('up').split('|')[0], 'text':request.cookies.get('up').split('|')[1] }
    up = { 'url':'/byvolume/{}#{}'.format(urllib.parse.quote(yacreader['volume']), yacreader['id']), 'text':'{} #{}'.format(yacreader['volume'], yacreader['issue']) }
    view = None

    previous_page_url = back['url']
    next_page_url = back['url']
    if (request.cookies.get('traversal_method') == 'byvolume'):
        if (page == 1 or page == c.page_count()):
        #back = {'url':'/byvolume/{}#{}'.format(urllib.parse.quote(yacreader['volume']), id), 'text':'{} #{}'.format(yacreader['volume'], yacreader['issue'])}
        #forth = back
            issues = yyreader.yacreader.get_comics_by_volume(yacreader['volume'])
            if (page == 1):
                i = 0
                while (i < len(issues)):
                    if (issues[i]['issue'] == yacreader['issue'] and (i > 0)):
                        previous_page_url =  '/read/{}'.format(issues[i-1]['id'])
                        break
                    i = i + 1
            elif (page == c.page_count()):
                i = 0
                while (i < len(issues)):
                    if (issues[i]['issue'] == yacreader['issue'] and (i < (len(issues) - 1))):
                        next_page_url =  '/read/{}'.format(issues[i+1]['id'])
                        break
                    i = i + 1

    if (page > 1):
        if (half == 2):
            previous_page_url = '/read/{}/{}/{}'.format(id, (page), 1)
        else:
            previous_page_url = '/read/{}/{}'.format(id, (page-1))

    if (page < c.page_count()):
        if (half == 1):
            next_page_url = '/read/{}/{}/{}'.format(id, (page), 2)
        else:
            next_page_url = '/read/{}/{}'.format(id, (page+1))

    yyreader.yacreader.update_read_log(id, page, page_count = c.page_count())
    return render_template('read.html', half = half, page = page, yacreader = yacreader, img = { 'height': image_height, 'width': image_width , 'half_width': int(image_width/2) }, next_page_url = next_page_url, previous_page_url = previous_page_url, page_count = c.page_count(), nav = { 'back':back, 'up': up, 'forth':forth, 'view':view }, data_dir = c.data_dir, background_color = color, text_color = text_color )

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
