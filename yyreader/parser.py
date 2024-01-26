
from datetime import datetime,timedelta
from dateutil.relativedelta import relativedelta
import minorimpact
import os
import os.path
import re
import requests
import time

formats = [
            # Fin Fang Four 001 [20081126].cbz
            '^(?P<series>.+) (?P<issue>-\d+[^ ]*) \[(?P<year>\d\d\d\d)(?P<month>\d\d)(?P<day>\d\d)\]\.(?P<extension>cb[rz])$',
            # 198900 Damage Control 001.cbr
            '^(?P<year>\d\d\d\d)00 (?P<series>.+) (?P<issue>\d+[^ ]*)\.(?P<extension>cb[rz])$',
            # 199800 Fantastic Four 1:2.cbr
            '^(?P<year>\d\d\d\d)(?P<month>\d\d) (?P<series>.+) (?P<issue>1:2)\.(?P<extension>cb[rz])$',
            # 198912 Damage Control 001.cbr
            '^(?P<year>\d\d\d\d)(?P<month>\d\d) (?P<series>.+) (?P<issue>\d+[^ ]*)\.(?P<extension>cb[rz])$',
            # 20050518 Official Handbook of the Marvel Universe - Teams 2005 001.cbz
            '^(?P<year>\d\d\d\d)(?P<month>\d\d)(?P<day>\d\d) (?P<series>.+) (?P<issue>\d+[^ ]*)\.(?P<extension>cb[rz])$',
            # 199707 Ghost Rider v2 -1.cbz
            '^(?P<year>\d\d\d\d)(?P<month>\d\d) (?P<series>.+) (?P<issue>-\d+[^ ]*)\.(?P<extension>cb[rz])$',
            # Damage Control (1989) 001 (1989-12-01).cbr
            '^(?P<series>.+) \((?P<volume>\d\d\d\d)\) (?P<issue>\d+[^ ]*) \((?P<year>\d\d\d\d)-(?P<month>\d\d)-(?P<day>\d\d)\)\.(?P<extension>cb[rz])$',
            # Damage Control (1989-2) 001 (1989-12-01).cbr
            '^(?P<series>.+) \((?P<volume>\d\d\d\d-\d)\) (?P<issue>\d+[^ ]*) \((?P<year>\d\d\d\d)-(?P<month>\d\d)-(?P<day>\d\d)\)\.(?P<extension>cb[rz])$',
            # Earth X (1999)/Earth X (1999) ½ (2000-01-01).cbz
            '^(?P<series>.+) \((?P<volume>\d\d\d\d[^\)]*)\) (?P<issue>[^ ]+) \((?P<year>\d\d\d\d)-(?P<month>\d\d)-(?P<day>\d\d)\)\.(?P<extension>cb[rz])$',
            '^(?P<series>.+) \((?P<volume>\d\d\d\d[^\)]*)\) (?P<issue>\d+[^ ]*) \((?P<year>\d\d\d\d)-(?P<month>\d\d)\)\.(?P<extension>cb[rz])$',
            '^(?P<series>.+) \((?P<volume>\d\d\d\d[^\)]*)\) (?P<issue>\d+[^ ]*) \((?P<year>\d\d\d\d)\)\.(?P<extension>cb[rz])$',
            # Daredevil 359 (1996-12-01).cbz
            '^(?P<series>.+) (?P<issue>\d+[^ ]*) \((?P<year>\d\d\d\d)-(?P<month>\d\d)-(?P<day>\d\d)\)\.(?P<extension>cb[rz])$',
            '^(?P<series>.+) (?P<issue>\d+[^ ]*) \((?P<year>\d\d\d\d)-(?P<month>\d\d)\)\.(?P<extension>cb[rz])$',
            '^(?P<series>.+) (?P<issue>\d+[^ ]*) \((?P<year>\d\d\d\d)\)\.(?P<extension>cb[rz])$',
            # Hulk - Grand Design 001 - Monster (2022).cbr
            '^(?P<series>.+) (?P<issue>\d\d\d) - .+ \((?P<year>\d\d\d\d)\)\.(?P<extension>cb[rz])$',
            # Mighty Avengers 004.INH (2014).cbr
            '^(?P<series>.+) (?P<issue>\d+\.INH) \((?P<year>\d\d\d\d)\)\.(?P<extension>cb[rz])$',
            # Cataclysm Ultimate Comics 000.1 (2013).cbr
            '^(?P<series>.+) (?P<issue>\d+\.1) \((?P<year>\d\d\d\d)\)\.(?P<extension>cb[rz])$',
            # Avengers Assemble 015AU.cbz
            '^(?P<series>.+) (?P<issue>\d+AU)\.(?P<extension>cb[rz])$',
            # Marvel Previews 008.cbz
            '^(?P<series>.+) (?P<issue>\d+)\.(?P<extension>cb[rz])$',
            # Iron Man 258.2.cbr
            '^(?P<series>.+) (?P<issue>\d+\.\d)\.(?P<extension>cb[rz])$',
            '^(?P<year>\d\d\d\d)00 (?P<series>.+)\.(?P<extension>cb[rz])$',
            '^(?P<year>\d\d\d\d)(?P<month>\d\d) (?P<series>.+)\.(?P<extension>cb[rz])$',
            '^(?P<series>.+) \((?P<year>\d\d\d\d)\)\.(?P<extension>cb[rz])$',
            '^(?P<series>.+)\.(?P<extension>cb[rz])$',
          ]

date_formats = [ '\((?P<month>\d\d)-(?P<day>\d\d)-(?P<year>\d\d\d\d)\)?',
                 '\(?(?P<year>\d\d\d\d)-(?P<month>\d\d)-(?P<day>\d\d)\)?',
                 '(?P<year>\d\d\d\d)(?P<month>\d\d)(?P<day>\d\d)',
                 '(?P<year>\d\d\d\d)(?P<month>\d\d)',
               ]

description_formats = [
                        '^<p><em>(?P<description>.+?)<\/em><\/p><p><em>(?P<description2>.+?)<\/em><\/p>.*$',
                        '^<p><em>(?P<description>.+?)<\/em><\/p>.*$',
                        '^<p><i>(?P<description>.+?)<\/i><\/p><p>(?P<description2>.+?)<\/p>.*$',
                        '^<p><i>(?P<description>.+?)<\/i><\/p>.*$',
                        '^<i>(?P<description>.+?)<\/i>.*$',
                        '^<p>(?P<description>.+?)<\/p>.*$',
                        '^<h3>(?P<description>.+?)<\/h3><p>(?P<description2>.+?)<\/p>.*$',
                    ]

description_subs = [
                    { 'm':'<h2> ?(.+)<\/h2><br\/>', 's':r'\1' },
                    { 'm':'<h2> ?(.+)<\/h2>', 's':r'\1' },
                    { 'm':'<u><b>(.+)<\/b><\/u><br\/>', 's':r'\1' },
                    { 'm':'<u><b>(.+)<\/b><\/u>', 's':r'\1' },
                    { 'm':'<br\/>', 's':r', ' },
                    { 'm':'<br \/>', 's':r', ' },
                    { 'm':', $', 's':r'' },
                 ]


series_formats = [ '^(?P<series>.+) \((?P<volume>.+)\)$',
                   '^(?P<series>.+)$'
                 ]

volume_formats = [ '^(?P<start_year>\d\d\d\d)$',
                   '^(?P<start_year>\d\d\d\d)[v\-](?P<ver>\d+)$',
                 ]

credit_pages = [ 'Scanned By Gird.jpg',
                 'z.jpg',
                 'zSoU-Nerd.jpg',
                 'xsou2.jpg',
                 'zaquila.jpg',
                 'zGGtag',
                 'zWater.jpg',
                 'zz-AVigilante407DCPScan-JLU.jpg',
                 'zzGGtag.jpg',
                 'zzoroboros.jpg',
                 'zzoronewtag10.jpg',
                 'zzorostnick11.jpg',
                 'zzzGlorithSolo.jpg',
               ]

cleanup_subs = [ { 'm':'\)\(', 's':') ('},
                 { 'm':'([^ ])\(', 's':r'\1 (' },
                 { 'm':'[\. ]+\.(cb[zr])$', 's':r'.\1' },
                 { 'm':' \[[^]]*\]+', 's':''},
                 { 'm':' \([^)]*[^)\d\-]+[^)]*\)', 's':'' },
                 { 'm':' \d+ of \d+ covers', 's':'' },
                 { 'm':' v\d+ (-?\d+)\.', 's':r' \1.' },
                 { 'm':' vII ', 's':r' ' },
                 { 'm':' #(\d+)', 's':r' \1' },
                 { 'm':' (\d)\.', 's':r' 00\1.' },
                 { 'm':' (\d\d)\.', 's':r' 0\1.' },
                 { 'm':'^\d+ ?- ', 's':'' },
                 { 'm':'__SLASH__', 's':'/' },
                 { 'm':'^FCBD (\d\d\d\d) ', 's':r'Free Comic Book Day \1 ' },
                 { 'm':'Marvel Universe - Avengers Earth\'s Mightiest Heroes', 's':'Avengers Earth\'s Mightiest Heroes' },
                 { 'm':'Marvel Universe - Ultimate Spider-Man', 's':'Ultimate Spider-Man' },
                 { 'm':' - Marvel Legacy Primer Pages \((\d\d\d\d)\)', 's':r' - Marvel Legacy Primer Pages 001 (\1)' },
                 { 'm':'^\d+ - House of M - ', 's':'' },
                 { 'm':r'Marvel Graphic Novel No (\d+) - .*\.(cb[rz])', 's':r'Marvel Graphic Novel \1.\2' },
                 { 'm':' - ', 's':': ', 'c':1 },
                 { 'm':' Book 1 of \d+', 's':' 001' },
                 { 'm':' Book 2 of \d+', 's':' 002' },
                 { 'm':' Book One of [^ \.]+', 's':' 001' },
                 { 'm':' Book Two of [^ \.]+', 's':' 002' },
                 { 'm':' Book Three of [^ \.]+', 's':' 003' },
                 { 'm':' Book Four of [^ \.]+', 's':' 004' },
                 { 'm':' Book One', 's':' 001' },
                 { 'm':' Book Two', 's':' 002' },
                 { 'm':' Book Three', 's':' 003' },
                 { 'm':' Book Four', 's':' 004' },
                 { 'm':' Part One', 's':' 001' },
                 { 'm':' Part Two', 's':' 002' },
                 { 'm':' Part Three', 's':' 003' },
                 { 'm':' Part Four', 's':' 004' },
                 { 'm':' -001', 's':' -1' },
                 { 'm':' \d\dpg digital scan by [^ \.]+', 's':'' },
                 { 'm':' \d\dpg scanned by [^ \.]+', 's':'' },
                 { 'm':' c2c scanned by [^ \.]+', 's':'' },
                 #{ 'm':'001 1:2', 's':'1½' },
                 #{ 'm':'1:2', 's':'½' },
               ]

series_subs = [
                { 'm': '(.+) starring .*', 's': r'\1' },
                { 'm': '(Marvel Action Hour) featuring (.*)', 's': r'\1 - \2' },
                { 'm': '(.+) featuring .*', 's': r'\1' },
                { 'm': 'Astonishing Tales and .*', 's': 'Astonishing Tales' },
                { 'm': 'Marvel Premiere and .*', 's': 'Marvel Premiere' },
                { 'm': 'Jungle Action & Black Panther', 's': 'Jungle Action' },
                { 'm': 'Marvel Spotlight and .*', 's': 'Marvel Spotlight' },
                { 'm': 'Marvel Team-Up: .*', 's': 'Marvel Team-Up' },
                { 'm': 'Marvel Two In One: .*', 's': 'Marvel Two-in-One' },
                { 'm': 'Marvel Two-in-One: .*', 's': 'Marvel Two-in-One' },
                { 'm': 'Supernatural Thrillers and .*', 's': 'Supernatural Thrillers' },
                { 'm': 'Peter Parker the Spectacular Spider-Man', 's':'The Spectacular Spider-Man' },
                { 'm': 'US1', 's':'U.S. 1' },
             ]

def FileNameException(Exception):
    pass

def make_dir(data, args = minorimpact.default_arg_flags):
    publisher = data["publisher"]
    series = series_filename(data['series'])
    volume = data['volume']
    return f'{publisher}/{series} ({volume})'

def make_name(data, extension, directors_cut = False, args = minorimpact.default_arg_flags):
    if ('issue' not in data):
        raise Exception("'issue' not found in comic data")

    if ('date' not in data or data['date'] is None):
        raise Exception(f"'date' not in data")

    if ('series' not in data or data['series'] is None):
        raise Exception(f"'series' not in data")

    issue = series_filename(data['issue'])
    series = series_filename(data['series'])
    volume = data['volume']
    return f"{series} ({volume}) {issue} ({data['date']}).{extension}"

def make_volume(start_year, ver = None, debug = False):
    volume = start_year
    if (ver is not None):
        volume = volume + '-' + ver
    return volume

def massage_description(description, args = minorimpact.default_arg_flags, debug = False):
    if (args.debug): debug = True

    if (debug): print("original description:", description)
    for f in description_formats:
        m = re.search(f, description)
        if (m is not None):
            if (debug): print("matched description {}".format(f))
            g = m.groupdict()
            if 'description' in g: description = g['description']
            if 'description2' in g: description = description + ':' + g['description2']
            break
            #print("FOUND",description)

    #if (debug): print("description2:", description)
    for c in description_subs:
        count = 0
        if 'c' in c:
            count = c['c']
        description = re.sub(c['m'], c['s'], description, count = count)
        #if (debug): print("'{}' -> '{}'".format(c['m'], c['s'])

    if (debug): print("final description:", description)
    return description

def massage_issue(issue, directors_cut = False):
    issue = re.sub('^0+','', issue)

    if (issue == '1:2'): issue = '½'
    if (issue == '' or re.search('^\.', issue)): issue = f'0{issue}'
    issue = issue.upper()
    m = re.search('^(\d+)\.(.+)$', issue)
    if (m is not None):
        i = m.group(1)
        extra_crap = m.group(2)
        if (int(i) < 10):
            i = f'00{i}'
        elif (int(i) < 100):
            i = f'0{i}'
        issue = i
        if (extra_crap not in ('NOW', 'INH')):
            issue = f'{issue}.{extra_crap}'
    elif (re.search('^\d+$', issue)):
        if (int(issue) < 10):
            issue = f'00{issue}'
        elif (int(issue) < 100):
            issue = f'0{issue}'
    if (directors_cut is True):
        issue = f'{issue}.DC'

    return issue

def convert_name_to_date(comic):
    m = re.search('([^/]+) \((\d\d\d\d)\) (\d+[^ ]+) \((\d\d\d\d)-(\d\d)-(\d\d)\)\.(cb[rz])$', comic)
    if (m is None):
        return None
    series = m.group(1)
    start_year = m.group(2)
    issue = m.group(3)
    year = m.group(4)
    month = m.group(5)
    day = m.group(6)
    extension = m.group(7)
    return f'{year}/{month}/{year}-{month}-{day} {series} ({start_year}) {issue}.{extension}'

def is_credit_page(filename):
    for credit_page in credit_pages:
        if filename == credit_page or re.search(credit_page, filename):
            return True
    return False

def parse(comic_file, year = None, verbose = False, debug = False):
    """Analyze the file name and pull as much information about it as possible."""
    if (debug): print("parsing {}".format(comic_file))

    data = { 'directors_cut': False }

    data['size'] = 0
    if (os.path.exists(comic_file)):
        data['size'] = os.path.getsize(comic_file)

    if (re.search('\.cb[rz]$', comic_file, re.I) is None):
        raise Exception("invalid file type")

    #if (debug is True): print(comic_file)

    day = None
    extension = None
    issue = None
    month = None
    start_year = ''
    date = None
    series = None
    ver = ''
    volume = ''

    (dirname, basename) = os.path.split(comic_file)
    if (re.search('fc only', basename, re.IGNORECASE) is not None or re.search('Cover ONLY', basename, re.IGNORECASE) is not None):
        raise Exception("Front cover only")

    for c in cleanup_subs:
        count = 0
        if 'c' in c:
            count = c['c']
        basename = re.sub(c['m'], c['s'], basename, count = count)
        #print(basename)

    if (re.search(r" - [dD]irector'?s? [Cc]ut", basename) is not None):
        data['directors_cut'] = True
        basename = re.sub(" - [dD]irector'?s? [cC]ut", '', basename)

    # Scan the parent directories for something that looks like a date.
    date = parse_date(dirname)
    if 'day' in date and date['day'] is not None: day = date['day']
    if 'month' in date and date['month'] is not None: month = date['month']
    if 'year' in date and date['year'] is not None: year = date['year']

    for f in formats:
        if (debug): print(f"testing '{f}' ({basename})")
        m = re.search(f, basename)
        if (m is not None):
            if (debug): print(f"matched format '{f}'")
            g = m.groupdict()
            if 'day' in g: day = g['day']
            if 'extension' in g: extension = g['extension']
            if 'issue' in g: issue = g['issue']
            if 'month' in g: month = g['month']
            if 'series' in g: series = g['series']
            if 'volume' in g: volume = g['volume']
            if 'year' in g and year is None: year = g['year']
            break

    if (volume is not None):
        parsed_volume = parse_volume(volume)
        if parsed_volume is not None:
            start_year = parsed_volume['start_year']
            ver = parsed_volume['ver']

    if (issue is None): issue = '001'
    if (series is None or extension is None):
        raise FileNameException("invalid filename")

    if (re.search('amazing spider-man', series) and year is not None):
        if (int(year) >= 1999 and int(year) < 2014 and (int(issue) <= 58)):
            issue = int(issue) + 441

    for c in series_subs:
        count = 0
        if 'c' in c:
            count = c['c']
        series = re.sub(c['m'], c['s'], series, count = count)

    #while (len(issue) > 1 and re.search('^0', issue)):
    #    issue = re.sub('^0','', issue)

    if (ver is None): ver = ''

    #if (debug): print(f"parsed series:{series},stat_year:{start_year},issue:{issue},year:{year},month:{month},day:{day}")
    data['extension'] = extension
    data['issue'] = issue
    data['start_year'] = start_year
    data['series'] = series_filename(series, reverse = True)
    data['ver'] = ver
    data['volume'] = volume
    data['date'] = ''

    if (year is not None):
        data['year'] = year
        if (month is not None and day is not None and day != '00'):
            data['date'] = f'{year}-{month}-{day}'
            data['day'] = day
            data['month'] = month
        elif (month is not None and month != '00'):
            data['date'] = f'{year}-{month}-01'
            data['day'] = '01'
            data['month'] = month
        if (re.search('^\d+$', year) and issue is not None and re.search('^\d+$', issue) and month is not None and month != '00' and re.search('^\d+$', month)):
            months = int(issue) - 1
            if (re.search(' annual',series.lower())):
                months = (int(issue) - 1) * 12
            est_start_date = datetime(int(year), int(month), 1) - relativedelta(months = months)
            data['est_start_year'] = est_start_date.year

    return data

def parse_date(search_date, debug = False):
    date = {}
    for f in date_formats:
        m = re.search(f, search_date)
        if (m is not None):
            if (debug): print("date '{}' matched '{}'".format(search_date, f))
            g = m.groupdict()
            if 'day' in g: date['day'] = g['day']
            if 'month' in g: date['month'] = g['month']
            if 'year' in g: date['year'] = g['year']
            break

    return date

def parse_series(search_series, debug = False):
    series = None
    volume = None

    for f in series_formats:
        m = re.search(f, search_series)
        if (m is not None):
            if (debug): print(f"'{search_series}' matched series format '{f}'")
            g = m.groupdict()
            if 'series' in g: series = g['series']
            if 'volume' in g: volume = parse_volume(g['volume'], debug = debug)
            if (debug): print("series:'{}', volume:'{}'".format(series, volume))
            break

    if (series is not None):
        return {'series':series, 'volume':volume}
    return None

def parse_volume(volume, debug = False):
    start_year = None
    ver = None
    for f in volume_formats:
        m = re.search(f, volume)
        if (m is not None):
            if (debug): print(f"matched volume format '{f}'")
            g = m.groupdict()
            if 'start_year' in g: start_year = g['start_year']
            if 'ver' in g: ver = g['ver']
            if (debug): print("start_year:'{}', ver:'{}'".format(start_year, ver))
            break
    if (start_year is not None):
        return {'start_year':start_year, 'ver':ver}
    return None

def publisher_filename(publisher, reverse = False, debug = False):
    """Turn the publisher name into something appropriate for a filename (or the opposite if reverse is True)."""

    publisher = publisher.strip()
    if (reverse is True):
        publisher = re.sub('__SLASH__', '/', publisher)
    else:
        publisher = re.sub('/','__SLASH__', publisher)

    return publisher

def series_filename(series, reverse = False, debug = False):
    """Turn the series name into something appropriate for a filename (or the opposite if reverse is True)."""

    parsed_series = parse_series(series, debug = debug)
    series = parsed_series['series']
    start_year = None
    ver = None
    if (parsed_series['volume'] is not None):
        start_year = parsed_series['volume']['start_year']
        ver = parsed_series['volume']['ver']

    if (reverse is True):
        series = re.sub('^(.+), A$', r'A \1', series)
        series = re.sub('^(.+), An$', r'An \1', series)
        series = re.sub('^(.+), The$', r'The \1', series)
        series = re.sub('__SLASH__', '/', series)
    else:
        series = re.sub('^A (.+)$', r'\1, A', series)
        series = re.sub('^An (.+)$', r'\1, An', series)
        series = re.sub('^The (.+)$', r'\1, The', series)
        series = re.sub('/','__SLASH__', series)
        series = series.strip()

    return series

