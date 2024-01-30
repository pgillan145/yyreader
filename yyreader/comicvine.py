
from datetime import datetime,timedelta
from dateutil.relativedelta import relativedelta
from dumper import dump
from fuzzywuzzy import fuzz
import json
import minorimpact
import minorimpact.config
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
headers = {'User-Agent': 'yyreader'}
params = {}

config = minorimpact.config.getConfig(script_name = 'yyreader')

class IssueNotFoundException(Exception):
    pass

class UserException(Exception):
    pass

class VolumeNotFoundException(Exception):
    pass

def add_date(result):
    if ('cover_date' in result and result['cover_date'] is not None):
        # Cover date is always just a month (i think), so the day should always be
        #   either the first or the last day of the month, but no one cares, so force it
        #   to be the first -- way easier, every month has a first.
        result['cover_date'] = re.sub('-\d\d$', '-01', result['cover_date'])

    if ('store_date' in result and result['store_date'] is not None):
        result['date'] = result['store_date']
    elif ('cover_date' in result and result['cover_date'] is not None):
        result['date'] = result['cover_date']
    else:
        result['date'] = ''

def get_issue(issue_id, api_key, cache = {}, clear_cache = False, debug = False, verbose = False, slow = False):
    url = f'{base_url}/issue/4000-{issue_id}/?api_key={api_key}&format=json&field_list=id,issue_number,name,store_date,story_arc_credits,cover_date,person_credits,description,character_credits,volume'
    #if (debug): print(url)
    result = get_results(url, cache = cache, clear_cache = clear_cache, debug = debug, verbose = verbose, slow = slow)[0]
    #if (debug): print(result)
    if (re.search('^ ', result['issue_number']) or re.search(' $', result['issue_number'])):
        result['issue_number'] = result['issue_number'].strip()

    add_date(result)

    return result

def get_issues(volume_id, api_key, cache = {}, clear_cache = False, debug = False, verbose = False, detailed = False, slow = False):
    setup_cache(cache)
    #volume = get_volume(volume_id, api_key,  cache = cache, clear_cache = clear_cache, verbose = verbose, debug = debug, slow = slow)
    #volume_name = '{} ({}) - {}'.format(volume['name'], volume['start_year'], volume['publisher']['name'])

    url = base_url + '/issues/?api_key=' + api_key + f'&format=json&sort=name:asc&filter=volume:{volume_id}&field_list=id,issue_number,name,store_date,story_arc_credits,cover_date'
    #if (debug): print(url)
    results = get_results(url, max = None, cache = cache, clear_cache = clear_cache, verbose = verbose, debug = debug, slow = slow)

    for result in results:
        add_date(result)

    if (detailed is not True):
        return results

    issues = []
    for result in results:
        issues.append(get_issue(result['id'], api_key, cache = cache, clear_cache = clear_cache, debug = debug, verbose = verbose))

    return issues

last_result = datetime.now()
def get_results(url, offset=0, limit = 100, max = 100, cache = {}, clear_cache = False, verbose = False, debug = False, slow = False):
    setup_cache(cache)
    global last_result
    seconds_between_requests = 3 if (slow is False) else 18
    if (debug): print(f"seconds_between_requests:{seconds_between_requests}")

    offset_url = url + f'&limit={limit}&offset={offset}'
    if (debug): print(f"request url:{offset_url}")

    text = None
    if (offset_url in cache['comicvine']['results'] and cache['comicvine']['results'][offset_url]['mod_date'] > (datetime.now() - timedelta(weeks = 4)) and clear_cache is False):
        if (debug): print("using cache")
        text = cache['comicvine']['results'][offset_url]['text']
    else:
        if (debug): print("requesting from comicvine")
        while(last_result > datetime.now() - timedelta(seconds=seconds_between_requests)):
            time.sleep(1)
        urllib3.disable_warnings()
        r = requests.get(offset_url, headers=headers, params=params, verify=False)
        last_result = datetime.now()
        text = r.text
        data = json.loads(text)
        if (data['error'] == 'OK'):
            cache['comicvine']['results'][offset_url] = { 'text': r.text, 'mod_date': datetime.now() }

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
        results = results + get_results(url, limit = limit, offset = offset + limit, max = max, cache = cache, clear_cache = clear_cache, slow = slow)

    return results

def get_volume(volume_id, api_key, cache = {}, clear_cache = False, debug = False, headless = False, verbose = False, slow = False):
    setup_cache(cache)

    url = base_url + f'/volume/4050-{volume_id}/?api_key={api_key}&format=json&field_list=id,name,start_year,count_of_issues,publisher,first_issue'
    #if (debug): print(url)
    results = get_results(url, cache = cache, debug = debug, verbose = verbose, clear_cache = clear_cache, slow = slow)
    result = results[0]
    if (re.search('^ ', result['name']) or re.search(' $', result['name'])):
        result['name'] = result['name'].strip()
    return result

def get_volumes(volume, api_key, start_year = None, year = None, cache = {}, clear_cache = False, debug = False, headless = False, verbose = False, slow = False):
    setup_cache(cache)

    if (debug): print(f"search volume:'{volume}',start_year:'{start_year}',year:'{year}'")

    url_volume = volume
    url_volume = re.sub('&', '%26', url_volume)
    url_volume = re.sub('\'', '%27', url_volume)
    url_volume = re.sub('\*', '%2A', url_volume)
    url_volume = re.sub('\+', '%2B', url_volume)
    url_volume = re.sub('/', '%2F', url_volume)
    url_volume = re.sub(':', '%3A', url_volume)
    results = []
    url = base_url + '/search/?api_key=' + api_key + f'&format=json&query={url_volume}&resources=volume&field_list=id,name,start_year,count_of_issues,publisher,first_issue'
    if (debug): print(url)
    try:
        results = get_results(url, max = 100, cache = cache, clear_cache = clear_cache, verbose = verbose, debug = debug, slow = slow)
    except Exception as e:
        pass

    skip_publishers = eval(config['default']['skip_publishers']) if ('skip_publishers' in config['default']) else []

    if (len(results) > 0):
        # Eliminate the volumes we can be reasonably certain are not correct based on the information
        #   we were provided or bad search results.
        i = len(results) - 1
        while i >= 0:
            if (re.search('^ ', results[i]['name']) or re.search(' $', results[i]['name'])):
                #print("WIKI ERROR: '{}':{}".format(results[i]['name'], results[i]['id']))
                results[i]['name'] = results[i]['name'].strip()

            if ('start_year' not in results[i]
              or results[i]['start_year'] is None
              or re.search('^\d+$', results[i]['start_year']) is None
              or results[i]['first_issue'] is None
              or (results[i]['first_issue']['name'] is not None and (re.search('TPB$', results[i]['first_issue']['name']) or re.search('^Volume \d+$', results[i]['first_issue']['name'])))
              or results[i]['publisher'] is None
              or (results[i]['publisher']['name'] in skip_publishers)
              or (year is not None and int(results[i]['start_year']) > int(year)+1)
              #or (volume.lower() == 'the amazing spider-man' and year is not None and int(year) < 2014 and results[i]['start_year'] != '1963')
                ):
                del results[i]
                pass
            i = i - 1

        # TODO: This could potentially solve my 'ver' problem! Instead of throwing away all the older volumes, just increment their 'ver' values.
        #   Except... start_year isn't enough to determine if which one is "-2" -- I need to get the date of the first issue.  So I have to figure out which
        #   comics have the same start year, then go through and pull the first issue of each one, so I get the actual date so I know which one was
        #   "first."
        #results = sorted(results, key = lambda x:int(x['start_year']))

        # Get a list of which of these results have identical names and identical start_years
        first_issues = {}
        for r in results:
            r['ver'] = ''
            volume_year = r['name'] +'|'+r['start_year']
            if (volume_year not in first_issues):
                first_issues[volume_year] = []
            if (debug):
                print(f"{volume_year}\n")
                dump(r['first_issue'])
            first_issues[volume_year].append({ 'name':r['name'], 'start_year':r['start_year'], 'id':r['id'], 'first_issue_id':r['first_issue']['id'], 'first_issue_number':r['first_issue']['issue_number'], 'result':r })

        # For volumes that appear multiple times in the same year, pull the first issues assign a 'ver' field based on the order they were released.
        for issues in first_issues:
            if (len(first_issues[issues]) > 1):
                for issue in first_issues[issues]:
                    i = get_issue(issue['first_issue_id'],  api_key, cache = cache, clear_cache = clear_cache, debug = debug, verbose = verbose, slow = slow)
                    if (debug): print(f"{issue['name']} ({issue['start_year']}), publisher:'{issue['result']['publisher']['name']}, first_issue date: '{i['date']}'")
                    issue['first_issue_date'] = i['date']
                    issue['result']['first_issue']['date'] = i['date']
                ver = 0
                for issue in sorted(first_issues[issues], key = lambda x:x['first_issue_date']):
                    if (issue['first_issue_date'] == ''): continue
                    ver += 1
                    if (ver > 1): issue['result']['ver'] = ver
                    if (debug): print(f"{issue['name']} ({issue['start_year']}), first_issue date: '{issue['first_issue_date']}' ver:'{issue['result']['ver']}'")

    return results

#TODO: Make this take a limited set of fields for search, rather than just passing it 'data'.
def search(data, api_key, cache = {}, clear_cache = False, headless = False, verbose = False, debug = True, slow = False):
    """Given a block of data parsed from a cbr/z file, attempts to match it to a comicvine issue and returns the data.

    In headless mode, will return a match only if it's an exceedingly accurate match based on title, issue and release date.
    """
    setup_cache(cache)

    if (headless):
        if ('year' in data and re.search(' Annual$', data['series'])):
            pass
        elif (('date' not in data or data['date'] is None) and headless is True):
            raise VolumeNotFoundException("Can't auto confirm without strict file date, skipping.")

    test_volume = data['series']
    test_volume = re.sub("\(\d\d\d\d-\)","", test_volume)
    if (test_volume in cache['comicvine']['volumes'] and clear_cache is False):
        test_volume = cache['comicvine']['volumes'][test_volume]['volume']

    result = search_volumes(test_volume, api_key, date=data['date'] if 'date' in data else None, start_year=data['start_year'], year = data['year'], issue = data['issue'], cache = cache, clear_cache = clear_cache, headless = headless, verbose = verbose, debug = debug, slow = slow)
    volume_id = result['id']
    #if (debug): print("comicvine data:", result)

    comicvine_data = {}
    comicvine_data['volume_id'] = volume_id
    comicvine_data['series'] = result['name']
    comicvine_data['start_year'] = result['start_year']
    comicvine_data['volume'] = result['start_year']
    comicvine_data['ver'] = ''
    if ('ver' in result and result['ver'] is not None and result['ver'] != ''):
        comicvine_data['ver'] = str(result['ver'])
        comicvine_data['volume'] = f"{result['start_year']}-{result['ver']}"

    comicvine_data['publisher'] = result['publisher']['name']

    i = None
    if ('match_issue' in result and result['match_issue'] is not None):
        i = result['match_issue']
    else:
        i = search_issues(volume_id, data['issue'], api_key, cache = cache, clear_cache = clear_cache, verbose = verbose, debug = debug)

    if (i is None):
        raise IssueNotFoundException(f"Couldn't find issue #{data['issue']} of {comicvine_data['series']}")

    comicvine_data['cover_date'] = i['cover_date']
    comicvine_data['description'] = ''
    comicvine_data['date'] = i['date']
    comicvine_data['issue'] = parser.massage_issue(i['issue_number'])
    comicvine_data['issue_details'] = i
    comicvine_data['issue_id'] = i['id']
    comicvine_data['issue_name'] = ''
    comicvine_data['ratio'] = result['ratio']
    comicvine_data['store_date'] = i['store_date']
    comicvine_data['url'] = 'http://www.comicvine.com/issue/4000-{}'.format(i['id'])
    comicvine_data['volume_url'] = 'http://www.comicvine.com/volume/4050-{}'.format(volume_id)

    comicvine_data['characters'] = []
    comicvine_data['colorists'] = []
    comicvine_data['inkers'] = []
    comicvine_data['letterers'] = []
    comicvine_data['pencillers'] = []
    comicvine_data['story_arcs'] = []
    comicvine_data['writers'] = []

    details = comicvine_data['issue_details']
    if (details['description'] is not None):
        comicvine_data['description'] = parser.massage_description(details['description'], debug = False)

    for person in details['person_credits']:
        person_name = re.sub(', ', ' ', person['name'])
        if (person['role'] == 'colorist'):
            comicvine_data['colorists'].append(person_name)
        elif (person['role'] == 'inker'):
            comicvine_data['inkers'].append(person_name)
        elif (person['role'] == 'letterer'):
            comicvine_data['letterers'].append(person_name)
        elif (person['role'] == 'penciller'):
            comicvine_data['pencillers'].append(person_name)
        elif (person['role'] == 'penciler'):
            comicvine_data['pencillers'].append(person_name)
        elif (person['role'] == 'writer'):
            comicvine_data['writers'].append(person_name)

    if (details['story_arc_credits'] is not None):
        for arc in details['story_arc_credits']:
            comicvine_data['story_arcs'].append(arc['name'])

    if (details['character_credits'] is not None):
        for character in details['character_credits']:
            comicvine_data['characters'].append(character['name'])

    comicvine_data['characters'].sort()
    comicvine_data['colorists'].sort()
    comicvine_data['inkers'].sort()
    comicvine_data['letterers'].sort()
    comicvine_data['pencillers'].sort()
    comicvine_data['story_arcs'].sort()
    comicvine_data['writers'].sort()

    if ('name' in i and i['name'] is not None):
        comicvine_data['issue_name'] = i['name']

    #details = get_issue_details(i['id'], cache = cache, args = args, clear_cache = clear_cache)
    #self.data['description'] = re.sub('<p><em>','', re.sub('</em></p>', '', details['description']))

    # Cache the old series with the new name so we can avoid all this if we see it again.
    cache['comicvine']['volumes'][data['series']] = { 'volume': comicvine_data['series'], 'mod_date': datetime.now() }

    return comicvine_data

def search_issues(volume_id, issue, api_key, cache = {}, clear_cache = False, debug = False, verbose = False, slow = False):
    setup_cache(cache)

    volume = get_volume(volume_id, api_key, cache = cache, clear_cache = clear_cache, verbose = verbose, debug = debug, slow = slow)
    volume_name = volume['name']
    start_year = volume['start_year']

    results = get_issues(volume_id, api_key, cache = cache, clear_cache = clear_cache, verbose = verbose, debug = debug, slow = slow)
    i = len(results) - 1
    while i >= 0:
        if (re.search('^ ', results[i]['issue_number']) or re.search(' $', results[i]['issue_number'])):
            print("WIKI ERROR: '{}({})' issue_number='{}'".format(volume_name, volume['start_year'], results[i]['issue_number']))
            results[i]['issue_number'] = results[i]['issue_number'].strip()
        if (results[i]['date'] == ''):
            del results[i]
        i = i - 1

    issue = parser.massage_issue(issue)
    if (debug): print(f"  searching for issue #{issue} of {volume_name} ({start_year})")
    for i in results:
        if (debug): print(i)
        if ('issue_number' in i and (issue == i['issue_number'].strip() or parser.massage_issue(i['issue_number']) == issue)):
            result = get_issue(i['id'], api_key, cache = cache, clear_cache = clear_cache, verbose = verbose, debug = debug, slow = slow)
            #print("'{}' issue_number='{}'".format(volume_name, result['issue_number']))
            #i['details'] = get_issue_details(i['id'], api_key, cache = cache, clear_cache = clear_cache, verbose = verbose, debug = debug)
            return result
    return None

def search_volumes(test_volume, api_key, start_year = None, year = None, date = None, issue = None, cache = {}, clear_cache = False, debug = False, verbose = False, headless = False, slow = False):
    """Returns the comicvine volume that best matches the given criteria."""

    result = None
    match_issue = None
    m = re.search('^(.+) \((\d\d\d\d)\)$', test_volume)
    if (m is not None):
        test_volume = m.group(1)
        start_year = m.group(2)

    while (result is None):
        # Get an initial list of volumes from the site that we can start to check.
        results = get_volumes(test_volume, api_key, start_year = start_year, year = year, cache = cache, clear_cache = clear_cache, verbose = verbose, debug = debug, slow = slow)

        for r in results:
            if ('ratio' not in r):
                ratio = fuzz.ratio(test_volume.lower(),r['name'].lower())
                r['ratio'] = ratio

            if ("The " + test_volume == r['name'] or "An " + test_volume == r['name'] or "A " + test_volume == r['name']):
                ratio = 100

            r['score'] = r['ratio']

        if (debug): print(f"  {len(results)} result(s) for '{test_volume}'")
        item = 0
        issue_date = {}
        # If we have a date for the issue, then we can look through each volume for the given issue number to see if it has the
        #   same date.  If so, then then this is *probably* the correct volume.
        if ((date is not None and date != '') or (re.search(r' Annual$', test_volume) and year is not None and re.search(r'^\d\d\d\d$', year))):
            search_date = ''

            if (date is not None and date != ''):
                search_date = datetime.fromisoformat(date)
                #print(f"  looking for an issue #{issue} released on {search_date.date()}")
                if (verbose): print("  looking for issues #{} released on {}".format(issue, date))
            elif (year is not None and re.search(r'^\d\d\d\d$', year)):
                search_date = datetime.fromisoformat(year + '-01-01')
                if (verbose): print(f"  looking for an issue #{issue} released in {year}")

            # Sort results so they're in order by start_year, since the next loop looks at the data in reverse order.
            results = sorted(results, key = lambda x:int(x['start_year']))
            for i in range(len(results)-1, -1, -1):
                r = results[i]
                score = r['ratio']
                if (r['ratio'] >= 80 and result is None and match_issue is None and issue is not None):
                    found_issue = search_issues(r['id'], issue, api_key, cache = cache, clear_cache = clear_cache, verbose = verbose, debug = debug, slow = slow)
                    # TODO: Delete items from 'results' that don't even *have* the issue I'm searching for?
                    if (found_issue is not None):
                        store_date = ''
                        cover_date = ''
                        if ('store_date' in found_issue and found_issue['store_date'] is not None):
                            store_date = datetime.fromisoformat(found_issue['store_date'])
                        if ('cover_date' in found_issue and found_issue['cover_date'] is not None):
                            cover_date = datetime.fromisoformat(found_issue['cover_date'])

                        if (store_date != '' or cover_date != ''):
                            issue_date[r['id']] = ''
                            if (store_date != ''):
                                issue_date[r['id']] = str(store_date.date())

                            if (cover_date != ''):
                                if (len(issue_date[r['id']])>0):
                                    issue_date[r['id']] = issue_date[r['id']] + '/' + str(cover_date.date())
                                else:
                                    issue_date[r['id']] = str(cover_date.date())

                            if (r['ratio'] >= 93):
                                if (search_date == store_date or search_date == cover_date
                                    #( store_date is not '' and search_date == store_date + timedelta(months=1))
                                    ):
                                    if (verbose): print(f"  found {r['name']} #{found_issue['issue_number']} released on {issue_date[r['id']]}")
                                    result = r
                                    match_issue = get_issue(found_issue['id'], api_key, cache = cache, clear_cache = clear_cache, verbose = verbose, debug = debug, slow = slow)
                            if ((store_date != '' and store_date > (search_date + timedelta(weeks = 52))) or (cover_date != '' and (cover_date > search_date + timedelta(weeks = 52)))):
                                # Issue found but one of the dates is more than a year in the future
                                score -= 25
                            elif ((store_date != '' and store_date > search_date + timedelta(weeks=8) or (cover_date != '' and cover_date > search_date + timedelta(weeks=8)))):
                                # Issue found but one of the dates is more than 2 months in the future
                                score -= 15
                            elif ((store_date != '' and store_date > search_date + timedelta(weeks=4) or (cover_date != '' and cover_date > search_date + timedelta(weeks=4)))):
                                # Issue found but one of the dates is between 1 and 2 months in the future
                                score -= 10
                            elif ((store_date != '' and store_date > search_date) or (cover_date != '' and cover_date > search_date)):
                                # Issue found but one of the dates is less than a month in the future.
                                score -= 5
                            elif ((store_date != '' and store_date < search_date - timedelta(weeks = 52)) or (cover_date != '' and cover_date < search_date - timedelta(weeks = 52))):
                                # Issue found but one of the dates is more than a year in the past
                                score -= 20
                            else:
                                # Neither of the dates match.
                                score -= 5
                        else:
                            # No cover dates for matching issue
                            score -= 20
                    else:
                        # No matching issue returned found for volume.
                        score -= 30
                else:
                    # Series title ratio is less than 80
                    score -= 40
                r['score'] = score

        if (result is None):
            for r in results:
                if (r['score'] == 100):
                    if (start_year is not None and r['start_year'] == start_year):
                        if (debug): print("  found exact match: {} ({})".format(r['name'], r['start_year']))
                        result = r

        if (result is not None or headless is True):
            break

        results = sorted(results, key = lambda x:x['score'], reverse = True)

        # We didn't find a date match, and we're not in auto-mode, so ask a grown-up for help.
        default = 0
        max_score = 0
        for r in results:
            item = item + 1
            if (r['score'] > max_score):
                if (r['score'] > 80): default = item
                max_score = r['score']
            if (r['score'] < (max_score - 50)):
                break
            menu_item = f"{item}: {r['name']} ({r['start_year']}) - {r['publisher']['name']}, {r['count_of_issues']} issue(s) (ratio:{r['ratio']}, score: {r['score']})"
            if (r['id'] in issue_date):
                menu_item = f"{menu_item} - {issue_date[r['id']]}"
            print(menu_item)
        input_string = "Choose a series"
        if (default > 0):
            input_string = f"{input_string} [{default}]"
        input_string = f"{input_string}: "
        pick = input(input_string).rstrip()
        clear_cache = False

        if ((pick == '' or pick == 'y') and default > 0):
            pick = f'{default}'

        if (pick == '0' or pick == '-' or pick == '_' or pick == ''):
            raise UserException('user cancelled')
        elif (pick == 'c'):
            clear_cache = True
            continue
        elif (pick == '?'):
            print("enter one of the following options:")
            print("  '0'/'-': Skip this item")
            if (len(results) > 0):
                print(f"  '1' - '{len(results)}': select one of the series above")
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
                raise UserException("invalid comicvine id")
            type_id = m.group(1)
            id = m.group(2)
            if (type_id == '4000'):
                match_issue = get_issue(id, api_key, cache = cache, clear_cache = clear_cache, verbose = verbose, debug = debug)

                # We did this in the opposite order -- usually we get the mathing series and then go looking for the matching issue. Set up
                #   the id and type variables to trigger collecting the appropriate volume information for this issue.
                test_volume = match_issue['volume']['name']
                id = match_issue['volume']['id']
                type_id = '4050'
                date = match_issue['date']

                if (verbose): print("found issue {} #{} ({})".format(test_volume,  match_issue['issue_number'],  date))


            if (type_id == '4050'):
                result = get_volume(id, api_key, cache = cache, clear_cache = clear_cache, verbose = verbose, debug = debug)
                result['ratio'] = 100
                test_volume = result['name']
                if (verbose and match_issue is None): print("found volume:{}".format(test_volume))
        else:
            test_volume = pick

    if (result is None):
        raise VolumeNotFoundException("can't find a volume for " + test_volume)

    if (match_issue is not None):
        result['match_issue'] = match_issue

    return result

def setup_cache(cache):
    if ('comicvine' not in cache):
        cache['comicvine'] = {}
    if ('results' not in cache['comicvine']):
        cache['comicvine']['results'] = {}
    if ('volumes' not in cache['comicvine']):
        cache['comicvine']['volumes'] = {}

    urls = [key for key in cache['comicvine']['results']]
    for url in urls:
        if cache['comicvine']['results'][url]['mod_date'] < (datetime.now() - timedelta(weeks = 1)):
            del cache['comicvine']['results'][url]

    volumes = [key for key in cache['comicvine']['volumes']]
    for volume in volumes:
        if cache['comicvine']['volumes'][volume]['mod_date'] < (datetime.now() - timedelta(weeks = 1)):
            del cache['comicvine']['volumes'][volume]

