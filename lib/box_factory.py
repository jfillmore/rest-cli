#!/usr/bin/python -tt

# omega - python client
# https://github.com/jfillmore/Omega-API-Engine
# 
# Copyright 2011, Jonathon Fillmore
# Licensed under the MIT license. See LICENSE file.
# http://www.opensource.org/licenses/mit-license.php


"""Library of GUI box objects for ncurses user interface design."""

# system
import sys
import curses
import curses.textpad
import types

# local
import dbg
from util import get_args

# globals
BORDER_STYLES = {
	'clear': [' ', ' ', ' ', ' ', ' ', ' ', ' ', ' ', curses.A_NORMAL], 
	'simple': ['|', '|', '-', '-', '.', '.', "'", "'", curses.A_NORMAL],
	'sharp': ['|', '|', '_', '_', ' ', ' ', "|", "|", curses.A_NORMAL]
}

class Doc:
	parent = None
	children = {}
	win = None
	_name = None
	_args = {}
	_is_root = True
	# style
	_bg_char = None
	_bg_attr = None
	_width = None
	_height = None
	_dirty = True
	_top = 0
	_left = 0
	_visible = True
	
	def __init__(self, parent, name = None, **args):
		if name == None:
			name = self._make_name()
		if isinstance(parent, Doc):
			# make sure we're unique
			if name in parent.children:
				raise Exception("A box by the name '%s' already exists within children of '%s' parent." % (name, parent.name()))
			self._is_root = False
			parent.children[name] = self
			self.parent = parent
			p_win = parent.win
		else:
			p_win = parent
		my_args = {
			'width': None,
			'height': None,
			'top': 0,
			'left': 0
		}
		my_args = get_args(my_args, args)
		for arg in my_args:
			self._args[arg] = my_args[arg]
		# create our subwin
		win_args = [self._args['top'], self._args['left']]
		if self._args['width'] != None and self._args['height'] != None:
			win_args.insert(0, self._args['height'])
			win_args.insert(0, self._args['width'])
		self.win = p_win.subwin(*win_args)
		# set our dimensions and location
		(self._height, self._width) = self.win.getmaxyx()
		self._top = my_args['top']
		self._left = my_args['left']
		self._name = name
		self.refresh()
	
	def _make_name(self):
		base_name = 'doc'
		# short cut if we're a top level doc
		if self._is_root:
			return base_name
		# otherwise just try to generate one by finding a free name, ugly as this is
		max_tries = 1000
		for i in range(0, max_tries):
			if not name in self.parent.children:
				return name
		raise Exception("Failed to find a free box name after %i iterations." \
			% max_tries)
	
	def name(self, name = None):
		if name == None:
			return self._name
		elif name in parent.children:
			raise Exception("A box by the name '%s' already exists within parent's children." % name)
		del parent.children[self._name]
		self._name = name
		parent.children[self._name] = self
	
	def get_metrics(self, from_screen = False):
		metrics = {}
		metrics['inner_top'] = self._top
		metrics['outer_top'] = self._top
		metrics['inner_left'] = self._left
		metrics['outer_left'] = self._left
		metrics['inner_bottom'] = self._top + self._height
		metrics['outer_bottom'] = metrics['inner_bottom']
		metrics['inner_right'] = self._left + self._width
		metrics['outer_right'] = metrics['inner_right']
		metrics['inner_height'] = self._height
		metrics['outer_height'] = self._height
		metrics['inner_width'] = self._width
		metrics['outer_width'] = self._width
		if from_screen:	
			# add in extra spacing for the window's position
			for item in metrics:
				if item.endswith('_left') or item.endswith('_right'):
					metrics[item] += self.doc._left
				if item.endswith('_top') or item.endswith('_bottom'):
					metrics[item] += self.doc._top
		return metrics

	def remove(self):
		# remove all the children boxes first
		for name in self.children:
			box = self.children[name]
			box.remove()
		# remove ourself from our parent, unless we're a root Doc
		if not self._is_root:
			del parent.children[self._name]

	def focus(self, name = None):
		focused = False
		if name == None:
			# TODO: check tab/focus order for the first box?
			for name in self.children:
				box = self.children[name]
				if box.focus():
					focused = True
					break
		else:
			if not name in self.children:
				raise Exception("Box '%s' not found." % name)
			focused = self.children[name].focus()
		return focused
	
	def visible(self, visibility = None, refresh = True):
		if visibility == None:
			return self._visible
		self._visible = visibility
		self._dirty = True
		if refresh:
			self.refresh()
		return self
	
	def move_to(self, top = None, left = None, refresh = True):
		if left == None and top == None:
			return self
		if left == None:
			left = self._left
		if top == None:
			top = self._top
		self._left = left
		self._top = top
		self._dirty = True
		self.win.movewin(top, left)
		if refresh:
			self.doc.win.refresh()
		return self
	
	def move_by(self, top = None, left = None, refresh = True):
		if left == None and top == None:
			return self
		if left == None:
			left = 0
		if top == None:
			top = 0
		self._top += top
		self._left += left
		self._dirty = True
		self.win.movewin(top, left)
		if refresh:
			self.doc.win.refresh()
		return self
	
	def top(self, top = None, refresh = True):
		if top == None:
			return self._top
		self._top = top
		self._dirty = True
		return self._move_to(self._top, self._left, refresh)
	
	def left(self, left = None, refresh = True):
		if left == None:
			return self._left
		self._left = left;
		self._dirt = True
		return self.move_to(self._top, self._left, refresh)
	
	def focus(self, name = None):
		focused = False
		# by default just look for a child to focus
		if name == None:
			# TODO: check tab/focus order for the first box?
			for name in self.children:
				box = self.children[name]
				if box.focus():
					focused = True
					break
		else:
			if not name in self.children:
				raise Exception("Box '%s' not found." % name)
			focused = self.children[name].focus()
		return focused
	
	def width(self):
		return self._width
	
	def height(self):
		return self._height
	
	def refresh(self, force = False, recurse = True):
		refreshed = False
		if not self._dirty or not force:
			return refreshed
		self.win.erase()
		if self._visible:
			self.move_to(self._top, self._left)
			self.bg(*self.bg())
		refreshed = True
		self._dirty = False
		if recurse:
			for name in self.children:
				box = self.children[name]
				refreshed = box.refresh(force, recurse) or refreshed
		return refreshed
	
	def bg(self, char = None, attr = curses.A_NORMAL, refresh = True):
		if char == None:
			return (self._bg_char, self._bg_attr)
		self._bg_char = char
		self._bg_attr = attr
		self._dirty = True
		self.win.bkgd(char, attr)
		if refresh:
			self.doc.win.refresh()
		return self
	
	def box(self, top, left, height, width, char, attr):
		str = ((char * width) + '\n') * height
		self.win.addstr(
			top,
			left,
			str[0:len(str) - 1], # ignore the extra \n
			attr
		)
		return self

class Box:
	parent = None
	children = {}
	_args = {}
	_dirty = False
	_name = None
	# style goodies
	_padding = [0, 0, 0, 0] # top, right, bottom, left
	_margin = [0, 0, 0, 0] # top, right, bottom, left
	_border = [0, 0, 0, 0] # top, right, bottom, left
	_border_attr = curses.A_NORMAL
	_border_chars = ['', '', '', '', '', '', '', ''] # left, right, top, bottom, lr, lr, bl, br
	_text_align = 'left' # | center | right
	_text_wrap = False
	_text_indent = 0
	_text_attr = curses.A_NORMAL
	_visible = True
	_bg_char = None
	_bg_attr = curses.A_NORMAL
	_position = 'relative' # | fixed
	_left = 0 # our position
	_top = 0
	_flow_top = 0 # our internal flow position for our children
	_flow_left = 0
	_height = None # our current height
	_max_height = True # whether or not our height will maximize to fill parent
	_min_height = False # whether or not our height will minimize to fit our children
	_virt_height = 0 # how tall our content would force us to be
	_width = None # our current width
	_max_width = True # whether or not our width will maximize to fill parent
	_min_width = False # whether or not our width will minimize to fit our children
	_virt_height = 0 # how wide our content would force us to be
	_overflow = 'visible' # | clip

	def __init__(self, parent, name = None, **args):
		# set the default top/left values based on parent type
		max_width = parent._width
		max_height = parent._height
		if isinstance(parent, Box):
			self.doc = parent.doc
			self._left = parent._left
			self._top = parent._top
			# shrink our size to account for our parent's padding
			max_width -= parent._padding[3] + parent._padding[1]
			max_height -= parent._padding[0] + parent._padding[2]
		elif isinstance(parent, Doc):
			self.doc = parent
			# default to 0, 0 when we're the child of a document
			if not 'left' in args:
				self._left = 0
			if not 'top' in args:
				self._top = 0
		else:
			raise Exception("Invalid parent object type of '%s'." % parent)
		self.parent = parent
		if name == None:
			name = self._make_name()
		if name in parent.children:
			raise Exception("A box by the name '%s' already exists within children of '%s' parent." \
				% (name, parent.name()))
		# subtract out border/margin space for our max size
		if 'border_style' in args:
			# TODO: figure out dynamically based on the style picked
			args['border'] = [1, 1, 1, 1]
		if 'border' in args:
			border = args['border']
		else:
			border = self._border
		if 'margin' in args:
			margin = args['margin']
		else:
			margin = self._margin
		max_width -= margin[3] + margin[1] + border[3] + border[1]
		max_height -= margin[0] + margin[2] + border[0] + border[2]
		my_args = {
			'padding': self._padding,
			'margin': self._margin,
			'border_style': None,
			'border': self._border,
			'border_attr': self._border_attr,
			'border_chars': self._border_chars,
			'text_align': getattr(parent, '_text_align', self._text_align),
			'text_wrap': getattr(parent, '_text_wrap', self._text_wrap),
			'text_indent': getattr(parent, '_text_indent', self._text_indent),
			'text_attr': getattr(parent, '_text_attr', self._text_attr),
			'visible': getattr(parent, '_visible', self._visible),
			'bg_char': getattr(parent, '_bg_char', self._bg_char),
			'bg_attr': getattr(parent, '_bg_attr', self._bg_attr),
			'left': self._left,
			'top': self._top,
			'height': max_height,
			'width': max_width,
			'overflow': getattr(parent, '_overflow', self._overflow),
			'refresh': False
		}
		my_args = get_args(my_args, args)
		self._name = name
		self._width = my_args['width']
		self._height = my_args['height']
		self._top = my_args['top']
		self._left = my_args['left']
		self._padding = my_args['padding']
		self._margin = my_args['margin']
		if my_args['border_style']:
			self.border(style = my_args['border_style'])
		else:
			self.border(
				border = my_args['border'],
				border_chars = my_args['border_chars'],
				border_attr = my_args['border_attr']
			)
		self._text_align = my_args['text_align']
		self._text_wrap = my_args['text_wrap']
		self._text_indent = my_args['text_indent']
		self._text_attr = my_args['text_attr']
		self._visible = my_args['visible']
		self._overflow = my_args['overflow']
		self.parent.children[self._name] = self
		self.refresh()
	
	def _make_name(self):
		base_name = 'box'
		max_tries = 5000
		for i in range(0, max_tries):
			name = '_'.join([base_name, str(i)])
			if not name in self.parent.children:
				return name
		raise Exception("Failed to find a free box name after %i iterations." \
			% max_tries)
	
	def name(self, name = None):
		if name == None:
			return self._name
		elif name in parent.children:
			raise Exception("A box by the name '%s' already exists within parent's children." % name)
		del parent.children[self._name]
		self._name = name
		parent.children[self._name] = self
	
	def flow_left(self, left = None):
		if left == None:	
			return self._flow_left
		self._flow_left = left
		return self
	
	def flow_top(self, top = None):
		if top == None:
			return self._flow_top
		self._flow_top = top
		return self

	def max_height(self, max = None, refresh = True):
		if max == None:
			return self._max_height
		elif max:
			self._max_height = True
			# check to see if we need to change our height to match our parent
			p_mets = self.parent.get_metrics()
			if self._height != p_mets['inner_height']:
				# account for our margins and resize
				max_height = p_mets['inner_height'] - self._margin[0] - self._margin[2];
				self.height(max_height, refresh)
				self._min_height = False # can't be min and max at the same time
				self._dirty = True
		else:
			self._max_height = False
			# no need to change from our current height in this case
		if refresh:
			self.refresh()
		return self
	
	def max_width(self, max = None, refresh = True):
		if max == None:
			return self._max_width
		elif max:
			self._max_width = True
			# check to see if we need to change our width to match our parent
			p_mets = self.parent.get_metrics()
			if self._width != p_mets['inner_width']:
				# account for our margins and resize
				max_width = p_mets['inner_width'] - self._margin[3] - self._margin[1];
				self.width(max_width, refresh)
				self._min_width = False # can't be min and max at the same time
				self._dirty = True
		else:
			self._max_width = False
			# no need to change from our current width in this case
		if refresh:
			self.refresh()
		return self
	
	def min_height(self, min = None, refresh = True):
		if min == None:
			return self._min_height
		if min:
			self._min_height = True
			self._max_height = False # can't be min and max at the same time
		else:
			self._min_height = False
		self._dirty = True
		if refresh:
			self.refresh()
		return self
	
	def min_width(self, min = None, refresh = True):
		if min == None:
			return self._min_width
		if min:
			self._min_width = True
			self._max_width = False # can't be min and max at the same time
		else:
			self._min_width = False
		self._dirty = True
		if refresh:
			self.refresh()
		return self
	
	def focus(self, name = None):
		focused = False
		# by default just look for a child to focus
		if name == None:
			# TODO: check tab/focus order for the first box?
			for name in self.children:
				child = self.children[name]
				if child.focus():
					focused = True
					break
		else:
			if not name in self.children:
				raise Exception("Box '%s' not found." % name)
			focused = self.children[name].focus()
		return focused
	
	def remove(self):
		# remove all the children boxes first
		for name in self.children:
			box = self.children[name]
			box.remove()
		# remove ourself from our parent
		del self.parent.children[self._name]

	def position(self, positioning = None, refresh = False):
		if positioning == None:
			return self._position
		if positioning not in ('fixed', 'relative'):
			raise Exception("Invalid box positioning of '%s' for box '%s'." % (positioning, self._name));
		self._position = positioning
		self._dirty = True
		if refresh:
			self.refresh(full = True)
			
	def refresh(self, force = False, recurse = True, full = False):
		refreshed = False
		if full:
			return self.doc.refresh(force = True, recurse = True)
		if not self._dirty and not force:
			return refreshed
		if self._visible:
			self.position(self.position(), refresh = False)
			self.left(self.left(), refresh = False)
			self.top(self.top(), refresh = False)
			self.margin(*self.margin(), refresh = False)
			self.padding(*self.padding(), refresh = False)
			self.width(self.width(), refresh = False)
			self.max_width(self.max_width(), refresh = False)
			self.min_width(self.min_width(), refresh = False)
			self.height(self.height(), refresh = False)
			self.max_height(self.max_height(), refresh = False)
			self.min_height(self.min_height(), refresh = False)
			self.bg(*self.bg(), refresh = False)
			border_args = self.border()
			border_args['refresh'] = False
			self.border(**border_args)
		self.doc.win.refresh()
		refreshed = True
		self._dirty = False
		if recurse:
			for name in self.children:
				box = self.children[name]
				refreshed = box.refresh(force, recurse) or refreshed
		return refreshed

	def apply(self, list):
		for item in list:
			method = getattr(self, item)
			if item.startswith('_') or item == 'apply':
				raise Exception("Invalid item of '%s'" % item)
			elif not hasattr(self, item):
				raise Exception("Unrecognized item of '%s'" % item)
			elif not type(method) == types.MethodType:
				raise Exception("Invalid item of '%s'" % item)
			args = list[item]
			# and call our internal method depending on how we were fed params
			if type(args) == types.DictType:
				method(**args)
			elif type(args) == types.ListType or type(args) == types.TupleType:
				method(*args)
			else:
				method(args)
		return self
	
	def bg(self, char = None, attr = None, refresh = True):
		if char == None:
			return (self._bg_char, self._bg_attr)
		self._bg_char = char
		if attr != None:
			self._bg_attr = attr
		# because they might be 'None' by default
		args = [
			self._top,
			self._left,
			self._height,
			self._width,
			self._bg_char
		]
		if self._bg_attr != None:
			args.append(self._bg_attr)
		if self._bg_char != None:
			self.doc.box(*args);
			self._dirty = True
		if refresh:
			self.doc.win.refresh()
		return self

	def hide(self):
		self.visible(False)
		return self

	def show(self):
		self.visible(True)
		return self
	
	def width(self, width = None, refresh = True):
		if width == None:
			return self._width
		self._width = self._width
		self._dirty = True
		if refresh:
			self.refresh()
		return self
	
	def height(self, height = None, refresh = True):
		if height == None:
			return self._height
		self._height = self._height
		self._dirty = True
		if refresh:
			self.refresh()
		return self

	def visible(self, visibility = None, refresh = True):
		if visibility == None:
			return self._visible
		else:
			self._visible = visibility
		self._dirty = True
		if refresh:
			self.refresh()
		return self
	
	def move_to(self, left = None, top = None, refresh = True):
		if left == None and top == None:
			return self
		if left != None:
			self._left = left
		if top != None:
			self._top = top
		self._dirty = True
		if refresh:
			self.refresh()
		return self
	
	def move_by(self, left = None, top = None, refresh = True):
		if left == None and top == None:
			return self
		if left != None:
			self._left += left
		if top != None:
			self._top += top
		self._dirty = True
		if refresh:
			self.refresh()
		return self

	def top(self, top = None, refresh = True):
		if top == None:
			return self._top
		else:
			self._top = top
		self._dirty = True
		if refresh:
			self.refresh()
		return self
	
	def left(self, left = None, refresh = True):
		if left == None:
			return self._left
		else:
			self._left = left
		self._dirty = True
		if refresh:
			self.refresh()
		return self
	
	def text_align(self, align = None):
		if align == None:
			return self._text_align
		self._text_align = align
		return self

	def text_attr(self, attr = None):
		if attr == None:
			return self._text_attr
		self._text_attr = attr
		return self
	
	def text_wrap(self, wrap = None):
		if wrap == None:
			return self._text_wrap
		self._text_wrap = wrap
		return self

	def text_indent(self, indent = None):
		if indent == None:
			return self._text_indent
		self._text_indent = indent
		return self

	def overflow(self, overflow = None):
		if overflow == None:
			return self._overflow
		if overflow in ('visible', 'clip'):
			self._overflow = overflow
		else:
			raise Exception("Invalid overflow value of '%s'." % overflow)
		return self

	def padding(self, top = None, right = None, bottom = None, left = None, refresh = True):
		if top == None and right == None and bottom == None and left == None:
			return self._padding
		if not top == None:
			self._padding[0] = top
		if not right == None:
			self._padding[1] = right
		if not bottom == None:
			self._padding[2] = bottom
		if not left == None:
			self._padding[3] = left
		self._dirty = True
		if refresh:
			self.refresh()
		return self

	def margin(self, top = None, right = None, bottom = None, left = None, refresh = True):
		if top == None and right == None and bottom == None and left == None:
			return self._margin
		if not top == None:
			self._margin[0] = top
		if not right == None:
			self._margin[1] = right
		if not bottom == None:
			self._margin[2] = bottom
		if not left == None:
			self._margin[3] = left
		self._dirty = True
		if refresh:
			self.refresh()
		return self
	
	def border(self, **args):
		my_args = {
			'style': None,
			'border': None,
			'border_chars': self._border_chars,
			'border_attr': self._border_attr,
			'refresh': True
		}
		my_args = get_args(my_args, args)
		# return our style info by default
		if my_args['style'] == None and my_args['border'] == None:
			return {
				'border': self._border,
				'border_chars': self._border_chars,
				'border_attr': self._border_attr
			}
		elif my_args['style'] in BORDER_STYLES:
			my_args['border'] = [1, 1, 1, 1];
			my_args['border_chars'] = BORDER_STYLES[my_args['style']][0:8]
			my_args['border_attr'] = BORDER_STYLES[my_args['style']][8]
		elif not (len(my_args['border_chars']) == 8 and len(my_args['border']) == 4):
			raise Exception("Invalid border sizes (%s), chars (%s), or style (%s)."
				% (str(my_args['border']), str(my_args['border_chars']), str(my_args['style']))
			)
		# set our border info
		self._border = my_args['border']
		self._border_chars = my_args['border_chars']
		self._border_attr = my_args['border_attr']
		# ['|', '|', '-', '-', '.', '.', "'", "'"]
		#  left rght top  btm  tl   tr   bl   br
		#  0    1    2    3    4    5    6    7
		top = self._top + self._margin[0] + my_args['border'][0]
		bottom = top + self._height + 1 - my_args['border'][2]
		metrics = self.get_metrics()
		for y in range(top, bottom):
			# left edge
			for i in range(0, my_args['border'][3]):
				self.doc.win.addch(
					y,
					self._left + self._margin[3] + i,
					ord(my_args['border_chars'][0]),
					my_args['border_attr']
				)
			# right edge
			for i in range(0, my_args['border'][3]):
				self.doc.win.addch(
					y,
					self._left + self._width + 1 + self._margin[3] + i,
					ord(my_args['border_chars'][1]),
					my_args['border_attr']
				)
		# top border
		for i in range(0, my_args['border'][0]):
			self.doc.win.addstr(
				self._top + self._margin[0] + i,
				self._left + self._margin[3] + my_args['border'][3],
				my_args['border_chars'][2] * (self._width + 1 - my_args['border'][1]),
				my_args['border_attr']
			)
		# bottom border
		for i in range(0, my_args['border'][2]):
			self.doc.win.addstr(
				bottom + i,
				self._left + self._margin[3] + my_args['border'][3],
				my_args['border_chars'][3] * (self._width + 1 - my_args['border'][1]),
				my_args['border_attr']
			)
		# top left and top right corners
		for i in range(0, my_args['border'][0]):
			# top left
			self.doc.win.addstr(
				self._top + self._margin[0] + i,
				self._left + self._margin[3],
				my_args['border_chars'][4] * my_args['border'][3],
				my_args['border_attr']
			)
			# top right
			self.doc.win.addstr(
				self._top + self._margin[0] + i,
				self._left + self._margin[3] + self._width + 1,
				my_args['border_chars'][5] * my_args['border'][1],
				my_args['border_attr']
			)
		# bottom left and bottom right corners
		for i in range(0, my_args['border'][2]):
			# bottom left
			self.doc.win.addstr(
				bottom + i,
				self._left + self._margin[3],
				my_args['border_chars'][6] * my_args['border'][3],
				my_args['border_attr']
			)
			# bottom right
			self.doc.win.addstr(
				bottom + i,
				self._left + self._margin[3] + self._width,
				my_args['border_chars'][7] * my_args['border'][1],
				my_args['border_attr']
			)
		self._dirty = True
		# and refresh if needed
		if my_args['refresh']:
			self.doc.win.refresh()
		return self

	def get_metrics(self, from_screen = False):
		metrics = {}
		metrics['inner_top'] = self._top + self._border[0] + self._padding[0]
		metrics['outer_top'] = self._top - self._margin[0]
		metrics['inner_left'] = self._left + self._border[3] + self._padding[3]
		metrics['outer_left'] = self._left - self._margin[3]
		metrics['inner_bottom'] = metrics['inner_top'] + self._height - 1
		metrics['outer_bottom'] = metrics['inner_top'] + self._height - 1 \
			+ self._border[2] + self._margin[2]
		metrics['inner_right'] = metrics['inner_left'] + self._width \
			- self._padding[1]
		metrics['outer_right'] = metrics['inner_left'] + self._width \
			+ self._border[1] + self._margin[1] - 1
		metrics['inner_height'] = self._height \
			- (self._padding[0] + self._padding[2])
		metrics['outer_height'] = self._height \
			+ (self._margin[0] + self._margin[2])
		metrics['inner_width'] = self._width \
			- (self._padding[3] + self._padding[1])
		metrics['outer_width'] = self._width \
			+ self._margin[3] + self._margin[1]
		if from_screen:	
			# add in extra spacing for the window's position
			for item in metrics:
				if item.endswith('_left') or item.endswith('_right'):
					metrics[item] += self.doc._left
				if item.endswith('_top') or item.endswith('_bottom'):
					metrics[item] += self.doc._top
		return metrics

	def write(self, text, **args):
		'''Prints formatted text to the box interior, returning the formatted
		text.'''
		my_args = {
			'text_align': self._text_align,
			'text_indent': self._text_indent,
			'text_attr': self._text_attr,
			'text_wrap': self._text_wrap,
			'left': 0,
			'top': 0,
			'refresh': True
		}
		my_args = get_args(my_args, args)
		center = self.get_center()
		# TODO: word-wrapping/overflow break our text up into multiple lines
		f_text = text
		# figure out how to format the text
		metrics = self.get_metrics()
		top = metrics['inner_top'] + my_args['top']
		left = metrics['inner_left'] + my_args['left']
		if my_args['text_align'] == 'left':
			if self._text_indent != 0:
				left += self._text_indent
		elif my_args['text_align'] == 'center':
			left = int(center['left'] - (len(text) / 2))
			if self._text_indent != 0:
				left += self._text_indent
		elif my_args['text_align'] == 'right':
			left = (metrics['inner_right'] - my_args['left']) - len(text)
			if self._text_indent != 0:
				left -= self._text_indent
		else:
			raise Exception("Invalid text alignment of '%s'." \
				% my_args['text_align'])
		self.doc.win.addstr(top, left, text, my_args['text_attr'])
		if my_args['refresh']:
			self.doc.win.refresh()
		return self
	
	def get_center(self):
		metrics = self.get_metrics()
		return {
			'left': int(metrics['inner_left'] + (metrics['inner_width'] / 2)),
			'top': int(metrics['inner_top'] + (metrics['inner_height'] / 2))
		}


class Text(Box):
	_text = None
	_lines = []

	def __init__(self, parent, **args):
		my_args = {
			'text': ''
		}
		my_args = _get_args(my_args, args)
		Box.__init__(self, parent, **args)
		self._text = my_args['text']
	
	def text(self, val = None, refresh = True):
		'''Sets/gets the text as a string.'''
		if val == None:
			return self._text
		self._text = val
		self._lines = val.split('\n');
		self.write(self._text, refresh = refresh)
		self._virt_height = len(self._lines)
		# longest line sets our width
		self._virt_width = max([len(line) for line in lines])
		# TODO: adjust how we do height to allow % like CSS
		#if self._min_height:
			#if self._height
		#if self._min_width:
			#text_width = 
		return self
	
	def lines(self, lines = None, refresh = True):
		'''Sets/gets the lines of text as a list.'''
		if val == None:
			return self._lines
		return self.text(lines.join('\n'), refresh)
	
	def refresh(self, force = False, recurse = True, full = False):
		refreshed = Box.refresh(self, force, recurse, full)
		if not full:
			self.text(self.text())
			self.dirty = False
			refreshed = True
		return refreshed
		

class Form(Box):
	_fields = {}

	def __init__(self, parent, fields = {}, **args):
		Box.__init__(self, parent, **args)
		self.fields(fields)
	
	def get_input(self):
		return self.doc.win.getch()

	def reset_fields(self):
		for name in self._fields:
			field = self_fields[name]
			field.val(field._default_val, False)
		self.doc.win.refresh()
	
	def remove_fields(self, refresh = True):
		for name in self._fields:
			self.remove_field(name, refresh = True)
		if refresh:
			self.refresh()

	def add_field(self, name, **args):
		my_args = {
			'refresh': True,
			'type': None,
			'caption': '',
			'args': {}
		}
		my_args = get_args(my_args, args)
		if name in self._fields:
			raise Exception("Form %s already contains a field by the name %s." % (self._name, name))
		if my_args['type'] == None:
			raise Exception("Unable to add a field without specifying the class type.");
		my_args = get_args(my_args, args)
		metrics = self.get_metrics()
		top = self._inner_top = len(self._fields)
		field = my_args['type'](self, name = name, top = top, **my_args['args'])
		self._fields[name] = field
		# determine the type and instan
	
	def remove_field(self, name, refresh = True):
		if not name in self._fields:
			raise Exception("Form %s does not contain a field by the name %s." % (self._name, name))
		self._fields[name].remove()
		del self._fields[name]
		self.dirty = True
		if refresh:
			self.refresh()
	
	def fields(self, fields = None, refresh = True):
		if fields == None:
			return self._fields
		self.remove_fields();
		for name in fields:
			self.add_field(name, **fields[name])
		if refresh:
			self.refresh()


class Field(Box):
	STYLES = ('simple')
	_style = 'simple'
	_caption = None
	_caption_attr = None
	_default_val = None
	_val = None
	_edit_top = 0
	_edit_left = 0
	_edit_width = 1
	_edit_height = 1

	def __init__(self, parent, **args):
		my_args = {
			'caption': self._caption,
			'caption_attr': self._caption_attr,
			'default_val': self._default_val,
			'style': 'simple'
		}
		if not isinstance(parent, Form):
			raise Exception("Fields may only be added to forms.")
		my_args = get_args(my_args, args)
		Box.__init__(self, parent, **args)
		self._caption = my_args['caption']
		self._caption_attr = my_args['caption_attr']
		self._default_val = my_args['default_val']
		self._val = my_args['default_val']
		if not my_args['style'] in self.STYLES:
			raise Exception("Unrecognized style %s for field %s." % (my_args['style'], self._name))
		self._style = my_args['style']
	
	def focus(self):
		curses.setsyx(self._edit_top, self._edit_left)

	def val(self, value = None, refresh = True):
		raise Exception("Unable to get or set value of abstract field object %s." % self._name)
	
	def edit(self):
		raise Exception("Unable to edit abstract field object %s." % self._name)
	
	def caption(self):
		raise Exception("Unable to get or set caption of abstract field object %s." % self._name)
	
	def refresh(self, force = False, recurse = True, full = False):
		refreshed = Box.refresh(self, force, recurse, full)
		if not full:
			self.caption(self.caption())
			self.val(self.val())
			self.dirty = False
			refreshed = True
		return refreshed


class TextBox(Field):
	STYLES = ('simple')
	_bg_char = '_'

	def __init__(self, parent, **args):
		args['height'] = 1
		Field.__init__(self, parent, **args)
		if self._style == 'simple':
			pass
		else:
			raise Exception("Unrecognized style %s for textbox %s." % (self._style, self._name))
	
	def caption(self, caption = None, attr = None, refresh = True):
		if caption == None:
			return self._caption
		self._caption = caption
		self.dirty = True
		metrics = self.get_metrics()
		if self._style == 'simple':
			caption = self._caption + ' ['
			self._edit_left = len(caption)
			# -1 below for ending ']' to come after
			self._edit_width = metrics['inner_width'] - len(caption) - 1
			self.write(text = caption, refresh = False)
			self.write(text = ']', text_align = 'right', refresh = False)
		else:
			raise Exception("Unrecognized style %s for textbox %s." % (self._style, self._name))
		if refresh:
			self.doc.win.refresh()

	def val(self, value = None, refresh = True):
		if value == None:
			return self._val
		self._val = value
		self.dirty = True
		if self._style == 'simple':
			val = self._val + self._bg_char * (self._edit_width - len(self._val))
			self.write(left = self._edit_left, text = val)
		else:
			raise Exception("Unrecognized style %s for textbox %s." % (self._style, self._name))
		if refresh:
			self.doc.win.refresh()

	def focus(self):
		# move the cursor to our location
		Field.focus(self)
		# TODO show something indicating ourselves as being focused (e.g. bold text)
		return True
	
	def edit(self):
		self.focus()
		# TODO: make the edit routine work
		while True:
			key = self.doc.win.getch()
			return key


class Message(Box):
	_title = None
	_title_attr = curses.A_NORMAL
	_title_align = 'center'
	_msg = None
	_msg_attr = curses.A_NORMAL
	
	def __init__(self, parent, **args):
		my_args = {
			'title': self._title,
			'title_attr': self._title_attr,
			'title_align': self._title_align,
			'msg': self._msg,
			'msg_attr': curses.color_pair(0)
		}
		my_args = get_args(my_args, args)
		self._title = my_args['title']
		self._title_attr = my_args['title_attr']
		self._title_align = my_args['title_align']
		self._msg = my_args['msg']
		self._msg_attr = my_args['msg_attr']
		Box.__init__(self, parent, **args)
	
	def title(self, title = None, attr = None, align = None, refresh = True):
		if title == None:
			return (self._title, self._title_attr, self._title_align)
		if attr != None:
			self._title_attr = attr
		if align != None:
			self._title_align = align
		self._title = title
		self._dirty = True
		self.write(
			text = self._title,
			text_attr = self._title_attr,
			text_align = self._title_align,
			top = 0,
			left = 0,
			refresh = refresh
		)
		return self
	
	def msg(self, msg = None, attr = None, refresh = True):
		if msg == None:
			return (self._msg, self._msg_attr)
		self._msg = msg
		self._dirty = True
		self.write(
			text = self._msg,
			text_attr = self._msg_attr,
			text_align = 'left',
			top = 2,
			left = 0,
			refresh = refresh
		)
		return self
	
	def refresh(self, force = False, recurse = True, full = False):
		refreshed = Box.refresh(self, force, recurse, full)
		if not full:
			self.title(*self.title(), refresh = False)
			self.msg(*self.msg(), refresh = False)
			self.dirty = False
			self.doc.win.refresh()
			refreshed = True
		return refreshed


class Collect(Message):
	_form = None

	def __init__(self, parent, **args):
		my_args = {
			'fields': {}
		}
		my_args = get_args(my_args, args)
		Message.__init__(self, parent, **args)
		self._form = Form(self, my_args['fields']);

	def get_input(self):
		return self._form.get_input()


if __name__ == '__main__':
	import dbg
	import sys
	sys.stdout.write('Box\n')
	dbg.pretty_print(Box, 1);
	sys.stdout.write('Collect\n')
	dbg.pretty_print(Collect, 1);
