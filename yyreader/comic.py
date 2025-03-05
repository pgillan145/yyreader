
from dumper import dump
from io import BytesIO
from fuzzywuzzy import fuzz
from hashlib import md5
import magic
import minorimpact
import minorimpact.config
import os
import os.path
from PIL import Image, ImageDraw, ImageStat
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

from . import comicvine
from . import parser

ext_map = { 'cbr': 'RAR archive data', 'cbz': 'Zip archive data' }
xml_map = { 'Characters':'a_characters', 'Publisher':'publisher', 'Number':'issue', 'Summary':'description', 'Series':'series', 'Volume':'volume', 'Day':'day', 'Month':'month', 'Year':'year', 'StoryArc':'a_story_arcs', 'Writer':'a_writers', 'Penciller':'a_pencillers', 'Inker':'a_inkers', 'Letterer':'a_letterers', 'Colorist':'a_colorists', 'Title':'issue_name', 'Web':'url' }

config = minorimpact.config.getConfig(script_name = 'yyreader')

def dive(dir, ext = 'jpg'):
    for f in os.listdir(dir):
        if (re.search(r'^\.', f)): continue
        if (re.search('\.' + ext + '$', f, re.I)):
            return dir
    for f in os.listdir(dir):
        if (re.search(r'^\.', f)): continue
        if (os.path.isdir(dir + '/' + f)):
            bottom = dive(dir + '/' + f)
            if (bottom is not None):
                return bottom

def to_hex(r, g, b):
    return '#{:02x}{:02x}{:02x}'.format(int(r), int(g), int(b))

def compare_lists(list1, list2, width = 22):
    ret = ''
    if (list1 != list2):
        max_len = len(list1)
        if (len(list2) > max_len): max_len = len(list2)
        for i in (range(0, max_len)):
            fw = list1[i] if (i< len(list1)) else '---'
            rw = list2[i] if (i< len(list2)) else '---'
            ret = ret + "{:{width}s} {:{width}s} {:{width}s} {:{width}s}\n".format('', '', fw, rw, width = width)
    return ret

class FileExistsException(Exception):
    pass

class FileSizeException(Exception):
    pass

class ExtensionMismatchException(Exception):
    pass

class comic():
    #data = {}
    #data_dir = None
    #file = None
    #temp_dir = None
    #_page_count = None
    #files = []

    def __init__(self, file, cache = {}, verbose = False, debug = False):
        self.data = {}
        self.data_dir = None
        self.temp_dir = None
        self._page_count = None
        self.files = []

        if (re.search('^/', file) is None):
            file = os.getcwd() + '/' + file

        self.file = file

        self.data['day'] = None
        self.data['date'] = None
        self.data['issue'] = None
        self.data['month'] = None
        self.data['series'] = None
        self.data['start_year'] = ''
        self.data['ver'] = ''
        self.data['volume'] = None
        self.data['year'] = ''
        self.data['description'] = ''
        self.data['characters'] = []
        self.data['colorists'] = []
        self.data['inkers'] = []
        self.data['letterers'] = []
        self.data['pencillers'] = []
        self.data['story_arcs'] = []
        self.data['url'] = ''
        self.data['writers'] = []

        self._read_data(verbose = verbose, debug = debug)
        self.cache = cache
        #print("_read_data()")
        #print(self.data)

    def __repr__(self):
        return self.file

    def _add_xml(self, verbose = False, debug = False):
        if (self.data_dir is None or os.path.exists(self.data_dir) is False):
            self._unpack()

        xml_data = self._generate_xml_data(verbose = verbose, debug = debug)
        #print(xml_data)
        cwd = os.getcwd()
        os.chdir(self.temp_dir.name)

        xml_file = 'ComicInfo.xml'

        if (os.path.exists(xml_file)):
            os.chmod(xml_file, 0o644)
        with (open(xml_file, 'w') as x):
            x.write(xml_data)

        command = None
        if (self.is_cbr()):
            command = [config['default']['rar'], 'a', '-inul', self.file, xml_file]
        elif (self.is_cbz()):
            command = [config['default']['zip'], '-q', self.file, xml_file]

        if (command is None): raise Exception("can't add xml files, unknown file type")
        result = subprocess.run(command)
        os.chdir(cwd)

    def box(self, target_dir = None, headless = True, args = minorimpact.default_arg_flags, debug = False, verbose = False, verify = False, large = False, small = False, slow = False):
        if (args.debug is True): debug = True
        if (args.verbose is True): verbose = True
        if (args.yes is True): headless = True

        data = self.data
        parse_data = self.parse_data
        if (parse_data is None or parse_data == {}):
            raise Exception("No info parsed from filename")

        comicvine_data = comicvine.search(parse_data, config['comicvine']['api_key'], cache = self.cache, headless = headless, debug = debug, verbose = verbose, slow = slow)
        if (comicvine_data is None):
            raise Exception("can't get comicvine data.")

        minimum_file_size = 1
        if ('minimum_file_size' in config['default']):
            minimum_file_size = int(config['default']['minimum_file_size'])
        minimum_file_size = minimum_file_size * 1024 * 1024

        maximum_file_size = 100
        if ('maximum_file_size' in config['default']):
            maximum_file_size = int(config['default']['maximum_file_size'])
        maximum_file_size = maximum_file_size * 1024 * 1024

        if (parse_data['size'] < minimum_file_size and small is False):
            raise FileSizeException("file too small")
        if (parse_data['size'] >= maximum_file_size and large is False):
            raise FileSizeException("file too large")

        go_for_it = False
        score = self.compare(comicvine_data = comicvine_data, verbose = False, verify = verify)
        if (score < 100):
            if (score >= 85):
                go_for_it = True

            if (headless is False):
                done = False
                while (done is False):
                    score = self.compare(comicvine_data = comicvine_data, verbose = True, verify = verify)

                    default = 'n' if go_for_it is False else 'y'
                    c = minorimpact.getChar(default=default, end='\n', prompt=f"Score:{score} update? (y/n/q/c/i/?) [default={default}] ", echo=True).lower()

                    if (c == '?'):
                        print("  'c': Clear cache and search comicvine again")
                        print("  'i': Dump the data collected for this issue")
                        print("  'n': Don't update the file")
                        print("  'q': Quit")
                        print("  'y': Update the file")
                    elif (c == 'c'):
                        comicvine_data = comicvine.search(parse_data, config['comicvine']['api_key'], verbose = verbose, debug = debug, clear_cache = True, headless=headless, slow = slow)
                        if (comicvine_data is None):
                            raise Exception("can't get comicvine data.")
                    elif (c == 'i'):
                        print("Data parsed from filename:", parse_data)
                        print("Data parsed from file:", data)
                        print("Data collected online:", '{}'.format(comicvine_data['url']), comicvine_data)
                    elif (c == 'q'):
                        sys.exit()
                    elif (c == 'n'):
                        done = True
                    elif (c == 'y'):
                        self._update(comicvine_data, target_dir = target_dir, debug = debug, args = args)
                        score = self.compare(comicvine_data = comicvine_data, verbose = False)
                        done = True
            else:
                if (go_for_it is True):
                    print("  auto updating {}".format(self.file))
                    self._update(comicvine_data, target_dir = target_dir, debug = debug, args = args)
                    score = self.compare(comicvine_data = comicvine_data, verbose = False, verify = verify)
                else:
                    print("  score:{} too low to auto update {} -- skipping".format(score, self.file))

        return score

    def collect_info(self):
        pass

    def compare(self, comicvine_data = None, verbose = False, debug = False, args = minorimpact.default_arg_flags, verify = False):
        if (verbose is False and args.verbose is True):
            verbose = args.verbose
        if (debug is False and args.debug is True):
            debug = args.debug

        data = self.data
        parse_data = self.parse_data

        if (comicvine_data is None):
            comicvine_data = comicvine.search(parse_data, config['comicvine']['api_key'], cache = self.cache, args = args, headless = headless)
            if (comicvine_data is None):
                raise Exception("can't get comicvine data.")

        score = fuzz.ratio(data['series'].lower(),comicvine_data['series'].lower())
        if ("The " + data['series'] == comicvine_data['series'] or "An " + data['series'] == comicvine_data['series'] or "A " + data['series'] == comicvine_data['series']):
            score = 100

        width = 28
        output = ""
        if (score < 100):
            output += "{:{width}s} {:{width}s} {:{width}s} {:{width}s}\n".format('series', parse_data['series'], data['series'], comicvine_data['series'], width = width)
        if (data['issue'] != comicvine_data['issue'] or parse_data['issue'] != comicvine_data['issue']):
            if (parser.massage_issue(data['issue']) == comicvine_data['issue'] or parser.massage_issue(parse_data['issue']) == comicvine_data['issue']):
                score -= 1
            else:
                score -= 10
        output += "{:{width}s} {:{width}s} {:{width}s} {:{width}s}\n".format('issue', parse_data['issue'], data['issue'], comicvine_data['issue'], width = width)
        if (data['start_year'] != comicvine_data['start_year'] or parse_data['start_year'] != comicvine_data['start_year']):
            score -= 1
        output += "{:{width}s} {:{width}s} {:{width}s} {:{width}s}\n".format('start year', parse_data['start_year'], data['start_year'], comicvine_data['start_year'], width = width )
        if (data['ver'] != comicvine_data['ver'] or parse_data['ver'] != comicvine_data['ver']):
            score -= 1
        output += "{:{width}s} {:{width}s} {:{width}s} {:{width}s}\n".format('ver', parse_data['ver'], data['ver'], comicvine_data['ver'], width = width)
        if (data['volume'] != comicvine_data['volume'] or parse_data['volume'] != comicvine_data['volume']):
            score -= 1
        output += "{:{width}s} {:{width}s} {:{width}s} {:{width}s}\n".format('volume', parse_data['volume'], data['volume'], comicvine_data['volume'], width = width)
        if (data['date'] != comicvine_data['date'] or parse_data['date'] != comicvine_data['date']):
            score -= 1
        output += "{:{width}s} {:{width}s} {:{width}s} {:{width}s}\n".format('date', parse_data['date'], data['date'], comicvine_data['date'], width = width )
        if (data['ver'] != parse_data['ver']):
            score -= 1
            output += "{:{width}s} {:{width}s} {:{width}s} {:{width}s}\n".format('ver', parse_data['ver'], data['ver'], '---', width = width)
        if (data['description'] != comicvine_data['description']):
            output += "{:{width}s} {:{width}s} {:<{width}d} {:<{width}d}\n".format('description', '---', len(data['description']), len(comicvine_data['description']), width = width)
            if (verify): score -= 1
        if (data['characters'] != comicvine_data['characters']):
            if (verify): score -= 1
            output += "{:{width}s} {:{width}s} {:<{width}d} {:<{width}d}\n".format('characters', '---', len(data['characters']), len(comicvine_data['characters']), width = width)
            #output += compare_lists(data['characters'], comicvine_data['characters'])
        if (data['colorists'] != comicvine_data['colorists']):
            if (verify): score -= 1
            output += "{:{width}s} {:{width}s} {:<{width}d} {:<{width}d}\n".format('colorists', '---', len(data['colorists']), len(comicvine_data['colorists']), width = width)
            #output += compare_lists(data['colorists'], comicvine_data['colorists'])
        if (data['inkers'] != comicvine_data['inkers']):
            if (verify):score -= 1
            output += "{:{width}s} {:{width}s} {:<{width}d} {:<{width}d}\n".format('inkers', '---', len(data['inkers']), len(comicvine_data['inkers']), width = width)
            #output += compare_lists(data['inkers'], comicvine_data['inkers'])
        if (data['letterers'] != comicvine_data['letterers']):
            if (verify): score -= 1
            output += "{:{width}s} {:{width}s} {:<{width}d} {:<{width}d}\n".format('letterers', '---', len(data['letterers']), len(comicvine_data['letterers']), width = width)
            #output += compare_lists(data['letterers'], comicvine_data['letterers'])
        if (data['pencillers'] != comicvine_data['pencillers']):
            if (verify): score -= 1
            output += "{:{width}s} {:{width}s} {:<{width}d} {:<{width}d}\n".format('pencillers', '---', len(data['pencillers']), len(comicvine_data['pencillers']), width = width)
            #output += compare_lists(data['pencillers'], comicvine_data['pencillers'])
        if (data['story_arcs'] != comicvine_data['story_arcs']):
            if (verify): score -= 1
            output += "{:{width}s} {:{width}s} {:<{width}d} {:<{width}d}\n".format('story_arcs', '---', len(data['story_arcs']), len(comicvine_data['story_arcs']), width = width)
            #output += compare_lists(data['story_arcs'], comicvine_data['story_arcs'])
        if (data['writers'] != comicvine_data['writers']):
            if (verify): score -= 1
            output += "{:{width}s} {:{width}s} {:<{width}d} {:<{width}d}\n".format('writers', '---', len(data['writers']), len(comicvine_data['writers']), width = width)
            #output += compare_lists(data['writers'], comicvine_data['writers'])
        if (output != ''):
            output = "{:{width}s} {:{width}s} {:{width}s} {:{width}s}\n".format('', 'File Name','Internal', 'Remote', width = width) + output

        if (data['description'] != comicvine_data['description']):
            if (verify): score -= 1
            output += "Internal Description:\n  "
            # TODO: Update minorimpact.splitstringlen() to try to split text on spaces.
            s1 = minorimpact.splitstringlen(data['description'], width*4)
            output += "\n  ".join(s1) + "\n"
            output += "Remote Description:\n  "
            s2 = minorimpact.splitstringlen(comicvine_data['description'], width*4)
            output += "\n  ".join(s2) + "\n"

        # We just want the last two directory names, "publisher/series", so do reverse/unreversing magic to get them
        dirname = '/'.join(list(reversed(list(reversed(os.path.dirname(self.file).split('/')))[0:2])))
        basename = os.path.basename(self.file)
        merge_data = self.merge_data(comicvine_data)
        merged_name = parser.make_name(merge_data, extension = parse_data['extension'], directors_cut = parse_data['directors_cut'], args = args)
        merged_dir = parser.make_dir(merge_data)
        output += "Current Filename: {}/{}\n".format(dirname, basename)
        if (merged_name != basename or merged_dir != dirname):
            if (verify or score == 100): score -= 1
            output += " Proper filename: {}/{}\n".format(merged_dir, merged_name)

        old_url = data['url']
        old_url_fixed = re.sub('placeholder', 'issue', old_url)
        new_url = comicvine_data['url']
        if (old_url != new_url and old_url_fixed == new_url):
            if (verify): score -= 1
            output += "old_url: " + old_url + "\n"
        elif ( old_url != new_url):
            if (verify): score -= 1
            output += "old_url: " + old_url + "\n"
        output += "    url: " + new_url + "\n"

        if (verbose):
            print(output)
        return score

    def date(self):
        return self.data['date']

    def issue(self):
        #print("SHIT data:")
        #dump(self.data)
        #print("SHIT parse_data:")
        #dump(self.parse_data)

        return self.data['issue']

    def merge_data(self, comicvine_data):
        merge_data = self.data.copy()
        merge_data['ver'] = self.parse_data['ver']

        merge_data['issue'] = comicvine_data['issue']
        merge_data['series'] = comicvine_data['series']
        merge_data['start_year'] = comicvine_data['start_year']
        #merge_data['volume'] = comicvine_data['start_year']
        merge_data['ver'] = comicvine_data['ver']
        merge_data['volume'] = comicvine_data['volume']

        merge_data['characters'] = comicvine_data['characters']
        merge_data['colorists'] = comicvine_data['colorists']
        merge_data['description'] = comicvine_data['description']
        merge_data['inkers'] = comicvine_data['inkers']
        merge_data['issue_id'] = comicvine_data['issue_id']
        merge_data['issue_name'] = comicvine_data['issue_name']
        merge_data['letterers'] = comicvine_data['letterers']
        merge_data['pencillers'] = comicvine_data['pencillers']
        merge_data['publisher'] = comicvine_data['publisher']
        merge_data['story_arcs'] = comicvine_data['story_arcs']
        merge_data['url'] = comicvine_data['url']
        merge_data['writers'] = comicvine_data['writers']

        #if (merge_data['ver']):
        #    merge_data['volume'] = "{}-{}".format(merge_data['start_year'], merge_data['ver'])

        #TODO: Figure out of this is at all necessary.  Can't I just set merge_data['date'] = comicvine_data['date']?
        m = re.search('(\d\d\d\d)-(\d\d)-(\d\d)', comicvine_data['date'])
        if (m is None):
            raise Exception(f"Invalid date:{comicvine_data['date']}")
        year = m.group(1)
        month = m.group(2)
        day = m.group(3)

        merge_data['day'] = day
        merge_data['month'] = month
        merge_data['year'] = year
        merge_data['date'] = '{}-{}-{}'.format(year, month, day)

        return merge_data

    def _files(self):
        if (len(self.files) > 0):
            return self.files

        files = []
        if (self.is_cbr() and True):
            command = [config['default']['rar'], 'lb', self.file]
            result = subprocess.run(command, capture_output = True, text = True)
            for f in result.stdout.split('\n'):
                files.append(f)
        elif (self.is_cbz() and True):
            command = [config['default']['unzip'], '-l', self.file]
            result = subprocess.run(command, capture_output = True, text = True)
            for f in result.stdout.split('\n'):
                m = re.search(r'^ *\d+ +[\d-]+ [\d:]+ +(.+)$', f)
                if (m is not None):
                    files.append(m.group(1))
        else:
            self._unpack()
            for f in os.listdir(self.data_dir):
                files.append(f)
        self.files = files
        return self.files

    def get(self, name):
        if (name in self.data):
            return self.data[name]

    def __getitem__(self, name):
        if (name in self.data):
            return self.data[name]

    def _generate_xml_data(self, verbose = False, debug = False):
        xml_version = '1.1'
        comicinfo = ET.Element('ComicInfo')
        for x in xml_map:
            array = False
            data_field = xml_map[x]
            m = re.search('^a_(.*)$', data_field)
            if (m is not None):
                data_field = m.group(1)
                array = True

            if (data_field in self.data):
                if (array): # or (type(self.data[data_field]) is list)):
                    if (len(self.data[data_field]) > 0):
                        element = ET.SubElement(comicinfo, x)
                        element.text = ','.join(self.data[data_field])
                        if (debug): print("xml write {}({})={}".format(x, data_field, ','.join(self.data[data_field])))
                else:
                    element = ET.SubElement(comicinfo, x)
                    element.text = self.data[data_field]
                    if (debug): print("xml write {}({})={}".format(x, data_field, self.data[data_field]))

        #if ('issue_id' in self.data):
        #    web = ET.SubElement(comicinfo, 'Web')
        #    web.text = 'http://www.comicvine.com/issue/4000-{}'.format(self.data['issue_id'])

        notes = ET.SubElement(comicinfo, 'Notes')
        notes.text = 'Generated by yyreader xml v{}'.format(xml_version)

        return ET.tostring(comicinfo, encoding='unicode')

    def is_cbr(self):
        if (re.search(r'\.cbr$', self.file, re.I) or (re.search(r'\.rar$', self.file))):
            magic_str = magic.from_file(self.file)
            if (re.search('^RAR archive data', magic_str) is None):
                raise ExtensionMismatchException("{} is rar, but file data is '{}'".format(self.file, magic_str[:16]))
            return True
        return False

    def is_cbz(self):
        if (re.search('\.cbz$', self.file, re.I) or (re.search('\.zip$', self.file))):
            magic_str = magic.from_file(self.file)
            if (re.search('^Zip archive data', magic_str) is None):
                raise ExtensionMismatchException("{} is zip, but file data is '{}'".format(self.file, magic_str[:16]))
            return True
        return False

    def make_temp_dir(self):
        if (self.temp_dir is None or os.path.isdir(self.temp_dir.name) is False):
            self.temp_dir = tempfile.TemporaryDirectory()
        return self.temp_dir.name

    def md5(self):
        #return md5(str(self.file, 'utf-8'))
        return md5(self.file.encode('utf-8')).hexdigest()

    def border(self, img):
        (w, h) = img.size
        #print("(",h,w,")")
        max_border_percent = 10
        interval_count = 5
        max_w = int(w * (max_border_percent/100))
        max_h = int(h * (max_border_percent/100))
        interval_w = int(w/interval_count)
        interval_h = int(h/interval_count)
        #mask = Image.new('1', img.size, 1)
        #d = ImageDraw.Draw(mask)
        #d.rectangle([(0,50), (50, 51)], fill=0)
        #stat = ImageStat.Stat(img, mask)

        #TODO: A lot of these pages have a slight tilt, which makes the cropping look weird.  See if I can find a reliable
        #   way to track the increase in crop along along one side to try and determine how much to rotate the page so it's
        #   perfectly vertical.
        #min_left = max_w
        #max_left = 0
        #direction = 0
        ##print("max_w:", max_w)
        #interval_tilt = int(h/20)
        #for x in range(1, 20):
        #    test = img.crop((0, x*interval_tilt, max_w, (x*interval_tilt)+1))
        #    test.save(f'/Users/pgillan/tmp/left{x}.jpg')
        #    size = 0
        #    last = None
        #    for b in test.getdata():
        #        hex = to_hex(b[0], b[1], b[2])
        #        #print(size, hex)
        #        if (hex != last and last is not None):
        #            size = size - 1
        #            break
        #        size = size + 1
        #        last = hex
        #    if (size < min_left):
        #        min_left = size
        #        direction = direction - 1
        #    if (size > max_left):
        #        max_left = size
        #        direction = direction + 1
        #    print("size:", size)
        #    print("min_left:", min_left)
        #    print("max_left:", max_left)
        #    print("dir:", direction)

        top = max_h
        for x in range(1, interval_count):
            test = img.crop((x*interval_w, 0,(x*interval_w) + 1, max_h))
            #test.save(f'/Users/pgillan/tmp/top{x}.jpg')
            width = 0
            last = None
            for b in test.getdata():
                hex = to_hex(b[0], b[1], b[2])
                if (hex != last and last is not None):
                    width = width - 1
                    break
                width = width + 1
                last = hex
            if (width < top):
                top = width
        #print("top:", top)

        right = max_w
        #print("max_w:", max_w)
        for x in range(1, interval_count):
            test = img.crop((w-max_w, x*interval_h, w, (x*interval_h)+1)).rotate(180)
            #test = test.rotate(180)
            #test.save(f'/Users/pgillan/tmp/right{x}.jpg')
            size = 0
            last = None
            for b in test.getdata():
                hex = to_hex(b[0], b[1], b[2])
                #print(size, hex)
                if (hex != last and last is not None):
                    size = size - 1
                    break
                size = size + 1
                last = hex
            if (size < right):
                right = size
        #print("right:", right)

        bottom = max_h
        for x in range(1, interval_count):
            test = img.crop((x*interval_w, h-max_h, (x*interval_w) + 1, h)).rotate(180)
            width = 0
            last = None
            for b in test.getdata():
                hex = to_hex(b[0], b[1], b[2])
                if (hex != last and last is not None):
                    width = width - 1
                    break
                width = width + 1
                last = hex
            if (width < bottom):
                bottom = width
        #print("bottom:", bottom)

        left = max_w
        #print("max_w:", max_w)
        for x in range(1, interval_count):
            test = img.crop((0, x*interval_h, max_w, (x*interval_h)+1))
            #test.save(f'/Users/pgillan/tmp/left{x}.jpg')
            size = 0
            last = None
            for b in test.getdata():
                hex = to_hex(b[0], b[1], b[2])
                #print(size, hex)
                if (hex != last and last is not None):
                    size = size - 1
                    break
                size = size + 1
                last = hex
            if (size < left):
                left = size
        #print("left:", left)
        return (left, top, w-right, h-bottom)

    def _page_img(self, number, crop = True):
        img = None
        if (self.is_cbr()):
            command = [config['default']['rar'], 'p', self.file, self.page_file(number)]
            result = subprocess.run(command, capture_output = True)
            tmp = BytesIO()
            tmp.write(result.stdout)
            img = Image.open(tmp, formats=['JPEG'])
        elif (self.is_cbz()):
            page_file = self.page_file(number)
            page_file = re.sub('\[', '\\\[', page_file)
            page_file = re.sub('\]', '\\\]', page_file)
            command = [config['default']['unzip'], '-p', self.file, page_file]
            result = subprocess.run(command, capture_output = True)
            tmp = BytesIO()
            tmp.write(result.stdout)
            img = Image.open(tmp, formats=['JPEG'])
        else:
            img = Image.open(self.page_file(number))

        if (img is not None and crop is True):
            img = img.crop(self.border(img))
            pass
        return img

    def page(self, number, crop = True):
        #test = img.crop((0, 0, 200, 200))
        #tmp = "/Users/pgillan/tmp/crop.jpg"
        #return test.tobytes()
        #f = open(tmp, 'bw')
        #f.write(data)
        #f.close()
        #return data

        img = self._page_img(number, crop = crop)
        out = BytesIO()
        img.save(out, format='JPEG')
        return out.getvalue()

        # Return raw file
        with (open(self.page_file(number), 'rb') as f):
            data = f.read()
        return data

    def page_color(self, page, crop = True):
        """Returns the hex code for the median color that appears along the outer edge of the page."""

        img = self._page_img(page, crop = crop)

        (w, h) = img.size
        mask = Image.new('1', img.size, 1)
        d = ImageDraw.Draw(mask)
        d.rectangle([(50,50), (w-50, h-50)], fill=0)
        stat = ImageStat.Stat(img, mask)
        #print("extrema:", stat.extrema)
        #print("count:", stat.count)
        #print("median:", stat.median)
        #print("mean:", stat.mean)
        #print("rms:", stat.rms)
        colors = stat.median
        return to_hex(colors[0], colors[1], colors[2])

    def page_count(self):
        if (self._page_count is None):
            self._page_count = len(self._page_files())
        return self._page_count

    def page_file(self, page):
        if (page < 1): page = 1
        if (page > self.page_count()): page = self.page_count()

        files = self._page_files()
        page_file = files[page - 1]
        return page_file
        return self.data_dir + '/' + page_file

    def _page_files(self):
        page_files = []
        files = self._files()
        for f in files:
            if (re.search(r'.jpg$', f, re.I) is None or parser.is_credit_page(f)):
                continue
            page_files.append(f)

        #return sorted(list(filter(lambda x:re.search(r'.jpg$', x), os.listdir(self.data_dir))))
        return sorted(page_files)

    def page_size(self, page = 1, crop = True):
        img = self._page_img(page, crop = crop)
        return img.size

    def _read_data(self, verbose = False, debug = False):
        """Collect as much information from the file as possible."""

        self.parse_data = parser.parse(self.file, verbose = verbose, debug = debug)
        if (self.parse_data is None or self.parse_data == {}):
            raise Exception("No info parsed from filename {}".format(self.file))

        #print("FUCK comic._read_data")
        #dump(self.parse_data)

        if (self.parse_data is not None):
            if ('day' in self.parse_data):
                self.data['day'] = self.parse_data['day']
            if ('issue' in self.parse_data):
                self.data['issue'] = self.parse_data['issue']
            if ('month' in self.parse_data):
                self.data['month'] = self.parse_data['month']
            if ('series' in self.parse_data):
                self.data['series'] = self.parse_data['series']
            if ('start_year' in self.parse_data):
                self.data['start_year'] = self.parse_data['start_year']
            if ('ver' in self.parse_data):
                self.data['ver'] = self.parse_data['ver']
            if ('volume' in self.parse_data):
                self.data['volume'] = self.parse_data['volume']
            if ('year' in self.parse_data):
                self.data['year'] = self.parse_data['year']

        command = None
        if (self.is_cbr()):
            # rar p Marvel\ Two-in-One\ \(1974\)\ 031\ \(1977-09-01\).cbr "*/ComicInfo.xml"
            command = [config['default']['rar'], 'p', self.file, 'ComicInfo.xml']
        elif (self.is_cbz()):
            # unzip -p Incredible\ Hulk\ Annual\,\ The\ \(1968\)\ 006\ \(1977-11-01\).cbz ComicInfo.xml
            command = [config['default']['unzip'], '-p', self.file, 'ComicInfo.xml']

        if (command is None): raise Exception("can't read xml files, unknown file type")

        result = subprocess.run(command, capture_output = True)
        try:
            comicinfo = ET.fromstring(result.stdout)
            # TODO: Find some way to ignore the garbage data in preexisting ComicInfo.xml files.  Leaning towards putting something in the Note
            #   field but I can't figure out how to get just one tag without having to iterate through though the whole thing twice.  I fucking
            #   hate XML.
            for x in comicinfo:
                if (x.tag in xml_map):
                    data_field = xml_map[x.tag]
                    array = False
                    m = re.search('^a_(.*)$', data_field)
                    if (m is not None):
                        data_field = m.group(1)
                        array = True

                    if (array is True):
                        if (re.search('\|', x.text)):
                            self.data[data_field] = x.text.split('|')
                        elif (re.search('\n', x.text)):
                            self.data[data_field] = x.text.split('\n')
                        elif (len(x.text) > 0):
                            self.data[data_field] = [ x.text ]
                        else:
                            self.data[data_field] = []
                    else:
                        self.data[data_field] = x.text if (x.text is not None) else ''

                    if (array is True):
                        self.data[data_field].sort()
                        if (debug): print("xml read {}({})={}".format(x.tag, data_field, ",".join(self.data[data_field])))
                    else:
                        if (debug): print("xml read {}({})={}".format(x.tag, data_field, self.data[data_field]))
                        pass

                elif (x.tag == 'Web'):
                    m = re.search(r'\/4000-(\d+)', x.text)
                    if (m is not None):
                        self.data['issue_id'] = int(m.group(1))
        except:
            pass

        self.data['date'] = None
        if ('year' in self.data and 'month' in self.data and 'day' in self.data):
            if (self.data['month'] is not None and int(self.data['month']) < 10 and re.search('^0', self.data['month']) is None): self.data['month'] = '0{}'.format(self.data['month'])
            if (self.data['day'] is not None and int(self.data['day']) < 10 and re.search('^0', self.data['day']) is None): self.data['day'] = '0{}'.format(self.data['day'])
            self.data['date'] = '{}-{}-{}'.format(self.data['year'], self.data['month'], self.data['day'])

        #print(result)

    def _unpack(self):
        if (self.data_dir is not None and os.path.exists(self.data_dir) is True):
            return

        temp_dir = self.make_temp_dir()
        cwd = os.getcwd()
        os.chdir(temp_dir)
        #print(temp_dir)
        command = None
        if (self.is_cbr()):
            command = [config['default']['rar'], 'x', '-inul', self.file]
        elif (self.is_cbz()):
            command = [config['default']['unzip'], '-q', self.file, '-d', temp_dir]

        if (command is None): raise Exception("can't unpack, unknown file type")
        result = subprocess.run(command)
        self.data_dir = dive(temp_dir, ext = 'jpg')
        os.chdir(cwd)

    def _update(self, comicvine_data, target_dir = None, args = minorimpact.default_arg_flags, verbose = True, debug = True):
        if (args.debug): debug = True
        if (args.verbose): verbose = True
        parse_data = self.parse_data

        merge_data = self.merge_data(comicvine_data)
        self.data = merge_data

        if (args.verbose): print("  adding ComicInfo.xml to file")
        if (args.dryrun is False): self._add_xml(verbose = verbose, debug = debug)

        original_file = self.file
        new_comic = parser.make_name(self.data, parse_data['extension'], directors_cut = parse_data['directors_cut'])
        dirname = os.path.dirname(self.file)
        if (dirname + '/' + new_comic != self.file):
            if (args.verbose): print(f"  renaming {self.file} => {new_comic}")
            if (args.dryrun is False):
                shutil.move(self.file, dirname + '/' + new_comic)
                self.file = dirname + '/' + new_comic

        if (target_dir is None):
            return

        target_dir = re.sub('/$', '', target_dir)
        target_dir = target_dir + '/' + parser.make_dir(self.data)
        if (dirname == target_dir):
            return

        if (os.path.exists(target_dir) is False):
            if (args.dryrun is False): os.makedirs(target_dir, exist_ok = True)

        if (args.verbose): print(f"  moving {new_comic} => {target_dir}/")
        if (os.path.exists(f'{target_dir}/{new_comic}') is True):
            raise FileExistsException(f"{target_dir}/{new_comic} already exists")
        if (args.dryrun is False):
            shutil.move(self.file, target_dir + '/' + new_comic)
            #if ('match_log_file' in config['default']):
            #    match_log[original_file] = new_comic
            #    with open(config['default']['match_log_file'], 'a') as f:
            #        f.write(f"{self.file} => {match_log[comic]}\n")
            self.file = target_dir + '/' + new_comic

    def url(self):
        return self.data['url']

    def __del__(self):
        if (self.temp_dir is not None):
            self.temp_dir.cleanup()

