# -*- coding: utf8 -*-
import os
import re
import sys
import json
import requests
import string
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
  groups_map = {
    "bg": "Български",
    "en": "Английски",
    "mv": "Филми",
    "st": "Спортни",
    "dc": "Документални",
    "th": "Тематични",
    "de": "Немски",
    "as": "Азиатски",
    "nw": "Новини",
    "mu": "Музикални",
    "ki": "Детски",
    "it": "Италиански",
    "tr": "Турски",
    "fr": "Френски",
    "nl": "Холандски",
    "xx": "Възрастни",
    "gr": "Гръцки",
    "ot": "Други",
    "sr": "Сръбски"
  }
  
  def __init__(self, **kwargs):
    try:
      ## keyword arguments
      self.location = kwargs.get('location')
      self.log_callback = kwargs.get('log')
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
      self.__load_map__()
      
      if self.location:
        self.__load__()

      self.log("Playlist initialized with %s channels" % self.count())
    except Exception as e:
      self.log("__init__() " + str(e), 4)
      raise

  def log(self, msg, level=2):
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
    self.log("__load__() started")
    self.progress(10, "Loading playlist from: %s" % self.location)
    if self.location.startswith("http") or self.location.startswith("ftp"):
      ret = self.download()
    
    if ret:
      self.parse()
    self.log("__load__() ended")

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
      if size > 0: return size/100
    except: pass
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
    self.log("parse() started")
    percent = 0  
    stream = None
    self.progress(0, "Parsing playlist")
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
            
            stream = None #reset
  
  
  def parse_line(self, line):
    '''
      Convert text line into a Stream object
    '''
    try:
      name = re.compile(',(?:\d+\.)*\s*(.*)').findall(line)[0].replace(",","") #remove comma from name i.e. Cosmo HD (es,en)
      stream = Stream(name)
      props = self.__get_stream_properties(name)
      stream.id = self.__get_id(props)      
      stream.group = self.__get_group(props, line)
      stream.logo = self.__get_logo(props)
      try: stream.shift = re.compile('shift[=\"\']+(.*?)["\'\s]+').findall(line)[0]
      except: pass
      
      return stream

    except Exception, er:
      self.log(er, 4)
      return False
 
  def __get_stream_properties(self, stream_name):
    name = stream_name
    props = {"name":stream_name}
    _props = self.streams_map.get(stream_name.decode("utf-8"))                  
    #If no stream is found, strip any HD or LQ identifiers and try again
    if _props == None:
      if Quality.HD in name or Quality.LQ in name:
        name = name.replace(Quality.HD, "").replace(Quality.LQ, "").rstrip()
        self.log("Stream name '%s' not found. Searching for '%s'" % (stream_name, name))
        _props = self.streams_map.get(name.decode("utf-8"))
    
    if _props != None:
      props.update(_props)
    
    return props
      
  def __get_id(self, props):
    ### Get stream ID. If it doesn't exist use the stream name.
    id = props.get("id")
    if id == None:
      id = props.get("name").replace(" " + Quality.HD, "").replace(Quality.HD, "").rstrip()
    self.log("Stream ID for channel '%s' set to '%s'" % (props.get("name"), id))  
    return id
  
  def __get_group(self, props, line):
    group = None
    try: 
      if self.groups_from_progider:
        group = re.compile('group-title[="\']+(.*?)"').findall(line)[0]
      else:
        group_id = props["g"]
        group = self.groups_map[group_id]
    except:
      ## Try go guess channel group
      if len(re.compile("spor", re.IGNORECASE).findall(props["name"])) > 0:
        group = self.groups_map["st"]
      elif len(re.compile("(movie)|(film)", re.IGNORECASE).findall(props["name"])) > 0:
        group = self.groups_map["mv"]
      elif len(re.compile("music", re.IGNORECASE).findall(props["name"])) > 0:
        group = self.groups_map["mu"]
      elif len(re.compile("xx", re.IGNORECASE).findall(props["name"])) > 0:
        group = self.groups_map["xx"]
      elif len(re.compile("pink", re.IGNORECASE).findall(props["name"])) > 0:
        group = self.groups_map["sr"]
      elif len(re.compile("NL").findall(props["name"])) > 0:
        group = self.groups_map["nl"]
      else:
        group = self.groups_map["ot"]
    
    self.log("Stream group set to '%s'" % group)
    return group

  def __get_logo(self, props):
    '''
    If no logo is in map, logo name is equal to lowercase channel name removing some special chars
    and translating cyrilic to latin
    If logo is in map but without HTTP prefix, then that's the logo name
    '''
    url = "https://raw.githubusercontent.com/harrygg/EPG/master/logos/%s.png"
    logo = None
    try: 
      logo = props["l"]
    except:
      name = re.sub(r'[\(\)&%/\!\:\.\s\'\*]*', '', props["name"].decode("utf-8"))
      # replace delayed channel identificators i.e. +1 or +12
      name = re.sub(r'\+\d+', '', name)
      logo = name.replace("LQ","").replace("+", "plus").replace("-", "minus").lower()
      try:
        # translate cyrilic chars to latin
        symbols = (u"абвгдеёжзийклмнопрстуфхцчшщъыьэюяАБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ", 
                 u"abvgdeejziiklmnoprstufhzcssiyyeuaABVGDEEJZIIKLMNOPRSTUFHZCSS_Y_EUA")
        tr = dict( [ (ord(a), ord(b)) for (a, b) in zip(*symbols) ] )
        logo = logo.translate(tr)     
      except:
        self.log("Translation of logo %s failed" % logo)
    if not logo.startswith("http"):
      logo = url % logo
    self.log("Logo for channel '%s' set to '%s'" % (props["name"], logo))
    return logo
    
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
      try: stream.order = template_order[stream.name]
      except: pass
    
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

  def __load_map__(self):
    '''
    Downloads mapping file. If downloads fails loads the local file.
    '''
    self.progress(2, "Downloading mapping file")
    try:
      if os.environ.get('PVRDEBUG'):
        raise Exception('Debug mode enabled. Load local map')
      url = "https://raw.githubusercontent.com/harrygg/plugin.program.tvbgpvr.backend/master/resources/mapping.json"
      headers = {"Accept-Encoding": "gzip, deflate"}
      self.log("Downloading streams map from: %s " % url)
      response = requests.get(url, headers=headers)
      self.log("Map server status code: %s " % response.status_code)
      self.log("Map size: %s " % response.headers["Content-Length"])
      if response.status_code < 200 and response.status_code >= 400:
        raise Exception("Unsupported status code!")
      self.streams_map = response.json()["streams"]
    except Exception as ex:
      self.log("Downloading map failed!")
      self.log(ex)
      self.log("Loading local map %s " % self.mapping_file)
      with open(self.mapping_file) as data_file:
        self.streams_map = json.load(data_file)["streams"]
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
  UN = "UNKNOWN"

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

  
  def __init__(self, name):
  
    self.name = name
    if Quality.HD in name:
      self.quality = Quality.HD
    if Quality.LQ in name:
      self.quality = Quality.LQ


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