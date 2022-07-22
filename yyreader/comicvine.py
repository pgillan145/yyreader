
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
cache = { 'results': {}, 'volumes': {} }
cache_setup = False
headers = {'User-Agent': 'yyreader'}
params = {}


def get_issue(volume_id, issue, api_key, args = minorimpact.default_arg_flags, cache_results = True, cache_file = '/tmp/yyreader.cache'):
    url = base_url + f'/volume/4050-{volume_id}/?api_key=' + api_key + f'&format=json&field_list=id,name,start_year,count_of_issues,publisher,first_issue'
    #if (args.debug is True): print(url)
    volume_results = get_results(url, cache_results = cache_results, cache_file = cache_file)
    
    volume_name = '{} ({})'.format(parser.massage_volume(volume_results[0]['name']), volume_results[0]['start_year'])

    url = base_url + '/issues/?api_key=' + api_key + f'&format=json&sort=name:asc&filter=volume:{volume_id}&field_list=id,issue_number,name,store_date,story_arc_credits,cover_date'
    #if (args.debug is True): print(url)
    results = get_results(url, max = None, cache_results = cache_results, cache_file = cache_file)
    i = len(results) - 1
    while i >= 0:
        if ('store_date' not in results[i] or results[i]['store_date'] is None) and ('cover_date' not in results[i] or results[i]['cover_date'] is None):
            del results[i]
        i = i - 1

    issue = parser.massage_issue(issue)
    if (args.debug): print(f"  searching for issue #{issue} of {volume_name}")
    for i in results:
        #if (args.debug): print(i)
        if (parser.massage_issue(i['issue_number']) == issue):
            return i
    return None

def get_issue_details(issue_id, api_key, args = minorimpact.default_arg_flags, cache_results = True, cache_file = '/tmp/yyreader.cache'):
    url = f'{base_url}/issue/4000-{issue_id}/?api_key={api_key}&format=json&field_list=id,issue_number,name,store_date,story_arc_credits,cover_date,person_credits,description,character_credits'
    #if (args.debug is True): print(url)
    results = get_results(url, cache_file = cache_file, cache_results = cache_results)
    #if (args.debug): print(results[0])
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
        if (data['error'] == 'OK'):
            cache['results'][offset_url] = { 'text': r.text, 'mod_date': datetime.now() }
            pickle_data = pickle.dumps(cache)
            done = False
            while done is False:
                try:
                    with open(cache_file, 'wb') as f:
                        f.write(pickle_data)
                    done = True
                except KeyboardInterrupt:
                    print("cache dump interrupted - retrying")
                    continue
    
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

def search(data, api_key, args = minorimpact.default_arg_flags, cache_results = True, cache_file = '/tmp/yyreader.cache'):
    global cache 
    if (('date' not in data or data['date'] is None) and args.yes is True):
        raise Exception("Can't auto confirm without file date. skipping.")

    use_cache = cache_results
    if (cache_setup is False):
        setup_cache(cache_file)

    test_volume = data['volume']
    if (test_volume in cache['volumes'] and use_cache):
        test_volume = cache['volumes'][test_volume]['volume']

    test_volume = parser.massage_volume(test_volume, reverse = True)

    result = None
    match_issue = None
    while (result is None):
        start_year = None
        if ('start_year' in data):
            start_year = data['start_year']
        elif ('est_start_year' in data):
            start_year = data['est_start_year']

        # Get an initial list of volumes from the site that we can start to check.
        results = search_volumes(test_volume, api_key, start_year = start_year, year = data['year'], args = args, cache_file = cache_file, cache_results = use_cache)

        if (args.verbose): print(f"  {len(results)} result(s) for '{test_volume}'")
        item = 0
        default = 0
        max_lev = 0
        issue_date = {}
        # If we have a date for the issue, then we can look through each volume for the given issue number to see if it has the
        #   same date.  If so, then then this is *probably* the correct volume.
        if (('date' in data and data['date'] is not None) or (re.search(r' Annual$', test_volume) and 'year' in data and data['year'] is not None and re.search(r'^\d\d\d\d$', data['year']))):
            if (args.verbose):
                if ('date' in data):
                    print(f"  looking for an issue #{data['issue']} released on {data['date']}")
                else:
                    print(f"  looking for an issue #{data['issue']} released in {data['year']}")
            for r in results:
                ratio = fuzz.ratio(test_volume.lower(),r['name'].lower())
                if ("The " + test_volume == r['name'] or "An " + test_volume == r['name'] or "A " + test_volume == r['name']):
                    ratio = 100

                r['ratio'] = ratio
                if (ratio >= 80):
                    i = get_issue(r['id'], data['issue'], api_key, args = args, cache_results = use_cache, cache_file = cache_file)
                    if (i is not None):
                        #print(i)
                        #date = None
                        store_date = ''
                        cover_date = ''
                        if ('store_date' in i and i['store_date'] is not None):
                            store_date = i['store_date']
                            #date = store_date
                        if ('cover_date' in i and i['cover_date'] is not None):
                            # Sometimes the cover daye is the first of day of the month, sometimes it's the last, so
                            #   for our generic 'date' comparison field, just force it to be the first, no one cares.
                            cover_date = re.sub('-\d\d$', '-01', i['cover_date'])
                            #if (date is None): date = cover_date

                        if (store_date != '' or cover_date != ''):
                            issue_date[r['id']] = f'{store_date}/{cover_date}'
                            if (ratio >= 93):
                                if ('date' in data and (data['date'] == cover_date or data['date'] == store_date)):
                                    if (args.verbose): print(f"  found {r['name']} #{i['issue_number']} released on {store_date}/{cover_date}")
                                    result = r
                                    match_issue = i
                                    break
                                elif (re.search(r' Annual$', test_volume) and (re.search(f'^{data["year"]}-', cover_date) or re.search(f'^{data["year"]}-', store_date))):
                                    result = r
                                    match_issue = i
                                    break

                        #if (date is not None):
                        #    issue_date[r['id']] = date
                        #    if (date == data['date'] and ratio >= 93):
                        #        if (args.verbose): print(f"  found {r['name']} #{i['issue_number']} released on {date}")
                        #        result = r
                        #        match_issue = i
                        #        break

        if (result is not None or args.yes is True):
            break

        # We didn't find a date match, and we're not in auto-mode, so ask a grown-up for help.
        results = sorted(results, key = lambda x:x['ratio'], reverse = True)
        for r in results:
            item = item + 1
            if (r['ratio'] > max_lev):
                default = item
                max_lev = ratio
            menu_item = f"{item}: {r['name']} ({r['start_year']}) - {r['publisher']['name']}, {r['count_of_issues']} issue(s) (ratio: {ratio})"
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

        use_cache = True
        if (pick == '0' or pick == '-' or pick == '_' or pick == ''):
            raise Exception('user cancelled')
        elif (pick == 'c'):
            use_cache = False
            continue
        elif (pick == '?'):
            print("enter one of the following options:")
            print("  '0'/'-': Skip this item")
            if (len(results) > 0):
                print(f"  '1' - '{len(results)}': select one of the volumes above")
            print("  'c': clear previous searches from cache")
            print("  '####-#####': a comicvine volume or issue id")
            print("  'https://XXXXX/####-#####': a url containing a comicvine volume or issue id")
            print("  'XXXXXX': a new search string")
            print("  'q': quit")
            continue
        elif (pick == 'q'):
            sys.exit()

        if (re.search('^\d+$', pick) and int(pick) <= len(results)):
            result = results[int(pick)-1]
        elif (re.search('\d+-\d+', pick)):
            comicvine_id = pick
            match_issue = None
            m = re.search('^http.*?\/(\d+-\d+)\/', pick)
            if (m is not None):
                comicvine_id = m.group(1)
            m = re.search('(\d+)-(\d+)', comicvine_id)
            if (m is None):
                raise Exception("invalid comicvine id")
            type_id = m.group(1)
            id = m.group(2)
            if (type_id == '4000'):
                url = f'{base_url}/issue/4000-{id}/?api_key={api_key}&format=json&field_list=id,issue_number,name,store_date,story_arc_credits,cover_date,person_credits,description,character_credits,volume'
                #if (args.debug): print(url)
                results = get_results(url, cache_file = cache_file, cache_results = False)
                match_issue = results[0]
                data['issue'] = match_issue['issue_number']
                test_volume = match_issue['volume']['name']
                id = match_issue['volume']['id']
                type_id = '4050'
                if (args.verbose): print("found volume {} #{}".format(test_volume, data['issue']))

            if (type_id == '4050'):
                url = base_url + f'/volume/4050-{id}/?api_key={api_key}&format=json&field_list=id,name,start_year,count_of_issues,publisher,first_issue'
                #if (args.debug): print(url)
                results = get_results(url, cache_file = cache_file, cache_results = False)
                result = results[0]
                test_volume = result['name']
                if (args.verbose and match_issue is None): print("found volume:{}".format(test_volume))
        else:
            test_volume = pick

    if (result is None):
        raise Exception("can't find a volume for " + test_volume)

    volume_id = result['id']
    #if (args.debug): print("comicvine data:", result)

    comicvine_data = {}
    comicvine_data['volume_id'] = volume_id
    comicvine_data['volume_name'] = result['name']
    comicvine_data['start_year'] = result['start_year']
    comicvine_data['publisher'] = result['publisher']['name']

    i = match_issue
    if i is None:
        i = get_issue(volume_id, data['issue'], api_key, args = args, cache_file = cache_file)

    if (i is None):
        raise Exception(f"Couldn't find issue #{data['issue']} of {comicvine_data['volume_name']}")

    comicvine_data['issue'] = i['issue_number']
    comicvine_data['issue_id'] = i['id']
    comicvine_data['issue_name'] = None
    comicvine_data['ratio'] = result['ratio']
    comicvine_data['url'] = 'http://www.comicvine.com/placeholder/4000-{}'.format(i['id'])

    if ('name' in i and i['name'] is not None):
        comicvine_data['issue_name'] = i['name']

    if ('store_date' in i and i['store_date'] is not None):
        comicvine_data['store_date'] = i['store_date']
        comicvine_data['date'] = i['store_date']

    if ('cover_date' in i):
        comicvine_data['cover_date'] = re.sub('-\d\d$', '-01', i['cover_date'])
        # Cover date is always just a month (i think), so the day should always be
        #   either the first or the last day of the month, but no one cares, so force it
        #   to be the first -- way easier.
        if ('date' not in comicvine_data):
            comicvine_data['date'] = comicvine_data['cover_date'] 

    cache['volumes'][data['volume']] = { 'volume': comicvine_data['volume_name'], 'mod_date': datetime.now() }

    return comicvine_data

def search_volumes(volume, api_key, start_year = None, year = None, args = minorimpact.default_arg_flags, cache_results = True, cache_file = '/tmp/yyreader.cache'):
    volume = parser.massage_volume(volume, reverse = True)
    volume = re.sub('^Amazing Spider-Man$', 'The Amazing Spider-Man', volume)
    volume = re.sub('^Immortal Hulk$', 'The Immortal Hulk', volume)
    if (args.debug): print(f"search volume:'{volume}',start_year:'{start_year}',year:'{year}'")

    results = []
    url = base_url + '/search/?api_key=' + api_key + f'&format=json&query={volume}&resources=volume&field_list=id,name,start_year,count_of_issues,publisher,first_issue'
    #if (args.debug): print(url)
    try:
        results = get_results(url, max = 100, cache_results = cache_results, cache_file = cache_file)
    except Exception as e:
        pass
    
    volume_year = {}
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
              or (volume.lower() == 'the amazing spider-man' and int(year) < 2014 and results[i]['start_year'] != '1963') \
              or (year is not None and int(results[i]['start_year']) > int(year)+1):
              #or (start_year is not None and int(results[i]['start_year']) < (int(start_year) - 5))\
              #or (start_year is not None and int(results[i]['start_year']) > (int(start_year) + 5))\
              #or (fuzz.ratio(volume,results[i]['name']) < 60) \
                del results[i]
                pass
            i = i - 1

        # If there are multiple volumes with identical volumes, only keep the 'latest' one.
        results = sorted(results, key = lambda x:int(x['start_year']), reverse = True)
        i = len(results) - 1
        while i >= 0:
            if (results[i]['name'] in volume_year):
                #del results[i]
                pass
            else:
                volume_year[results[i]['name']] = results[i]['start_year']
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
        if ('volumes' not in cache):
            cache['volumes'] = {}

    urls = [key for key in cache['results']]
    for url in urls:
        if cache['results'][url]['mod_date'] < (datetime.now() - timedelta(weeks = 2)):
            del cache['results'][url]

    volumes = [key for key in cache['volumes']]
    for volume in volumes:
        if cache['volumes'][volume]['mod_date'] < (datetime.now() - timedelta(weeks = 2)):
            del cache['volumes'][volume]

    cache_setup = True
