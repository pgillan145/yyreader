
from fuzzywuzzy import fuzz
import minorimpact
import minorimpact.config
import os
import os.path
import re
import shutil
import subprocess
import sys
import tempfile

from . import comicvine
from . import parser

config = minorimpact.config.getConfig(script_name = 'yyreader')

class comic():
    data_dir = None
    file = None
    issue = None
    title = None
    temp_dir = None

    def __init__(self, file, args = minorimpact.default_arg_flags):
        self.file = file
        self.parse_data = parser.parse(self.file, args = args)
        if ('title' in self.parse_data):
            self.title = self.parse_data['title']
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
        if (os.path.basename(self.file) != new_comic):
            # Figure out how 'close' the filename is to what we got back from comicvine.
            ratio = 0
            if (("The " + parse_data['title']) == comicvine_data['volume_name']):
                ratio = 100
            elif (("A " + parse_data['title']) == comicvine_data['volume_name']):
                ratio = 100
            else:
                ratio = fuzz.ratio(f"{parse_data['title']}", f"{comicvine_data['volume_name']}")
        
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
                print("  'd': Dump the data for this issue")
                print("  'n': Don't move the file")
                print("  'q': Quit")
                print("  'y': Move the file")
                parse_data = None
            elif (c == 'd'):
                print("Data parsed from filename:")
                print(parse_data)
                print("Data collected online:")
                print(comicvine_data)
                parse_data = None
            elif (c == 'q'):
                sys.exit()
            elif (c == 'y'):
                # If this comic is already in the system, get the ByDate filename so we can delete it before we re-add it later.
                comic_date = parser.convert_name_to_date(self.file)
                if (comic_date is not None):
                    if (args.debug): print(comic_date)
                    comic_date = target_dir + '/ByDate/' + comic_date

                volume_name = parser.massage_volume(comicvine_data['volume_name'])
                self.title = volume_name
                issue = parser.massage_issue(comicvine_data['issue'])
                self.issue = issue
                extension = parse_data['extension']
                name_dir = f'{target_dir}/ByName/{volume_name} ({comicvine_data["start_year"]})'
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
            if (re.search(r'.jpg$', f) is None or f in parser.credit_pages):
                continue
            files.append(f)

        return sorted(files)

        #return sorted(list(filter(lambda x:re.search(r'.jpg$', x), os.listdir(self.data_dir))))

    def is_cbr(self):
        if (re.search('\.cbr$', self.file)):
            return True
        elif (re.search('\.tar$', self.file)):
            return True
        return False

    def is_cbz(self):
        if (re.search('\.cbz$', self.file)):
            return True
        elif (re.search('\.zip$', self.file)):
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

    def page_file(self, number):
        if (number < 1 or number > self.page_count()):
            raise Exception("Invalid page number")

        files = self._files()
        page = files[number - 1]
        return self.data_dir + '/' + page
        

    def page_count(self):
        self._unpack()

        return len(self._files())

    def _unpack(self):
        if (self.data_dir is not None):
            return

        temp_dir = self.make_temp_dir()
        cwd = os.getcwd()
        os.chdir(temp_dir)
        command = None
        if (self.is_cbr()):
            command = [config['default']['unrar'], 'x', '-inul', self.file]
        elif (self.is_cbz()):
            command = [config['default']['unzip'], '-q', self.file, '-d', temp_dir]

        if (command is None): raise Exception("can't unpack, unknown file type")
        result = subprocess.run(command)
        self.data_dir = temp_dir
        for f in os.listdir(temp_dir):
            if (re.search('^\.', f)): continue
            if (os.path.isdir(temp_dir + '/' + f)):
                self.data_dir = temp_dir + '/' + f
                break
        os.chdir(cwd)

    def __del__(self):
        if (self.temp_dir is not None):
            self.temp_dir.cleanup()
