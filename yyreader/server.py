#!/usr/bin/env python3

from datetime import datetime,timedelta
from dumper import dump
from flask import current_app, Flask, g, make_response, render_template, redirect, request, Response
import minorimpact.config
import base64
import os
import pickle
import re
import sqlite3
import urllib.parse
from . import comic, backend

app = Flask(__name__, template_folder='templates')
app.config.from_mapping(
        #EXPLAIN_TEMPLATE_LOADING=True,
        #SECRET_KEY='dev',
        #DATABASE=config['default']['db'],
    )
comic_cache = {}
comic_dir = '/'
config = None

def main():
    global comic_dir
    global config

    config = minorimpact.config.getConfig(script_name = 'yyreader')

    comic_dir = config['default']['comic_dir']
    comic_dir = re.sub(r'/$', '', comic_dir)

    debug = False
    if ('debug' in config['server']):
        config_debug = eval(config['server']['debug'])
        if (config_debug is True):
            debug = True

    backend.init_db()

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

def get_filter(filter = None):
    cookie_filter = request.cookies.get('filter')
    if (cookie_filter):
        f = pickle.loads(base64.urlsafe_b64decode(cookie_filter))
        if (f is None):
            return None
        if (filter in f):
            return f[filter]
        return f
    return None

def get_home_link(year = None, month = None):
    # I can't decide if going back to the latest beacon or going back to the last date viewed is a better definition of 'home'
    beacons = backend.get_beacons()
    if (len(beacons) > 0):
        if ( year is not None and month is not None and beacons[0]['name'] == f'{year}/{month}'):
            # TODO: Figure out why this is here and why it returns 'None' rather than a link to this
            #   year and month.
            return None
        # TODO: Just change everything on the frontend over to 'year/month' so I can stop all these stupid translations.
        return { 'url':'/dates/' + beacons[0]['name'], 'text': "{}/{}".format(beacons[0]['name'].split('/')[1], beacons[0]['name'].split('/')[0]) }
    elif (request.cookies.get('date')):
        traversal_date = request.cookies.get('date')
        print(f"traversal_date:{traversal_date}")
        return {'url':traversal_date.split('|')[0], 'text':traversal_date.split('|')[1]}

    year = backend.get_years()[0]
    month = backend.get_months(year)[0]
    home = '{}/{}'.format(year, month)
    backend.add_beacon(home)
    return {'url':'/dates/' + home, 'text':'{}/{}'.format(month, year) }

@app.before_request
def before_request():
    #request.cookies.get('filter')
    if (request.path != '/login' and 'password' in config['server'] and request.cookies.get('authorized') != 'True'):
        return redirect('/login')
    clean_cache()

@app.route('/arc/<arc>')
def arc(arc = None):
    db = backend.connect()
    home = get_home_link()
    cursor = db.cursor()
    comics = []
    #TODO: backend.get_comics_by_arc()
    #TODO: Fix navigation.
    for row in cursor.execute('select id, storyArc, comicInfoId from comic_info_arc where storyArc=?', (arc,)).fetchall():
        comics.append({ 'yacreader':backend.get_comic_by_id(row['comicInfoId'], db = db) })

    db.close()
    nav = { 'home':home }
    return render_template('comics.html',  items = comics, nav = nav)

@app.route('/arclink')
@app.route('/arclink/<int:aft_id>')
@app.route('/arclink/<int:aft_id>/<int:fore_id>')
def arclink(aft_id = None, fore_id = None):
    home = get_home_link()
    db = backend.connect()
    cursor = db.cursor()

    if (aft_id is not None):
        if (fore_id is not None):
            backend.link(fore_id, aft_id, db = db)
        else:
            cursor.execute('insert into arclinkskip(comicInfoId) values (?)', (aft_id,))
            db.commit()
        return redirect('/arclink')

    for row in cursor.execute('select id, storyArc, comicInfoId from comic_info_arc').fetchall():
        storyArc = row['storyArc']
        arclinkskip = cursor.execute('select id from arclinkskip where comicInfoId=?', (row['comicInfoId'],)).fetchone()
        if (arclinkskip is not None):
            continue

        arc_issue = backend.get_comic_by_id(row['comicInfoId'], db=db)
        if (arc_issue['fore_id'] is not None):
            continue
        previous_issue = None

        i = 0
        comics = backend.get_comics_by_series(arc_issue['series'])
        for i in range(0, len(comics)):
            if (arc_issue['id'] == comics[i]['id'] and i > 0):
                row = cursor.execute('select id, storyArc, comicInfoId from comic_info_arc where comicInfoId=?', (comics[i-1]['id'],)).fetchone()
                if (row is not None and row['storyArc'] == storyArc):
                    previous_issue = comics[i-1]
                break
        if (previous_issue is not None):
            break

    c1 = comic.comic(comic_dir + '/' + arc_issue['path'])
    c2 = comic.comic(comic_dir + '/' + previous_issue['path'])
    db.close()
    nav = { 'home':home }
    return render_template('arclink.html',  story_arc = storyArc, issue = arc_issue, issue_page_count = c1.page_count(),  previous_issue = previous_issue, previous_issue_page_count = c2.page_count(), nav = nav)

@app.route('/arcs')
def arcs():
    db = backend.connect()
    cursor = db.cursor()
    arcs = []
    #TODO: Add an index.
    #TODO: Fix navigation.
    for row in cursor.execute('select distinct(storyArc) as arc from comic_info_arc order by arc').fetchall():
        arcs.append({ 'url':'/arc/{}'.format(urllib.parse.quote(row['arc'])), 'text':row['arc'] })

    db.close()
    nav = { 'home':True }
    return render_template('arcs.html',  items = arcs, nav = nav)

@app.route('/beacons')
def beacons():
    beacons = backend.get_beacons()
    return render_template('beacons.html', beacons = beacons, nav = { 'home':True })

@app.route('/dates')
@app.route('/dates/<int:year>')
@app.route('/dates/<int:year>/<int:month>')
def dates(year = None, month = None):
    items = []
    up = None
    back = None
    forth = None
    home = get_home_link(year, month)

    if (year is None and month is None):
        for year in backend.get_years():
            items.append({ 'url':'/dates/{}'.format(year), 'text':'{}'.format(year) })
        nav = { 'back':back, 'up':up, 'forth':forth, 'home':home }
        return render_template('byyear.html', items = items, nav = nav)

    elif (year is not None and month is None):
        years = backend.get_years()
        i = 0
        while i < len(years):
            if (years[i] == year):
                if (i > 0): back = { 'url': '/dates/{}'.format(years[i-1]), 'text':'{}'.format(years[i-1]) }
                if (i < len(years)-1): forth = { 'url': '/dates/{}'.format(years[i+1]), 'text':'{}'.format(years[i+1]) }
                break
            i = i + 1
        for month in backend.get_months(year):
            items.append({ 'url':'/dates/{}/{}'.format(year, month), 'text':'{}/{}'.format(month, year) })

        up = { 'url':'/dates', 'text':'Years' }
        nav = { 'back':back, 'forth':forth, 'up': up,'home':home }
        return render_template('bymonth.html', items = items, nav = nav)

    elif (year is not None and month is not None):
        backend.update_beacon('{}/{}'.format(year, month))

        up = { 'url':'/dates/{}'.format(year), 'text':str(year) }
        (prev_year, prev_month) = backend.get_previous_date(year, month)
        if (prev_year is not None):
            back = { 'url':'/dates/{}/{}'.format(prev_year, prev_month), 'text':'{}/{}'.format(prev_month, prev_year) }
            if (backend.get_beacon('{}/{}'.format(prev_year, prev_month)) is not None):
                backend.delete_beacon('{}/{}'.format(prev_year, prev_month))
                backend.add_beacon('{}/{}'.format(year, month))

        (next_year, next_month) = backend.get_next_date(year, month)
        if (next_year is not None):
            forth = { 'url':'/dates/{}/{}'.format(next_year, next_month), 'text':'{}/{}'.format(next_month, next_year) }

        for y in backend.get_comics_by_date(year, month):
            short_series = '{} ({})'.format(y['series'][0:25], y['series'])
            items.append({ 'yacreader': y, 'date':y['date'].strftime('%m/%d/%Y'), 'short_series':short_series, 'datelink':'/dates/{}'.format(y['date'].strftime('%Y/%m')) })

        #if (backend.get_beacon('{}/{}'.format(year, month)) is None):
        #    beacon = {'url':'/drop/{}/{}'.format(year, month), 'text':'Drop Beacon'}
        if (len(backend.get_beacons()) > 1):
            beacon = {'url':'/take/{}/{}'.format(year, month), 'text':'Take Beacon'}
        else:
            beacon = {'url':'/drop/{}/{}'.format(year, month), 'text':'Drop Beacon'}
        nav = {'back':back, 'forth':forth, 'up':up, 'beacon':beacon, 'home':home }
        response = make_response(render_template('comics.html', items = items, nav = nav ))
        response.set_cookie('traversal', 'date', max_age=60*60*24*365)
        response.set_cookie('date', '/dates/{}/{}|{}/{}'.format(year, month, month, year), max_age=60*60*24*365)
        return response

@app.route('/cover/<int:id>')
def cover(id):
    cover_file = None

    #if (id in comic_cache):
    #    cover_file = comic_cache[id]['cover']
    #else:
    #    y = backend.get_comic_by_id(id)
    #    comic_cache[id] = {}
    #    comic_cache[id]['yacreader'] = y
    #    comic_cache[id]['comic'] = comic.comic(comic_dir + '/' + y['path'])
    #    cover_file = backend.get_cover_file(id, hash = y['hash'])
    #    comic_cache[id]['cover'] = cover_file
    #    comic_cache[id]['date'] = datetime.now()
    y = backend.get_comic_by_id(id)
    cover_file = backend.get_cover_file(id, hash = y['hash'])

    cover_data = None
    with (open(cover_file, 'rb') as f):
        cover_data = f.read()

    if (cover_data is not None):
        return Response(cover_data, mimetype = 'image/jpeg')

@app.route('/drop/<int:year>/<int:month>')
def drop(year, month):
    beacon = '{}/{}'.format(year, month)
    backend.add_beacon(beacon)
    return redirect('/dates/' + beacon)

@app.route('/filter')
def filter():
    filter = {'publishers':[], 'labels':[]}
    cookie_filter = request.cookies.get('filter')
    if (cookie_filter):
        filter = get_filter()
        if (filter is not None):
            if ('publishers' not in filter):
                filter['publishers'] = []
            if ('labels' not in filter):
                filter['labels'] = []

    if (len(request.args) > 0):
        filter = {'publishers':[], 'labels':[]}
        for arg in request.args:
            m = re.search('^p_(.+)$', arg)
            if (m):
                publisher = m.group(1)
                if (request.args.get(arg) == 'on' and publisher not in filter['publishers']):
                    filter['publishers'].append(publisher)
            m = re.search('^l_(.+)$', arg)
            if (m):
                label = m.group(1)
                if (request.args.get(arg) == 'on' and label not in filter['labels']):
                    filter['labels'].append(label)
        #print(filter)
        pickled = str(base64.urlsafe_b64encode(pickle.dumps(filter)), 'utf-8')
        response = make_response(redirect('/seriess'))
        response.set_cookie('filter', pickled)
        return response

    publishers = []
    for publisher in backend.get_publishers():
        publishers.append(publisher)

    labels = []
    for label in backend.get_labels():
        labels.append(label)


    home = get_home_link()
    nav = nav = {'home':home }
    response = make_response(render_template('filter.html', filter = filter, publishers = publishers, labels = labels, nav = nav))
    return response

@app.route('/history')
@app.route('/history/<int:page>')
def history(page = 1):
    per_page = 50
    back = None
    index = []
    up = { 'url':'/', 'text':'Index' }
    forth = None
    items = []
    history = backend.get_history()
    home = get_home_link()

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
        items.append({ 'yacreader': y, 'date':y['date'].strftime('%m/%d/%Y'), 'datelink':'/dates/{}'.format(y['date'].strftime('%Y/%m')) })
    nav = { 'up':None, 'back':None, 'forth':None, 'home':home }
    response = Response(render_template('history.html',  items = items, nav = nav, index = index))
    return response

@app.route('/')
@app.route('/home')
def home():
    return redirect(get_home_link()['url'])

@app.route('/label/<int:id>')
def label(id):
    labels = []
    if (len(request.args) > 0):
        for arg in request.args:
            m = re.search('^l_(.+)$', arg)
            if (m):
                label = m.group(1)
                if (request.args.get(arg) == 'on' and label not in labels):
                    labels.append(label)
    backend.set_labels(id, labels)
    return redirect('/read/{}'.format(id))

@app.route('/login', methods = ['GET', 'POST'])
def login():
    response = Response(render_template('login.html'))
    if request.method == 'POST':
        if (request.form['password'] == config['server']['password']):
            response = redirect('/home')
            response.set_cookie('authorized', 'True')

    return response

@app.route('/update/<int:id>')
def update(id):
    y = backend.get_comic_by_id(id)
    nav = { 'home':get_home_link() }
    return render_template('update.html', yacreader = y, nav = nav, labels = backend.get_labels())

@app.route('/link/<int:aft_id>')
@app.route('/link/<int:aft_id>/<int:fore_id>')
def link(aft_id, fore_id = None):
    y = backend.get_comic_by_id(aft_id)
    if (y['fore_id'] is not None):
        backend.unlink(aft_id)
    else:
        if (fore_id is None):
            # Get the previous series
            issues = backend.get_comics_by_series(y['series'])
            i = 0
            while (i < len(issues)):
                if (issues[i]['issue'] == y['issue'] and (i > 0)):
                    fore_id = issues[i-1]['id']
                    break
                i = i + 1

        if (fore_id is not None):
            backend.link(fore_id, aft_id)

    response = make_response(redirect('/read/{}'.format(aft_id)))
    return response

@app.route('/read/<int:id>')
@app.route('/read/<int:id>/<int:page>')
@app.route('/read/<int:id>/<int:page>/<int:half>')
def read(id, page = None, half = None):
    linked = False
    # TODO: Experiment with removing the cache.  Up to this point there's been very little need to optimize, and since I started
    #   reading the image data directly from the file without unpacking it first it could be argued that caching as whole is
    #   largely unecessary (I only started caching the 'comic.py' object in the first place so the temp directory didn't get obliterated
    #   every time the object was destroyed, necessitating a lengthy decompression on every read.)
    # This isn't in the cache because subsequent views won't refect the currentPage values.
    #y = backend.get_comic_by_id(id)
    #if (id in comic_cache):
    #    #yacreader = comic_cache[id]['yacreader']
    #    c = comic_cache[id]['comic']
    #else:
    #    c = comic.comic(comic_dir + '/' + y['path'])
    #    comic_cache[id] = {}
    #    comic_cache[id]['yacreader'] = y
    #    comic_cache[id]['cover'] = backend.get_cover_file(id, hash = y['hash'])
    #    comic_cache[id]['comic'] = c
    #    comic_cache[id]['date'] = datetime.now()

    y = backend.get_comic_by_id(id)
    c = comic.comic(comic_dir + '/' + y['path'])

    if (page is None):
        page = 1
        if ('current_page' in y and y['current_page'] is not None and y['current_page'] < c.page_count()):
            page = int(y['current_page'])

    if (page > c.page_count()): page = c.page_count()
    if (page < 1): page = 1

    crop = parse_settings_cookie(request.cookies.get('settings'), 'crop') if request.cookies.get('settings') else True
    if (request.args.get('crop','')):
        crop = False if (request.args.get('crop','') == 'False') else True

    #print(f"page:{page}")
    (w, h) = c.page_size(page, crop = crop)
    image_height = h
    image_width = w
    if (image_height < image_width and half is None):
        half = 1

    color = c.page_color(page, crop = crop)
    text_color = '#' + complementaryColor(color)

    forth = None
    back = None
    next_page_url = None
    previous_page_url = None
    up = { 'url':'/series/{}#{}'.format(urllib.parse.quote(f"{y['series']} ({y['volume']})"), y['id']), 'text':'{} #{}'.format(y['series'], y['issue']) }

    traversal = request.cookies.get('traversal') if request.cookies.get('traversal') else 'date'
    traversal_date = '/dates/{}#{}|{}'.format(y['date'].strftime('%Y/%-m'), id, y['date'].strftime('%d/%Y'))
    if (request.cookies.get('date')):
        traversal_date = request.cookies.get('date')
        # Tack on the id of the first book we look at to the last date we visited, so we can always snap back to this point.
        if (re.search(r'^/dates/\d+/\d+#\d+\|', traversal_date) is None):
            traversal_date = traversal_date.split('|')[0] + '#{}'.format(id) + '|' + traversal_date.split('|')[1]

    home = {'url':traversal_date.split('|')[0], 'text':traversal_date.split('|')[1]}

    if (traversal == 'series'):
        # If the user was looking specifically at the issues in a particular series, then the page turns on the first and last pages will go the prev/next issues.
        issues = backend.get_comics_by_series(y['series'])
        i = 0
        while (i < len(issues)):
            if (issues[i]['issue'] == y['issue'] and (i > 0) and back is None):
                p = issues[i-1]
                back = {'url': '/read/{}'.format(p['id']), 'text': '#{}'.format(p['issue']) }
                if (p['aft_id'] == y['id']):
                    linked = True
            if (issues[i]['issue'] == y['issue'] and (i < (len(issues) - 1)) and forth is None):
                forth = {'url': '/read/{}'.format(issues[i+1]['id']), 'text': '#{}'.format(issues[i+1]['issue']) }
            if (back is not None and forth is not None):
                break
            i = i + 1
        if (back is None):
            back = {'url': '/series/{}#{}'.format(urllib.parse.quote(f"{y['series']} ({y['volume']})"), id), 'text': '{}'.format(y['series']) }
        if (forth is None):
            forth = {'url': '/series/{}#{}'.format(urllib.parse.quote(f"{y['series']} ({y['volume']})"), id), 'text': '{}'.format(y['series']) }
    elif (traversal == 'strict'):
        #TODO: Add a traversal method that goes by date but ignores linking.
        pass
    elif (traversal == 'date'):
        #back = {'url':traversal_date.split('|')[0], 'text':traversal_date.split('|')[1]}
        #forth = back
        print("FOO")
        p = backend.get_previous_comic(y['id'])
        print("FOO2")
        n = backend.get_next_comic(y['id'])
        print("FOO3")
        #TODO: Figure out how to display long ass titles in what are supposed to be small buttons.  Just the first few
        #   characters?  Maybe tiny cover thumbnails?
        if (p and p['aft_id'] == y['id']):
            linked = True
        if (p):
            back = {'url': '/read/{}'.format(p['id']), 'text':'{} #{}'.format(p['series'], p['issue'])}
        if (n):
            forth = {'url': '/read/{}'.format(n['id']), 'text':'{} #{}'.format(n['series'], n['issue'])}
    else:
        print("unknown traversal:", traversal)

    if (page == 1 and back):
        previous_page_url =  back['url']
    elif (page > 1):
        if (half == 2):
            previous_page_url = '/read/{}/{}/{}'.format(id, (page), 1)
        else:
            previous_page_url = '/read/{}/{}'.format(id, (page-1))

    if (page < c.page_count()):
        if (half == 1):
            next_page_url = '/read/{}/{}/{}'.format(id, (page), 2)
        else:
            next_page_url = '/read/{}/{}'.format(id, (page+1))
    elif (page == c.page_count()):
        next_page_url =  forth['url']

    if (parse_settings_cookie(request.cookies.get('settings'), 'logging') is True):
        # TODO: This doesn't get set until you go into settings and turn logging off and on again.
        backend.update_read_log(id, page, page_count = c.page_count())

    nav = { 'back':back, 'up': up, 'forth':forth, 'home':home, 'unfixed':True }
    response = make_response(render_template('read.html', half = half, page = page, yacreader = y, crop = crop, next_page_url = next_page_url, previous_page_url = previous_page_url, page_count = c.page_count(), nav = nav, data_dir = c.data_dir, background_color = color, text_color = text_color, traversal = traversal, linked = linked ))
    response.set_cookie('series', '/series/{}|{}'.format(urllib.parse.quote(f"{y['series']} ({y['volume']})"), y['series']), max_age=60*60*24*365)
    response.set_cookie('date', traversal_date, max_age=60*60*24*365)
    return response

@app.route('/page/<int:id>/<int:page>')
def page(id, page):
    y = None
    #if (id in comic_cache):
    #    y = comic_cache[id]['yacreader']
    #    c = comic_cache[id]['comic']
    #else:
    #    y = backend.get_comic_by_id(id)
    #    c = comic.comic('/Volumes/Media/Comics/' + y['path'])
    #    comic_cache[id] = {}
    #    comic_cache[id]['yacreader'] = y
    #    comic_cache[id]['comic'] = c
    #    comic_cache[id]['cover'] = backend.get_cover_file(id, hash = y['hash'])
    #    comic_cache[id]['date'] = datetime.now()

    y = backend.get_comic_by_id(id)
    c = comic.comic(f"{config['default']['comic_dir']}/{y['path']}")

    if (page < 0): page = 1
    if (page > c.page_count()): page = c.page_count()

    crop = True if (request.args.get('crop','True') == 'True') else False
    return Response(c.page(page, crop = crop), mimetype = 'image/jpeg')

@app.route('/settings')
@app.route('/settings/<setting>/<value>')
@app.route('/settings/<setting>/<value>/<int:id>')
def settings(setting = None, value = None, id = None):
    settings = parse_settings_cookie(request.cookies.get('settings'))

    if ('crop' not in settings): settings['crop'] = True
    if ('logging' not in settings): settings['logging'] = True

    if (setting == 'crop'):
        if (id is not None):
            settings['crop'] = True if (settings['crop'] is False) else False
        else:
            settings['crop'] = True if (value == 'True') else False

    if (setting == 'logging'):
        if (id is not None):
            settings['logging'] = True if (settings['logging'] is False) else False
        else:
            settings['logging'] = False if (value == 'False') else True

    if (id is not None):
        response = make_response(redirect('/read/{}'.format(id)))
    else:
        home = get_home_link()
        nav = nav = {'home':home }
        response = make_response(render_template('settings.html', settings = settings, nav = nav))

    pickled = str(base64.urlsafe_b64encode(pickle.dumps(settings)), 'utf-8')
    response.set_cookie('settings', pickled)
    return response

def parse_settings_cookie(cookie_settings, setting = None):
    settings = {}
    if (cookie_settings):
        settings = pickle.loads(base64.urlsafe_b64decode(cookie_settings))

    if (setting is None):
        return settings
    if (setting in settings):
        return settings[setting]
    return None

@app.route('/series/<series>')
def series(series = None):
    items = []
    up = None
    home = get_home_link()

    filter = get_filter()

    series = urllib.parse.unquote(series)
    for y in backend.get_comics_by_series(series, filter = filter):
        items.append({ 'yacreader': y, 'date':y['date'].strftime('%m/%d/%Y'), 'datelink':'/dates/{}#{}'.format(y['date'].strftime('%Y/%m'), y['id']) })

    traversal_method = request.cookies.get('traversal')
    if (traversal_method == 'date'):
        traversal_date = request.cookies.get('date')
        if (traversal_date):
            home = {'url':traversal_date.split('|')[0], 'text':traversal_date.split('|')[1]}
    up = { 'url':'/seriess', 'text':'Series' }
    nav = { 'up':up, 'home':home }
    response = make_response(render_template('comics.html', items = items, nav = nav))
    response.set_cookie('traversal', 'series', max_age=60*60*24*365)
    response.set_cookie('series', '/series/{}|{}'.format(urllib.parse.quote(series), series), max_age=60*60*24*365)
    return response

@app.route('/seriess')
def seriess():
    items = []
    up = None
    home = get_home_link()

    filter = get_filter()

    last = None
    index = []
    for series in backend.get_seriess(filter = filter):
        if (series[0:1] != last):
            last = series[0:1]
            items.append({ 'name':last })
            index.append({ 'url':'#{}'.format(last), 'text':last })

        items.append({ 'url':'/series/{}'.format(urllib.parse.quote(series)), 'text':series, 'name':None })
    nav = {'up':up, 'home':home }
    return render_template('seriess.html', items = items, nav = nav, index = index)

@app.route('/take/<int:year>/<int:month>')
def take(year, month):
    beacon = '{}/{}'.format(year, month)
    backend.delete_beacon(beacon)
    return redirect('/dates/' + beacon)

@app.route('/traverse/<method>/<int:id>')
def traverse(method, id):
    response = make_response(redirect('/read/{}'.format(id)))
    if (method =='series'):
        response.set_cookie('traversal', 'series', max_age=60*60*24*365)
    else:
        response.set_cookie('traversal', 'date', max_age=60*60*24*365)
    return response
