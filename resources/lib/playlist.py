# -*- coding: utf8 -*-
import os
import re
import sys
import json
import urllib
import cPickle
import requests
from stream import *
from utils import *

reload(sys)  
sys.setdefaultencoding('utf8')

class Playlist:
  streams = []
  channels = {}
  disabled_groups = []
  disabled_qualities = []
  size = 0
  cache_file = ".cache"
  streams_file = ".streams"
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
      self.temp_folder = kwargs.get('temp_folder')
      if self.temp_folder:
        self.cache_file = os.path.join(self.temp_folder, self.cache_file)
        self.streams_file = os.path.join(self.temp_folder, self.streams_file)
      
      self.mapping_file = kwargs.get('mapping_file')
      #Download mapping file
      self.__load_map()
      
      if self.location:
        self.__load()

      self.__serialize()
      
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
        
        if not line.startswith(START_MARKER):
          line = line.rstrip()
          if line and line.startswith(INFO_MARKER):
            stream = Stream(line, self.streams_map)
          else:
            if not stream:
              continue
            stream.url = line
            self.streams.append(stream)
            
            stream = None #reset

    log("parse() ended")

    
  def __serialize(self):
    '''
    Serializes streams dict into a file so it can be used later
    '''
    log("__serialize() started")
    _streams = {}
    for stream in self.streams:
      _streams[stream.name.decode("utf-8")] = stream.url
    log("serializing %s streams in %s" % (len(_streams), self.streams_file))
    cPickle.dump(_streams, open(self.streams_file, "wb"))
    log("__serialize() ended")

  
  def disable_groups(self, disabled_group_names):
    '''
    Remove all channels from disabled groups
    '''
    log("Disbling streams from groups: %s" % ", ".join(disabled_group_names))
    i = 0
    for stream in self.streams:
      if stream.group in disabled_group_names:
        stream.disabled = True
        i += 1
      else:
        stream.disabled = False
    
    log("%s streams disabled" % i)

    
  def reorder(self, **kwargs):
    ''' 
      Reorders channels in the playlist
      Keyword Args:
        template_file: a template txt file with channel names. Single name on each a row
    '''
    log("reorder() started")
    self.template_file = kwargs.get('template_file', self.template_file)
    template_order = self.__load_order_template()
    
    for stream in self.streams:
      try:
        stream.order = template_order[stream.name]
        log ("Found order for '%s'=%s" % (stream.name, stream.order))
        # Streams in template should not be disabled
        # So enable stream in case it was disabled
        stream.disabled = False 
      except: 
        log ("Order for '%s'=%s" % (stream.name, stream.order))
        pass
    
    self.streams = sorted(self.streams, key=lambda stream: stream.order)
    log("reorder() ended")

  def __load_order_template(self):
    template_order = {}
    try:
      with open(self.template_file) as file_content:
        log("Reading template file %s " % self.template_file)
        for i, line in enumerate(file_content):
          template_order[line.rstrip()] = i
          log("%s=%s" % (line.rstrip(), i))
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

  def __to_string(self, type):
    ''' 
      Outputs the current streams into different formats
    '''
    ordered   = ''
    unordered = ''
    if not type:
      type = self.type
    
    n = len(self.streams)
    for i in range(0, n):
      if not self.streams[i].disabled or type == PlaylistType.NAMES or type == PlaylistType.JSON:
        stream_string = self.streams[i].to_string(type)
        if type == PlaylistType.JSON: #append comma
          if i < (n-1): stream_string += ","

        if self.streams[i].order < 9999:
          ordered += stream_string
        else:
          unordered += stream_string
    
    buffer = ordered + unordered
    
    if type == PlaylistType.KODIPVR or type == PlaylistType.PLAIN:
      buffer = "%s\n%s" % (START_MARKER, buffer)
      
    if type == PlaylistType.JSON:
      buffer = "map=[%s]" % buffer

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
    
    # If no path is provided overwite current file
    file_path = kwargs.get('path', self.cache_file)
    type = kwargs.get('type', self.type)
      
    try:
      with open(file_path, 'w') as file:
        log("Saving playlist type %s in %s " % (str(type), file_path))
        file.write(self.__to_string(type))
      return True
    
    except Exception, er:
      log(er, 4)
      return False

  def set_static_stream_urls(self, url, port):
    '''
    Replaces all stream urls with static ones
    That point to our proxy server
    '''
    for stream in self.streams:
      name = urllib.quote(stream.name)
      stream.url = url % (port, name)
  

  def disable_streams(self, preferred_quality, forced_disable=False):
    '''
    Disables streams that are not of preferred quality
    Args:
      preferred_quality: The preffered quality of the channel - UHD, HD, SD or LQ
      forced_disable: Should a channel be disabled if it has no alternative qualities. Defaults to False
        Example:
        If a channel has only one stream and forced_disable is False, the stream will be enabled 
        regardless of its quality. If a channel has more than one streams but none of them matches 
        the preferred_quality, the logic will select the highest available quality.
    '''
    _streams = []
    try:
      log("set_preferred_quality() started")
      log("Selecting channels with preferred quality '%s'" % preferred_quality)
      # group streams by channel
      if len(self.channels) == 0:
        self.channels = self.get_channels()
      
      for channel_name, channel in self.channels.iteritems():
        q = preferred_quality
        log("Searching for '%s' stream from channel '%s'" % (q, channel_name))
        ### change quality if there is no stream with the preferred_quality
        if not channel.has_quality(q):
          q = HD if q == SD else SD
          log("%s stream not found for channel '%s' changing quality to %s" % (preferred_quality, channel_name, q))
        # disable channels with unpreferred quality
        for stream in channel.streams:
          if stream.quality == q:
            stream.disabled = False
            log("Preferred %s stream found. Adding '%s'" % (stream.quality, stream.name))
            #log(stream.to_json())
          else:
            if len(channel.streams) == 1 and not forced_disable:
              stream.disabled = False
              log("Adding '%s' stream '%s' (single stream, quality setting is ignored)" % (stream.quality, stream.name))
            else:
              log("Disabling unpreferred '%s' stream %s" % (stream.quality, stream.name))
              stream.disabled = True
          _streams.append(stream)
      
      self.streams = _streams
    except Exception as er:
      log(er)
    
    log("Filtered %s channels with preferred quality"% len(self.streams) )
    log("set_preferred_quality() ended!")

  def get_channels(self):
    '''
    Group all streams by stream id
    Returns:
      A dict of channels, each of them holding a list of streams
    '''
    log("get_channels() started!")
    for stream in self.streams:
      if stream.id not in self.channels.iterkeys():
        log("Creating channel '%s', adding %s stream '%s'" % (stream.id, stream.quality, stream.name))
        channel = Channel()
        channel.name = stream.id.decode("utf-8")
        channel.streams.append(stream)
        self.channels[channel.name.decode("utf-8")] = channel
      else:
        log("Appending stream '%s' to channel '%s'" % (stream.name, stream.id))
        channel = self.channels[stream.id.decode("utf-8")]
        channel.streams.append(stream)
        log("Channel '%s' has %s streams" % (stream.id, len(self.channels[stream.id.decode("utf-8")].streams)))
    log("Streams grouped by id. Results in %s channels" % len(self.channels))
    log("get_channels() ended!")
   
    return self.channels