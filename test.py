#!/usr/bin/env python3

import configparser
from hashlib import md5
import minorimpact
import os
import tarfile
import tempfile
import unittest
#from unittest import mock
#import random
#import subprocess
import sys
import time
import yyreader.comic
import yyreader.comicvine
import yyreader.parser

class TestUtils(unittest.TestCase):
    test_dir = None
    config = None
    dir = os.getcwd()

    def setUp(self):
        self.config = minorimpact.config.getConfig(script_name = 'yyreader')
        self.test_dir = tempfile.TemporaryDirectory()
        os.chdir(self.test_dir.name)

    def tearDown(self):
        self.test_dir.cleanup()

    def test_config(self):
        config = minorimpact.config.getConfig(script_name='yyreader')
        self.assertIsNotNone(config)
        self.assertIsInstance(config, configparser.ConfigParser)

    def test_comic(self):
        c = yyreader.comic.comic(self.dir + '/test_data/test.cbz')
        self.assertEqual(c.page_count(), 1)
        self.assertEqual(md5(c.page(1)).hexdigest(), 'd5ad9ac2b9d3cea48fc67d5cea893ea2')

    def test_comicvine(self):
        volume = 'Warlock (1972)'
        results = yyreader.comicvine.search_volumes(volume, self.config['comicvine']['api_key'], cache_results = False)
        self.assertTrue(len(results) > 0)
        found = False
        for r in results:
            if ('id' in r and r['id'] == 2583 and 'count_of_issues' in r and r['count_of_issues'] == 15 and 'start_year' in r and r['start_year'] == '1972'): found = True 
        self.assertTrue(found)

    def test_parser(self):
        issue = yyreader.parser.massage_issue('1')
        self.assertEqual(issue, '001')
        test_volume = 'The Amazing Spider-Man'
        new_volume = yyreader.parser.massage_volume(test_volume)
        self.assertEqual(new_volume, 'Amazing Spider-Man, The')
        new_volume = yyreader.parser.massage_volume(new_volume, reverse = True)
        self.assertEqual(new_volume, test_volume)
        filename = 'Yondu (2019) 003 (2019-12-11).cbr'
        new_filename = yyreader.parser.convert_name_to_date(filename)
        self.assertEqual(new_filename, '2019/12/2019-12-11 Yondu (2019) 003.cbr')

if __name__ == '__main__':
    unittest.main()
