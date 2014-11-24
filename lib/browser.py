#!/usr/bin/python -tt

# omega - python client
# https://github.com/jfillmore/Omega-API-Engine
# 
# Copyright 2011, Jonathon Fillmore
# Licensed under the MIT license. See LICENSE file.
# http://www.opensource.org/licenses/mit-license.php


"""Omega serice curses-based GUI for automatic service API nagivation
and interaction."""

import sys
import curses

# local
import box_factory as bf
import dbg
from util import get_args

class Palette:
	pair_num = None
	colors = {
		'normal': [curses.COLOR_WHITE, curses.COLOR_BLACK, curses.A_NORMAL, 0],
		'title': [curses.COLOR_CYAN, curses.COLOR_YELLOW, curses.A_BOLD, 1],
		'warning': [curses.COLOR_WHITE, curses.COLOR_RED, curses.A_BOLD, 2],
		'error': [curses.COLOR_RED, curses.COLOR_RED, curses.A_BOLD, 3],
		'notice': [curses.COLOR_MAGENTA, curses.COLOR_WHITE, curses.A_NORMAL, 4],
		'highlight': [curses.COLOR_WHITE, curses.COLOR_BLACK, curses.A_BOLD, 5],
		'shadow': [curses.COLOR_BLACK, curses.COLOR_BLACK, curses.A_BOLD, 6]
	}

	def __init__(self):
		for name in self.colors:
			fg = self.colors[name][0]
			bg = self.colors[name][1]
			id = self.colors[name][3]
			if id == 0:
				continue
			curses.init_pair(id, fg, bg)

	def color(self, name):
		if not name in self.colors:
			raise Exception("Unrecognized color name of '%s'." % name)
		pair_num = self.colors[name][3]
		attr = self.colors[name][2]
		clr = curses.color_pair(pair_num)
		return clr | attr
	

class Browser:
	"""Omega service browser."""

	pal = None

	def __init__(self, client, api = None, params = None, auto_):
		"""Initializes the browser, optionally to a specific API with some
		pre-filled parameters.
		expects: client=object, api=string, params=object, auto_run=boolean
		returns: object"""
		self.client = client
		curses.wrapper(self.build, api, params, auto_run)
		curses.start_color()

	def error(self, msg):
		error = bf.Box(self.root_win)
		error.text(msg)

	def build(self, win, api, params, auto_run):
		"""Initializes the connection to the omega service, authenticating
		and initializing as needed."""
		win.nodelay(0)
		curses.noecho()
		self.pal = Palette()
		self.root_win = win
		self.gui = bf.Doc(self.root_win)

		service_info = None
		while service_info == None:
			try:
				service_info = self.client.run('?')
			except Exception as e:
				# missing username or password? prompt for that and try again
				if str(e).find('Missing username or password') != -1:
					creds = {'username': '', 'password': ''}
					while creds['username'] == '':
						clt = bf.Collect(
							parent = self.gui,
							title = 'Login',
							title_attr = self.pal.color('highlight'),
							msg = 'Please enter your username and password.',
							border_style = 'simple',
							fields = {
								'username': {
									'type': bf.TextBox,
									'args': {
										'caption': 'Username',
										'default_val': 'foobar'
									}
								},
								'password': {
									'type': bf.TextBox,
									'args': {
										'caption': 'Password'
									}
								}
							}
						)
						input = clt.get_input()
						if input != None:
							self.client.set_credentials(
								creds = {'username': input['username'], 'password': input['password']}
							)
						else:
							sys.exit()
		# see if we have an API to query up by default
	
	def start(self):
		#import rpdb2
		#rpdb2.start_embedded_debugger('pdb')
		box = bf.Message(
			parent = self.gui,
			title = 'Testing',
			msg = '\033[1;0;31mHi there!',
			border = [1, 1, 1, 1],
			margin = [1, 2, 1, 2],
			padding = [1, 1, 1, 1],
			border_chars = ['.', '.', '.', '.', '.', '.', '.', '.']
		);
		key = self.root_win.getch()
		curses.endwin()

if __name__ == '__main__':
	import client
	browser = Browser(client.OmegaClient())
	browser.start()
