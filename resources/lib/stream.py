# -*- coding: utf8 -*-
import re
import sys
import string
from utils import *

reload(sys)  
sys.setdefaultencoding('utf8')

class Stream:
  '''
    Class definition for m3u stream entries
  '''
  name      = None
  base_name = None # Name without Quality attribute
  id        = None
  url       = None
  logo      = None
  group     = None
  shift     = None
  is_radio  = False
  disabled  = False
  order     = 9999
  quality   = Quality.SD
  __props   = {}
  
  def __init__(self, line, streams_map):
    
    self.line = line
    self.name = re.compile(',(?:\d+\.)*\s*(.*)').findall(self.line)[0]
    self.streams_map = streams_map
    self.base_name = self.name
    
    if Quality.HD in self.name:
      self.quality = Quality.HD
      self.base_name = self.base_name.replace(" " + Quality.HD, "").replace(Quality.HD, "").rstrip()
    if Quality.LQ in self.name:
      self.quality = Quality.LQ
      self.base_name = self.base_name.replace(Quality.LQ, "").rstrip()

    # Get stream properties from the map of streams
    self.__get_stream_properties()
    
    # Overwrite stream name in case we have a new name.
    self.name = self.__props.get("n", self.name)
    # If no overwrite name is found remove any commas
    self.name = self.name.replace(",","")
    
    # Set ID
    try: self.id = self.__props["id"]
    except: self.id = self.base_name
    log("Stream ID for channel '%s' set to '%s'" % (self.name, self.id))  
    
    self.group = self.__get_group()
    self.logo = self.__get_logo()
    
    try: self.shift = re.compile('shift[=\"\']+(.*?)["\'\s]+').findall(self.line)[0]
    except: pass

  
  def __get_stream_properties(self):
    try: 
      self.__props = self.streams_map[self.name.decode("utf-8")]
      log("Found map entry for channel %s" % self.name)
    except:
      if self.quality != Quality.SD:
        log("Map entry for channel '%s' not found. Searching for '%s'" % (self.name, self.base_name))
        self.__props = self.streams_map.get(self.base_name.decode("utf-8"), {})
        log("Found map entry for channel %s" % self.base_name)
  
  
  def __get_group(self):
    group = None
    try: 
      if settings.groups_from_progider:
        group = re.compile('group-title[="\']+(.*?)["\'\s]+').findall(self.line)[0]
      else:
        group_id = self.__props["g"]
        group = self.groups_map[group_id]
    except:
      ## Try go guess channel group from channel name
      lname = self.base_name.lower()
      if "spor" in lname:
        group = self.groups_map["st"]
      elif "movie" in lname or "film" in lname or "cinema" in lname:
        group = self.groups_map["mv"]
      elif "music" in lname:
        group = self.groups_map["mu"]
      elif "XX" in self.base_name:
        group = self.groups_map["xx"]
      elif "укр" in lname:
        group = self.groups_map["sr"]
      elif "pink" in lname:
        group = self.groups_map["sr"]
      elif "nl" in lname:
        group = self.groups_map["nl"]
      elif "RAI" in self.base_name:
        group = self.groups_map["it"]      
      elif "TVR" in self.base_name or "RO" in self.base_name:
        group = self.groups_map["ro"]
      else:
        group = self.groups_map["ot"]

    log("Stream group set to '%s'" % group)
    return group

    
  def __get_logo(self):
    '''
    If no logo is in map, logo name is equal to the lowercase channel name removing any special chars
    and translating cyrilic to latin letters
    If logo is in map but without HTTP prefix, then that's the image name
    '''
    url = "https://raw.githubusercontent.com/harrygg/EPG/master/logos/%s.png"
    logo = None
    
    try: 
      logo = self.__props["l"]
    except:
      name = re.sub(r'[\(\)&%/\!\:\.\s\'\*\,]*', '', self.name.decode("utf-8"))
      # replace delayed channel identificators i.e. +1 or +12
      name = re.sub(r'\+\d+', '', name)
      logo = name.replace(Quality.LQ,"").replace("+", "plus").replace("-", "minus").lower()
      try:
        # translate cyrilic chars to latin
        symbols = (u"абвгдеёжзийклмнопрстуфхцчшщъыьэюяАБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ", 
                 u"abvgdeejziiklmnoprstufhzcssiyyeuaABVGDEEJZIIKLMNOPRSTUFHZCSS_Y_EUA")
        tr = dict( [ (ord(a), ord(b)) for (a, b) in zip(*symbols) ] )
        logo = logo.translate(tr)     
      except:
        log("Translation of logo %s failed" % logo)
        
    if not logo.startswith("http"):
      logo = url % logo.lower()
    log("Logo for channel '%s' set to '%s'" % (self.name, logo))
    
    return logo  
    
    
  def to_string(self, type):
  
    if type is PlaylistType.NAMES:
      return '%s\n' % self.name
    
    if type is PlaylistType.JSON:
      return '%s' % self.to_json()
      
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
  
  
  def to_json():
    '''
    '''
    return '{"name":"%s", "id":"%", "url": "%s", "logo":"%s", "group": "%s", "shift": "%s", "is_radio": %s, "disabled": %s, "order": %s, "quality": "%s"}' % (name, id, url, logo, group, shift, is_radio, disabled, order, quality)

    
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
    "ru": "Руски",
    "fr": "Френски",
    "nl": "Холандски",
    "xx": "Възрастни",
    "gr": "Гръцки",
    "ot": "Други",
    "sr": "Сръбски",
    "ro": "Румънски"
  }
