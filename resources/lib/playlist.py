# -*- coding: utf8 -*-
import os
import re
import sys
import xbmc
import json
import requests
from mapping import *

reload(sys)  
sys.setdefaultencoding('utf8')

class Playlist:
  streams = []
  disabled_groups = []
  disabled_qualities = []
  size = 0
  cache_file = ".cache"
  streams_map = {}

  def __init__(self, **kwargs):
    try:
      ## keyword arguments
      self.location = kwargs.get('location', None)
      self.log_callback = kwargs.get('log', None)
      self.progress_callback = kwargs.get('progress', None)
      self.name = kwargs.get('name', 'playlist.m3u')
      self.include_radios = kwargs.get('include_radios', True)
      self.template_file = kwargs.get('template_file', 'order.txt')
      self.user_agent = kwargs.get('user_agent', None)
      self.groups_from_progider = kwargs.get('groups_from_progider', False)
      self.type = kwargs.get('type', PlaylistType.KODIPVR)
      #self.preffered_quality = kwargs.get('preffered_quality', None)
      self.temp_folder = kwargs.get('temp_folder', None)
      if self.temp_folder:
        self.cache_file = os.path.join(self.temp_folder, self.cache_file)
      
      self.mapping_file = kwargs.get('mapping_file', None)
      #Download mapping file
      self.__init_streams_map__()
      
      if self.location:
        self.__load__()

      self.log("Playlist initialized with %s channels" % self.count())
    except Exception as e:
      xbmc.log(str(e), 4)
      raise

  def log(self, msg, level = xbmc.LOGNOTICE):
    if self.log_callback:
      self.log_callback(str(msg), level)

  def progress(self, percent, msg):
    if self.progress_callback:
      self.progress_callback.update(percent, str(msg))
    
  def __load__(self):
    ''' 
    Loads m3u from given location - local storage or online resource
    '''
    ret = True
    xbmc.log("__load__() started")
    self.progress(1, "Loading playlist from: %s" % self.location)
    if self.location.startswith("http") or self.location.startswith("ftp"):
      ret = self.download()
    
    if ret:
      self.parse()
    xbmc.log("__load__() ended")

  def download(self):
    try:
      headers = {}
      if self.user_agent:
        headers = {"User-agent": self.user_agent}
      self.log("Downloading resource from: %s " % self.location)
      response = requests.get(self.location, headers=headers)
      self.log("Server status_code: %s " % response.status_code)
      if response.status_code >= 200 and response.status_code < 400:
        chunk_size = self.get_chunk_size(response)
        self.cache(self.iter_lines(response, chunk_size)) #using response.text.splitlines() is way too slow on singleboard devices!!!
      else:
        self.log("Unsupported status code received from server: %s" % response.status_code)
        return False
      return True
    except Exception, er:
      self.log(er, 4)
      return False
    
  def get_chunk_size(self, response):
    try:
      size = int(response.headers['Content-length'])
      if size > 0:
        return size / 100
    except: 
      return 2048
  
  def iter_lines(self, response, chunk_size, delimiter=None):
    '''
      Implementation of iter_lines to include progress bar
    '''
    pending = None
    i = 0
    percent = 0
    for chunk in response.iter_content(chunk_size=chunk_size, decode_unicode=True):
      if i >= chunk_size:
        percent += 1 
        self.progress(percent, 'Parsing server response')
      i += chunk_size 
      if pending is not None:
        chunk = pending + chunk
      if delimiter:
        lines = chunk.split(delimiter)
      else:
        lines = chunk.splitlines()
      if lines and lines[-1] and chunk and lines[-1][-1] == chunk[-1]:
        pending = lines.pop()
      else:
        pending = None
      for line in lines:
        yield line
    if pending is not None:
        yield pending

  def cache(self, file_content):
    '''
    Saves the m3u locally and counts the lines 
    Needed for the progress bar
    '''
    self.log("cache() started")
    self.location = self.cache_file
    with open(self.location, "w") as file:
      for line in file_content:
        self.size += 1
        file.write("%s\n" % line.rstrip().encode("utf-8"))
    self.log("cache() ended")
 
  def parse(self):
    '''
      Parse any given m3u file line by line
    '''
    xbmc.log("parse() started")
    percent = 0  
    stream = None
    self.progress(0, "Parsing playlist")
    #xbmc.sleep(500)
    with open(self.location, "r") as file_content:
      for i, line in enumerate(file_content):
        if self.size > 0: 
          # if self.size is > 0 we have counted the lines
          percent = int(round(i + 1 / float(self.size) * 100))
          self.progress(percent, "Parsing playlist")
        
        if not line.startswith(M3U_START_MARKER):
          if line.rstrip() and line.startswith(M3U_INFO_MARKER):
            stream = self.parse_line(line.rstrip())
          else:
            if not stream:
              continue
            stream.url = line.rstrip()
            self.streams.append(stream)
            
            stream = Stream() #reset
  
  
  def parse_line(self, line):
    '''
      Convert line into a Stream object
    '''
    try:
      stream = Stream()
      stream_name = re.compile(',(?:\d+\.)*\s*(.*)').findall(line)[0]
      stream.name = stream_name
      stream_in_map = self.streams_map.get(stream_name, None)                  
      
      if stream_in_map == None: 
        #If no stream is found, strip any HD or LQ identifiers and try again
        stream_name = stream_name.replace("HD", "").replace("LQ", "")
        self.log("Stripped stream name %s" % stream_name)
        stream_in_map = self.streams_map.get(stream_name, None)   
        
      if stream_in_map != None:
        stream.id = stream_in_map.get("id")
        if self.groups_from_progider:
          try: stream.group = re.compile('group-title[="\']+(.*?)"').findall(line)[0]
          except: stream.group = "Други"
        else:
          stream.group = stream_in_map.get("group", "Други") 
        stream.logo = stream_in_map.get("logo", "")
      else:
        stream.id = stream_name
        if self.groups_from_progider:
          try: stream.group = re.compile('group-title[="\']+(.*?)"').findall(line)[0]
          except: stream.group = "Други"
        else:
          stream.group = "Други"
        try: stream.logo = re.compile('logo[=\"\']+(.*?)["\'\s]+').findall(line)[0]
        except: pass

      try: stream.is_radio = len(re.compile('radio[=\"\']+T|true["\'\s]+').findall(line)) > 0
      except: pass

      try: stream.shift = re.compile('shift[=\"\']+(.*?)["\'\s]+').findall(line)[0]
      except: pass

      if Quality.HD in stream_name:
        stream.quality = Quality.HD
      if Quality.LQ in stream_name:
        stream.quality = Quality.LQ
      
      return stream

    except Exception, er:
      self.log(er, 4)
      return False
  
  def disable_group(self, group_name):
    self.disabled_groups.append(group_name)
  
  def disable_quality(self, quality):
    self.disabled_qualities.append(quality)
    
  def reorder(self, **kwargs):
    ''' 
      Reorders channels in the playlist
      Keyword Args:
        template_file: a template txt file with channel names.  
          Template files contains channel names - single name on each a row
    '''
    
    self.log("reorder() started")
    self.template_file = kwargs.get('template_file', self.template_file)
    template_order = self.load_order_template()
    
    for stream in self.streams:
      try:
        stream.order = template_order[stream.name]
      except:
        pass
    
    self.streams = sorted(self.streams, key=lambda stream: stream.order)
    self.log("reorder() ended")

  def load_order_template(self):
    template_order = {}
    try:
      with open(self.template_file) as file_content:
        for i, line in enumerate(file_content):
          template_order[line.rstrip()] = i
    except Exception, er:
      self.log(er, 4)
    return template_order

  def add(self, new_m3u_location):
    ''' 
    Adds channels from new playlist to current one
    '''
    self.load(new_m3u_location)
  
  def count(self, count_disabled_channels=True):
    if count_disabled_channels:
      return len(self.streams)
    else:
      i = 0
      for stream in self.streams:
        if stream.group not in self.disabled_groups:
          i += 1
      return i

  def to_string(self):
    ''' 
      Deserializes the current streams into m3u formatted strings
    '''
    ordered   = ''
    unordered = ''
    
    for stream in self.streams:
      if stream.order < 9999:
        ordered += stream.to_string(self.type)
      else:
        if stream.group in self.disabled_groups:
          #self.log('Excluding stream "%s" due to disabled group %s' % (stream.name, stream.group))
          continue
        if stream.quality in self.disabled_qualities:
          #self.log('Excluding stream "%s" due to disabled quality' % stream.name)
          continue
        if not self.include_radios and stream.is_radio:
          #self.log('Excluding stream "%s" due to disabled radios' % stream.name)
          continue
        unordered += stream.to_string(self.type)
    
    buffer = ordered + unordered
    if self.type is not PlaylistType.NAMES:
      buffer = "%s\n%s" % (M3U_START_MARKER, buffer)

    return buffer.encode("utf-8", "replace")

  def __init_streams_map__(self):
    try:
      url = "https://raw.githubusercontent.com/harrygg/plugin.program.tvbgpvr.backend/master/resources/lib/mapping.json"
      headers = {"Accept-Encoding": "gzip, deflate"}
      self.log("Downloading streams map from: %s " % url)
      response = requests.get(url, headers=headers)
      self.log("Map server status code: %s " % response.status_code)
      if response.status_code >= 200 and response.status_code < 400:
        #self.log(response.text)
        streams_map = response.json()
        #streams_map = json.loads(response.text)
        #streams_map = response.json()
      else:
        self.log("Unsupported status code received from server when downloading streams map: %s" % response.status_code)
    except Exception as ex:
      self.log("Downloading map failed!")
      self.log(ex)
      self.log("Loading local map %s " % self.mapping_file)
      with open(self.mapping_file) as data_file:    
        streams_map = json.load(data_file)
    self.log("Streams map loaded!")
    
    
  def save(self, **kwargs):
    '''
    Saves current playlist into a file
    Kwargs:
      path - path to the file where the playlist will be saved. 
        If no path is given and the playlist is loaded from file 
        it will be overwritten. If no path is given and the 
        playlist is loaded from url, it will be saved in the current folder 
      type - the type of playlist
    '''
    
    path = kwargs.get('path', None)
    self.type = kwargs.get('type', self.type)
    
    # If no path is provided overwite current file
    file_path = path if path else self.cache_file
      
    try:
      with open(file_path, 'w') as file:
        self.log("Saving channels in %s " % (file_path))
        file.write(self.to_string())
      return True
    
    except Exception, er:
      self.log(er, 4)
      return False
      
  def get_channel_by_name(self, name):
    for channel in self.channels:
      if channel.name == name:
        return channel
    return None
  
  def get_stream_id(self, name):
    for stream in self.streams:
      if stream.name == name:
        return stream.id
    return None
  
class Channel:
  streams = []
  def __init__(self, stream):
    self.name = stream.id
    self.streams.append(stream)

class PlaylistType:
  KODIPVR = 0
  PLAIN = 1
  NAMES = 2
  LOCAL = 3
  
class Quality:
  HD = "HD"
  SD = "SD"
  LQ = "LQ"
  UNKNOWN = "UNKNOWN"

class Stream:
  name = None
  id = None
  url = None
  logo = None
  group = None
  shift = None
  is_radio = False
  disabled = False
  order = 9999
  quality = Quality.SD

  def to_string(self, type):
  
    if type is PlaylistType.NAMES:
      return '%s\n' % self.name
    
    buffer = '%s:-1' % M3U_INFO_MARKER
    
    if type is not PlaylistType.PLAIN:
      if self.is_radio:
        buffer += ' radio="%s"' % self.is_radio
      if self.shift:
        buffer += ' tvg-shift="%s"' % self.shift
      if self.group:
        buffer += ' group-title="%s"' % self.group
      if self.logo:
        buffer += ' tvg-logo="%s"' % self.logo
      if self.id:
        buffer += ' tvg-id="%s"' % self.id
    
    buffer += ',%s\n' % self.name
    buffer += '%s\n' % self.url

    return buffer

M3U_START_MARKER = "#EXTM3U"
M3U_INFO_MARKER = "#EXTINF"