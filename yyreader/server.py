#!/usr/bin/env python3

from datetime import datetime,timedelta
from flask import current_app, Flask, g, render_template, redirect, request, Response
import minorimpact.config
import os
import re
import sqlite3
import urllib.parse
from . import comic, yacreader

app = Flask(__name__, template_folder='server/templates')
app.config.from_mapping(
        #EXPLAIN_TEMPLATE_LOADING=True,
        #SECRET_KEY='dev',
        #DATABASE=config['default']['db'],
    )
comic_cache = {}
comic_dir = '/'

def main():
    global comic_dir
    config = minorimpact.config.getConfig(script_name = 'yyreader')

    comic_dir = config['default']['comic_dir']
    comic_dir = re.sub(r'/$', '', comic_dir)

    debug = False
    if ('debug' in config['server']):
        config_debug = eval(config['server']['debug'])
        if (config_debug is True):
            debug = True

    yacreader.init_db()
    app.run(port = config['server']['port'], host = '0.0.0.0', debug = debug)

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

@app.route('/beacons')
def beacons():
    beacons = yacreader.get_beacons()
    return render_template('beacons.html', beacons = beacons, nav = { 'history':True })

@app.route('/bydate')
@app.route('/bydate/<int:year>')
@app.route('/bydate/<int:year>/<int:month>')
def bydate(year = None, month = None):
    items = []
    up = None
    back = None
    forth = None
    clean_cache()
    if (year is None and month is None):
        for year in yacreader.get_years():
            items.append({ 'url':'/bydate/{}'.format(year), 'text':'{}'.format(year) })
        view = {'url':'/byvolume', 'text':'Volumes' }
        nav = { 'back':None, 'up':None, 'forth':None, 'view':view, 'fixed':True }
        return render_template('byyear.html', back = back, items = items, nav = nav)

    elif (year is not None and month is None):
        years = yacreader.get_years()
        i = 0
        while i < len(years):
            if (years[i] == year):
                if (i > 0): back = { 'url': '/bydate/{}'.format(years[i-1]), 'text':'{}'.format(years[i-1]) }
                if (i < len(years)-1): forth = { 'url': '/bydate/{}'.format(years[i+1]), 'text':'{}'.format(years[i+1]) }
                break
            i = i + 1
        for month in yacreader.get_months(year):
            items.append({ 'url':'/bydate/{}/{}'.format(year, month), 'text':'{}/{}'.format(month, year) })

        up = { 'url':'/bydate', 'text':'Years' }
        nav = { 'back':back, 'forth':forth, 'up': up, 'fixed':True  }
        return render_template('bymonth.html', back = back, items = items, nav = nav)

    elif (year is not None and month is not None):
        yacreader.update_beacon('{}/{}'.format(year, month))

        up = { 'url':'/bydate/{}'.format(year), 'text':str(year) }
        (prev_year, prev_month) = yacreader.get_prevdate(year, month)
        if (prev_year is not None):
            back = { 'url':'/bydate/{}/{}'.format(prev_year, prev_month), 'text':'{}/{}'.format(prev_month, prev_year) }
            if (yacreader.get_beacon('{}/{}'.format(prev_year, prev_month)) is not None):
                yacreader.delete_beacon('{}/{}'.format(prev_year, prev_month))
                yacreader.add_beacon('{}/{}'.format(year, month))

        (next_year, next_month) = yacreader.get_nextdate(year, month)
        if (next_year is not None):
            forth = { 'url':'/bydate/{}/{}'.format(next_year, next_month), 'text':'{}/{}'.format(next_month, next_year) }

        for y in yacreader.get_comics_by_date(year, month):
            items.append({ 'yacreader': y, 'date':y['date'].strftime('%m/%d/%Y'), 'short_volume':y['volume'][0:25], 'datelink':'/bydate/{}'.format(y['date'].strftime('%Y/%m')) })
        drop = None
        if (yacreader.get_beacon('{}/{}'.format(year, month)) is None):
            drop = {'url':'/drop/{}/{}'.format(year, month), 'text':'Drop Beacon'} 
        elif (len(yacreader.get_beacons()) > 1):
            drop = {'url':'/take/{}/{}'.format(year, month), 'text':'Take Beacon'} 
        nav = {'back':back, 'forth':forth, 'up':up, 'drop':drop, 'fixed':True }
        response = Response(render_template('comics.html', items = items, nav = nav ))
        response.set_cookie('traversal_method', 'bydate', max_age=60*60*24*365)
        response.set_cookie('back', '/bydate/{}/{}|{}/{}'.format(year, month, month, year), max_age=60*60*24*365)
        response.delete_cookie('up')
        return response

@app.route('/byvolume')
@app.route('/byvolume/<volume>')
def byvolume(volume = None):
    items = []
    back = None
    up = None
    forth = None
    view = None #{'url':'/bydate', 'text':'Dates' }
    clean_cache()
    if (volume is None):
        last = None
        index = []
        for volume in yacreader.get_volumes():
            if (volume[0:1] != last):
                last = volume[0:1]
                items.append({ 'name':last })
                index.append({ 'url':'#{}'.format(last), 'text':last })

            items.append({ 'url':'/byvolume/{}'.format(urllib.parse.quote(volume)), 'text':volume, 'name':None })
        view = {'url':'/bydate', 'text':'Dates' }
        nav = {'back':back, 'forth':forth, 'up':up, 'view':view, 'fixed':True }
        return render_template('byvolume.html', items = items, nav = nav, index = index)
    else:
        volume = urllib.parse.unquote(volume)
        for y in yacreader.get_comics_by_volume(volume):
            items.append({ 'yacreader': y, 'date':y['date'].strftime('%m/%d/%Y'), 'datelink':'/bydate/{}#{}'.format(y['date'].strftime('%Y/%m'), y['id']) })

        up = { 'url':'/byvolume', 'text':'Volumes' }
        nav = { 'back':back, 'forth':forth, 'up':up, 'view':view, 'fixed':True}
        response = Response(render_template('comics.html', back = back, items = items, nav = nav))
        response.set_cookie('traversal_method', 'byvolume', max_age=60*60*24*365)
        response.set_cookie('back', '/byvolume/{}|{}'.format(urllib.parse.quote(volume), volume), max_age=60*60*24*365)
        return response

@app.route('/cover/<int:id>')
def cover(id):
    cover_file = None
    if (id in comic_cache):
        cover_file = comic_cache[id]['cover']
    else:
        y = yacreader.get_comic_by_id(id)
        comic_cache[id] = {}
        comic_cache[id]['yacreader'] = y
        comic_cache[id]['comic'] = comic.comic(comic_dir + '/' + y['path'])
        cover_file = yacreader.get_cover_file(id, hash = y['hash'])
        comic_cache[id]['cover'] = cover_file
        comic_cache[id]['date'] = datetime.now()

    cover_data = None
    with (open(cover_file, 'rb') as f):
        cover_data = f.read()

    if (cover_data is not None):
        return Response(cover_data, mimetype = 'image/jpeg')

@app.route('/drop/<int:year>/<int:month>')
def drop(year, month):
    beacon = '{}/{}'.format(year, month)
    yacreader.add_beacon(beacon)
    return redirect('/bydate/' + beacon)

@app.route('/history')
@app.route('/history/<int:page>')
def history(page = 1):
    per_page = 50
    back = None
    index = []
    up = { 'url':'/', 'text':'Index' }
    forth = None
    items = []
    history = yacreader.get_history()

    (page_count, spillover) = divmod(len(history), per_page)
    if (spillover > 0): page_count = page_count + 1
    if (page < 1): page = 1
    if (page > page_count): page = page_count

    if (page_count > 1):
        for p in range(1,page_count+1):
            if (p == page):
                index.append({'text':str(p) })
            else:
                index.append({'url':'/history/{}'.format(p), 'text':str(p) })

    for y in history[((page-1)*per_page):(page*per_page)]:
        items.append({ 'yacreader': y, 'date':y['date'].strftime('%m/%d/%Y'), 'datelink':'/bydate/{}'.format(y['date'].strftime('%Y/%m')) })
    nav = { 'up':None, 'back':None, 'forth':None, 'home':True, 'drop':{'url':'/beacons', 'text':'Beacons' } }
    response = Response(render_template('history.html',  items = items, nav = nav, index = index))
    response.set_cookie('back', '/history|History')
    return response

@app.route('/')
@app.route('/home')
def home():
    beacons = yacreader.get_beacons()
    if (len(beacons) == 0):
        year = yacreader.get_years()[0]
        month = yacreader.get_months(year)[0]
        home = '{}/{}'.format(year, month)
        yacreader.add_beacon(home)
    else:
        home = beacons[0]['name']
    return redirect('/bydate/' + home)

@app.route('/read/<int:id>')
@app.route('/read/<int:id>/<int:page>')
@app.route('/read/<int:id>/<int:page>/<int:half>')
def read(id, page = None, half = None):
    y = None
    y = yacreader.get_comic_by_id(id)
    if (id in comic_cache):
        #yacreader = comic_cache[id]['yacreader']
        c = comic_cache[id]['comic']
    else:
        c = comic.comic(comic_dir + '/' + y['path'])
        comic_cache[id] = {}
        comic_cache[id]['yacreader'] = y
        comic_cache[id]['cover'] = yacreader.get_cover_file(id, hash = y['hash'])
        comic_cache[id]['comic'] = c
        comic_cache[id]['date'] = datetime.now()

    if (page is None):
        page = 1
        if ('current_page' in y and y['current_page'] is not None and y['current_page'] < c.page_count()):
            page = int(y['current_page'])

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

    up = { 'url':'/byvolume/{}#{}'.format(urllib.parse.quote(y['volume']), y['id']), 'text':'{} #{}'.format(y['volume'], y['issue']) }
    forth = { 'url':'/bydate/{}#{}'.format(y['date'].strftime('%Y/%-m'), y['id']), 'text':'{}'.format(y['date'].strftime('%m/%d/%Y')) }
    view = None

    previous_page_url = forth['url']
    if (request.cookies.get('back')):
        previous_page_url = request.cookies.get('back').split('|')[0] + '#{}'.format(id)
    next_page_url = previous_page_url

    if (request.cookies.get('traversal_method') == 'byvolume'):
        # If the user was looking specifically at the issues in a particular volume, then the page turns on the first and last pages will go the prev/next issues.
        if (page == 1 or page == c.page_count()):
            issues = yacreader.get_comics_by_volume(y['volume'])
            if (page == 1):
                i = 0
                while (i < len(issues)):
                    if (issues[i]['issue'] == y['issue'] and (i > 0)):
                        previous_page_url =  '/read/{}'.format(issues[i-1]['id'])
                        break
                    i = i + 1
            elif (page == c.page_count()):
                i = 0
                while (i < len(issues)):
                    if (issues[i]['issue'] == y['issue'] and (i < (len(issues) - 1))):
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

    yacreader.update_read_log(id, page, page_count = c.page_count())
    nav = { 'back':back, 'up': up, 'forth':forth, 'view':view, 'history':False, 'home':True }
    response = Response(render_template('read.html', half = half, page = page, yacreader = y, img = { 'height': image_height, 'width': image_width , 'half_width': int(image_width/2) }, next_page_url = next_page_url, previous_page_url = previous_page_url, page_count = c.page_count(), nav = nav, data_dir = c.data_dir, background_color = color, text_color = text_color ))
    return response

@app.route('/page/<int:id>/<int:page>')
def page(id, page):
    y = None
    if (id in comic_cache):
        y = comic_cache[id]['yacreader']
        c = comic_cache[id]['comic']
    else:
        y = yacreader.get_comic_by_id(id)
        c = comic.comic('/Volumes/Media/Comics/' + y['path'])
        comic_cache[id] = {}
        comic_cache[id]['yacreader'] = y
        comic_cache[id]['comic'] = c
        comic_cache[id]['cover'] = yacreader.get_cover_file(id, hash = y['hash'])
        comic_cache[id]['date'] = datetime.now()

    if (page < 0): page = 1
    if (page > c.page_count()): page = c.page_count()

    return Response(c.page(page), mimetype = 'image/jpeg')

@app.route('/take/<int:year>/<int:month>')
def take(year, month):
    beacon = '{}/{}'.format(year, month)
    yacreader.delete_beacon(beacon)
    return redirect('/bydate/' + beacon)

