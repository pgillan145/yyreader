
from datetime import datetime,timedelta
from dateutil.relativedelta import relativedelta
from fuzzywuzzy import fuzz
import json
import minorimpact
import os
import os.path
import pickle
import re
import requests
import sys
import time
import urllib3
import xml.etree.ElementTree as ET

from . import parser

base_url = 'https://comicvine.gamespot.com/api'
cache = { 'results': {} }
cache_setup = False
date_formats = [ '\((?P<month>\d\d)-(?P<day>\d\d)-(?P<year>\d\d\d\d)\)',
                 '\((?P<year>\d\d\d\d)-(?P<month>\d\d)-(?P<day>\d\d)\)',
                 '(?P<year>\d\d\d\d)(?P<month>\d\d)(?P<day>\d\d)',
                 '(?P<year>\d\d\d\d)(?P<month>\d\d)' ]
headers = {'User-Agent': 'yyreader'}
params = {}


def get_issue(volume_id, issue, api_key, args = minorimpact.default_arg_flags, cache_file = '/tmp/yyreader.cache'):
    url = base_url + f'/volume/4050-{volume_id}/?api_key=' + api_key + f'&format=json&field_list=id,name,start_year,count_of_issues,publisher,first_issue'
    if (args.debug is True): print(url)
    volume_name = parser.massage_volume(get_results(url, cache_file = cache_file)[0]['name'])

    url = base_url + '/issues/?api_key=' + api_key + f'&format=json&sort=name:asc&filter=volume:{volume_id}&field_list=id,issue_number,name,store_date,story_arc_credits,cover_date'
    if (args.debug is True): print(url)
    results = get_results(url, max = None, cache_file = cache_file)
    i = len(results) - 1
    while i >= 0:
        if ('store_date' not in results[i] or results[i]['store_date'] is None) and ('cover_date' not in results[i] or results[i]['cover_date'] is None):
            del results[i]
        i = i - 1

    issue = parser.massage_issue(issue)
    if (args.debug): print(f"searching for issue #{issue} for {volume_name}")
    for i in results:
        if (parser.massage_issue(i['issue_number']) == issue):
            return i
    return None

def get_issue_details(issue_id, api_key, args = minorimpact.default_arg_flags, cache_file = '/tmp/yyreader.cache'):
    url = base_url + f'/issue/4000-' + str(issue_id) + '/?api_key=' + api_key + f'&format=json&field_list=id,issue_number,name,store_date,story_arc_credits,cover_date'
    if (args.debug is True): print(url)
    results = get_results(url, cache_file = cache_file)
    return results[0]

last_result = datetime.now()
def get_results(url, offset=0, limit = 100, max = 100, cache_results = True, cache_file = '/tmp/yyreader.cache'):
    global cache
    global last_result
    seconds_between_requests = 3

    offset_url = url + f'&limit={limit}&offset={offset}'

    text = None
    if (cache_results is True and offset_url in cache['results'] and cache['results'][offset_url]['mod_date'] > (datetime.now() - timedelta(weeks = 4))):
        text = cache['results'][offset_url]['text']
    else:
        while(last_result > datetime.now() - timedelta(seconds=seconds_between_requests)):
            time.sleep(1)
        urllib3.disable_warnings()
        r = requests.get(offset_url, headers=headers, params=params, verify=False)
        last_result = datetime.now()
        text = r.text
        data = json.loads(text)
        if (data['error'] == 'OK' and cache_results is True):
            cache['results'][offset_url] = { 'text': r.text, 'mod_date': datetime.now() }
            with open(cache_file, 'wb') as f:
                pickle.dump(cache, f)
    
    if (text is None):
        raise Exception(f"Unable to request '{offset_url}'")

    data = json.loads(text)
    if (data['error'] != 'OK'):
        raise Exception("Request error:" + data['error'])
    
    if (data['number_of_total_results'] == 0):
        raise Exception("No results.")

    if (max is None):
        max = data['number_of_total_results']

    results = []
    if (isinstance(data['results'], list)):
        results = results + data['results']
    elif (isinstance(data['results'], dict)):
        results = results + [data['results']]
    
    if (data['number_of_total_results'] > (limit + offset) and (limit + offset) < max):
        results = results + get_results(url, limit = limit, offset = offset + limit, max = max, cache_results = cache_results, cache_file = cache_file)

    return results

def search(data, api_key, args = minorimpact.default_arg_flags, cache_file = '/tmp/yyreader.cache'):
    global cache 
    if (('date' not in data or data['date'] is None) and args.yes is True):
        raise Exception("Can't auto confirm without file date. skipping.")

    if (cache_setup is False):
        setup_cache(cache_file)

    test_title = data['title']

    result = None
    match_issue = None
    while (result is None):
        start_year = None
        if ('start_year' in data):
            start_year = data['start_year']
        elif ('est_start_year' in data):
            start_year = data['est_start_year']

        results = search_volumes(test_title, api_key, start_year = start_year, year = data['year'], args = args, cache_file = cache_file)

        if (args.verbose): print(f"found {len(results)} result(s) for '{test_title}'")
        item = 0
        default = 0
        max_lev = 0
        issue_date = {}
        if ('date' in data and data['date'] is not None):
            if (args.verbose): print(f"looking for an issue #{data['issue']} released on {data['date']}")
            for r in results:
                i = get_issue(r['id'], data['issue'], api_key, args = args, cache_file = cache_file)
                if (i is not None):
                    #print(i)
                    date = None
                    if ('store_date' in i and i['store_date'] is not None):
                        date = i['store_date']
                    elif ('cover_date' in i and i['cover_date'] is not None):
                        date = i['cover_date']
                        # Sometimes the cover daye is the first of day of the month, sometimes it's the last, so
                        #   for our generic 'date' comparison field, just force it to be the first, no one cares.
                        date = re.sub('-\d\d$', '-01', date)

                    if (date is not None):
                        if (args.verbose): print(f"found {r['name']} #{i['issue_number']} released on {date}")
                        issue_date[r['id']] = date
                        if (date == data['date']):
                            result = r
                            match_issue = i
                            break

        if (result is not None or args.yes is True):
            break

        # We didn't find a date match, and we're not in auto-mode, so ask a grown-up for help.
        for r in results:
            item = item + 1
            if (fuzz.ratio(test_title,r['name']) > max_lev):
                default = item
                max_lev = fuzz.ratio(test_title,r['name'])
            menu_item = f"{item}: {r['name']} ({r['start_year']}) - {r['publisher']['name']}, {r['count_of_issues']} issue(s)"
            if (r['id'] in issue_date):
                menu_item = f"{menu_item} - {issue_date[r['id']]}"
            print(menu_item)
        input_string = "Choose a volume"
        if (default > 0):
            input_string = f"{input_string} [{default}]"
        input_string = f"{input_string}: "
        pick = input(input_string).rstrip()

        if (pick == '' and default > 0):
            pick = f'{default}'

        if (pick == '0' or pick == '-' or pick == '_'):
            return None
        elif (pick == '?'):
            print("enter one of the following options:")
            print(f"  '0'/'-': Skip this item")
            if (len(results) > 0):
                print(f"  '1' - '{len(results)}': select one of the volumes above")
            print("  '####-#####': a comicvine volume id")
            print("  'https://XXXXX/####-#####': a url containing a comicvine volume id")
            print("  'XXXXXX': a new search string")
            print("  'q': quit")
            continue
        elif (pick == 'q'):
            sys.exit()
        elif (pick == ''):
            return None

        if (re.search('^\d+$', pick) and int(pick) <= len(results)):
            result = results[int(pick)-1]
        elif (re.search('\d+-\d+', pick)):
            m = re.search('^http.*?\/(\d+-\d+)\/', pick)
            if (m is not None):
                volume_id = m.group(1)
            else:
                volume_id = pick
            url = base_url + f'/volume/{volume_id}/?api_key=' + api_key + f'&format=json&field_list=id,name,start_year,count_of_issues,publisher,first_issue'
            if (args.debug is True): print(url)
            results = get_results(url, cache_file = cache_file)
            result = results[0]
        else:
            test_title = pick

    if (result is None):
        raise Exception("can't find a volume")

    volume_id = result['id']
    if (args.debug): print(result)

    comicvine_data = {}
    comicvine_data['volume_id'] = volume_id
    comicvine_data['volume_name'] = result['name']
    comicvine_data['start_year'] = result['start_year']
    comicvine_data['publisher'] = result['publisher']['name']

    i = match_issue
    if i is None:
        i = get_issue(volume_id, data['issue'], api_key, args = args, cache_file = cache_file)

    if (i is not None):
        comicvine_data['issue'] = i['issue_number']
        comicvine_data['issue_id'] = i['id']
        comicvine_data['issue_name'] = None
        comicvine_data['store_date'] = i['store_date']
        comicvine_data['cover_date'] = i['cover_date']

        if ('name' in i and i['name'] is not None):
            comicvine_data['issue_name'] = i['name']

        if ('store_date' in i and i['store_date'] is not None):
            comicvine_data['date'] = i['store_date']
        elif ('cover_date' in i):
            # Cover date is always just a month (i think), so the day should always be
            #   either the first or the last day of the month, but no one cares, so force it
            #   to be the first -- way easier.
            comicvine_data['date'] = re.sub('-\d\d$', '-01', i['cover_date'])
    else:
        if (args.debug): print(f"NO ISSUE RETURNED FROM get_issue({volume_id},{issue})")

    return comicvine_data

def search_volumes(title, api_key, start_year = None, year = None, args = minorimpact.default_arg_flags, cache_results = True, cache_file = '/tmp/yyreader.cache'):
    title = parser.massage_volume(title, reverse = True)
    title = re.sub('^Amazing Spider-Man$', 'The Amazing Spider-Man', title)
    title = re.sub('^Immortal Hulk$', 'The Immortal Hulk', title)
    if (args.debug): print(f"search title:'{title}',start_year:'{start_year}',year:'{year}'")

    results = []
    url = base_url + '/search/?api_key=' + api_key + f'&format=json&query={title}&resources=volume&field_list=id,name,start_year,count_of_issues,publisher,first_issue'
    #if (args.debug): print(url)
    try:
        results = get_results(url, max = 100, cache_results = cache_results, cache_file = cache_file)
    except Exception as e:
        pass
    
    title_year = {}
    if (len(results) > 0):
        i = len(results) - 1
        while i >= 0:
            # Eliminate the volumes we can be reasonably certain are not correct based on the information
            #   we were provided or bad search results.
            if results[i]['start_year'] is None \
              or re.search('^\d+$', results[i]['start_year']) is None \
              or results[i]['first_issue'] is None \
              or ( results[i]['first_issue']['name'] is not None and (re.search('TPB$', results[i]['first_issue']['name']) or re.search('^Volume \d+$', results[i]['first_issue']['name']))) \
              or results[i]['publisher'] is None  \
              or (results[i]['publisher']['name'] not in ('Marvel', 'Epic', 'IDW', 'Star Comics', 'Max', 'Max Comics', 'Atlas', 'Curtis Magazine', 'Curtis Magazines')) \
              or (title.lower() == 'the amazing spider-man' and int(year) < 2014 and results[i]['start_year'] != '1963') \
              or (year is not None and int(results[i]['start_year']) > int(year)+1):
              #or (start_year is not None and int(results[i]['start_year']) < (int(start_year) - 5))\
              #or (start_year is not None and int(results[i]['start_year']) > (int(start_year) + 5))\
              #or (fuzz.ratio(title,results[i]['name']) < 60) \
                del results[i]
                pass
            i = i - 1

        # If there are multiple volumes with identical titles, only keep the 'latest' one.
        results = sorted(results, key = lambda x:int(x['start_year']), reverse = True)
        i = len(results) - 1
        while i >= 0:
            if (results[i]['name'] in title_year):
                #del results[i]
                pass
            else:
                title_year[results[i]['name']] = results[i]['start_year']
            i = i - 1

        #results = sorted(results, key = lambda x:int(x['start_year']))
    return results

def setup_cache(cache_file):
    global cache
    global cache_setup

    if (os.path.exists(cache_file) is True):
        with open(cache_file, 'rb') as f:
            cache = pickle.load(f)
        if ('results' not in cache):
            cache['results'] = {}

    urls = [key for key in cache['results']]
    for url in urls:
        if cache['results'][url]['mod_date'] < (datetime.now() - timedelta(weeks = 4)):
            del cache['results'][url]

    cache_setup = True
