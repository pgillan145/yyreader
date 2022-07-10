
from datetime import datetime,timedelta
from dateutil.relativedelta import relativedelta
import minorimpact
import os
import os.path
import re
import requests
import time

date_formats = [ '\((?P<month>\d\d)-(?P<day>\d\d)-(?P<year>\d\d\d\d)\)',
                 '\((?P<year>\d\d\d\d)-(?P<month>\d\d)-(?P<day>\d\d)\)',
                 '(?P<year>\d\d\d\d)(?P<month>\d\d)(?P<day>\d\d)',
                 '(?P<year>\d\d\d\d)(?P<month>\d\d)' ]

formats = [ '^(?P<year>\d\d\d\d)00 (?P<volume>.+) (?P<issue>\d+[^ ]*)\.(?P<extension>cb[rz])$',
            '^(?P<year>\d\d\d\d)(?P<month>\d\d) (?P<volume>.+) (?P<issue>\d+[^ ]*)\.(?P<extension>cb[rz])$',
            # Damage Control (1989v2) 001 (1989-12-01).cbr
            '^(?P<volume>.+) \((?P<start_year>\d\d\d\d)-(?P<ver>\d)\) (?P<issue>\d+[^ ]*) \((?P<year>\d\d\d\d)-(?P<month>\d\d)-(?P<day>\d\d)\)\.(?P<extension>cb[rz])$',
            # Alien Legion (1984) 001 (1984-06-01).cbr
            '^(?P<volume>.+) \((?P<start_year>\d\d\d\d)\) (?P<issue>\d+[^ ]*) \((?P<year>\d\d\d\d)-(?P<month>\d\d)-(?P<day>\d\d)\)\.(?P<extension>cb[rz])$',
            # Earth X (1999)/Earth X (1999) ½ (2000-01-01).cbz
            '^(?P<volume>.+) \((?P<start_year>\d\d\d\d)\) (?P<issue>[^ ]+) \((?P<year>\d\d\d\d)-(?P<month>\d\d)-(?P<day>\d\d)\)\.(?P<extension>cb[rz])$',
            '^(?P<volume>.+) \((?P<start_year>\d\d\d\d)\) (?P<issue>\d+[^ ]*) \((?P<year>\d\d\d\d)-(?P<month>\d\d)\)\.(?P<extension>cb[rz])$',
            '^(?P<volume>.+) \((?P<start_year>\d\d\d\d)\) (?P<issue>\d+[^ ]*) \((?P<year>\d\d\d\d)\)\.(?P<extension>cb[rz])$',
            '^(?P<volume>.+) (?P<issue>\d+[^ ]*) \((?P<year>\d\d\d\d)-(?P<month>\d\d)-(?P<day>\d\d)\)\.(?P<extension>cb[rz])$',
            '^(?P<volume>.+) (?P<issue>\d+[^ ]*) \((?P<year>\d\d\d\d)-(?P<month>\d\d)\)\.(?P<extension>cb[rz])$',
            '^(?P<volume>.+) (?P<issue>\d+[^ ]*) \((?P<year>\d\d\d\d)\)\.(?P<extension>cb[rz])$',
            # Hulk - Grand Design 001 - Monster (2022).cbr
            '^(?P<volume>.+) (?P<issue>\d\d\d) - .+ \((?P<year>\d\d\d\d)\)\.(?P<extension>cb[rz])$',
            '^(?P<volume>.+) (?P<issue>\d+)\.(?P<extension>cb[rz])$',
            '^(?P<year>\d\d\d\d)00 (?P<volume>.+)\.(?P<extension>cb[rz])$',
            '^(?P<year>\d\d\d\d)(?P<month>\d\d) (?P<volume>.+)\.(?P<extension>cb[rz])$',
            '^(?P<volume>.+) \((?P<year>\d\d\d\d)\)\.(?P<extension>cb[rz])$',
            '^(?P<volume>.+)\.(?P<extension>cb[rz])$',
          ]

credit_pages = [ 'z.jpg',
                 'zzoroboros.jpg',
                 'zzGGtag.jpg',
                 'zWater.jpg',
               ]

cleanup_subs = [ { 'm':'\)\(', 's':') ('},
                 { 'm':'([^ ])\(', 's':r'\1 (' },
                 { 'm':'[. ]\.(cb[zr])$', 's':r'.\1' },
                 { 'm':' \[[^]]*\]+', 's':''},
                 { 'm':' \([^)]*[^)\d\-]+[^)]*\)', 's':'' },
                 { 'm':' \d+ of \d+ covers', 's':'' },
                 { 'm':' v\d+ (\d+)\.', 's':r' \1.' },
                 { 'm':' vII ', 's':r' ' },
                 { 'm':' #(\d+)', 's':r' \1' },
                 { 'm':' (\d)\.', 's':r' 00\1.' },
                 { 'm':' (\d\d)\.', 's':r' 0\1.' },
                 { 'm':'^\d+ ?- ', 's':'' },
                 { 'm':'__SLASH__', 's':'/' },
                 { 'm':'^FCBD (\d\d\d\d) ', 's':r'Free Comic Book Day \1 ' },
                 { 'm':' - Marvel Legacy Primer Pages \((\d\d\d\d)\)', 's':r' - Marvel Legacy Primer Pages 001 (\1)' },
                 { 'm':'^\d+ - House of M - ', 's':'' },
                 { 'm':' - ', 's':': ', 'c':1 },
               ]

volume_subs = [ 
                { 'm': '(.+) starring .*', 's': r'\1' },
                { 'm': '(.+) featuring .*', 's': r'\1' },
                { 'm': 'Astonishing Tales and .*', 's': 'Astonishing Tales' },
                { 'm': 'Marvel Premiere and .*', 's': 'Marvel Premiere' },
                { 'm': 'Jungle Action & Black Panther', 's': 'Jungle Action' },
                { 'm': 'Marvel Spotlight and .*', 's': 'Marvel Spotlight' },
                { 'm': 'Marvel Team-Up: .*', 's': 'Marvel Team-Up' },
                { 'm': 'Marvel Two In One: .*', 's': 'Marvel Two-in-One' },
                { 'm': 'Marvel Two-in-One: .*', 's': 'Marvel Two-in-One' },
                { 'm': 'Supernatural Thrillers and .*', 's': 'Supernatural Thrillers' },
             ]

def make_date(data, extension, ver = None, directors_cut = False):
    if ('issue' not in data):
        raise Exception("'issue' not found in comic data")

    if ('date' not in data or data['date'] is None):
        raise Exception(f"'date' not in data")

    if ('volume_name' not in data or data['volume_name'] is None):
        raise Exception(f"'volume_name' not in data")

    issue = massage_issue(data['issue'], directors_cut = directors_cut)
    volume_name = massage_volume(data['volume_name'])
    start_year = data['start_year']
    if (ver is not None):
        start_year = start_year + "-" + ver
    return f"{data['date']} {volume_name} ({start_year}) {issue}.{extension}"

def make_name(data, extension, ver = None, directors_cut = False):
    if ('issue' not in data):
        raise Exception("'issue' not found in comic data")

    if ('date' not in data or data['date'] is None):
        raise Exception(f"'date' not in data")

    if ('volume_name' not in data or data['volume_name'] is None):
        raise Exception(f"'volume_name' not in data")

    issue = massage_issue(data['issue'], directors_cut = directors_cut)
    volume_name = massage_volume(data['volume_name'])
    start_year = data['start_year']
    if (ver is not None):
        start_year = start_year + "-" + ver
    return f"{volume_name} ({start_year}) {issue} ({data['date']}).{extension}"

def massage_issue(issue, directors_cut = False):
    issue = re.sub('^0+','', issue)

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

def massage_volume(volume, reverse = False):
    if (reverse is True):
        volume = re.sub('^(.+), A$', r'A \1', volume)
        volume = re.sub('^(.+), An$', r'An \1', volume)
        volume = re.sub('^(.+), The$', r'The \1', volume)
        volume = re.sub('__SLASH__', '/', volume)
    else:
        volume = re.sub('^A (.+)$', r'\1, A', volume)
        volume = re.sub('^An (.+)$', r'\1, An', volume)
        volume = re.sub('^The (.+)$', r'\1, The', volume)
        volume = re.sub('/','__SLASH__', volume)
        volume = volume.strip()
    return volume

def convert_name_to_date(comic):
    m = re.search('([^/]+) \((\d\d\d\d)\) (\d+[^ ]+) \((\d\d\d\d)-(\d\d)-(\d\d)\)\.(cb[rz])$', comic)
    if (m is None):
        return None
    volume_name = m.group(1)
    start_year = m.group(2)
    issue = m.group(3)
    year = m.group(4)
    month = m.group(5)
    day = m.group(6)
    extension = m.group(7)
    return f'{year}/{month}/{year}-{month}-{day} {volume_name} ({start_year}) {issue}.{extension}'

def parse(comic_file, year = None, args = minorimpact.default_arg_flags):
    """Analyze the file name and pull as much information about it as possible."""
    if (args.verbose): print("Parsing {}".format(comic_file))

    data = { 'directors_cut': False }

    data['size'] = 0
    if (os.path.exists(comic_file)):
        data['size'] = os.path.getsize(comic_file)

    if (re.search('\.cb[rz]$', comic_file) is None):
        raise Exception("invalid file type")

    if (args.debug is True): print(comic_file)

    day = None
    extension = None
    issue = None
    month = None
    start_year = None
    date = None
    volume = None
    ver = None

    (dirname, basename) = os.path.split(comic_file)
    if (re.search('fc only', basename) is not None or re.search('cover ONLY', basename) is not None or re.search('cover only', basename) is not None):
        raise Exception("Front cover only")

    for c in cleanup_subs:
        count = 0
        if 'c' in c:
            count = c['c']
        basename = re.sub(c['m'], c['s'], basename, count = count)

    if (re.search(r" - [dD]irector'?s? [Cc]ut", basename) is not None):
        data['directors_cut'] = True
        basename = re.sub(" - [dD]irector'?s? [cC]ut", '', basename)
    if (args.debug): print("basename:" + basename)

    # Scan the parent directories for something that looks like a date.
    for f in date_formats:
        m = re.search(f, dirname)
        if (m is not None):
            g = m.groupdict()
            if 'day' in g: day = g['day']
            if 'month' in g: month = g['month']
            if 'year' in g: year = g['year']
            break

    for f in formats:
        if (args.debug): print(f"testing '{f}'")
        m = re.search(f, basename)
        if (m is not None):
            if (args.debug): print(f"matched format '{f}'")
            g = m.groupdict()
            if 'day' in g: day = g['day']
            if 'extension' in g: extension = g['extension']
            if 'issue' in g: issue = g['issue']
            if 'month' in g: month = g['month']
            if 'start_year' in g: start_year = g['start_year']
            if 'volume' in g: volume = g['volume']
            if 'ver' in g: ver = g['ver']
            if 'year' in g and year is None: year = g['year']
            break

    if (issue is None): issue = '001'
    if (volume is None or extension is None):
        raise FileNameException("invalid filename")

    if (re.search('amazing spider-man', volume) and year is not None):
        if (int(year) >= 1999 and int(year) < 2014 and (int(issue) <= 58)):
            issue = int(issue) + 441

    for c in volume_subs:
        count = 0
        if 'c' in c:
            count = c['c']
        volume = re.sub(c['m'], c['s'], volume, count = count)

    if (args.debug): print(f"parsed volume:{volume},issue:{issue},year:{year},month:{month},day:{day}")
    data['extension'] = extension
    data['issue'] = issue
    data['start_year'] = start_year
    data['volume'] = volume
    data['ver'] = ver
    data['year'] = year

    if (year is not None and month is not None and day is not None and day != '00'):
        data['date'] = f'{year}-{month}-{day}'
    elif (year is not None and month is not None and month != '00'):
        data['date'] = f'{year}-{month}-01'

    if (year is not None):
        if (re.search('^\d+$', year) and issue is not None and re.search('^\d+$', issue) and month is not None and month != '00' and re.search('^\d+$', month)):
            months = int(issue) - 1
            if (re.search(' annual',volume.lower())):
                months = (int(issue) - 1) * 12
            est_start_date = datetime(int(year), int(month), 1) - relativedelta(months = months)
            data['est_start_year'] = est_start_date.year
            
    return data
