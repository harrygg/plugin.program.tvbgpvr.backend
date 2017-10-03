# -*- coding: utf8 -*-
import os
import re
import sys
import json
import requests
import cPickle
from stream import *
from utils import *

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
      self.location = kwargs.get('location')
      self.progress_callback = kwargs.get('progress')
      self.name = kwargs.get('name', 'playlist.m3u')
      self.include_radios = kwargs.get('include_radios', False)
      self.template_file = kwargs.get('template_file', 'order.txt')
      self.user_agent = kwargs.get('user_agent')
      self.groups_from_progider = kwargs.get('groups_from_progider', False)
      self.type = kwargs.get('type', PlaylistType.KODIPVR)
      #self.preffered_quality = kwargs.get('preffered_quality', None)
      self.temp_folder = kwargs.get('temp_folder')
      if self.temp_folder:
        self.cache_file = os.path.join(self.temp_folder, self.cache_file)
      
      self.mapping_file = kwargs.get('mapping_file')
      #Download mapping file
      self.__load_map()
      
      if self.location:
        self.__load()

      log("Playlist initialized with %s channels" % self.count())
    except Exception as e:
      log("__init__() " + str(e), 4)
      raise

  def __progress(self, percent, msg):
    if self.progress_callback:
      self.progress_callback.update(percent, str(msg))
    
  def __load(self):
    ''' 
    Loads m3u from given location - local storage or online resource
    '''
    ret = True
    log("__load() started")
    self.__progress(10, "Loading playlist from: %s" % self.location)
    if self.location.startswith("http") or self.location.startswith("ftp"):
      ret = self.__download()
    
    if ret:
      self.__parse()
      
    log("__load() ended")

  def __download(self):
    try:
      headers = {}
      if self.user_agent:
        headers = {"User-agent": self.user_agent}
      log("Downloading resource from: %s " % self.location)
      response = requests.get(self.location, headers=headers)
      log("Server status_code: %s " % response.status_code)
      if response.status_code >= 200 and response.status_code < 400:
        chunk_size = self.__get_chunk_size__(response)
        self.__cache(self.__iter_lines__(response, chunk_size)) #using response.text.splitlines() is way too slow on singleboard devices!!!
      else:
        log("Unsupported status code received from server: %s" % response.status_code)
        return False
      return True
    except Exception, er:
      log(er, 4)
      return False
    
  def __get_chunk_size__(self, response):
    try:
      size = int(response.headers['Content-length'])
      if size > 0: return size/100
    except: pass
    return 2048
  
  def __iter_lines__(self, response, chunk_size, delimiter=None):
    '''
      Implementation of iter_lines to include progress bar
    '''
    pending = None
    i = 0
    percent = 0
    for chunk in response.iter_content(chunk_size=chunk_size, decode_unicode=True):
      if i >= chunk_size:
        percent += 1 
        self.__progress(percent, 'Parsing server response')
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

  def __cache(self, file_content):
    '''
    Saves the m3u locally and counts the lines 
    Needed for the progress bar
    '''
    log("cache() started")
    self.location = self.cache_file
    with open(self.location, "w") as file:
      for line in file_content:
        self.size += 1
        file.write("%s\n" % line.rstrip().encode("utf-8"))
    log("cache() ended")
 
  def __parse(self):
    '''
      Parse any given m3u file line by line
    '''
    log("parse() started")
    percent = 0  
    stream = None
    self.__progress(0, "Parsing playlist")
    with open(self.location, "r") as file_content:
      for i, line in enumerate(file_content):
        if self.size > 0: # if true, we have counted the lines
          percent = int(round(i + 1 / float(self.size) * 100))
          self.__progress(percent, "Parsing playlist")
        
        if not line.startswith(M3U_START_MARKER):
          line = line.rstrip()
          if line and line.startswith(M3U_INFO_MARKER):
            stream = Stream(line, self.streams_map)
          else:
            if not stream:
              continue
            stream.url = line
            self.streams.append(stream)
            
            stream = None #reset
    # serialize streams
    cPickle.dump(self.streams, open(self.cache_file + "_streams", "wb"))
    log("Playlist streams successfully serialized!")
    #cPickle.dump(self, open(self.cache_file + "_playlist", "wb"))
    
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
    log("reorder() started")
    self.template_file = kwargs.get('template_file', self.template_file)
    template_order = self.__load_order_template()
    
    for stream in self.streams:
      try: stream.order = template_order[stream.name]
      except: pass
    
    self.streams = sorted(self.streams, key=lambda stream: stream.order)
    log("reorder() ended")

  def __load_order_template(self):
    template_order = {}
    try:
      with open(self.template_file) as file_content:
        for i, line in enumerate(file_content):
          template_order[line.rstrip()] = i
    except Exception, er:
      log(er, 4)
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

  def to_string(self, type):
    ''' 
      Deserializes the current streams into m3u formatted strings
    '''
    ordered   = ''
    unordered = ''
    if not type:
      type = self.type
    
    for stream in self.streams:
      if stream.order < 9999:
        ordered += stream.to_string(type)
      else:
        if stream.group in self.disabled_groups:
          #log('Excluding stream "%s" due to disabled group %s' % (stream.name, stream.group))
          continue
        if stream.quality in self.disabled_qualities:
          #log('Excluding stream "%s" due to disabled quality' % stream.name)
          continue
        if not self.include_radios and stream.is_radio:
          #log('Excluding stream "%s" due to disabled radios' % stream.name)
          continue
        unordered += stream.to_string(type)
    
    buffer = ordered + unordered
    if type is not PlaylistType.NAMES and type is not PlaylistType.JSON:
      buffer = "%s\n%s" % (M3U_START_MARKER, buffer)

    return buffer.encode("utf-8", "replace")
    
    
  def __load_map(self):
    '''
    Downloads mapping file. If downloads fails loads the local file.
    '''
    self.__progress(2, "Downloading mapping file")
    try:
      if os.environ.get('PVRDEBUG'):
        raise Exception('Debug mode enabled')
      url = "https://raw.githubusercontent.com/harrygg/plugin.program.tvbgpvr.backend/master/resources/mapping.json"
      headers = {"Accept-Encoding": "gzip, deflate"}
      log("Downloading streams map from: %s " % url)
      response = requests.get(url, headers=headers)
      log("Map server status code: %s " % response.status_code)
      log("Map size: %s " % response.headers["Content-Length"])
      if response.status_code < 200 and response.status_code >= 400:
        raise Exception("Unsupported status code!")
      self.streams_map = response.json()["streams"]
    except Exception as ex:
      log("Downloading map failed!")
      log(ex)
      log("Loading local map %s " % self.mapping_file)
      with open(self.mapping_file) as data_file:
        self.streams_map = json.load(data_file)["streams"]
    log("Streams map loaded!")
    
    
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
    
    path = kwargs.get('path')
    type = kwargs.get('type', self.type)
    
    # If no path is provided overwite current file
    file_path = path if path else self.cache_file
      
    try:
      with open(file_path, 'w') as file:
        log("Saving playlist in %s " % (file_path))
        file.write(self.to_string(type))
      return True
    
    except Exception, er:
      log(er, 4)
      return False

      
  #@staticmethod
  # def get_stream_url(name):
    # """
    # Reads stream list from cache and returns url of the selected stream name
    # """
    # try:
      # streams = cPickle.loads(pl_cache + "_streams")
      # log("deserialized %s streams from file " % (len(streams), pl_cache + "_streams"))
      # for stream in streams:
        # if stream.name == name:
          # log("Found url for stream %s" % name)
          # return stream.url
    # except:
      # return None