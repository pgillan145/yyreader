
from io import BytesIO
from fuzzywuzzy import fuzz
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
xml_map = { 'Characters':'a_characters', 'Publisher':'publisher', 'Number':'issue', 'Summary':'description', 'Series':'volume_name', 'Volume':'start_year', 'Day':'day', 'Month':'month', 'Year':'year', 'StoryArc':'a_story_arcs', 'Writer':'a_writers', 'Penciller':'a_pencillers', 'Inker':'a_inkers', 'Letterer':'a_letterers', 'Colorist':'a_colorists', 'Title':'name' }

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

class FileExistsException(Exception):
    pass

class FileSizeException(Exception):
    pass

class ExtensionMismatchException(Exception):
    pass

class comic():
    data = {}
    data_dir = None
    file = None
    temp_dir = None
    _page_count = None
    files = []

    def __init__(self, file, args = minorimpact.default_arg_flags):
        if (re.search('^/', file) is None):
            file = os.getcwd() + '/' + file
        self.file = file
        self._read_data()
        #print("_read_data()")
        #print(self.data)

    def __repr__(self):
        return self.file

    def _add_xml(self):
        if (self.data_dir is None or os.path.exists(self.data_dir) is False):
            self._unpack()

        xml_data = self._generate_xml_data()
        cwd = os.getcwd()
        os.chdir(self.temp_dir.name)

        xml_file = 'ComicInfo.xml'

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

    def box(self, target_dir, data = None, args = minorimpact.default_arg_flags):
        if (target_dir is None):
            raise Exception("No target directory specified.")
        elif (os.path.exists(target_dir) is False):
            raise Exception(f"{target_dir} doesn't exist")

        target_dir = re.sub('/$', '', target_dir)

        match_log = {}
        if ('match_log_file' in config['default'] and os.path.exists(config['default']['match_log_file'])):
            with open(config['default']['match_log_file'], 'r') as f:
                line = f.readline()
                while line:
                    (original,processed) = line.rstrip().split(' => ')
                    match_log[original] = processed
                    line = f.readline()
        #print(match_log)

        if (os.path.exists(target_dir) is False):
            os.mkdir(target_dir)

        minimum_file_size = 1
        if ('minimum_file_size' in config['default']):
            minimum_file_size = int(config['default']['minimum_file_size'])
        minimum_file_size = minimum_file_size * 1024 * 1024

        parse_data = self.parse_data
        if (parse_data is None or parse_data == {}):
            raise Exception("No info parsed from filename")
        if (parse_data['size'] < minimum_file_size):
            raise Exception("file too small")

        comicvine_data = comicvine.search(parse_data, config['comicvine']['api_key'], cache_file = config['default']['cache_file'], args = args)
        if (comicvine_data is None):
            raise Exception("can't get comicvine data.")
        if (os.path.exists(target_dir + '/' + comicvine_data['publisher']) is False):
            os.mkdir(target_dir + '/' + comicvine_data['publisher'])

        new_comic = parser.make_name(comicvine_data, parse_data['extension'], directors_cut = parse_data['directors_cut'], ver = parse_data['ver'])
        volume_name = parser.massage_volume(comicvine_data['volume_name'])
        name_dir = f'{target_dir}/{comicvine_data["publisher"]}/{volume_name} ({comicvine_data["start_year"]})'

        while (self.file != name_dir + '/' + new_comic):
            # Figure out how 'close' the filename is to what we got back from comicvine.
            ratio = comicvine_data['ratio']

            c = ''
            if (ratio >= 93 and ('date' in parse_data and (('store_date' in comicvine_data and comicvine_data['store_date'] == parse_data['date']) or ('cover_date' in comicvine_data and comicvine_data['cover_date'] == parse_data['date']))) or (re.search(r' Annual$', comicvine_data['volume_name']) and ('cover_date' in comicvine_data and re.search(f'^{parse_data["year"]}-', comicvine_data['cover_date']) or 'store_date' in comicvine_data and re.search(f'^{parse_data["year"]}-', comicvine_data['store_date'])))):
                default_c = 'y'
                default_text = 'Y/n'
            else:
                default_c = 'n'
                default_text = 'y/N'

            if (args.yes is True):
                if (default_c == 'y'):
                    c = 'y'
                else:
                    return

            if (c == ''):
                c = minorimpact.getChar(default=default_c, end='\n', prompt=f"move to {new_comic} (ratio:{ratio})? ({default_text}/?) ", echo=True).lower()

            if (c == '?'):
                print("  'c': Clear cache and search comicvine again")
                print("  'd': Dump the data for this issue")
                print("  'n': Don't move the file")
                print("  'q': Quit")
                print("  'y': Move the file")
            elif (c == 'c'):
                comicvine_data = comicvine.search(parse_data, config['comicvine']['api_key'], cache_results = False,  cache_file = config['default']['cache_file'], args = args)
                if (comicvine_data is None):
                    raise Exception("can't get comicvine data.")
                if (os.path.exists(target_dir + '/' + comicvine_data['publisher']) is False):
                    os.mkdir(target_dir + '/' + comicvine_data['publisher'])
                new_comic = parser.make_name(comicvine_data, parse_data['extension'], directors_cut = parse_data['directors_cut'], ver = parse_data['ver'])
                volume_name = parser.massage_volume(comicvine_data['volume_name'])
                name_dir = f'{target_dir}/{comicvine_data["publisher"]}/{volume_name} ({comicvine_data["start_year"]})'
            elif (c == 'd'):
                print("Data parsed from filename:", parse_data)
                print("Data collected online:", comicvine_data)
            elif (c == 'q'):
                sys.exit()
            elif (c == 'n'):
                return
            elif (c == 'y'):

                self.data['volume'] = '{} ({})'.format(comicvine_data['volume_name'], comicvine_data['start_year'])
                self.data['volume_name'] = comicvine_data['volume_name']
                self.data['start_year'] = comicvine_data['start_year']
                self.data['ver'] = parse_data['ver']
                issue = parser.massage_issue(comicvine_data['issue'])
                self.data['issue'] = comicvine_data['issue']
                extension = parse_data['extension']

                m = re.search('(\d\d\d\d)-(\d\d)-(\d\d)', comicvine_data['date'])
                if (m is None):
                    raise Exception(f"Invalid date:{comicvine_data['date']}")
                year = m.group(1)
                month = m.group(2)
                day = m.group(3)
                self.data['day'] = day
                self.data['issue_id'] = comicvine_data['issue_id']
                self.data['issue_name'] = comicvine_data['issue_name']
                self.data['month'] = month
                self.data['publisher'] = comicvine_data['publisher']
                self.data['year'] = year
                self.data['date'] = '{}-{}-{}'.format(year, month, day)

                details = comicvine.get_issue_details(self.data['issue_id'], config['comicvine']['api_key'], cache_file = config['default']['cache_file'], args = args)
                self.data['description'] = details['description']
                self.data['name'] = details['name']

                self.data['story_arcs'] = []
                if (details['story_arc_credits'] is not None):
                    for arc in details['story_arc_credits']:
                        self.data['story_arcs'].append(arc['name'])

                self.data['characters'] = []
                if (details['character_credits'] is not None):
                    for character in details['character_credits']:
                        self.data['characters'].append(character['name'])

                self.data['colorists'] = []
                self.data['inkers'] = []
                self.data['letterers'] = []
                self.data['pencillers'] = []
                self.data['writers'] = []
                if (details['person_credits'] is not None):
                    #{'api_detail_url': 'https://comicvine.gamespot.com/api/person/4040-40982/', 'id': 40982, 'name': 'Joe Kelly', 'site_detail_url': 'https://comicvine.gamespot.com/joe-kelly/4040-40982/', 'role': 'writer'}
                    for person in details['person_credits']:
                        if (person['role'] == 'colorist'):
                            self.data['colorists'].append(person['name'])
                        elif (person['role'] == 'inker'):
                            self.data['inkers'].append(person['name'])
                        elif (person['role'] == 'letterer'):
                            self.data['letterers'].append(person['name'])
                        elif (person['role'] == 'penciller'):
                            self.data['pencillers'].append(person['name'])
                        elif (person['role'] == 'penciler'):
                            self.data['pencillers'].append(person['name'])
                        elif (person['role'] == 'writer'):
                            self.data['writers'].append(person['name'])
                if (args.verbose): print("  adding ComicInfo.xml to file")
                if (args.dryrun is False): self._add_xml()

                dirname = os.path.dirname(self.file)
                if (args.debug): print(f"RENAME {self.file} => {dirname}/{new_comic}")
                if (args.dryrun is False):
                    shutil.move(self.file, dirname + '/' + new_comic)
                    self.file = dirname + '/' + new_comic

                if (os.path.exists(name_dir) is False):
                    if (args.dryrun is False): os.mkdir(name_dir)

                if (args.debug): print(f"MOVE {self.file} => {name_dir}/{new_comic}")
                if (os.path.exists(f'{name_dir}/{new_comic}') is True):
                    raise FileExistsException(f"{name_dir}/{new_comic} already exists")
                if (args.dryrun is False):
                    shutil.move(self.file, name_dir + '/' + new_comic)
                    if ('match_log_file' in config['default']):
                        match_log[comic] = new_comic
                        with open(config['default']['match_log_file'], 'a') as f:
                            f.write(f"{self.file} => {match_log[comic]}\n")
                    self.file = name_dir + '/' + new_comic
                else:
                    return

    def collect_info(self):
        pass

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

    def _generate_xml_data(self):
        xml_version = '1'
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
                        element.text = '|'.join(self.data[data_field])
                else:
                    element = ET.SubElement(comicinfo, x)
                    element.text = self.data[data_field]

        if ('issue_id' in self.data):
            web = ET.SubElement(comicinfo, 'Web')
            web.text = 'http://www.comicvine.com/placeholder/4000-{}'.format(self.data['issue_id'])

        notes = ET.SubElement(comicinfo, 'Notes')
        notes.text = 'Generated by yyreader xml v{}'.format(xml_version)

        return ET.tostring(comicinfo, encoding='unicode')

    def is_cbr(self):
        if (re.search(r'\.cbr$', self.file, re.I) or (re.search(r'\.rar$', self.file))):
            magic_str = magic.from_file(self.file)
            if (re.search('^RAR archive data', magic_str) is None):
                raise ExtensionMismatchException("file is rar, but file data is '{}'".format(magic_str[:16]))
            return True
        return False

    def is_cbz(self):
        if (re.search('\.cbz$', self.file, re.I) or (re.search('\.zip$', self.file))):
            magic_str = magic.from_file(self.file)
            if (re.search('^Zip archive data', magic_str) is None):
                raise ExtensionMismatchException("file is zip, but file data is '{}'".format(magic_str[:16]))
            return True
        return False

    def make_temp_dir(self):
        if (self.temp_dir is None or os.path.isdir(self.temp_dir.name) is False):
            self.temp_dir = tempfile.TemporaryDirectory()
        return self.temp_dir.name

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
            command = [config['default']['unzip'], '-p', self.file, self.page_file(number)]
            result = subprocess.run(command, capture_output = True)
            tmp = BytesIO()
            tmp.write(result.stdout)
            img = Image.open(tmp, formats=['JPEG'])
        else:
            img = Image.open(self.page_file(number))

        if (img is not None and crop is True):
            img = img.crop(self.border(img))
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

    def page_color(self, page):
        """Returns the hex code for the median color that appears along the outer edge of the page."""

        img = self._page_img(page)

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
            if (re.search(r'.jpg$', f, re.I) is None or f in parser.credit_pages):
                continue
            page_files.append(f)

        #return sorted(list(filter(lambda x:re.search(r'.jpg$', x), os.listdir(self.data_dir))))
        return sorted(page_files)

    def page_size(self, page = 1):
        img = self._page_img(page)
        return img.size

    def _parse_xml_data(self, xml_data):
        comicinfo = ET.fromstring(xml_data)
        for x in comicinfo:
            print(x.tag, x.attrib, x.text)
        return None

    def _read_data(self):
        """Collect as much information from the file as possible."""

        self.parse_data = parser.parse(self.file)
        if (self.parse_data is not None):
            if ('day' in self.parse_data):
                self.data['day'] = self.parse_data['day']
            if ('issue' in self.parse_data):
                self.data['issue'] = self.parse_data['issue']
            if ('month' in self.parse_data):
                self.data['month'] = self.parse_data['month']
            if ('start_year' in self.parse_data):
                self.data['start_year'] = self.parse_data['start_year']
            if ('volume_name' in self.parse_data):
                self.data['volume_name'] = self.parse_data['volume_name']
            if ('year' in self.parse_data):
                self.data['year'] = self.parse_data['year']
            if ('start_year' in self.data and 'volume_name' in self.data):
                self.data['volume'] = "{} ({})".format(self.data['volume_name'], self.data['start_year'])

        command = None
        if (self.is_cbr()):
            # rar p Marvel\ Two-in-One\ \(1974\)\ 031\ \(1977-09-01\).cbr "*/ComicInfo.xml"
            command = [config['default']['rar'], 'p', self.file, 'ComicInfo.xml']
        elif (self.is_cbz()):
            # unzip -p Incredible\ Hulk\ Annual\,\ The\ \(1968\)\ 006\ \(1977-11-01\).cbz ComicInfo.xml
            command = [config['default']['unzip'], '-p', self.file, 'ComicInfo.xml']

        if (command is None): raise Exception("can't read xml files, unknown file type")

        self.data['characters'] = []
        self.data['colorists'] = []
        self.data['inkers'] = []
        self.data['letterers'] = []
        self.data['pencillers'] = []
        self.data['story_arcs'] = []
        self.data['writers'] = []
        result = subprocess.run(command, capture_output = True)
        try:
            comicinfo = ET.fromstring(result.stdout)
            #TODO: Find some way to ignore the garbage data in preexisting ComicInfo.xml files.  Leaning towards putting something in the Note
            #   frield but I can't figure out how to get just one tag without having to iteratite through though the whole thing twice.  I fucking
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
                        self.data[data_field] = x.text.split('|')
                    else:
                        self.data[data_field] = x.text
                elif (x.tag == 'Web'):
                    m = re.search(r'\/4000-(\d+)', x.text)
                    if (m is not None):
                        self.data['issue_id'] = int(m.group(1))
        except:
            pass

        if ('year' in self.data and 'month' in self.data and 'day' in self.data):
            if (int(self.data['month']) < 10 and re.search('^0', self.data['month']) is None): self.data['month'] = '0{}'.format(self.data['month'])
            if (int(self.data['day']) < 10 and re.search('^0', self.data['day']) is None): self.data['day'] = '0{}'.format(self.data['day'])
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

    def __del__(self):
        if (self.temp_dir is not None):
            self.temp_dir.cleanup()
