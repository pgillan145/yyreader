
from fuzzywuzzy import fuzz
import magic
import minorimpact
import minorimpact.config
import os
import os.path
from PIL import Image, ImageDraw
import re
import shutil
import subprocess
import sys
import tempfile

from . import comicvine
from . import parser

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

class comic():
    data_dir = None
    file = None
    issue = None
    volume = None
    temp_dir = None

    def __init__(self, file, args = minorimpact.default_arg_flags):
        self.file = file
        self.parse_data = parser.parse(self.file, args = args)
        if ('volume' in self.parse_data):
            self.volume = self.parse_data['volume']
        if ('issue' in self.parse_data):
            self.issue = self.parse_data['issue']

    def __repr__(self):
        return self.file

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

        if (os.path.exists(target_dir + '/ByName') is False):
            os.mkdir(target_dir + '/ByName')
        if (os.path.exists(target_dir + '/ByDate') is False):
            os.mkdir(target_dir + '/ByDate')

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
        new_comic = parser.make_name(comicvine_data, parse_data['extension'], directors_cut = parse_data['directors_cut'], ver = parse_data['ver'])
        volume_name = parser.massage_volume(comicvine_data['volume_name'])
        name_dir = f'{target_dir}/ByName/{volume_name} ({comicvine_data["start_year"]})'

        while (self.file != name_dir + '/' + new_comic):
            # Figure out how 'close' the filename is to what we got back from comicvine.
            ratio = 0
            if (("The " + parse_data['volume']) == comicvine_data['volume_name']):
                ratio = 100
            elif (("A " + parse_data['volume']) == comicvine_data['volume_name']):
                ratio = 100
            else:
                ratio = fuzz.ratio(f"{parse_data['volume']}", f"{comicvine_data['volume_name']}")
        
            c = ''
            if ( 'date' in parse_data and 'date' in comicvine_data and comicvine_data['date'] == parse_data['date'] and ratio >= 93):
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
                print("  'c': Search comicvine again")
                print("  'd': Dump the data for this issue")
                print("  'n': Don't move the file")
                print("  'q': Quit")
                print("  'y': Move the file")
            elif (c == 'c'):
                comicvine_data = comicvine.search(parse_data, config['comicvine']['api_key'], cache_file = config['default']['cache_file'], args = args)
                new_comic = parser.make_name(comicvine_data, parse_data['extension'], directors_cut = parse_data['directors_cut'], ver = parse_data['ver'])
                volume_name = parser.massage_volume(comicvine_data['volume_name'])
                name_dir = f'{target_dir}/ByName/{volume_name} ({comicvine_data["start_year"]})'
            elif (c == 'd'):
                print("Data parsed from filename:")
                print(parse_data)
                print("Data collected online:")
                print(comicvine_data)
            elif (c == 'q'):
                sys.exit()
            elif (c == 'y'):
                # If this comic is already in the system, get the ByDate filename so we can delete it before we re-add it later.
                comic_date = parser.convert_name_to_date(self.file)
                if (comic_date is not None):
                    if (args.debug): print(comic_date)
                    comic_date = target_dir + '/ByDate/' + comic_date

                self.volume = volume_name
                issue = parser.massage_issue(comicvine_data['issue'])
                self.issue = issue
                extension = parse_data['extension']
                if (os.path.exists(name_dir) is False):
                    if (args.dryrun is False): os.mkdir(name_dir)
                if (os.path.exists(f'{name_dir}/{new_comic}') is True):
                    raise Exception(f"{name_dir}/{new_comic} already exists")

                m = re.search('(\d\d\d\d)-(\d\d)-(\d\d)', comicvine_data['date'])
                if (m is None):
                    raise Exception(f"Invalid date:{comicvine_data['date']}")
                year = m.group(1)
                month = m.group(2)
                day = m.group(3)
                date_dir = f'{target_dir}/ByDate/{year}/{month}'
                if (os.path.exists(date_dir) is False):
                    if (args.dryrun is False): os.makedirs(f'{date_dir}', exist_ok=True)
                new_comic_date = parser.make_date(comicvine_data, extension, directors_cut = parse_data['directors_cut'])
                if (os.path.exists(f'{date_dir}/{new_comic_date}') is True):
                    raise Exception(f"{date_dir}/{new_comic_date} already exists")

                if (args.verbose): print(f"MOVE {self.file} => {name_dir}/{new_comic}")
                if (args.dryrun is False):
                    shutil.move(self.file, name_dir + '/' + new_comic)
                    if ('match_log_file' in config['default']):
                        match_log[comic] = new_comic
                        with open(config['default']['match_log_file'], 'a') as f:
                            f.write(f"{self.file} => {match_log[comic]}\n")
                    self.file = name_dir + '/' + new_comic
                if (comic_date is not None and os.path.exists(comic_date) is True):
                    if (args.verbose): print(f"REMOVE {comic_date}")
                    if (args.dryrun is False): os.remove(comic_date)

                if (args.verbose): print(f"LINK {name_dir}/{new_comic} => {date_dir}/{new_comic_date}")
                if (args.dryrun is False): os.link(name_dir + '/' + new_comic, date_dir + '/' + new_comic_date)


    def collect_info(self):
        pass

    def _files(self):
        files = []
        self._unpack()
        for f in os.listdir(self.data_dir):
            files.append(f)

        return files

    def is_cbr(self):
        if (re.search('\.cbr$', self.file) or (re.search('\.rar$', self.file))):
            magic_str = magic.from_file(self.file)
            if (re.search('^RAR archive data', magic_str) is None):
                raise Exception("extension is rar, but filetype is '{}'".format(magic_str))
            return True
        return False

    def is_cbz(self):
        if (re.search('\.cbz$', self.file) or (re.search('\.zip$', self.file))):
            magic_str = magic.from_file(self.file)
            if (re.search('^Zip archive data', magic_str) is None):
                raise Exception("extension is zip, but filetype is '{}'".format(magic_str))
            return True
        return False

    def make_temp_dir(self):
        if (self.temp_dir is None):
            self.temp_dir = tempfile.TemporaryDirectory()
        return self.temp_dir.name

    def page(self, number = 1):
        f = open(self.page_file(number), 'rb')
        data = f.read()
        f.close()
        return data

    def page_color(self, page = 1):
        """Returns the hex code for the color that appears most often on the page."""

        img = Image.open(self.page_file(page))
        #(w, h) = img.size
        #d = ImageDraw.Draw(img)
        #d.rectangle([(50,50), (w-50, h-50)], fill=(0,0,0,255))
        colors = sorted(img.getcolors(maxcolors=1024*1024), key=lambda x:x[0], reverse = True)
        #img.save(self.data_dir + "/fuck.png")
        #print(self.data_dir + "/fuck.png")
        return '#{:02x}{:02x}{:02x}'.format(colors[0][1][0], colors[0][1][1], colors[0][1][2])

    def page_color1(self, page = 1):
        img = Image.open(self.page_file(page))
        (w, h) = img.size
        mask = Image.new('1', img.size, 1)
        d = ImageDraw.Draw(mask)
        d.rectangle([(50,50), (w-50, h-50)], fill=0)
        #mask.save(self.data_dir + "/fuck.png")
        #print(self.data_dir + "/fuck.png")

        r,g,b = img.split()
        big_r = 0
        tr = 0
        h =  r.histogram() #mask=mask)
        i = 0
        while (i < len(h)):
            if (h[i] > big_r):
                big_r = h[i]
                tr = i
            #print("{}:{}".format(i, h[i]))
            i = i + 1

        big_g = 0
        tg = 0
        h =  g.histogram() #mask=mask)
        i = 0
        while (i < len(h)):
            if (h[i] > big_g):
                big_g = h[i]
                tg = i
            #print("{}:{}".format(i, h[i]))
            i = i + 1

        big_b = 0
        tb = 0
        h =  b.histogram() #mask=mask)
        i = 0
        while (i < len(h)):
            if (h[i] > big_b):
                big_b = h[i]
                tb = i
            #print("{}:{}".format(i, h[i]))
            i = i + 1
        h = re.sub('0x', '', "#" + str(hex((tr*256*256) + (tg*256) + tb)))
        #print(h)
        return h

    def page_count(self):
        return len(self._page_files())

    def page_file(self, page):
        if (page < 1): page = 1
        if (page > self.page_count()): page = self.page_count()

        files = self._page_files()
        page_file = files[page - 1]
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
        img = Image.open(self.page_file(page))
        return img.size

    def _unpack(self):
        if (self.data_dir is not None):
            return

        temp_dir = self.make_temp_dir()
        cwd = os.getcwd()
        os.chdir(temp_dir)
        #print(temp_dir)
        command = None
        if (self.is_cbr()):
            command = [config['default']['unrar'], 'x', '-inul', self.file]
        elif (self.is_cbz()):
            command = [config['default']['unzip'], '-q', self.file, '-d', temp_dir]

        if (command is None): raise Exception("can't unpack, unknown file type")
        #print(command)
        result = subprocess.run(command)
        self.data_dir = dive(temp_dir, ext = 'jpg')
        os.chdir(cwd)

    def __del__(self):
        if (self.temp_dir is not None):
            self.temp_dir.cleanup()
